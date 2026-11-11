"""The same lesson draws and verified targets; only prompt length differs."""
import collections
import difflib
from functools import lru_cache
import hashlib
import json
import random
import torch
import torch.nn.functional as F
from aq_common import ROOT, ACTIONS, ACTION_IDS, read
from aq_model import action_weight, correct_weight
from aq_protocol import prompt_ids, header_ids, NO_BODY, END
from aq_runtime import render
from ha_protocol import bytes_text


def encoded(tokenizer, row, arm):
    x=prompt_ids(tokenizer,render(row['state'],arm));action=row['action']
    header=[] if action in NO_BODY else header_ids(tokenizer,action)
    body=[] if action in NO_BODY else tokenizer.encode(bytes_text(row['body']),add_special_tokens=False)+[END]
    return x+header+body,[-100]*(len(x)+len(header))+body,len(x)-1,ACTIONS.index(action)


def pad(rows,device):
    width=max(len(r[0])for r in rows);ids=torch.zeros((len(rows),width),dtype=torch.long)
    mask=torch.zeros_like(ids);labels=torch.full_like(ids,-100)
    for i,(x,y,*_)in enumerate(rows):
        ids[i,:len(x)]=torch.tensor(x);mask[i,:len(x)]=1;labels[i,:len(y)]=torch.tensor(y)
    return tuple(v.to(device)for v in [ids,mask,labels,torch.tensor([r[2]for r in rows]),torch.tensor([r[3]for r in rows])])


class Course:
    def __init__(self,tokenizer,arm):
        self.tokenizer=tokenizer;self.arm=arm;self.rows=read(ROOT/'lessons.jsonl')+read(ROOT/'extra-lessons.jsonl')
        self.policy=json.loads((ROOT/'policy.json').read_text());self.rng=random.Random(171601)
        self.valid=json.loads((ROOT/'common-valid-lesson-ids.json').read_text())
        self.pools={};self.diag_pools={};self.digest='00'*32;self.counts=collections.Counter()
        for stage in [1,2]:
            pools=collections.defaultdict(list)
            for i in self.valid:
                r=self.rows[i]
                if stage==1 and r['family']not in ['binary','memory']:continue
                source=r['origin'] if r['origin']in ['goal_program','localized_diagnosis'] else r['action']
                pools[source].append(i)
            assert all(pools[n]for n in self.policy['stage'+str(stage)])
            self.pools[stage]=pools
            self.diag_pools[stage]={k:[i for i in pools['localized_diagnosis']if self.rows[i]['error_kind']==k]for k in ['correct','operation','argument','order']}
            assert all(self.diag_pools[stage].values())

    @lru_cache(maxsize=40000)
    def encoding(self,index,arm):
        return encoded(self.tokenizer,self.rows[index],arm)

    def batch(self,step,device):
        stage=1 if step<=self.policy['curriculum_steps']else 2;indexes=[]
        for source,n in self.policy['stage'+str(stage)].items():
            if source=='localized_diagnosis':
                assert n==8
                for kind in ['correct','operation','argument','order']:indexes+=self.rng.choices(self.diag_pools[stage][kind],k=2)
            else:indexes+=self.rng.choices(self.pools[stage][source],k=n)
        self.rng.shuffle(indexes)
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps(indexes,separators=(',',':')).encode()).hexdigest()
        rows=[self.rows[i]for i in indexes];enc=[self.encoding(i,self.arm)for i in indexes]
        batch=pad(enc,device);teacher=pad([self.encoding(i,'full')for i in indexes],device)
        weights=torch.ones_like(batch[0],dtype=torch.float32)
        for j,(r,e)in enumerate(zip(rows,enc)):
            self.counts[r['origin']]+=1
            if r.get('before_body')and r['action']=='write':
                old=self.tokenizer.encode(bytes_text(r['before_body']),add_special_tokens=False)
                body=[t for t in e[1]if t!=-100];start=len(e[0])-len(body)
                for tag,_,__,a,b in difflib.SequenceMatcher(a=old,b=body[:-1],autojunk=False).get_opcodes():
                    if tag!='equal':weights[j,start+a:start+max(a+1,b)]=self.policy['changed_token_weight']
        truth=torch.tensor([r['correctness']for r in rows],device=device)
        return batch,teacher,weights,truth


def loss(model,teacher,batch,tbatch,weights,truth,head,policy):
    ids,mask,labels,positions,actions=batch
    h=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    last=h[torch.arange(len(ids),device=ids.device),positions]
    logits=F.linear(last,action_weight(model)).float();semantic=F.linear(last,correct_weight(model)).float()
    action=F.cross_entropy(logits,actions)
    known=truth>=0
    classification=F.cross_entropy(semantic[known],truth[known],weight=torch.tensor([1.5,1.],device=ids.device))
    valid=labels[:,1:]!=-100;coords=valid.nonzero();mapping=torch.full((len(model.get_input_embeddings().weight),),-100,dtype=torch.long,device=ids.device)
    mapping[head]=torch.arange(len(head),device=ids.device);target=mapping[labels[:,1:][valid]];assert(target>=0).all()
    body_logits=F.linear(h[:,:-1][valid],model.get_input_embeddings().weight[head]).float()
    body_log=body_logits.log_softmax(-1);logs=body_log.gather(1,target[:,None]).flatten()
    w=weights[:,1:][valid];sums=torch.zeros(len(ids),device=ids.device).scatter_add(0,coords[:,0],logs*w)
    den=torch.zeros_like(sums).scatter_add(0,coords[:,0],w);has_body=den>0
    body=-(sums[has_body]/den[has_body]).mean()
    bad=truth==0;others=[i for i,a in enumerate(ACTIONS)if a!='done']
    risk=(logits[bad].logsumexp(-1)-logits[bad][:,others].logsumexp(-1)).mean()if bad.any()else logits.sum()*0
    ti,tm,tl,tp,ta=tbatch
    with torch.no_grad():
        th=teacher.model(input_ids=ti,attention_mask=tm,use_cache=False).last_hidden_state
        teacher_actions=F.linear(th[torch.arange(len(ti),device=ti.device),tp],action_weight(teacher)).float()
        tv=tl[:,1:]!=-100;assert torch.equal(tl[:,1:][tv],labels[:,1:][valid])
        teacher_body=F.linear(th[:,:-1][tv],teacher.get_input_embeddings().weight[head]).float()
        # Only copy individual predictions which agree with verified targets.
        keep_actions=(teacher_actions.argmax(-1)==actions)&(actions!=ACTIONS.index('diag'))
        keep_body=(teacher_body.argmax(-1)==target)&(actions[coords[:,0]]!=ACTIONS.index('diag'))
    kd=logits.sum()*0
    if keep_actions.any():kd+=F.kl_div(logits[keep_actions].log_softmax(-1),teacher_actions[keep_actions].softmax(-1),reduction='batchmean')
    if keep_body.any():kd+=F.kl_div(body_log[keep_body],teacher_body[keep_body].softmax(-1),reduction='batchmean')
    value=action+policy['body_weight']*body+policy['semantic_weight']*classification+policy['risk_weight']*risk+policy['distill_weight']*kd
    return value,{'action':float(action.detach()),'body':float(body.detach()),'semantic':float(classification.detach()),
      'wrong_DONE_risk':float(risk.detach()),'context_distillation':float(kd.detach()),
      'teacher_action_matches':int(keep_actions.sum()),'teacher_body_matches':int(keep_body.sum())}
