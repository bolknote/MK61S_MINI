"""Matched core examples, direct vs teacher auxiliary task, Q4 throughout."""
import argparse
import collections
import fcntl
from functools import lru_cache
import hashlib
import json
import math
import random
import re
import shutil
import time
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from semantic_common import ROOT,ARMS,INITIAL,read,sha,write_json,allowed_ids,compact_head,auxiliary_prompt,auxiliary_answer
from semantic_eval import development,selection,simple_rate
from codec_train import compact_loss
from codec_eval import summary
from compose_common import rename_task
from compose_semantics import core_labels
from course_common import program_prompt,calc_prompt,prefix,answer
from emulator import Emulator
from harness import check_program,feedback,trace_feedback
from native_context import wrap
from native_quant import attach,save,packed_copy
from tasks import BUILD


class Course:
    def __init__(self,tokenizer):
        self.tokenizer=tokenizer;self.rng=random.Random(6116030);self.train=read(ROOT/'train.jsonl')
        self.pool=collections.defaultdict(list);self.pairs=collections.defaultdict(list);self.new=[]
        for i,t in enumerate(self.train):
            fresh=t['source']=='semantic_teacher_new';self.pool[(t['level'],fresh)].append(i)
            self.pairs[(t['level'],t['pair_id'])].append(i)
            if fresh:self.new.append(i)
        self.replay=[self.encode(re.sub(r'<plan>.*?</plan>','',r['prompt'],flags=re.S),re.sub(r'<plan>.*?</plan>','',r['answer'],flags=re.S))for r in read(ROOT/'replay.jsonl')]
        self.errors=[self.encode(r['prompt'],r['answer'])for r in read(ROOT/'actual-error-replay.jsonl')]
        self.fit={name:{c:[i for i,(x,y)in enumerate(rows)if len(x)<=c]for c in [512,1024,2048]}for name,rows in [('replay',self.replay),('error',self.errors)]}
        assert all(self.fit[name][c]for name in self.fit for c in [512,1024,2048])
        self.stream=np.memmap(BUILD/'native-mixed-v1/language/train.u16',mode='r',dtype='<u2')
        self.domain=[tokenizer.encode(r['text'],add_special_tokens=False)for r in read(BUILD/'training/domain-documents.jsonl')]
        self.domain=[x for x in self.domain if len(x)>=32];self.em=Emulator();self.counts=collections.Counter();self.contexts=collections.Counter();self.plan_digest='00'*32

    def encode(self,prompt,target,semantic=False):
        x=self.tokenizer.encode(prompt,add_special_tokens=False)
        encoded=self.tokenizer(target,add_special_tokens=False,return_offsets_mapping=True);y=encoded['input_ids']+[self.tokenizer.eos_token_id]
        labels=core_labels(encoded['input_ids'],encoded['offset_mapping'],6,len(target)-7,self.tokenizer.eos_token_id)if semantic else y
        return x+y,[-100]*len(x)+labels

    def choose(self,level):
        fresh=self.rng.random()<(.65 if level==1 else .85)
        return self.rng.choice(self.pool[(level,fresh)])

    @lru_cache(maxsize=16384)
    def encoded(self,index,permutation,kind,context,salt):
        row=rename_task(self.train[index],permutation)
        row['task']=wrap(row['task'],self.tokenizer,context-160 if context>512 and kind in ['repair','trace_repair','done']else context,salt)
        if kind in ['parse','parse_semantic']:return self.encode(calc_prompt(row['task']),'<calc>'+prefix(row['expression'])+'</calc>',kind=='parse_semantic')
        if kind=='program':return self.encode(program_prompt(row),answer(row))
        if kind=='done':return self.encode(program_prompt({**row,'initial_code':row['reference_code']},observation='PASS'),'<done/>')
        rng=random.Random(6116031+index);positions=list(range(len(row['reference_code'])-1));rng.shuffle(positions)
        for at in positions:
            wrong=list(row['reference_code']);old=wrong[at]
            pool=[0x60,0x61,0x62,0x63]if 0x60<=old<=0x63 else[0x10,0x11,0x12,0x13,0x31,0x0B,0x22]
            wrong[at]=rng.choice([x for x in pool if x!=old]);checked=check_program(self.em,wrong,row['public_tests'])
            if not checked['pass']:break
        else:return self.encode(program_prompt(row),answer(row))
        observed=trace_feedback(self.em,wrong,row['public_tests'][0])if kind=='trace_repair'else feedback(checked)
        return self.encode(program_prompt({**row,'initial_code':wrong},observation=observed),answer(row))

    @lru_cache(maxsize=8192)
    def side(self,index,permutation,context,salt):
        original=self.train[index];row=rename_task(original,permutation);mapping=dict(zip(['R0','R1','R2','R3'],permutation))
        rename=lambda text:re.sub(r'R[0-3]',lambda m:mapping[m.group()],text)
        row['roles']={mapping[k]:rename(v)for k,v in original['roles'].items()}
        row['steps']=[{**s,'explanation':rename(s['explanation'])}for s in original['steps']]
        row['task']=wrap(row['task'],self.tokenizer,context,salt)
        direct=self.encode(calc_prompt(row['task']),'<calc>'+prefix(row['expression'])+'</calc>',semantic=True)
        auxiliary=self.encode(auxiliary_prompt(row['task']),auxiliary_answer(row))
        return {'direct':direct,'auxiliary':auxiliary}

    def batch(self,arm,context,step,device):
        rng=self.rng;draws=[];rows=[];language=[]
        for name,n,source in [('replay',24,self.replay),('error',8,self.errors)]:
            for _ in range(n):
                i=rng.choice(self.fit[name][context]);rows.append(source[i]);language.append(False);draws.append([name,i])
            self.counts[name]+=n
        for _ in range(6):
            if rng.random()<.5:
                i=rng.randrange(len(self.domain));source=self.domain[i];at=rng.randrange(max(1,len(source)-511));ids=source[at:at+512];draws.append(['domain',i,at])
            else:
                at=rng.randrange(len(self.stream)-513);ids=self.stream[at:at+512].astype('int64').tolist();draws.append(['language',at])
            rows.append((ids,ids));language.append(True)
        self.counts['language']+=6
        for label,n in [('simple',26),('composed',64)]:
            added=0
            while added<n:
                level=1 if label=='simple'else rng.choice([2,3]);i=self.choose(level)
                j=rng.choice(self.pairs[(level,self.train[i]['pair_id'])]);perm=tuple(rng.sample(['R0','R1','R2','R3'],4));salt=rng.randrange(32)
                kind=rng.choices(['parse_semantic','parse','program','repair','trace_repair','done'],weights=[.25,.1,.5,.1,.03,.02])[0]
                for index in [i,j]:
                    if added>=n:break
                    pair=self.encoded(index,perm,kind,context,salt)
                    if len(pair[0])>context:self.counts['resampled_core_overlength']+=1;continue
                    rows.append(pair);language.append(False);draws.append(['core',index,perm,kind,context,salt]);added+=1
                    self.counts[f'level{level}:{kind}']+=1;self.counts['source:'+self.train[index]['source']]+=1
            self.counts[label]+=added
        assert len(rows)==128
        # Same 32 conditions in both arms. Direct rehearses their compact parse;
        # auxiliary learns blinded teacher roles/steps with the Russian head.
        added=0
        while added<32:
            index=rng.choice(self.new);perm=tuple(rng.sample(['R0','R1','R2','R3'],4));salt=rng.randrange(32)
            pairs=self.side(index,perm,context,salt)
            if max(len(p[0])for p in pairs.values())>context:self.counts['resampled_side_overlength_both']+=1;continue
            rows.append(pairs[arm]);language.append(arm=='auxiliary');draws.append(['side',index,perm,context,salt]);added+=1
        self.counts['side_conditions']+=added
        order=list(range(len(rows)));rng.shuffle(order);rows=[rows[i]for i in order];language=[language[i]for i in order]
        self.plan_digest=hashlib.sha256(bytes.fromhex(self.plan_digest)+json.dumps([step,context,draws,order],separators=(',',':')).encode()).hexdigest()
        length=max(len(x)for x,y in rows);ids=torch.full((len(rows),length),self.tokenizer.pad_token_id or 0,dtype=torch.long)
        labels=torch.full_like(ids,-100);mask=torch.zeros_like(ids)
        for i,(x,y)in enumerate(rows):ids[i,:len(x)]=torch.tensor(x);labels[i,:len(y)]=torch.tensor(y);mask[i,:len(x)]=1
        return ids.to(device),mask.to(device),labels.to(device),torch.tensor(language,dtype=torch.bool,device=device)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=ARMS,required=True);a=ap.parse_args()
    out=ROOT/a.arm;out.mkdir(exist_ok=True);lock=(out/'training.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    policy=json.loads((ROOT/'policy.json').read_text());resources=json.loads((ROOT/'resources.json').read_text());prepared=json.loads((ROOT/'prepared.json').read_text())
    assert all(sha(ROOT/name)==value['sha256']for name,value in prepared['files'].items())
    source_names=['semantic_train.py','semantic_common.py','semantic_eval.py','codec_train.py','codec_common.py','codec_eval.py','byte_codec.py','compose_common.py','compose_semantics.py','course_common.py','native_quant.py','lowbit.py','quantization.py','native_context.py','harness.py','emulator.py','tasks.py']
    signature={'arm':a.arm,'source_master_sha256':sha(INITIAL/'model.safetensors'),'prepared_sha256':sha(ROOT/'prepared.json'),
      'steps':policy['steps_each'],'core_batch':128,'side_batch':32,'sources':{name:sha(Path(__file__).parent/name)for name in source_names}}
    if(out/'training.json').exists():assert json.loads((out/'training.json').read_text())['signature']==signature;print('Semantic training complete');return
    archive=out/'source';archive.mkdir(exist_ok=True)
    for name in source_names:shutil.copyfile(Path(__file__).parent/name,archive/name)
    torch.set_num_threads(4);torch.manual_seed(6116032);torch.cuda.set_per_process_memory_fraction(resources['memory_fraction_each']);torch.backends.cuda.matmul.allow_tf32=True
    resume=out/'optimizer/state.pt';saved=torch.load(resume,map_location='cpu',weights_only=True)if resume.exists()else None
    if saved:assert saved['signature']==signature
    source=out/'last'if saved else INITIAL
    tokenizer=AutoTokenizer.from_pretrained(source,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False).to('cuda');attach(model,'q4')
    embedding=model.get_input_embeddings().parametrizations.weight.original
    optimizer=torch.optim.AdamW([{'params':[p for p in model.parameters()if p is not embedding],'factor':1.},
      {'params':[embedding],'factor':policy['embedding_lr_factor']}],lr=policy['lr'],weight_decay=policy['weight_decay'])
    optimizer_ids={id(p)for p in model.parameters()};course=Course(tokenizer);allowed=torch.tensor(allowed_ids('hex'),device='cuda');history=[];best=None;best_step=0;first=0;baseline_simple=None
    if saved:
        optimizer.load_state_dict(saved['optimizer']);course.rng.setstate(saved['rng']);torch.set_rng_state(saved['torch_rng']);torch.cuda.set_rng_state_all(saved['cuda_rng'])
        course.counts.update(saved['counts']);course.contexts.update(saved['contexts']);course.plan_digest=saved['plan_digest'];history=saved['history'];best=saved['best'];best_step=saved['best_step'];first=saved['step']
        baseline_simple=saved['baseline_simple']
    def validate(step):
        nonlocal best,best_step,baseline_simple
        replica,packet=packed_copy(model,out/'development.mkqb','q4');replica.to('cuda').eval();compact_head(replica,allowed_ids('hex'))
        result=development(replica,tokenizer)
        if baseline_simple is None:baseline_simple=simple_rate(result)
        key=selection(result,baseline_simple)
        record={'step':step,'key':key,'summary':summary(result),'packed':packet};history.append(record)
        write_json(out/f'development-{step}.json',{'metrics':result,**record})
        if best is None or key>best:best=key;best_step=step;save(model,tokenizer,out/'best','q4')
        assert optimizer_ids=={id(p)for p in model.parameters()}
        print(json.dumps({'development':step,'best_step':best_step,'key':key,'summary':record['summary']}),flush=True);del replica
    if not saved:validate(0)
    started=time.monotonic();losses=[];steps=policy['steps_each']
    for step in range(first+1,steps+1):
        context=course.rng.choices(policy['contexts'],weights=policy['context_probabilities'])[0];course.contexts[str(context)]+=1
        model.train();optimizer.zero_grad(set_to_none=True)
        rate=policy['lr']*min(1.,step/policy['warmup_updates'])*(.25+.75*(1+math.cos(math.pi*step/steps))/2)
        for group in optimizer.param_groups:group['lr']=rate*group['factor']
        ids,mask,labels,lm=course.batch(a.arm,context,step,'cuda')
        with torch.autocast('cuda',dtype=torch.bfloat16):loss=compact_loss(model,ids,mask,labels,lm,allowed)
        if not torch.isfinite(loss):raise ValueError('Nonfinite semantic QAT loss')
        losses.append(float(loss.detach()));loss.backward();del loss,ids,mask,labels,lm
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
        if step==1 or step%50==0:
            status={'phase':'training','arm':a.arm,'step':step,'steps':steps,'best_step':best_step,'loss':sum(losses[-50:])/len(losses[-50:]),
              'seconds':time.monotonic()-started,'context':context,'counts':dict(course.counts),'sample_plan_digest':course.plan_digest}
            write_json(out/'status.json',status);print(json.dumps(status),flush=True)
        if step%policy['validation_interval']==0 or step==steps:
            validate(step);save(model,tokenizer,out/'last','q4');resume.parent.mkdir(exist_ok=True)
            state={'signature':signature,'step':step,'optimizer':optimizer.state_dict(),'rng':course.rng.getstate(),'torch_rng':torch.get_rng_state(),
              'cuda_rng':torch.cuda.get_rng_state_all(),'counts':dict(course.counts),'contexts':dict(course.contexts),'plan_digest':course.plan_digest,'history':history,'best':best,'best_step':best_step,'baseline_simple':baseline_simple}
            temporary=resume.with_suffix('.tmp');torch.save(state,temporary);temporary.replace(resume)
    report={'signature':signature,'completed':True,'steps':steps,'best_step':best_step,'best_key':best,'history':history,
      'core_sample_counts':dict(course.counts),'optimizer_steps_by_context':dict(course.contexts),'sample_plan_digest':course.plan_digest,
      'seconds':time.monotonic()-started,'new_audit_used_for_selection':False,'target_precision_throughout':'Q4',
      'core_examples':128*steps,'side_conditions':32*steps,'side_task':'compact_parse'if a.arm=='direct'else'Russian_teacher_roles_and_steps',
      'auxiliary_output_required_at_inference':False}
    report['simple_validation_guard']={'baseline_rate':baseline_simple,'maximum_drop':.03,'formal_minimum':.95}
    write_json(out/'training.json',report);write_json(out/'status.json',{'phase':'complete','step':steps,'best_step':best_step})


if __name__=='__main__':main()
