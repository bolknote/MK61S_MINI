"""Matched batches, stronger erroneous operand supervision, no extra inference rows."""
import collections
import hashlib
import json
import random
import re
from functools import lru_cache
import torch
import torch.nn.functional as F
from ag_common import ROOT,ACTIONS,END,read
from ag_model import action_weight,correct_weight
from ag_teacher import changed_indexes
from ac_course import encoded,pad
from ha_protocol import bytes_text


def loss(model,batch,head,policy):
    ids,mask,labels,positions,actions,truth,important,hard=batch
    focused=model.training_arm=='focused';row_weight=1+hard*(policy['focused_hard_weight']-1)if focused else torch.ones_like(hard)
    h=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    chosen=h[torch.arange(len(ids),device=ids.device),positions]
    logits=F.linear(chosen,action_weight(model)).float();semantic=F.linear(chosen,correct_weight(model)).float()
    reduce=lambda x:(x*row_weight).sum()/row_weight.sum()
    classification=reduce(F.cross_entropy(semantic,truth,weight=torch.tensor([policy['incorrect_class_weight'],1.],device=ids.device),reduction='none'))
    action=reduce(F.cross_entropy(logits,actions,reduction='none'))
    target=labels[:,1:];valid=target!=-100;coords=valid.nonzero();sums=torch.zeros(len(ids),device=ids.device);denom=torch.zeros_like(sums)
    if len(coords):
        weights=model.get_input_embeddings().weight;mapping=torch.full((len(weights),),-100,device=ids.device,dtype=torch.long)
        mapping[head]=torch.arange(len(head),device=ids.device);local=mapping[target[valid]];assert(local>=0).all()
        logs=F.linear(h[:,:-1][valid],weights[head]).float().log_softmax(-1).gather(1,local[:,None]).flatten()
        token_weight=1+important[:,1:][valid]*(policy['focused_changed_token_weight']-1)if focused else torch.ones_like(logs)
        sums=sums.scatter_add(0,coords[:,0],logs*token_weight);denom=denom.scatter_add(0,coords[:,0],token_weight)
    body=reduce(-sums/denom.clamp_min(1));bad=truth==0;other=[i for i,a in enumerate(ACTIONS)if a!='done']
    suppress=((logits[bad].logsumexp(-1)-logits[bad][:,other].logsumexp(-1))*row_weight[bad]).sum()/row_weight[bad].sum()if bad.any()else logits.sum()*0
    value=action+policy['body_weight']*body+policy['semantic_weight']*classification+policy['false_DONE_penalty']*suppress
    return value,{'action':float(action.detach()),'body':float(body.detach()),'semantic':float(classification.detach()),
      'false_DONE_suppression':float(suppress.detach()),'hard_rows':int(hard.sum()),'critical_body_tokens':int(important.sum())}


class Course:
    def __init__(self,tokenizer,block):
        self.tokenizer=tokenizer;self.rng=random.Random(1013901+block);self.policy=json.loads((ROOT/'policy.json').read_text())
        self.rows={'targeted':read(ROOT/'lessons.jsonl'),'hard':read(ROOT/'hard-lessons.jsonl'),'retention':read(ROOT/'retention.jsonl')}
        p=ROOT/f'onpolicy-union-{block-1}.jsonl'
        if p.exists():self.rows['online']=read(p)
        self.pools={s:collections.defaultdict(list)for s in self.rows}
        for source,rows in self.rows.items():
            for i,r in enumerate(rows):self.pools[source][r['action']].append(i)
        self.digest='00'*32;self.counts=collections.Counter()

    @lru_cache(maxsize=30000)
    def encode_row(self,source,i):
        r=self.rows[source][i];enc=encoded(self.tokenizer,r);marks=[0.]*len(enc[0])
        if r['action']=='write':
            text=bytes_text(r['body']);indexes=r.get('changed_byte_indexes')
            if not indexes:
                old=' '.join(re.findall(r'^[0-9A-F]{4}: ([0-9A-F ]+)$',r['prompt'],re.M)).split()
                indexes=changed_indexes(old,text.split())if old else list(range(len(r['body'])))
            e=self.tokenizer(text,add_special_tokens=False,return_offsets_mapping=True)
            body_tokens=[y for y in enc[1]if y!=-100];assert e['input_ids']+[END]==body_tokens
            begin=len(enc[0])-len(body_tokens)
            for j,(a,b)in enumerate(e['offset_mapping']):
                if any(a<3*k+2 and b>3*k for k in indexes):marks[begin+j]=1.
        return enc,marks

    def batch(self,step,device):
        encodings=[];marks=[];truth=[];hard=[];draws=[]
        for special,quotas in [(True,self.policy['hard_quotas']),(False,self.policy['other_quotas'])]:
            for action,n in quotas.items():
                for _ in range(n):
                    for attempt in range(100):
                        if special:source='hard'
                        else:
                            p=self.rng.random();source='targeted'if p<self.policy['targeted_fraction']else'online'if p<self.policy['targeted_fraction']+self.policy['online_fraction']and'online'in self.rows else'retention'
                        if not self.pools[source][action]:source='retention'
                        i=self.rng.choice(self.pools[source][action]);enc,weight=self.encode_row(source,i)
                        if len(enc[0])<=1024:break
                        self.counts['overlength_resampled']+=1
                    else:raise RuntimeError('No fitting training state')
                    r=self.rows[source][i];encodings.append(enc);marks.append(weight);truth.append(r['correctness']);hard.append(source=='hard'or r.get('hard_case',False));draws.append([source,i])
                    self.counts[source]+=1;self.counts[action]+=1
        batch=pad(self.tokenizer,encodings,device);importance=torch.zeros_like(batch[0],dtype=torch.float)
        for i,m in enumerate(marks):importance[i,:len(m)]=torch.tensor(m,device=device)
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,draws],separators=(',',':')).encode()).hexdigest()
        return (*batch,torch.tensor(truth,device=device),importance,torch.tensor(hard,dtype=torch.float,device=device))
