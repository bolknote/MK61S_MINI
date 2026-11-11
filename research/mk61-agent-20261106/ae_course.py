"""SFT with independent semantic correctness and explicit false-DONE suppression."""
import collections
import hashlib
import json
import random
from functools import lru_cache
import torch
import torch.nn.functional as F
from ae_common import ROOT,ACTIONS,body_ids,read
from ae_model import action_weight,correct_weight
from ac_course import encoded,pad


def batch_pad(tokenizer,rows,device):
    batch=pad(tokenizer,[encoded(tokenizer,r)for r in rows],device)
    return (*batch,torch.tensor([r['correctness']for r in rows],device=device))


def loss(model,batch,head,*,warmup=False):
    ids,mask,labels,positions,actions,truth=batch
    hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    selected=hidden[torch.arange(len(ids),device=ids.device),positions]
    logits=F.linear(selected,action_weight(model)).float()
    semantic=F.linear(selected,correct_weight(model)).float()
    classification=F.cross_entropy(semantic,truth,weight=torch.tensor([4.,1.],device=ids.device))
    if warmup:return classification,{'semantic':float(classification.detach())}
    action=F.cross_entropy(logits,actions);target=labels[:,1:];valid=target!=-100;coords=valid.nonzero();sums=torch.zeros(len(ids),device=ids.device)
    if len(coords):
        weights=model.get_input_embeddings().weight;mapping=torch.full((len(weights),),-100,device=ids.device,dtype=torch.long)
        mapping[head]=torch.arange(len(head),device=ids.device);local=mapping[target[valid]];assert(local>=0).all()
        values=F.linear(hidden[:,:-1][valid],weights[head]).float();logs=values.log_softmax(-1).gather(1,local[:,None]).flatten()
        sums=sums.scatter_add(0,coords[:,0],logs)
    body=-(sums/valid.sum(1).clamp_min(1)).mean()
    bad=truth==0;not_done=[i for i,a in enumerate(ACTIONS)if a!='done']
    suppress=(logits[bad].logsumexp(-1)-logits[bad][:,not_done].logsumexp(-1)).mean()if bad.any()else logits.sum()*0
    total=action+body+classification+suppress
    return total,{'action':float(action.detach()),'body':float(body.detach()),'semantic':float(classification.detach()),
                  'false_DONE_suppression':float(suppress.detach()),'correct_rows':int(truth.sum()),'incorrect_rows':int((truth==0).sum())}


class Course:
    def __init__(self,tokenizer,block):
        self.tokenizer=tokenizer;self.block=block;self.rng=random.Random(712411+block)
        self.rows={'expert':read(ROOT/'lessons.jsonl')};path=ROOT/f'onpolicy-union-{block-1}.jsonl'
        if path.exists():self.rows['online']=read(path)
        self.pools={}
        for source,rows in self.rows.items():
            d=collections.defaultdict(list)
            for i,r in enumerate(rows):d[(r['level'],r['action'])].append(i)
            self.pools[source]=d
        self.mix=json.loads((ROOT/'policy.json').read_text())['stage_level_mix'].get(str(max(1,block)),[.3,.4,.3])
        self.digest='00'*32;self.counts=collections.Counter()

    @lru_cache(maxsize=30000)
    def encode_row(self,source,index):return encoded(self.tokenizer,self.rows[source][index])

    def batch(self,step,device):
        rows=[];draws=[];encodings=[]
        for action,n in [('write',28),('done',16),('run',12),('trace',4),('unsure',4)]:
            got=0
            while got<n:
                source='online'if'online'in self.rows and self.rng.random()<.4 else'expert'
                level=self.rng.choices([1,2,3],self.mix)[0];pool=self.pools[source].get((level,action))
                if not pool:source='expert';pool=self.pools[source].get((level,action))
                if not pool:pool=[i for (l,a),values in self.pools[source].items()if a==action for i in values]
                if not pool:action='write';pool=[i for (l,a),values in self.pools[source].items()if a==action for i in values]
                i=self.rng.choice(pool);row=self.rows[source][i]
                enc=self.encode_row(source,i)
                if len(enc[0])>1024:self.counts['overlength_resampled']+=1;continue
                rows.append(row);encodings.append(enc);draws.append([source,i]);self.counts[action]+=1;self.counts['level'+str(row['level'])]+=1;got+=1
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,draws],separators=(',',':')).encode()).hexdigest()
        return (*pad(self.tokenizer,encodings,device),torch.tensor([r['correctness']for r in rows],device=device))
