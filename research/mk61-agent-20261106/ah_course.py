"""Balanced SFT and KL retention of verified old actions and full HEX payloads."""
import collections
import hashlib
import json
import random
from functools import lru_cache
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM
from ah_common import ROOT,TEACHER,START_PACKET,ACTIONS,ACTION_IDS,body_ids,read
from ah_model import action_weight,correct_weight
from ac_course import encoded,pad
from lowbit import load


def output_logits(model,batch,head):
    ids,mask,labels,positions,actions=batch[:5]
    h=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    action=F.linear(h[torch.arange(len(ids),device=ids.device),positions],action_weight(model)).float()
    target=labels[:,1:];valid=target!=-100
    body=F.linear(h[:,:-1][valid],model.get_input_embeddings().weight[head]).float()if valid.any()else None
    return h,action,body,valid


def loss(model,batch,head,policy):
    ids,mask,labels,positions,actions,truth=batch
    h,logits,body_logits,valid=output_logits(model,batch,head)
    semantic=F.linear(h[torch.arange(len(ids),device=ids.device),positions],correct_weight(model)).float()
    classification=F.cross_entropy(semantic,truth,weight=torch.tensor([policy['incorrect_class_weight'],1.],device=ids.device))
    action=F.cross_entropy(logits,actions);sums=torch.zeros(len(ids),device=ids.device)
    if body_logits is not None:
        target=labels[:,1:];mapping=torch.full((len(model.get_input_embeddings().weight),),-100,device=ids.device,dtype=torch.long)
        mapping[head]=torch.arange(len(head),device=ids.device);local=mapping[target[valid]];assert(local>=0).all()
        logs=body_logits.log_softmax(-1).gather(1,local[:,None]).flatten();coords=valid.nonzero()
        sums=sums.scatter_add(0,coords[:,0],logs)
    body=-(sums/valid.sum(1).clamp_min(1)).mean();bad=truth==0;other=[i for i,a in enumerate(ACTIONS)if a!='done']
    suppress=(logits[bad].logsumexp(-1)-logits[bad][:,other].logsumexp(-1)).mean()if bad.any()else logits.sum()*0
    total=action+policy['body_weight']*body+policy['semantic_weight']*classification+policy['false_DONE_penalty']*suppress
    return total,{'action':float(action.detach()),'body':float(body.detach()),'semantic':float(classification.detach()),'false_DONE_suppression':float(suppress.detach())}


def frozen_teacher(device='cuda'):
    model=AutoModelForCausalLM.from_pretrained(TEACHER,local_files_only=True);load(model,START_PACKET)
    model.requires_grad_(False);model.to(device).eval();return model


def distillation_loss(model,teacher,batch,head,policy):
    with torch.no_grad():_,old_action,old_body,old_valid=output_logits(teacher,batch,head)
    _,new_action,new_body,new_valid=output_logits(model,batch,head);assert torch.equal(old_valid,new_valid)
    temperature=policy['temperature']
    def kl(new,old):
        a=F.log_softmax(new/temperature,-1);b=F.log_softmax(old/temperature,-1)
        return (b.exp()*(b-a)).sum(-1).mean().clamp_min(0)*temperature**2
    action=kl(new_action,old_action);body=kl(new_body,old_body)if new_body is not None else action*0
    return action+body,{'KL_action':float(action.detach()),'KL_body':float(body.detach())}


class Course:
    def __init__(self,tokenizer,block):
        self.tokenizer=tokenizer;self.rng=random.Random(1113901+block);self.policy=json.loads((ROOT/'policy.json').read_text())
        lessons=read(ROOT/'lessons.jsonl')
        self.rows={'skills':[r for r in lessons if r['origin']=='skill_pair'],
          'composition':[r for r in lessons if r['origin']in ['composition','general_basic']],
          'retention':read(ROOT/'retention.jsonl')+[r for r in lessons if r['action']=='unsure'],
          'completion':read(ROOT/'completion.jsonl'),'anchors':read(ROOT/'anchors.jsonl')}
        p=ROOT/f'onpolicy-union-{block-1}.jsonl'
        self.rows['online']=read(p)if p.exists()else lessons
        self.pools={s:collections.defaultdict(list)for s in self.rows}
        for source,rows in self.rows.items():
            for i,r in enumerate(rows):
                self.pools[source][r['action']].append(i)
                if r['action']=='run':self.pools[source]['run'+str(r['body'][0])].append(i)
                if r.get('group')=='power_pair':self.pools[source]['power_'+r['action']].append(i)
        self.digest='00'*32;self.counts=collections.Counter()

    @lru_cache(maxsize=30000)
    def encoding(self,source,index):return encoded(self.tokenizer,self.rows[source][index])

    def draw(self,source,action):
        for _ in range(200):
            pool=self.pools[source][action]
            if source=='skills'and self.rng.random()<self.policy['power_skill_fraction']and self.pools[source]['power_'+action]:pool=self.pools[source]['power_'+action]
            if action=='run':
                options=[self.pools[source]['run'+str(k)]for k in [1,2,3]if self.pools[source]['run'+str(k)]]
                if options:pool=self.rng.choice(options)
            if not pool:source='retention'if source!='anchors'else'anchors';pool=self.pools[source][action]or self.pools[source]['done'];action=self.rows[source][pool[0]]['action']
            i=self.rng.choice(pool);enc=self.encoding(source,i)
            if len(enc[0])<=1024:return source,i,enc
            self.counts['overlength_resampled']+=1
        raise RuntimeError('No fitting balanced course example')

    def batch(self,step,device):
        rows=[];truth=[];draws=[];anchors=[]
        for source,quotas in self.policy['quotas'].items():
            for action,n in quotas.items():
                for _ in range(n):
                    src,i,enc=self.draw(source,action);r=self.rows[src][i];rows.append(enc);truth.append(r['correctness']);draws.append([src,i]);self.counts[source]+=1;self.counts[action]+=1
        for action,n in self.policy['anchor_quotas'].items():
            for _ in range(n):
                src,i,enc=self.draw('anchors',action);anchors.append(enc);draws.append(['anchor',i]);self.counts['anchor_'+action]+=1
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,draws],separators=(',',':')).encode()).hexdigest()
        return (*pad(self.tokenizer,rows,device),torch.tensor(truth,device=device)),pad(self.tokenizer,anchors,device)
