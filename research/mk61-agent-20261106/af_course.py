"""Matched targeted replay, with optional semantic and DONE-odds pair ranking."""
import collections
import hashlib
import json
import random
from functools import lru_cache
import torch
import torch.nn.functional as F
from af_common import ROOT,ACTIONS,read
from af_model import action_weight,correct_weight
from ac_course import encoded,pad
from ac_protocol import prompt_ids


def loss(model,batch,head,policy):
    ids,mask,labels,positions,actions,truth=batch
    h=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    chosen=h[torch.arange(len(ids),device=ids.device),positions]
    logits=F.linear(chosen,action_weight(model)).float();semantic=F.linear(chosen,correct_weight(model)).float()
    classification=F.cross_entropy(semantic,truth,weight=torch.tensor([policy['incorrect_class_weight'],1.],device=ids.device))
    action=F.cross_entropy(logits,actions);target=labels[:,1:];valid=target!=-100;coords=valid.nonzero();sums=torch.zeros(len(ids),device=ids.device)
    if len(coords):
        weights=model.get_input_embeddings().weight;mapping=torch.full((len(weights),),-100,device=ids.device,dtype=torch.long)
        mapping[head]=torch.arange(len(head),device=ids.device);local=mapping[target[valid]];assert(local>=0).all()
        logs=F.linear(h[:,:-1][valid],weights[head]).float().log_softmax(-1).gather(1,local[:,None]).flatten()
        sums=sums.scatter_add(0,coords[:,0],logs)
    body=-(sums/valid.sum(1).clamp_min(1)).mean();bad=truth==0;others=[i for i,a in enumerate(ACTIONS)if a!='done']
    suppress=(logits[bad].logsumexp(-1)-logits[bad][:,others].logsumexp(-1)).mean()if bad.any()else logits.sum()*0
    total=action+body+policy['semantic_weight']*classification+policy['false_DONE_penalty']*suppress
    return total,{'action':float(action.detach()),'body':float(body.detach()),'semantic':float(classification.detach()),'false_DONE_suppression':float(suppress.detach())}


def pair_loss(model,batch,policy):
    ids,mask,actions=batch;positions=mask.sum(1)-1
    h=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    chosen=h[torch.arange(len(ids),device=ids.device),positions]
    semantic=F.linear(chosen,correct_weight(model)).float();margin=(semantic[:,1]-semantic[:,0]).reshape(-1,2)
    logits=F.linear(chosen,action_weight(model)).float();done=ACTIONS.index('done');others=[i for i in range(len(ACTIONS))if i!=done]
    odds=(logits[:,done]-logits[:,others].logsumexp(-1)).reshape(-1,2)
    semantic_rank=F.softplus(policy['pair_margin']-(margin[:,1]-margin[:,0])).mean()
    action_rank=F.softplus(policy['pair_margin']-(odds[:,1]-odds[:,0])).mean()
    action=F.cross_entropy(logits,actions)
    value=semantic_rank+.5*action_rank+.25*action
    return value,{'paired_semantic_rank':float(semantic_rank.detach()),'paired_DONE_odds_rank':float(action_rank.detach()),'paired_action':float(action.detach())}


class Course:
    def __init__(self,tokenizer,block):
        self.tokenizer=tokenizer;self.rng=random.Random(913701+block);self.policy=json.loads((ROOT/'policy.json').read_text())
        self.rows={'targeted':read(ROOT/'lessons.jsonl'),'retention':read(ROOT/'retention.jsonl')}
        p=ROOT/f'onpolicy-union-{block-1}.jsonl'
        if p.exists():self.rows['online']=read(p)
        self.pools={s:collections.defaultdict(list)for s in self.rows}
        for source,rows in self.rows.items():
            for i,r in enumerate(rows):self.pools[source][r['action']].append(i)
        self.pairs=read(ROOT/'pairs.jsonl');self.digest='00'*32;self.counts=collections.Counter()

    @lru_cache(maxsize=30000)
    def encode_row(self,source,i):return encoded(self.tokenizer,self.rows[source][i])

    def batch(self,step,device):
        encodings=[];truth=[];draws=[]
        for action,n in self.policy['action_quotas'].items():
            for _ in range(n):
                for attempt in range(100):
                    source='targeted'if self.rng.random()<self.policy['targeted_fraction']else'retention'
                    if source=='targeted'and'online'in self.rows and self.rng.random()<self.policy['online_fraction_within_targeted']:source='online'
                    if not self.pools[source][action]:source='retention'
                    i=self.rng.choice(self.pools[source][action]);enc=self.encode_row(source,i)
                    if len(enc[0])<=1024:break
                    self.counts['overlength_resampled']+=1
                else:raise RuntimeError('No fitting course example')
                row=self.rows[source][i];encodings.append(enc);truth.append(row['correctness']);draws.append([source,i])
                self.counts[action]+=1;self.counts[source]+=1
        pair_rows=[]
        while len(pair_rows)<2*self.policy['pairs_per_step']:
            j=self.rng.randrange(len(self.pairs));p=self.pairs[j]
            e=[prompt_ids(self.tokenizer,p[k]['prompt'])for k in ['bad','good']]
            if max(map(len,e))>1016:continue
            pair_rows.extend((e[x],ACTIONS.index(p[k]['action']))for x,k in enumerate(['bad','good']));draws.append(['pair',j])
        width=max(len(x[0])for x in pair_rows);ids=torch.zeros((len(pair_rows),width),device=device,dtype=torch.long);mask=torch.zeros_like(ids)
        for i,(tokens,act)in enumerate(pair_rows):ids[i,:len(tokens)]=torch.tensor(tokens,device=device);mask[i,:len(tokens)]=1
        pairs=(ids,mask,torch.tensor([x[1]for x in pair_rows],device=device))
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,draws],separators=(',',':')).encode()).hexdigest()
        return (*pad(self.tokenizer,encodings,device),torch.tensor(truth,device=device)),pairs

