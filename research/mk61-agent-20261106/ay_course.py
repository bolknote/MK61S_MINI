"""Identical lesson draws and per-example loss; only WRITE targets differ."""
import collections
from functools import lru_cache
import hashlib
import json
import random
import torch
import torch.nn.functional as F
from ay_common import ROOT,ACTIONS,rows,read,END
from ay_runtime import render
from aq_protocol import prompt_ids,header_ids,NO_BODY
from aq_course import pad
from aq_model import action_weight
from ha_protocol import bytes_text


def encoded(tokenizer,row,arm):
    x=prompt_ids(tokenizer,render(row['state'],arm));action=row['action']
    body=row['spec_body']if action=='write'and arm=='spec'else row['reference_body']if action=='write'else row['body']
    header=[]if action in NO_BODY else header_ids(tokenizer,action)
    y=[]if action in NO_BODY else tokenizer.encode(bytes_text(body),add_special_tokens=False)+[END]
    return x+header+y,[-100]*(len(x)+len(header))+y,len(x)-1,ACTIONS.index(action)


class Course:
    def __init__(self,tokenizer,arm):
        self.tokenizer=tokenizer;self.arm=arm;self.rows=rows(ROOT/'lessons.jsonl');self.policy=read(ROOT/'policy.json')
        self.valid=read(ROOT/'common-valid-ids.json');self.rng=random.Random(26110804)
        self.digest='00'*32;self.counts=collections.Counter();self.pools={}
        for stage in ['simple','all']:
            p=collections.defaultdict(list)
            for i in self.valid:
                r=self.rows[i]
                if stage=='simple'and not r['simple']:continue
                p[r['origin']].append(i)
            assert all(p[k]for k in self.policy['batch_sources'])
            self.pools[stage]=p

    @lru_cache(maxsize=40000)
    def encoding(self,index):return encoded(self.tokenizer,self.rows[index],self.arm)

    def batch(self,step,device):
        stage='simple'if step<=self.policy['curriculum_steps']else'all';p=self.pools[stage];ids=[]
        for origin,n in self.policy['batch_sources'].items():ids+=self.rng.choices(p[origin],k=n)
        self.rng.shuffle(ids);self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps(ids,separators=(',',':')).encode()).hexdigest()
        for i in ids:self.counts[self.rows[i]['origin']]+=1
        return pad([self.encoding(i)for i in ids],device)


def loss(model,batch,head):
    ids,mask,labels,positions,actions=batch
    hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    logits=F.linear(hidden[torch.arange(len(ids),device=ids.device),positions],action_weight(model)).float()
    act=F.cross_entropy(logits,actions)
    valid=labels[:,1:]!=-100
    if valid.any():
        mapping=torch.full((len(model.get_input_embeddings().weight),),-100,dtype=torch.long,device=ids.device)
        mapping[head]=torch.arange(len(head),device=ids.device);target=mapping[labels[:,1:][valid]];assert(target>=0).all()
        body_logits=F.linear(hidden[:,:-1][valid],model.get_input_embeddings().weight[head]).float()
        losses=F.cross_entropy(body_logits,target,reduction='none');coords=valid.nonzero()[:,0]
        sums=torch.zeros(len(ids),device=ids.device).scatter_add(0,coords,losses)
        den=torch.zeros_like(sums).scatter_add(0,coords,torch.ones_like(losses))
        body=(sums[den>0]/den[den>0]).mean()
    else:body=act*0
    return act+2*body,{'action':float(act.detach()),'body':float(body.detach())}
