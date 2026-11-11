"""Matched code contrasts, paired formats, successful replay and verified-token KD."""
import collections
from functools import lru_cache
import hashlib
import json
import random
import torch
import torch.nn.functional as F
from cb_common import ROOT,read,rows,ACTIONS,END
from cb_runtime import render
from aq_protocol import prompt_ids,header_ids,NO_BODY
from aq_course import pad
from aq_model import action_weight
from ha_protocol import bytes_text


def encoded(tok,row,format):
    x=prompt_ids(tok,render(row['state'],format));action=row['action']
    h=[]if action in NO_BODY else header_ids(tok,action)
    y=[]if action in NO_BODY else tok.encode(bytes_text(row['body']),add_special_tokens=False)+[END]
    assert len(x)+len(h)+len(y)<=1000
    return x+h+y,[-100]*(len(x)+len(h))+y,len(x)-1,ACTIONS.index(action)


class Course:
    def __init__(self,tok):
        self.rows=rows(ROOT/'lessons.jsonl');self.tok=tok;self.rng=random.Random(read(ROOT/'policy.json')['data_seed'])
        self.pools=collections.defaultdict(list);self.counts=collections.Counter();self.digest='00'*32;pairs=collections.defaultdict(dict)
        for i,r in enumerate(self.rows):
            self.pools[r['action']].append(i)
            if r['retain']:self.pools['replay'].append(i)
            if r['origin']=='after_reject'or(r['state'].get('observation')or'').startswith('DONE_REJECTED'):self.pools['rejected'].append(i)
            if r.get('contrast_id')and r['origin']=='clean_initial':pairs[r['contrast_id']][r['contrast_side']]=i
        self.pairs=[v for v in pairs.values()if set(v)=={'good','bad'}]
        assert self.pairs and all(self.pools[p]for p in ['replay','run','diag','unsure','rejected'])
    @lru_cache(maxsize=8000)
    def encoding(self,index,format):return encoded(self.tok,self.rows[index],format)
    def step(self,step,device='cuda:0'):
        indexes=[]
        for _ in range(3):
            pair=self.rng.choice(self.pairs);indexes.extend([pair['good'],pair['bad']])
        for pool,n in [('replay',4),('run',2),('diag',2),('unsure',1),('rejected',1)]:indexes.extend(self.rng.choices(self.pools[pool],k=n))
        assert len(indexes)==16;self.rng.shuffle(indexes);values=[];retain=[];record=[]
        for index in indexes:
            row=self.rows[index];first='full'if row['full_fits']else'notes'
            if row['retain']and row['original_fits']and self.rng.random()<.5:first='original'
            for format in [first,'notes']:
                values.append(self.encoding(index,format));retain.append(row['retain']and format!='notes')
                self.counts['format_'+format]+=1;self.counts['action_'+row['action']]+=1
            self.counts[row['origin']]+=1;record.append([index,first])
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,record],separators=(',',':')).encode()).hexdigest()
        micro=read(ROOT/'policy.json')['microbatch']
        return [(*pad(values[i:i+micro],device),torch.tensor(retain[i:i+micro],device=device))for i in range(0,32,micro)]


def loss(model,teacher,batch,head,js_weight=.05,kd_weight=.2):
    ids,mask,labels,positions,actions,retain=batch
    hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    logits=F.linear(hidden[torch.arange(len(ids),device=ids.device),positions],action_weight(model)).float()
    action=F.cross_entropy(logits,actions);logp=logits.log_softmax(-1);pair=logp.reshape(-1,2,logp.shape[-1])
    mid=torch.logaddexp(pair[:,0],pair[:,1])-0.6931471805599453
    js=.5*((pair[:,0].exp()*(pair[:,0]-mid)).sum(-1)+(pair[:,1].exp()*(pair[:,1]-mid)).sum(-1)).mean()
    valid=labels[:,1:]!=-100;coords=valid.nonzero();mapping=torch.full((len(model.get_input_embeddings().weight),),-100,dtype=torch.long,device=ids.device)
    mapping[head]=torch.arange(len(head),device=ids.device)
    if valid.any():
        target=mapping[labels[:,1:][valid]];assert(target>=0).all()
        body_log=F.linear(hidden[:,:-1][valid],model.get_input_embeddings().weight[head]).float().log_softmax(-1)
        losses=-body_log.gather(1,target[:,None]).flatten();sums=torch.zeros(len(ids),device=ids.device).scatter_add(0,coords[:,0],losses)
        counts=torch.zeros_like(sums).scatter_add(0,coords[:,0],torch.ones_like(losses));body=(sums[counts>0]/counts[counts>0]).mean()
    else:body=action*0;target=None;body_log=None
    kd=action*0;kept_actions=kept_tokens=0
    if retain.any():
        with torch.no_grad():
            th=teacher.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
            ta=F.linear(th[torch.arange(len(ids),device=ids.device),positions],action_weight(teacher)).float()
            keep=retain&(ta.argmax(-1)==actions)
            tb=F.linear(th[:,:-1][valid],teacher.get_input_embeddings().weight[head]).float()if valid.any()else None
        if keep.any():kd+=F.kl_div(logp[keep],ta[keep].softmax(-1),reduction='batchmean');kept_actions=int(keep.sum())
        if tb is not None:
            keep_body=retain[coords[:,0]]&(tb.argmax(-1)==target)
            if keep_body.any():kd+=F.kl_div(body_log[keep_body],tb[keep_body].softmax(-1),reduction='batchmean');kept_tokens=int(keep_body.sum())
    value=action+2*body+js_weight*js+kd_weight*kd
    return value,{'action':float(action.detach()),'body':float(body.detach()),'JS_action':float(js.detach()),'verified_KD':float(kd.detach()),
        'teacher_correct_actions':kept_actions,'teacher_correct_body_tokens':kept_tokens}
