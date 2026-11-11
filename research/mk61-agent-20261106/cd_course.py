"""Utility gate BCE with verified successful non-review anchors, without DONE penalties."""
import collections
import hashlib
import json
import random
import torch
import torch.nn.functional as F
from safetensors.torch import load_file
from cd_common import ROOT,read,rows
from cd_model import ROWS
from cd_rollout import OTHER

class Course:
    def __init__(self):
        self.rows=rows(ROOT/'lessons.jsonl');self.rng=random.Random(read(ROOT/'policy.json')['data_seed']);self.features=None
        self.pools=collections.defaultdict(list);self.counts=collections.Counter();self.digest='00'*32
        for i,r in enumerate(self.rows):
            if r['origin']=='measured_utility':self.pools['useful_review'if r['review']else'nonreview_utility'].append(i)
            if r['retain']:self.pools['replay'].append(i)
            if r.get('repair_replay'):self.pools['repair'].append(i)
            if r.get('correct_done'):self.pools['correct_done'].append(i)
        assert all(self.pools[k]for k in ['useful_review','nonreview_utility','replay','repair','correct_done'])
    def draw(self,step):
        indexes=[]
        for pool,n in [('useful_review',8),('nonreview_utility',24),('replay',64),('repair',16),('correct_done',16)]:
            indexes.extend(self.rng.choices(self.pools[pool],k=n));self.counts[pool]+=n
        self.rng.shuffle(indexes);assert len(indexes)==128
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,indexes],separators=(',',':')).encode()).hexdigest()
        return indexes
    def batch(self,step):
        if self.features is None:self.features=load_file(str(ROOT/'features.safetensors'))
        ids=torch.tensor(self.draw(step));return{k:v[ids]for k,v in self.features.items()}

def loss(model,batch,policy):
    logits=F.linear(batch['hidden'],model.action_weight()).float();margin=logits[:,ROWS[0]]-logits[:,OTHER].max(-1).values
    bce=F.binary_cross_entropy_with_logits(margin,batch['review']);keep=batch['retain'].bool();kd=bce*0
    if keep.any():kd=F.kl_div(logits[keep].log_softmax(-1),batch['teacher_logits'][keep].softmax(-1),reduction='batchmean')
    l2=(model.decision_head-model.action_head[ROWS]).square().mean();value=bce+policy['KD_weight']*kd+policy['L2_weight']*l2
    return value,{'gate_BCE':float(bce.detach()),'verified_success_KL':float(kd.detach()),'head_L2':float(l2.detach()),'anchor_rows':int(keep.sum())}
