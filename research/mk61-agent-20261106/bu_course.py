"""Only SPEC-token loss; matched order pairs, replay, and code-free review."""
import collections
import hashlib
import json
import random
import torch
import torch.nn.functional as F
from bu_common import ROOT,read,rows,ACTIONS
from ay_runtime import goal_state
from bj_runtime import render
from ay_codec import encode
from aq_protocol import prompt_ids,header_ids,END
from aq_course import pad
from bc_pools import layout
from ha_protocol import bytes_text


def encoded(tokenizer,g,identity,mode='default',review=False,remaining=12):
    state=goal_state(g);state['pool']=layout(state['pool'],identity,mode);state['view']['constants']=list(state['pool'])
    state['remaining']=remaining
    if review:state['replan']=True
    text=render(state,'spec');x=prompt_ids(tokenizer,text);h=header_ids(tokenizer,'write')
    body=tokenizer.encode(bytes_text(encode(g['spec'],state['pool'])),add_special_tokens=False)+[END]
    if len(x)+len(h)+len(body)>1000 or len(body)>160:raise ValueError('Oversized translation lesson')
    return x+h+body,[-100]*(len(x)+len(h))+body,len(x)-1,ACTIONS.index('write')


class Course:
    def __init__(self,tokenizer):
        self.tokenizer=tokenizer;self.rows=rows(ROOT/'train.jsonl');self.replay=rows(ROOT/'replay.jsonl')
        self.rng=random.Random(read(ROOT/'policy.json')['data_seed']);self.digest='00'*32;self.counts=collections.Counter()
        pairs=collections.defaultdict(lambda:collections.defaultdict(list))
        for g in self.rows:
            if 'contrast_id'in g:pairs[g['contrast_id']][g['contrast_side']].append(g)
        self.pairs=[p for p in pairs.values()if 0 in p and 1 in p];assert len(self.pairs)>=96
    def draw(self,g,step,slot,salt=None,mode=None,review=None):
        modes=['default','extras','full','distractors'];review=(step+slot)%4==0 if review is None else review;mode=mode or self.rng.choice(modes)
        for attempt in range(30):
            identity=salt or f'{step}:{slot}:{attempt}:{self.rng.randrange(2**63)}'
            try:v=encoded(self.tokenizer,g,identity,mode,review,self.rng.randrange(3,12)if review else 12)
            except ValueError:mode='default';continue
            self.counts['review'if review else'initial']+=1;self.counts['layout_'+mode]+=1
            self.counts[g.get('curriculum','new')]+=1
            self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([g['id'],g.get('paraphrase'),identity,mode,review]).encode()).hexdigest()
            return v
        raise RuntimeError(('No bounded translation',g['id']))
    def step(self,step,device='cuda'):
        values=[]
        for _ in range(4):
            p=self.rng.choice(self.pairs);salt=f'pair:{step}:{len(values)}:{self.rng.randrange(2**63)}';mode=self.rng.choice(['default','extras','full','distractors'])
            review=(step+len(values)//2)%4==0
            for side in [0,1]:values.append(self.draw(self.rng.choice(p[side]),step,len(values),salt,mode,review))
        for _ in range(8):values.append(self.draw(self.rng.choice(self.rows),step,len(values)))
        for _ in range(16):values.append(self.draw(self.rng.choice(self.replay),step,len(values)))
        self.rng.shuffle(values)
        return [pad(values[i:i+8],device)for i in range(0,32,8)]


def loss(model,batch,head):
    ids,mask,labels,*_=batch;hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    valid=labels[:,1:]!=-100;where=valid.nonzero();mapping=torch.full((len(model.get_input_embeddings().weight),),-100,device=ids.device,dtype=torch.long)
    mapping[head]=torch.arange(len(head),device=ids.device);target=mapping[labels[:,1:][valid]];assert(target>=0).all()
    logits=F.linear(hidden[:,:-1][valid],model.get_input_embeddings().weight[head]).float()
    parts=F.cross_entropy(logits,target,reduction='none');sums=torch.zeros(len(ids),device=ids.device).scatter_add(0,where[:,0],parts)
    den=torch.zeros_like(sums).scatter_add(0,where[:,0],torch.ones_like(parts));return(sums/den).mean()
