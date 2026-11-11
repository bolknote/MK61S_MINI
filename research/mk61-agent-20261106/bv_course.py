"""Targeted repair with successful replay and masked, correct-token distillation."""
import collections
import hashlib
import json
import random
import torch
import torch.nn.functional as F
from bv_common import ROOT,read,rows
from bu_course import encoded
from aq_course import pad


class Course:
    def __init__(self,tokenizer):
        self.tokenizer=tokenizer;self.rng=random.Random(read(ROOT/'policy.json')['data_seed']);self.counts=collections.Counter();self.digest='00'*32
        self.hard=rows(ROOT/'hard.jsonl');self.variants=rows(ROOT/'train.jsonl');general=rows(ROOT/'general.jsonl');self.general=[general[i]for i in read(ROOT/'general-valid-ids.json')];anchors=rows(ROOT/'anchors.jsonl')
        self.old=[g for g in anchors if g['curriculum']=='retained_success'];self.comp=[g for g in anchors if g['curriculum']=='composition_success']
        self.lookup={g['id']:g for g in self.hard+anchors};self.focus=[];self.priority_updates=[]
        assert len(self.hard)==10 and len(self.old)==102 and len(self.comp)==185
    def draw(self,g,step,slot,exact=False):
        review=(step+slot)%4==0;mode='default'if exact else self.rng.choice(['default','extras','full','distractors'])
        for attempt in range(30):
            identity=f'{step}:{slot}:{attempt}:{self.rng.randrange(2**63)}'
            try:value=encoded(self.tokenizer,g,identity,mode,review,self.rng.randrange(3,12)if review else 12)
            except ValueError:mode='default';continue
            self.counts[g.get('curriculum','general')]+=1;self.counts['review'if review else'initial']+=1;self.counts['layout_'+mode]+=1
            self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([g['id'],g.get('paraphrase'),identity,mode,review]).encode()).hexdigest()
            return value,bool(g.get('verified_parent_success'))
        raise RuntimeError(('No bounded retention lesson',g['id']))
    def prioritize(self,report,step):
        ids=[]
        for mode in ['hard','retention','composition']:
            ids.extend(r['id']for r in report[mode]['records']if not r['program_correct']and r['id']in self.lookup)
        self.focus=list(dict.fromkeys(ids));self.priority_updates.append({'step':step,'training_fit_error_ids':self.focus[:]})
    def step(self,step,device='cuda'):
        values=[]
        for _ in range(4):values.append(self.draw(self.rng.choice(self.hard),step,len(values),True))
        for _ in range(4):values.append(self.draw(self.rng.choice(self.variants),step,len(values)))
        for pool in [self.old,self.comp]:
            for _ in range(8):values.append(self.draw(self.rng.choice(pool),step,len(values)))
        for _ in range(8):
            if self.focus and _<4:
                g=self.lookup[self.rng.choice(self.focus)];values.append(self.draw(g,step,len(values),g['curriculum']=='exact_repair'));self.counts['focused_fit_replay']+=1
            else:values.append(self.draw(self.rng.choice(self.general),step,len(values)))
        self.rng.shuffle(values)
        micro=read(ROOT/'policy.json')['microbatch']
        return [(*pad([v for v,_ in values[i:i+micro]],device),torch.tensor([keep for _,keep in values[i:i+micro]],device=device))for i in range(0,32,micro)]


def loss(model,teacher,batch,head,kd_weight=.5):
    ids,mask,labels,_,_,positive=batch;hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    valid=labels[:,1:]!=-100;coords=valid.nonzero();mapping=torch.full((len(model.get_input_embeddings().weight),),-100,device=ids.device,dtype=torch.long)
    mapping[head]=torch.arange(len(head),device=ids.device);target=mapping[labels[:,1:][valid]];assert(target>=0).all()
    logp=F.linear(hidden[:,:-1][valid],model.get_input_embeddings().weight[head]).float().log_softmax(-1)
    parts=-logp.gather(1,target[:,None]).flatten();sums=torch.zeros(len(ids),device=ids.device).scatter_add(0,coords[:,0],parts)
    den=torch.zeros_like(sums).scatter_add(0,coords[:,0],torch.ones_like(parts));ce=(sums/den).mean();kd=ce*0;kept=0
    if positive.any():
        with torch.no_grad():
            th=teacher.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
            logits=F.linear(th[:,:-1][valid],teacher.get_input_embeddings().weight[head]).float()
            keep=positive[coords[:,0]]&(logits.argmax(-1)==target);prob=logits.softmax(-1)
        if keep.any():kd=F.kl_div(logp[keep],prob[keep],reduction='batchmean');kept=int(keep.sum())
    return ce+kd_weight*kd,{'CE':float(ce.detach()),'KD':float(kd.detach()),'copied_correct_tokens':kept}
