"""Matched Q4 continuation on real multi-op meanings, bytecode and tool feedback."""
import argparse
import collections
import fcntl
from functools import lru_cache
import json
import math
from pathlib import Path
import random
import re
import shutil
import sys
import time

import numpy as np
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from capacity_train import example_loss
from compose_common import ROOT,ARMS,read,sha,formula_prompt,make_task,rename_task
from compose_eval import panel,summary,key_for,good
from course_common import calc_prompt,program_prompt,answer,prefix
from emulator import Emulator
from harness import check_program,feedback,trace_feedback
from native_context import wrap
from native_quant import attach,save,packed_copy
from tasks import BUILD,program_text
from compose_semantics import core_labels


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=ARMS,required=True);p.add_argument('--phase',type=int,required=True)
    p.add_argument('--initial',type=Path,required=True);p.add_argument('--steps',type=int,default=8000);a=p.parse_args()
    out=ROOT/f'{a.arm}-phase{a.phase}';out.mkdir(exist_ok=True)
    lock=(out/'training.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    signature={'arm':a.arm,'phase':a.phase,'steps':a.steps,'initial_sha256':sha(a.initial/'model.safetensors'),
      'course_sha256':sha(ROOT/'course/train.jsonl'),'precision':'Q4 group32 throughout','effective_batch':32}
    extra_train=ROOT/f'phase{a.phase}-extra-train.jsonl'
    feedback_file=ROOT/f'phase{a.phase}-feedback.jsonl'
    signature['extra_train_sha256']=sha(extra_train)if extra_train.exists()else None
    signature['feedback_sha256']=sha(feedback_file)if feedback_file.exists()else None
    signature['semantic_focus']=a.phase>=3
    source_names=['compose_train.py','compose_common.py','compose_eval.py','native_quant.py','native_context.py','course_common.py','harness.py','compose_semantics.py']
    signature['source_sha256']={n:sha(Path(__file__).parent/n)for n in source_names}
    if(out/'training.json').exists():
        previous=json.loads((out/'training.json').read_text())['signature']
        previous.setdefault('semantic_focus',False)
        assert{k:v for k,v in previous.items()if k!='source_sha256'}=={k:v for k,v in signature.items()if k!='source_sha256'}
        for name,digest in previous['source_sha256'].items():assert sha(out/'source'/name)==digest
        print('Matching phase complete');return
    if(out/'failed.json').exists():(out/'failed.json').rename(out/f'previous-failed-{int(time.time())}.json')
    source=out/'source';source.mkdir(exist_ok=True)
    for name in source_names:
        shutil.copyfile(Path(__file__).parent/name,source/name)
    signature['source_sha256']={p.name:sha(p)for p in source.glob('*.py')}
    torch.set_num_threads(2);torch.manual_seed(6113000+a.phase);rng=random.Random(6113000+a.phase)
    torch.cuda.set_per_process_memory_fraction(.025);torch.backends.cuda.matmul.allow_tf32=True
    resume=out/'optimizer/state.pt';state=torch.load(resume,map_location='cpu',weights_only=True)if resume.exists()else None
    initial=out/'last'if state else a.initial
    tokenizer=AutoTokenizer.from_pretrained(initial,local_files_only=True,trust_remote_code=False);tokenizer.model_max_length=2048
    model=AutoModelForCausalLM.from_pretrained(initial,local_files_only=True,trust_remote_code=False).to('cuda')
    assert model.config.max_position_embeddings==2048;attach(model,'q4')
    embed=model.get_input_embeddings().parametrizations.weight.original
    optimizer=torch.optim.AdamW([{'params':[p for p in model.parameters()if p is not embed],'factor':1.},
       {'params':[embed],'factor':.3}],lr=6e-5,weight_decay=.01)
    optimizer_ids={id(x)for g in optimizer.param_groups for x in g['params']}
    training=read(ROOT/'course/train.jsonl');pools=collections.defaultdict(lambda:collections.defaultdict(list));pairs=collections.defaultdict(list)
    if extra_train.exists():training+=read(extra_train)
    for i,t in enumerate(training):pools[t['level']][t['source']].append(i);pairs[(t['level'],t['pair_id'])].append(i)
    replay=read(ROOT/'course/formal-replay.jsonl')
    replay += [r for r in read(BUILD/'training/sft-combined-v2.jsonl')if r['kind']in ['repair_after_failure','repair_after_trace','finish_after_pass','trace_call']][:3000]
    supplemental=ROOT/f'phase{a.phase}-feedback.jsonl'
    if supplemental.exists():replay+=read(supplemental)
    def encode(prompt,target,context=2048):
        x=tokenizer.encode(prompt,add_special_tokens=False);y=tokenizer.encode(target,add_special_tokens=False)+[tokenizer.eos_token_id]
        if len(x)+len(y)>context:raise ValueError(f'Target does not fit{context}: {len(x)}+{len(y)}')
        return x+y,[-100]*len(x)+y
    def semantic_encode(prompt,expression,context):
        content=prefix(expression);target='<calc>'+content+'</calc>'
        x=tokenizer.encode(prompt,add_special_tokens=False)
        item=tokenizer(target,add_special_tokens=False,return_offsets_mapping=True)
        y=item['input_ids']+[tokenizer.eos_token_id]
        if len(x)+len(y)>context:raise ValueError(f'Target does not fit{context}: {len(x)}+{len(y)}')
        labels=core_labels(item['input_ids'],item['offset_mapping'],6,6+len(content),tokenizer.eos_token_id)
        return x+y,[-100]*len(x)+labels
    replay=[encode(re.sub(r'<plan>.*?</plan>','',r['prompt'],flags=re.S),re.sub(r'<plan>.*?</plan>','',r['answer'],flags=re.S))for r in replay]
    replay_by_context={c:[row for row in replay if len(row[0])<=c]for c in [512,1024,2048]}
    assert all(replay_by_context.values())
    stream=np.memmap(BUILD/'native-mixed-v1/language/train.u16',mode='r',dtype='<u2')
    domain=[tokenizer.encode(r['text'],add_special_tokens=False)for r in read(BUILD/'training/domain-documents.jsonl')];domain=[x for x in domain if len(x)>=32]
    em=Emulator();counts=collections.Counter();contexts=collections.Counter();length_bins=collections.Counter()
    @lru_cache(maxsize=16384)
    def encoded(index,permutation,kind,context,salt):
        row=rename_task(training[index],permutation)
        if kind=='compile':return encode(formula_prompt(row['expression']),'<write>'+program_text(row['reference_code'])+'</write><run/>',context)
        wrapping=context-160 if context>512 and kind in ['repair','trace_repair','done']else context
        row['task']=wrap(row['task'],tokenizer,wrapping,salt)
        if kind=='parse_semantic':return semantic_encode(calc_prompt(row['task']),row['expression'],context)
        if kind=='parse':return encode(calc_prompt(row['task']),'<calc>'+prefix(row['expression'])+'</calc>',context)
        if kind=='program':return encode(program_prompt(row),answer(row),context)
        if kind=='done':return encode(program_prompt({**row,'initial_code':row['reference_code']},observation='PASS'),'<done/>',context)
        wrong=list(row['reference_code']);local=random.Random(6113101+index)
        positions=list(range(len(wrong)-1));local.shuffle(positions);checked=None
        for position in positions:
            wrong=list(row['reference_code']);old=wrong[position]
            alternatives=[0x60,0x61,0x62,0x63]if 0x60<=old<=0x63 else[0x10,0x11,0x12,0x13,0x31,0x0B,0x22]
            wrong[position]=local.choice([x for x in alternatives if x!=old]);checked=check_program(em,wrong,row['public_tests'])
            if not checked['pass']:break
        if checked is None or checked['pass']:return encode(program_prompt(row),answer(row),context)
        observed=trace_feedback(em,wrong,row['public_tests'][0])if kind=='trace_repair'else feedback(checked)
        return encode(program_prompt({**row,'initial_code':wrong},observation=observed),answer(row),context)
    def choose(level):
        sources=sorted(pools[level]);weights=[.55 if x=='teacher_new'else .25 if x=='compound_legacy'else .2 if x=='procedural'else .5 for x in sources]
        source=rng.choices(sources,weights=weights)[0];return rng.choice(pools[level][source])
    def batch(context,micro,global_step):
        def quota(frac):
            x=frac*micro;return int(x)+(rng.random()<x%1)
        n_replay=quota(.25);n_lm=min(quota(.05),micro-n_replay)
        n_basic=min(quota(.35 if global_step<=1000 else .25),micro-n_replay-n_lm)
        n_comp=micro-n_replay-n_lm-n_basic
        rows=[rng.choice(replay_by_context[context])for _ in range(n_replay)];counts['formal_tool_replay']+=n_replay
        for _ in range(n_lm):
            if rng.random()<.5:
                ids=rng.choice(domain);start=rng.randrange(max(1,len(ids)-511));ids=ids[start:start+512];counts['domain_lm']+=1
            else:
                start=rng.randrange(len(stream)-513);ids=stream[start:start+512].astype(np.int64).tolist();counts['public_lm']+=1
            rows.append((ids,ids));counts['language_replay']+=1
        for category,total in [('basic',n_basic),('composed',n_comp)]:
            group=[]
            while len(group)<total:
                level=1 if category=='basic'else 2 if global_step<=1000 or rng.random()<(.7 if global_step<=4000 else .5)else 3
                i=choose(level);j=rng.choice(pairs[(level,training[i]['pair_id'])]);perm=tuple(rng.sample(['R0','R1','R2','R3'],4))
                draw=rng.random()
                if a.phase>=3:kind='parse_semantic'if draw<.35 else'parse'if draw<.7 else'program'if draw<.9 else'compile'if draw<.94 else'repair'if draw<.98 else'trace_repair'if draw<.99 else'done'
                else:kind='parse'if draw<.35 else'program'if draw<.8 else'compile'if draw<.9 else'repair'if draw<.96 else'trace_repair'if draw<.99 else'done'
                salt=rng.randrange(32)
                for index in [i,j]:
                    if len(group)>=total:break
                    try:value=encoded(index,perm,kind,context,salt)
                    except ValueError as error:
                        if not str(error).startswith('Target does not fit'):raise
                        counts['resampled_overlength']+=1;continue
                    group.append(value);counts[f'level{level}:{kind}']+=1;counts['source:'+training[index]['source']]+=1
            counts[category]+=len(group);rows+=group
        assert len(rows)==micro;rng.shuffle(rows);length=max(len(x)for x,y in rows)
        length_bins[str((length//256)*256)]+=1
        ids=torch.full((micro,length),tokenizer.pad_token_id or 0,dtype=torch.long);labels=torch.full_like(ids,-100);mask=torch.zeros_like(ids)
        for i,(x,y)in enumerate(rows):ids[i,:len(x)]=torch.tensor(x);labels[i,:len(y)]=torch.tensor(y);mask[i,:len(x)]=1
        return ids.to('cuda'),mask.to('cuda'),labels.to('cuda')
    history=[];best=None;beststep=0;start_step=0;losses=[];started=time.monotonic()
    if state:
        assert state['signature']==signature
        optimizer.load_state_dict(state['optimizer']);rng.setstate(state['python_rng']);torch.set_rng_state(state['torch_rng']);torch.cuda.set_rng_state_all(state['cuda_rng'])
        start_step=state['step'];counts.update(state['counts']);contexts.update(state['contexts']);length_bins.update(state['length_bins'])
        history=state['history'];best=state['best'];beststep=state['best_step']
    def development(step):
        nonlocal best,beststep
        replica,packet=packed_copy(model,out/'development.mkqb','q4');result=panel(replica.to('cuda'),tokenizer)
        key=key_for(result);record={'step':step,'key':key,'good_quality_gate':good(result),'summary':summary(result),'packet':packet}
        (out/f'development-{step}.json').write_text(json.dumps({'metrics':result,**record},ensure_ascii=False,indent=2)+'\n');history.append(record)
        if best is None or key>best:best=key;beststep=step;save(model,tokenizer,out/'best','q4')
        print(json.dumps({'development':step,'best_step':beststep,'good_quality_gate':good(result),'summary':record['summary']},ensure_ascii=False),flush=True)
        assert optimizer_ids=={id(p)for p in model.parameters()};del replica
    if not state:development(0)
    for step in range(start_step+1,a.steps+1):
        global_step=(a.phase-1)*8000+step;context=rng.choices([512,1024,2048],weights=[.8,.1,.1])[0];contexts[str(context)]+=1
        micro=16 if context==512 else 8 if context==1024 else 4
        model.train();optimizer.zero_grad(set_to_none=True)
        rate=(6e-5 if a.phase==1 else 4e-5)*min(1.,step/100)*(.25+.75*(1+math.cos(math.pi*step/a.steps))/2)
        for group in optimizer.param_groups:group['lr']=rate*group['factor']
        value=0.
        for _ in range(32//micro):
            ids,mask,labels=batch(context,micro,global_step)
            with torch.autocast('cuda',dtype=torch.bfloat16):
                prediction=model(input_ids=ids,attention_mask=mask,use_cache=False).logits;loss=example_loss(prediction,labels)/(32//micro)
            if not torch.isfinite(loss):raise ValueError('Nonfinite Q4 composition loss')
            value+=float(loss.detach());loss.backward();del prediction,loss,ids,mask,labels
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step();losses.append(value)
        if step==1 or step%50==0:
            status={'phase':'training','arm':a.arm,'course_phase':a.phase,'step':step,'steps':a.steps,
              'loss':sum(losses[-50:])/len(losses[-50:]),'context':context,'best_step':beststep,'seconds':time.monotonic()-started,'counts':dict(counts)}
            (out/'status.json').write_text(json.dumps(status)+'\n');print(json.dumps(status),flush=True)
        if step%1000==0 or step==a.steps:
            development(step);save(model,tokenizer,out/'last','q4');resume.parent.mkdir(exist_ok=True)
            checkpoint={'signature':signature,'step':step,'optimizer':optimizer.state_dict(),'python_rng':rng.getstate(),
              'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all(),'counts':dict(counts),
              'contexts':dict(contexts),'length_bins':dict(length_bins),'history':history,'best':best,'best_step':beststep}
            temp=resume.with_suffix('.tmp');torch.save(checkpoint,temp);temp.replace(resume)
    report={'signature':signature,'completed':True,'steps':a.steps,'best_step':beststep,'best_key':best,'history':history,
      'actual_sample_counts':dict(counts),'optimizer_steps_by_context':dict(contexts),'actual_batch_length_bins':dict(length_bins),
      'seconds':time.monotonic()-started,'fresh_used_for_selection':False,'target_precision_throughout':'Q4 group32',
      'compiler_supplies_training_references_only':True,'self_predicted_calc_before_neural_bytecode':True}
    (out/'training.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (out/'status.json').write_text(json.dumps({'phase':'complete','best_step':beststep,'key':best})+'\n')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if '--arm'in sys.argv and'--phase'in sys.argv:
            arm=sys.argv[sys.argv.index('--arm')+1];phase=sys.argv[sys.argv.index('--phase')+1]
            folder=ROOT/f'{arm}-phase{phase}';folder.mkdir(exist_ok=True);(folder/'failed.json').write_text(json.dumps({'error':str(error)})+'\n')
        raise
