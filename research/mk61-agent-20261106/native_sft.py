"""Full target-format MK-61 SFT, paired meanings, real tool feedback and long context."""
import argparse
import collections
import fcntl
from functools import lru_cache
import hashlib
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

from capacity_train import renamed,example_loss
from course_common import answer,calc_prompt,prefix,program_prompt,numeric_cases
from emulator import Emulator
from harness import check_program,feedback,trace_feedback
from native_context import wrap
from native_eval import panel,key_for,summary,read
from native_quant import attach,restore_scales,save,packed_copy
from tasks import BUILD,program_text


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['q4','mixed'],required=True);a=p.parse_args()
    root=BUILD/'native-mixed-v1';out=root/(a.arm+'-sft');out.mkdir(exist_ok=True)
    lock=(out/'training.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX)
    if(out/'training.json').exists():print('Full SFT complete');return
    source=out/'source';source.mkdir(exist_ok=True)
    for name in ['native_sft.py','native_quant.py','native_eval.py','native_context.py','course_common.py','harness.py']:
        shutil.copyfile(Path(__file__).parent/name,source/name)
    torch.set_num_threads(2);torch.manual_seed(6112001);rng=random.Random(6112001)
    torch.cuda.set_per_process_memory_fraction(.025);torch.backends.cuda.matmul.allow_tf32=True
    initial=root/(a.arm+'-language/best')
    tokenizer=AutoTokenizer.from_pretrained(initial,local_files_only=True,trust_remote_code=False)
    tokenizer.model_max_length=2048
    model=AutoModelForCausalLM.from_pretrained(initial,local_files_only=True,trust_remote_code=False).to('cuda')
    attach(model,a.arm);restore_scales(model,initial)
    embed=model.get_input_embeddings().parametrizations.weight.original
    normal=[v for n,v in model.named_parameters()if not n.endswith('.log_scale')and v is not embed]
    scales=[v for n,v in model.named_parameters()if n.endswith('.log_scale')]
    optimizer=torch.optim.AdamW([{'params':normal,'factor':1.},{'params':[embed],'factor':.1}]+
      ([{'params':scales,'factor':5.}]if scales else[]),lr=1e-4,weight_decay=.01)
    optimizer_ids={id(x)for g in optimizer.param_groups for x in g['params']}
    training=read(root/'course/train.jsonl');groups=collections.defaultdict(list);partners=collections.defaultdict(list)
    for i,t in enumerate(training):groups[t['expression'][0]].append(i);partners[t['pair_id']].append(i)
    compound_start=len(training);training+=read(root/'course/compound-train.jsonl');compound_enabled=False
    replay=read(root/'course/formal-replay.jsonl')
    repair_old=[r for r in read(BUILD/'training/sft-combined-v2.jsonl')if r['kind']in ['repair_after_failure','repair_after_trace','finish_after_pass','trace_call']]
    # Existing tool trajectories are executable-generated training examples.
    replay+=repair_old[:3000]
    def encode_text(prompt,target,context=2048):
        x=tokenizer.encode(prompt,add_special_tokens=False);y=tokenizer.encode(target,add_special_tokens=False)+[tokenizer.eos_token_id]
        if len(x)+len(y)>context:raise ValueError('A supervised target exceeds its context')
        return x+y,[-100]*len(x)+y
    replay=[encode_text(re.sub(r'<plan>.*?</plan>','',r['prompt'],flags=re.S),
                        re.sub(r'<plan>.*?</plan>','',r['answer'],flags=re.S))for r in replay]
    stream=np.memmap(root/'language/train.u16',mode='r',dtype='<u2');em=Emulator();counts=collections.Counter();context_steps=collections.Counter()
    domain=[tokenizer.encode(r['text'],add_special_tokens=False)for r in read(BUILD/'training/domain-documents.jsonl')]
    domain=[x for x in domain if len(x)>=32]
    @lru_cache(maxsize=16384)
    def encoded(index,permutation,kind,context,salt):
        task=renamed(training[index],permutation);task['task']=wrap(task['task'],tokenizer,context,salt)
        local=random.Random(hashlib.sha256((str(index)+repr(permutation)).encode()).hexdigest())
        cases=numeric_cases(task['expression'],local);task['public_tests']=cases[:2];task['hidden_tests']=cases[2:]
        if kind=='parse':return encode_text(calc_prompt(task['task']),'<calc>'+prefix(task['expression'])+'</calc>')
        if kind=='program':return encode_text(program_prompt(task),answer(task))
        if kind=='done':
            prompt=program_prompt({**task,'initial_code':task['reference_code']},observation='PASS')
            return encode_text(prompt,'<done/>')
        wrong=list(task['reference_code']);operator=wrong[-2]
        alternatives=[0x10,0x11,0x12,0x13]if operator in[0x10,0x11,0x12,0x13]else[0x31,0x0B,0x22]
        alternatives=[x for x in alternatives if x!=operator];wrong[-2]=local.choice(alternatives)
        checked=check_program(em,wrong,task['public_tests'])
        if checked['pass']:return encode_text(program_prompt(task),answer(task))
        observed=trace_feedback(em,wrong,task['public_tests'][0])if kind=='trace_repair'else feedback(checked)
        return encode_text(program_prompt({**task,'initial_code':wrong},observation=observed),answer(task))
    def batch(context,micro):
        rows=[];n_replay=int(.3*micro)+(rng.random()<(.3*micro)%1);n_lm=int(.1*micro)+(rng.random()<(.1*micro)%1)
        n_lm=min(n_lm,micro-n_replay)
        rows=[rng.choice(replay)for _ in range(n_replay)];counts['formal_or_tool_replay']+=n_replay
        for _ in range(n_lm):
            if domain and rng.random()<.5:
                document=rng.choice(domain);at=rng.randrange(max(1,len(document)-511));ids=document[at:at+512];counts['book_and_game_lm_replay']+=1
            else:
                at=rng.randrange(len(stream)-513);ids=stream[at:at+512].astype(np.int64).tolist();counts['public_language_lm_replay']+=1
            rows.append((ids,ids));counts['language_replay']+=1
        while len(rows)<micro:
            if compound_enabled and rng.random()<.25 and len(training)>compound_start:
                i=rng.randrange(compound_start,len(training));j=i;counts['composed_draws']+=1
            else:
                op=rng.choice(sorted(groups));i=rng.choice(groups[op]);j=rng.choice(partners[training[i]['pair_id']])
            perm=tuple(rng.sample(['R0','R1','R2','R3'],4));draw=rng.random()
            kind='parse'if draw<.4 else'program'if draw<.8 else'repair'if draw<.9 else'trace_repair'if draw<.95 else'done'
            salt=rng.randrange(32)
            rows.append(encoded(i,perm,kind,context,salt));counts[kind]+=1
            if len(rows)<micro:rows.append(encoded(j,perm,kind,context,salt));counts[kind]+=1
        rng.shuffle(rows);length=max(len(x)for x,y in rows)
        ids=torch.full((len(rows),length),tokenizer.pad_token_id or 0,dtype=torch.long);labels=torch.full_like(ids,-100);mask=torch.zeros_like(ids)
        for i,(x,y)in enumerate(rows):ids[i,:len(x)]=torch.tensor(x);labels[i,:len(y)]=torch.tensor(y);mask[i,:len(x)]=1
        return ids.to('cuda'),mask.to('cuda'),labels.to('cuda')
    history=[];best_key=None;best_step=0;started=time.monotonic();losses=[]
    def dev(step):
        nonlocal best_key,best_step
        if step==6000:
            # From here the checkpoint must also be judged on long context.
            # Retain the short-only winner separately instead of comparing keys
            # that were computed over different required skills.
            shutil.copytree(out/'best',out/'best-short',dirs_exist_ok=True)
            save(model,tokenizer,out/'before-context',a.arm)
            best_key=None
        replica,packed=packed_copy(model,out/'development.mkqb',a.arm)
        result=panel(replica.to('cuda'),tokenizer,root,long_context=step>=6000,include_compound=compound_enabled);key=key_for(result)
        record={'step':step,'key':key,'summary':summary(result),'packed':packed}
        history.append(record);(out/f'development-{step}.json').write_text(json.dumps({'metrics':result,**record},ensure_ascii=False,indent=2)+'\n')
        if best_key is None or key>best_key:best_key=key;best_step=step;save(model,tokenizer,out/'best',a.arm)
        print(json.dumps({'development_step':step,'summary':record['summary'],'best_step':best_step},ensure_ascii=False),flush=True)
        del replica
        assert optimizer_ids=={id(v)for v in model.parameters()}
    dev(0)
    for step in range(1,8001):
        # Basic semantics first; then matched explicit long-context exercises.
        context=512 if step<=6000 else rng.choice([512,1024,2048])
        micro=16 if context==512 else 8 if context==1024 else 4
        context_steps[str(context)]+=1
        model.train();optimizer.zero_grad(set_to_none=True)
        rate=1e-4*min(1.,step/100)*(.2+.8*(1+math.cos(math.pi*step/8000))/2)
        for g in optimizer.param_groups:g['lr']=rate*g['factor']
        value=0.
        for _ in range(32//micro):
            ids,mask,labels=batch(context,micro)
            with torch.autocast('cuda',dtype=torch.bfloat16):
                prediction=model(input_ids=ids,attention_mask=mask,use_cache=False).logits
                loss=example_loss(prediction,labels)/(32//micro)
            if not torch.isfinite(loss):raise ValueError('Nonfinite target-format SFT')
            value+=float(loss.detach());loss.backward();del prediction,loss,ids,mask,labels
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step();losses.append(value)
        if step==1 or step%50==0:
            status={'phase':'mk61_sft','step':step,'steps':8000,'context':context,'loss':sum(losses[-50:])/len(losses[-50:]),
              'best_step':best_step,'seconds':time.monotonic()-started,'sample_counts':dict(counts)}
            (out/'status.json').write_text(json.dumps(status)+'\n');print(json.dumps(status),flush=True)
        if step%1000==0 or step==8000:dev(step)
        if step==4000:
            last=history[-1]['summary'];rates=[last[p][kind]['rate']for p in ['manual','teacher']for kind in ['parse','program']]
            own={'basic_gate':min(rates)>=.9 and last['formal']['rate']>=.95,'step':step}
            (root/(a.arm+'-basic-gate.json')).write_text(json.dumps(own)+'\n')
            start_wait=time.monotonic()
            while not all((root/(arm+'-basic-gate.json')).exists()for arm in ['q4','mixed']):
                if any((root/(arm+'-sft/failed.json')).exists()for arm in ['q4','mixed']):raise RuntimeError('Other matched SFT arm failed')
                if time.monotonic()-start_wait>3600:raise TimeoutError('Other matched arm did not reach progression barrier')
                time.sleep(10)
            compound_enabled=any(json.loads((root/(arm+'-basic-gate.json')).read_text())['basic_gate']for arm in ['q4','mixed'])
            (out/'progression.json').write_text(json.dumps({'composed_training_enabled':compound_enabled,'decision_from_both_basic_panels':True})+'\n')
    save(model,tokenizer,out/'last',a.arm)
    result={'completed':True,'arm':a.arm,'steps':8000,'best_step':best_step,'best_key':best_key,'history':history,
      'actual_sample_counts':dict(counts),'target_precision_from_first_language_and_sft_update':True,
      'tool_feedback_from_real_emulator_training_cases_only':True,'context_curriculum_steps':2000,'optimizer_steps_by_context':dict(context_steps),
      'composed_training_enabled':compound_enabled,
      'fresh_used_for_selection':False,'seconds':time.monotonic()-started}
    (out/'training.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (out/'status.json').write_text(json.dumps({'phase':'complete','best_step':best_step,'key':best_key})+'\n')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        if '--arm'in sys.argv:
            arm=sys.argv[sys.argv.index('--arm')+1];folder=BUILD/'native-mixed-v1'/(arm+'-sft')
            folder.mkdir(exist_ok=True);(folder/'failed.json').write_text(json.dumps({'error':str(error)})+'\n')
        raise
