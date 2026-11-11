"""Identical draws for both treatments; goal-only examples train body, not WRITE bias."""
import collections
import hashlib
import json
import random
import torch
import torch.nn.functional as F
from be_common import ROOT,read,rows,body_ids
from ay_course import encoded
from aq_course import pad
from aq_model import action_weight
from bc_pools import lesson_layout

class Course:
    def __init__(self,tokenizer):
        self.tokenizer=tokenizer;self.rows=rows(ROOT/'lessons.jsonl');self.rng=random.Random(read(ROOT/'policy.json')['data_seed'])
        self.pools=collections.defaultdict(list);self.digest='00'*32;self.counts=collections.Counter()
        for i in read(ROOT/'valid-ids.json'):self.pools[self.rows[i]['origin']].append(i)
        self.simple=[i for i in self.pools['goal']if self.rows[i]['simple']]
    def draw(self,ids,mode,step,slot):
        for attempt in range(40):
            i=self.rng.choice(ids);salt=f'{step}:{slot}:{attempt}:{self.rng.randrange(2**63)}'
            r=lesson_layout(self.rows[i],mode,salt);value=encoded(self.tokenizer,r,'spec')
            if len(value[0])>1000:continue
            self.counts[r['origin']]+=1;self.counts['layout_'+mode]+=1
            self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([i,mode,salt],separators=(',',':')).encode()).hexdigest()
            return value
        raise RuntimeError('No bounded clean sample')
    def batch(self,step,device):
        result=[];flags=[];pool=self.simple if step<=400 else self.pools['goal']
        for _ in range(14):
            i=self.rng.choice(pool)
            for mode in [self.rng.choice(['default','extras']),self.rng.choice(['full','distractors'])]:
                result.append(self.draw([i],mode,step,len(result)));flags.append(False)
        for kind in ['run_'+str(step%2),'done','repair','unsure']:
            result.append(self.draw(self.pools[kind],self.rng.choice(['default','extras','full','distractors']),step,len(result)));flags.append(True)
        order=list(range(32));self.rng.shuffle(order)
        return (*pad([result[i]for i in order],device),torch.tensor([flags[i]for i in order],device=device))

def loss(model,batch,head):
    ids,mask,labels,positions,actions,action_mask=batch
    hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    logits=F.linear(hidden[torch.arange(len(ids),device=ids.device),positions],action_weight(model)).float()
    act=F.cross_entropy(logits[action_mask],actions[action_mask])
    valid=labels[:,1:]!=-100
    mapping=torch.full((len(model.get_input_embeddings().weight),),-100,dtype=torch.long,device=ids.device)
    mapping[head]=torch.arange(len(head),device=ids.device);target=mapping[labels[:,1:][valid]];assert(target>=0).all()
    body_logits=F.linear(hidden[:,:-1][valid],model.get_input_embeddings().weight[head]).float()
    parts=F.cross_entropy(body_logits,target,reduction='none');coords=valid.nonzero()[:,0]
    sums=torch.zeros(len(ids),device=ids.device).scatter_add(0,coords,parts)
    den=torch.zeros_like(sums).scatter_add(0,coords,torch.ones_like(parts));body=(sums[den>0]/den[den>0]).mean()
    return act+2*body,{'action':float(act.detach()),'body':float(body.detach())}
