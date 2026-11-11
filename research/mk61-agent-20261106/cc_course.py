"""Balanced four-way decisions, missed-review cases and successful replay."""
import collections
import hashlib
import json
import random
import torch
import torch.nn.functional as F
from safetensors.torch import load_file
from cc_common import ROOT,read,rows,ACTIONS

class Course:
    def __init__(self):
        self.rows=rows(ROOT/'lessons.jsonl');self.quads=read(ROOT/'quadruples.json');self.rng=random.Random(read(ROOT/'policy.json')['data_seed'])
        self.pools=collections.defaultdict(list);self.counts=collections.Counter();self.digest='00'*32
        for i,r in enumerate(self.rows):
            self.pools[r['action']].append(i)
            if r.get('retain'):self.pools['replay'].append(i)
            if r.get('successful_repair_replay'):self.pools['successful_repair'].append(i)
            if r.get('missed_review'):self.pools['missed_review'].append(i)
            if r['code_correct']and r['spec_correct']and r['action']=='done':self.pools['correct_done'].append(i)
        assert all(self.pools[k]for k in ['replay','successful_repair','missed_review','correct_done','run','unsure'])
        self.features=None
    def draw(self,step):
        indexes=[]
        for _ in range(8):indexes.extend(self.rng.choice(self.quads))
        for pool,n in [('missed_review',16),('successful_repair',16),('replay',16),('correct_done',16),('run',8),('unsure',8)]:
            indexes.extend(self.rng.choices(self.pools[pool],k=n));self.counts[pool]+=n
        assert len(indexes)==112
        indexes.extend(self.rng.choices(self.pools['replay'],k=16));self.counts['replay']+=16
        self.rng.shuffle(indexes)
        for i in indexes:self.counts['action_'+self.rows[i]['action']]+=1
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,indexes],separators=(',',':')).encode()).hexdigest()
        return indexes
    def batch(self,step):
        if self.features is None:self.features=load_file(str(ROOT/'features.safetensors'))
        ids=torch.tensor(self.draw(step));return {k:v[ids]for k,v in self.features.items()}

def loss(model,batch,policy):
    logits=F.linear(batch['hidden'],model.action_weight()).float();labels=batch['labels'].long()
    ce=F.cross_entropy(logits,labels);keep=batch['retain'].bool()&(batch['teacher_logits'].argmax(-1)==labels)
    kd=ce*0
    if keep.any():kd=F.kl_div(logits[keep].log_softmax(-1),batch['teacher_logits'][keep].softmax(-1),reduction='batchmean')
    l2=(model.decision_head-model.action_head[__import__('cc_model').ROWS]).square().mean()
    value=ce+policy['KD_weight']*kd+policy['L2_weight']*l2
    return value,{'CE':float(ce.detach()),'verified_action_KD':float(kd.detach()),'L2':float(l2.detach()),'KD_rows':int(keep.sum())}
