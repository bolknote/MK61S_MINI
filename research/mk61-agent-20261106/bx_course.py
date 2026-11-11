"""Matched initial/replan pairs, gold supervision, JS consistency, durable replay."""
import collections
import hashlib
import json
import random
import torch
import torch.nn.functional as F
from bx_common import ROOT,read,rows
from bu_course import encoded
from aq_course import pad
from az_teacher import pool_for


def training_pool(g):
    # The protocol keeps its base constants first; semantic contrasts still
    # share the same remaining constants and the same resulting layout.
    base=pool_for('');return base+[x for x in g['pool']if x not in base]


class Course:
    def __init__(self,tokenizer):
        self.tokenizer=tokenizer;self.rng=random.Random(read(ROOT/'policy.json')['data_seed']);self.counts=collections.Counter();self.digest='00'*32
        self.hard=rows(ROOT/'hard.jsonl');self.regressions=rows(ROOT/'regressions.jsonl');self.anchors=rows(ROOT/'anchors.jsonl')
        self.old=[g for g in self.anchors if g['curriculum']=='retained_success'];self.comp=[g for g in self.anchors if g['curriculum']=='composition_success']
        all_general=rows(ROOT/'general.jsonl');self.general=[all_general[i]for i in read(ROOT/'general-valid-ids.json')]
        self.new=[g for g in rows(ROOT/'train.jsonl')if'contrast_id'not in g]
        groups=collections.defaultdict(lambda:collections.defaultdict(list))
        for g in rows(ROOT/'train.jsonl'):
            g['pool']=training_pool(g)
            if'contrast_id'in g:groups[g['contrast_id']][g['contrast_side']].append(g)
        for g in self.new:g['pool']=training_pool(g)
        self.contrasts=[v for v in groups.values()if set(v)=={0,1}];assert len(self.contrasts)==96
        self.lookup={g['id']:g for g in self.hard+self.regressions+self.anchors}
        self.cumulative=set(g['id']for g in self.regressions);self.active=set(self.cumulative);self.priority_updates=[]
        assert len(self.hard)==10 and self.old and self.comp and self.general and self.new
    def pair(self,g,step,slot,identity=None,mode=None,exact=False):
        mode=mode or('default'if exact else self.rng.choice(['default','extras','full','distractors']))
        for attempt in range(30):
            salt=identity or f'{step}:{slot}:{attempt}:{self.rng.randrange(2**63)}';remaining=self.rng.randrange(3,12)
            try:a=encoded(self.tokenizer,g,salt,mode,False,12);b=encoded(self.tokenizer,g,salt,mode,True,remaining)
            except ValueError:mode='default';continue
            assert [x for x in a[1]if x!=-100]==[x for x in b[1]if x!=-100]
            self.counts[g.get('curriculum','general')]+=1;self.counts['phase_pairs']+=1;self.counts['layout_'+mode]+=1
            record=[g['id'],g.get('paraphrase'),salt,mode,remaining]
            self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps(record).encode()).hexdigest()
            return a,b,bool(g.get('verified_parent_success'))
        raise RuntimeError(('Unbounded phase pair',g['id']))
    def prioritize(self,report,step):
        current={r['id']for p in ['hard','retention','composition']for r in report[p]['records']if not r['program_correct']and r['id']in self.lookup}
        before=self.cumulative.copy();self.cumulative.update(current);assert before<=self.cumulative
        self.active=current
        self.priority_updates.append({'step':step,'newly_added':sorted(self.cumulative-before),'active_fit_errors':sorted(current),'cumulative_count':len(self.cumulative),'never_removed':True})
    def step(self,step,device='cuda'):
        pairs=[]
        for j in range(2):pairs.append(self.pair(self.hard[(2*(step-1)+j)%len(self.hard)],step,len(pairs),exact=True))
        for pool in [sorted(self.active or self.cumulative),sorted(self.cumulative)]:
            g=self.lookup[self.rng.choice(pool)];pairs.append(self.pair(g,step,len(pairs),exact=step%2==0))
        for _ in range(2):
            c=self.rng.choice(self.contrasts);salt=f'contrast:{step}:{len(pairs)}:{self.rng.randrange(2**63)}';mode=self.rng.choice(['default','extras','full','distractors'])
            for side in [0,1]:pairs.append(self.pair(self.rng.choice(c[side]),step,len(pairs),salt,mode))
        for pool in [self.old,self.comp]:
            for _ in range(3):pairs.append(self.pair(self.rng.choice(pool),step,len(pairs)))
        for pool in [self.general,self.new]:pairs.append(self.pair(self.rng.choice(pool),step,len(pairs)))
        assert len(pairs)==16;self.rng.shuffle(pairs);values=[];positive=[]
        for a,b,keep in pairs:values.extend([a,b]);positive.extend([keep,keep])
        micro=read(ROOT/'policy.json')['microbatch'];assert micro%2==0
        return [(*pad(values[i:i+micro],device),torch.tensor(positive[i:i+micro],device=device))for i in range(0,32,micro)]


def loss(model,teacher,batch,head,js_weight=.1,kd_weight=.25):
    ids,mask,labels,_,_,positive=batch
    hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    valid=labels[:,1:]!=-100;coords=valid.nonzero();mapping=torch.full((len(model.get_input_embeddings().weight),),-100,device=ids.device,dtype=torch.long)
    mapping[head]=torch.arange(len(head),device=ids.device);target=mapping[labels[:,1:][valid]];assert(target>=0).all()
    logp=F.linear(hidden[:,:-1][valid],model.get_input_embeddings().weight[head]).float().log_softmax(-1)
    token_loss=-logp.gather(1,target[:,None]).flatten();sums=torch.zeros(len(ids),device=ids.device).scatter_add(0,coords[:,0],token_loss)
    counts=torch.zeros_like(sums).scatter_add(0,coords[:,0],torch.ones_like(token_loss));ce=(sums/counts).mean()
    js=[]
    for i in range(0,len(ids),2):
        left=logp[coords[:,0]==i];right=logp[coords[:,0]==i+1]
        assert torch.equal(target[coords[:,0]==i],target[coords[:,0]==i+1])
        mid=torch.logaddexp(left,right)-0.6931471805599453
        js.append(.5*((left.exp()*(left-mid)).sum(-1).mean()+(right.exp()*(right-mid)).sum(-1).mean()))
    consistency=torch.stack(js).mean();kd=ce*0;kept=0
    if positive.any():
        with torch.no_grad():
            th=teacher.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
            logits=F.linear(th[:,:-1][valid],teacher.get_input_embeddings().weight[head]).float()
            keep=positive[coords[:,0]]&(logits.argmax(-1)==target);prob=logits.softmax(-1)
        if keep.any():kd=F.kl_div(logp[keep],prob[keep],reduction='batchmean');kept=int(keep.sum())
    value=ce+js_weight*consistency+kd_weight*kd
    return value,{'CE':float(ce.detach()),'JS':float(consistency.detach()),'KD':float(kd.detach()),'correct_teacher_tokens':kept}
