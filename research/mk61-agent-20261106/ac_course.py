"""Full-payload supervised loss and full execution-trajectory preferences."""
from functools import lru_cache
import collections
import hashlib
import json
import random
import torch
import torch.nn.functional as F
from ac_common import ROOT,ACTIONS,ACTION_ID,ACTION_IDS,END,read,body_ids
from ac_protocol import prompt_ids,header_ids,NO_BODY
from ac_model import action_weight
from ha_protocol import bytes_text


def encoded(tokenizer,row):
    x=prompt_ids(tokenizer,row['prompt']);action=row['action']
    header=[]if action in NO_BODY else header_ids(tokenizer,action)
    body=[]if action in NO_BODY else tokenizer.encode(bytes_text(row['body']),add_special_tokens=False)+[END]
    return x+header+body,[-100]*(len(x)+len(header))+body,len(x)-1,ACTIONS.index(action)


def pad(tokenizer,rows,device):
    n=max(len(r[0])for r in rows);ids=torch.zeros((len(rows),n),dtype=torch.long);mask=torch.zeros_like(ids);labels=torch.full_like(ids,-100)
    for i,(x,y,*_)in enumerate(rows):
        ids[i,:len(x)]=torch.tensor(x);mask[i,:len(x)]=1;labels[i,:len(y)]=torch.tensor(y)
    return tuple(v.to(device)for v in [ids,mask,labels,torch.tensor([r[2]for r in rows]),torch.tensor([r[3]for r in rows])])


def scores(model,batch,body_head):
    ids,mask,labels,positions,actions=batch
    hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    logits=F.linear(hidden[torch.arange(len(ids),device=ids.device),positions],action_weight(model)).float()
    action_log=logits.log_softmax(-1).gather(1,actions[:,None]).flatten()
    target=labels[:,1:];valid=target!=-100;coordinates=valid.nonzero()
    sums=torch.zeros(len(ids),device=ids.device)
    if len(coordinates):
        weight=model.get_input_embeddings().weight
        mapping=torch.full((len(weight),),-100,dtype=torch.long,device=ids.device)
        mapping[body_head]=torch.arange(len(body_head),device=ids.device)
        local=mapping[target[valid]]
        if(local<0).any():raise ValueError('Argument outside HEX head')
        body_logits=F.linear(hidden[:,:-1][valid],weight[body_head]).float()
        logs=body_logits.log_softmax(-1).gather(1,local[:,None]).flatten()
        sums=sums.scatter_add(0,coordinates[:,0],logs)
    return action_log,sums,valid.sum(1)


def supervised_loss(model,batch,head):
    a,b,n=scores(model,batch,head)
    action=-a.mean();body=-(b/n.clamp_min(1)).mean()
    return action+body,{'action':float(action.detach()),'body':float(body.detach())}


def trajectory_dpo(model,reference,packed,head,beta):
    batch,owners,signs,n=packed
    a,b,_=scores(model,batch,head);decision=a+b
    policy=torch.zeros(n*2,device=a.device).scatter_add(0,owners,decision)
    with torch.no_grad():
        ra,rb,_=scores(reference,batch,head)
        ref=torch.zeros(n*2,device=a.device).scatter_add(0,owners,ra+rb)
    delta=(policy[0::2]-policy[1::2])-(ref[0::2]-ref[1::2])
    return -F.logsigmoid(beta*delta).mean()


class Course:
    def __init__(self,tokenizer,block,level):
        self.tokenizer=tokenizer;self.rng=random.Random(811411+block);self.pref_rng=random.Random(911411+block)
        self.rows=read(ROOT/'lessons.jsonl');self.pairs=read(ROOT/'preferences.jsonl')
        online=ROOT/f'onpolicy-union-{block-1}.jsonl';prefs=ROOT/f'preference-union-{block-1}.jsonl'
        self.online=read(online)if online.exists()else self.rows
        self.online_pairs=read(prefs)if prefs.exists()else self.pairs
        self.level=level;self.pools={}
        for name,values in [('expert',self.rows),('online',self.online)]:
            d=collections.defaultdict(list)
            for i,r in enumerate(values):
                if r.get('level',1)<=level:d[r['action']].append(i)
            self.pools[name]=d
        self.valid_prefs={name:[i for i,r in enumerate(values)if r.get('level',1)<=level]
                          for name,values in [('expert',self.pairs),('online',self.online_pairs)]}
        self.digest='00'*32;self.counts=collections.Counter()

    @lru_cache(maxsize=30000)
    def pair(self,source,index):return encoded(self.tokenizer,(self.rows if source=='expert'else self.online)[index])

    def batch(self,step,device):
        rows=[];draws=[]
        quotas=[('write',30),('done',16),('run',12),('trace',4),('unsure',2)]
        for action,n in quotas:
            count=0
            while count<n:
                source='online'if self.rng.random()<.5 else'expert'
                pool=self.pools[source].get(action)
                if not pool:
                    source='expert';pool=self.pools[source].get(action)
                if not pool:
                    action='write';pool=self.pools[source][action]
                index=self.rng.choice(pool);row=self.pair(source,index)
                if len(row[0])>1024:self.counts['overlength_resampled']+=1;continue
                rows.append(row);draws.append([source,index]);count+=1;self.counts[action]+=1
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,draws],separators=(',',':')).encode()).hexdigest()
        return pad(self.tokenizer,rows,device)

    @lru_cache(maxsize=12000)
    def pref_encoded(self,source,index):
        pair=(self.pairs if source=='expert'else self.online_pairs)[index]
        return [[encoded(self.tokenizer,r)for r in pair[side]]for side in ['chosen','rejected']]

    def preferences(self,n,device):
        rows=[];owners=[];draws=[];count=0
        while count<n:
            source='online'if self.pref_rng.random()<.5 else'expert'
            if not self.valid_prefs[source]:source='expert'
            index=self.pref_rng.choice(self.valid_prefs[source]);pair=self.pref_encoded(source,index)
            if any(len(r[0])>1024 for path in pair for r in path):continue
            for side,path in enumerate(pair):
                rows+=path;owners += [2*count+side]*len(path)
            draws.append([source,index]);count+=1
        self.counts['preference_paths']+=2*n
        return pad(self.tokenizer,rows,device),torch.tensor(owners,device=device),None,n
