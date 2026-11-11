"""Target loop exits while preserving complementary verified teacher decisions."""
import collections
import hashlib
import json
import random
from functools import lru_cache
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM
from aj_common import ROOT,TEACHERS,ACTIONS,read
from aj_model import action_weight,correct_weight
from ac_course import encoded,pad
from lowbit import load


def output_logits(model,batch,head):
    ids,mask,labels,positions,actions=batch[:5]
    h=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    action=F.linear(h[torch.arange(len(ids),device=ids.device),positions],action_weight(model)).float()
    valid=labels[:,1:]!=-100
    body=F.linear(h[:,:-1][valid],model.get_input_embeddings().weight[head]).float()if valid.any()else None
    return h,action,body,valid


def loss(model,batch,head,policy):
    ids,mask,labels,positions,actions,truth,exits=batch
    h,logits,body_logits,valid=output_logits(model,batch,head)
    semantic=F.linear(h[torch.arange(len(ids),device=ids.device),positions],correct_weight(model)).float()
    classification=F.cross_entropy(semantic,truth,weight=torch.tensor([policy['incorrect_class_weight'],1.],device=ids.device))
    action=F.cross_entropy(logits,actions);sums=torch.zeros(len(ids),device=ids.device)
    if body_logits is not None:
        target=labels[:,1:];mapping=torch.full((len(model.get_input_embeddings().weight),),-100,device=ids.device,dtype=torch.long)
        mapping[head]=torch.arange(len(head),device=ids.device);local=mapping[target[valid]];assert(local>=0).all()
        logs=body_logits.log_softmax(-1).gather(1,local[:,None]).flatten();coords=valid.nonzero();sums=sums.scatter_add(0,coords[:,0],logs)
    body=-(sums/valid.sum(1).clamp_min(1)).mean();bad=truth==0;other=[i for i,a in enumerate(ACTIONS)if a!='done']
    suppress=(logits[bad].logsumexp(-1)-logits[bad][:,other].logsumexp(-1)).mean()if bad.any()else logits.sum()*0
    # Only ROM-correct states whose valid next action is RUN/DONE receive this
    # term. A wrong program or insufficient checking budget never gets pushed
    # from an honest UNSURE into DONE.
    if exits.any():
        chosen=logits[exits].gather(1,actions[exits,None]).flatten();wrong=logits[exits][:,[ACTIONS.index('write'),ACTIONS.index('unsure')]].max(-1).values
        exit_loss=F.relu(policy['completion_margin']+wrong-chosen).mean()
    else:exit_loss=logits.sum()*0
    value=action+policy['body_weight']*body+policy['semantic_weight']*classification+policy['false_DONE_penalty']*suppress+policy['completion_margin_weight']*exit_loss
    return value,{'action':float(action.detach()),'body':float(body.detach()),'semantic':float(classification.detach()),
      'false_DONE_suppression':float(suppress.detach()),'loop_exit_margin':float(exit_loss.detach()),'loop_exit_rows':int(exits.sum())}


def frozen_teachers(device='cuda'):
    result={}
    for name,(folder,packet)in TEACHERS.items():
        model=AutoModelForCausalLM.from_pretrained(folder,local_files_only=True);load(model,packet)
        model.requires_grad_(False);model.to(device).eval();result[name]=model
    return result


def distillation_loss(model,teachers,batches,head,policy):
    details={};values=[];temperature=policy['temperature']
    def kl(new,old):
        a=F.log_softmax(new/temperature,-1);b=F.log_softmax(old/temperature,-1)
        return(b.exp()*(b-a)).sum(-1).mean().clamp_min(0)*temperature**2
    for name,teacher in teachers.items():
        batch=batches[name]
        with torch.no_grad():_,old_action,old_body,old_valid=output_logits(teacher,batch,head)
        _,new_action,new_body,new_valid=output_logits(model,batch,head);assert torch.equal(old_valid,new_valid)
        action=kl(new_action,old_action);body=kl(new_body,old_body)if new_body is not None else action*0
        values.append(action+body);details[name+'_KL_action']=float(action.detach());details[name+'_KL_body']=float(body.detach())
    return sum(values)/len(values),details


class Course:
    def __init__(self,tokenizer,block):
        self.tokenizer=tokenizer;self.rng=random.Random(1213901+block);self.policy=json.loads((ROOT/'policy.json').read_text())
        lessons=read(ROOT/'lessons.jsonl')
        self.rows={'hard':read(ROOT/'hard-lessons.jsonl'),'completion':read(ROOT/'completion.jsonl'),
          'composition':[r for r in lessons if r['level']>=2],'skills':[r for r in lessons if r['origin']=='skill_pair'],
          'retention':read(ROOT/'retention.jsonl'),**{n:read(ROOT/f'anchors-{n}.jsonl')for n in TEACHERS}}
        p=ROOT/f'onpolicy-union-{block-1}.jsonl';self.rows['online']=read(p)if p.exists()else self.rows['hard']+lessons
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
        requested=source
        for _ in range(300):
            pool=self.pools[source][action]
            if source=='skills'and self.rng.random()<self.policy['power_skill_fraction']and self.pools[source]['power_'+action]:pool=self.pools[source]['power_'+action]
            if action=='run':
                options=[self.pools[source]['run'+str(k)]for k in self.policy['run_sampling_indices']if self.pools[source]['run'+str(k)]]
                if options:pool=self.rng.choice(options)
            if not pool:
                source='retention'if requested not in TEACHERS else requested
                pool=self.pools[source][action]or self.pools[source]['done'];assert pool,(requested,action)
            i=self.rng.choice(pool);enc=self.encoding(source,i)
            if len(enc[0])<=1024:return source,i,enc
            self.counts['overlength_resampled']+=1
        raise RuntimeError(('No fitting course row',requested,action))

    def batch(self,step,device):
        rows=[];truth=[];exits=[];draws=[];anchors={}
        for source,quotas in self.policy['quotas'].items():
            for action,n in quotas.items():
                for _ in range(n):
                    src,i,enc=self.draw(source,action);r=self.rows[src][i];rows.append(enc);truth.append(r['correctness'])
                    exits.append(bool(r.get('loop_exit'))and r['correctness']==1 and r['action']in ['run','done'])
                    draws.append([src,i]);self.counts[source]+=1;self.counts[r['action']]+=1
        for name in TEACHERS:
            values=[]
            for action,n in self.policy['anchor_quotas'].items():
                for _ in range(n):
                    src,i,enc=self.draw(name,action);values.append(enc);draws.append(['KL_'+name,i]);self.counts['KL_'+name+'_'+action]+=1
            anchors[name]=pad(self.tokenizer,values,device)
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,draws],separators=(',',':')).encode()).hexdigest()
        return(*pad(self.tokenizer,rows,device),torch.tensor(truth,device=device),torch.tensor(exits,device=device,dtype=torch.bool)),anchors
