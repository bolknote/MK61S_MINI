"""Separate action and argument losses, plus action-level DPO preferences."""
import collections
from functools import lru_cache
import hashlib
import json
import random
import numpy as np
import torch
import torch.nn.functional as F
from aa_common import ROOT, ACTION_IDS, ACTION_ID, body_ids, read
from aa_protocol import target_ids
from aa_runtime import initial_prompt
from ha_protocol import constants, encode
from tasks import BUILD


def action_logits(model, ids, mask):
    hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    positions=mask.sum(1)-1
    selected=hidden[torch.arange(len(ids),device=ids.device),positions]
    return F.linear(selected,model.get_input_embeddings().weight[ACTION_IDS]).float()


def separate_loss(model,batch,body_head):
    ids,mask,labels,positions,actions,lm=batch
    hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    weight=model.get_input_embeddings().weight
    supervised=torch.nonzero(~lm).flatten()
    logits=F.linear(hidden[supervised,positions[supervised]],weight[ACTION_IDS]).float()
    action=F.cross_entropy(logits,actions[supervised])
    targets=labels[:,1:];h=hidden[:,:-1]
    valid=(targets!=-100)&(~lm[:,None]);coordinates=valid.nonzero()
    if len(coordinates):
        mapping=torch.full((weight.shape[0],),-100,dtype=torch.long,device=ids.device)
        mapping[body_head]=torch.arange(len(body_head),device=ids.device)
        local=mapping[targets[valid]]
        if (local<0).any():raise ValueError('Body token outside HEX/EOS head')
        ce=F.cross_entropy(F.linear(h[valid],weight[body_head]).float(),local,reduction='none')
        sums=torch.zeros(len(ids),device=ids.device).scatter_add(0,coordinates[:,0],ce)
        body=(sums/valid.sum(1).clamp_min(1)).sum()/len(supervised)
    else:body=action*0
    valid=(targets!=-100)&lm[:,None]
    replay=F.cross_entropy(F.linear(h[valid],weight[:8192]).float(),targets[valid])if valid.any()else action*0
    total=action+.5*body+.03*replay
    return total,{'action':float(action.detach()),'body':float(body.detach()),'language':float(replay.detach())}


def preference_loss(model, reference, ids, mask, chosen, rejected, beta):
    logits=action_logits(model,ids,mask).log_softmax(-1)
    with torch.no_grad():fixed=action_logits(reference,ids,mask).log_softmax(-1)
    index=torch.arange(len(ids),device=ids.device)
    delta=logits[index,chosen]-logits[index,rejected]
    ref=fixed[index,chosen]-fixed[index,rejected]
    return -F.logsigmoid(beta*(delta-ref)).mean()


class Course:
    def __init__(self,tokenizer,stage):
        self.tokenizer=tokenizer;self.rng=random.Random(712411+stage);self.pref_rng=random.Random(912411+stage)
        self.rows=read(ROOT/'replay-light.jsonl');self.training=read(ROOT/'training-tasks.jsonl')
        self.expert=read(ROOT/'expert-lessons.jsonl')
        online=ROOT/f'onpolicy-union-{stage-1}.jsonl'
        self.online=read(online)if online.exists()else self.expert
        self.pools=collections.defaultdict(list);self.lesson_pools={}
        for i,t in enumerate(self.rows):
            category='primitive'if t['kind']=='primitive'else'composition'if t['group']=='composition'else'algorithm'if t['group'].startswith('algorithm_')else'basic'if t['group']in ['literal_copy','literal_function','register_source','stack_source']else'legacy'
            self.pools[category].append(i)
        for name,values in [('expert',self.expert),('online',self.online)]:
            pools=collections.defaultdict(list)
            for i,r in enumerate(values):pools[r['action']].append(i)
            self.lesson_pools[name]=pools
        self.stream=np.memmap(BUILD/'native-mixed-v1/language/train.u16',mode='r',dtype='<u2')
        self.digest='00'*32;self.counts=collections.Counter()

    @lru_cache(maxsize=30000)
    def pair(self,category,index):
        if category in ['expert','online']:
            row=(self.expert if category=='expert'else self.online)[index]
            text=row['prompt'];action=row['action'];body=row['body']
        else:
            row=self.training[index]if category=='compile'else self.rows[index]
            text=initial_prompt(row);action='write';body=encode(row['reference_code'],row.get('constants')or constants(row['task']),'asm')
        x=self.tokenizer.encode(text,add_special_tokens=False);y=target_ids(self.tokenizer,action,body)
        return x+y,[-100]*(len(x)+1)+y[1:],len(x)-1,ACTION_IDS.index(ACTION_ID[action])

    def pick_lesson(self,category,rng):
        pools=self.lesson_pools[category];actions=sorted(pools)
        weights={'done':1.,'run':1.,'diag':1.,'patch':1.5,'trace':.5,'unsure':.3,'write':1.}
        action=rng.choices(actions,weights=[weights[k]for k in actions])[0]
        return rng.choice(pools[action])

    def batch(self,step,device):
        rows=[];draws=[];lm=[]
        quotas=[('legacy',28),('primitive',12),('basic',8),('composition',8),('algorithm',4),
                ('compile',16),('expert',24),('online',24)]
        for category,n in quotas:
            count=0
            while count<n:
                if category in ['expert','online']:index=self.pick_lesson(category,self.rng)
                elif category=='compile':index=self.rng.randrange(len(self.training))
                else:index=self.rng.choice(self.pools[category])
                pair=self.pair(category,index)
                if len(pair[0])>1024:self.counts['overlength_resampled']+=1;continue
                rows.append(pair);draws.append([category,index]);lm.append(False);count+=1
                self.counts[category]+=1;self.counts['action:'+str(pair[3])]+=1
        for _ in range(4):
            start=self.rng.randrange(len(self.stream)-513);values=self.stream[start:start+512].astype('int64').tolist()
            rows.append((values,values,-1,-1));lm.append(True);draws.append(['language',start])
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,draws],separators=(',',':')).encode()).hexdigest()
        length=max(len(r[0])for r in rows);ids=torch.full((len(rows),length),self.tokenizer.pad_token_id or 0,dtype=torch.long)
        labels=torch.full_like(ids,-100);mask=torch.zeros_like(ids)
        for i,(x,y,*_)in enumerate(rows):
            ids[i,:len(x)]=torch.tensor(x);labels[i,:len(y)]=torch.tensor(y);mask[i,:len(x)]=1
        return tuple(x.to(device)for x in [ids,mask,labels,torch.tensor([r[2]for r in rows]),
                                         torch.tensor([r[3]for r in rows]),torch.tensor(lm,dtype=torch.bool)])

    def preferences(self,count,device):
        pairs=[]
        while len(pairs)<count:
            category='online'if self.pref_rng.random()<.6 else'expert'
            values=self.online if category=='online'else self.expert
            row=values[self.pick_lesson(category,self.pref_rng)]
            if row['action']==row['rejected']:continue
            ids=self.tokenizer.encode(row['prompt'],add_special_tokens=False)
            if len(ids)>1024:continue
            pairs.append((ids,ACTION_IDS.index(ACTION_ID[row['action']]),ACTION_IDS.index(ACTION_ID[row['rejected']])))
        length=max(len(x[0])for x in pairs);ids=torch.full((count,length),self.tokenizer.pad_token_id or 0,dtype=torch.long)
        mask=torch.zeros_like(ids)
        for i,(x,*_)in enumerate(pairs):ids[i,:len(x)]=torch.tensor(x);mask[i,:len(x)]=1
        return tuple(x.to(device)for x in [ids,mask,torch.tensor([x[1]for x in pairs]),torch.tensor([x[2]for x in pairs])])
