"""Matched capacity / precision continuation with paired short supervised plans."""
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
import time

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM,AutoTokenizer

from course_common import answer,calc_prompt,prefix,program_prompt
from course_eval import assess,gate,selection,short
from evaluate import read_tasks
from lowbit import attach as attach_lowbit,export as export_lowbit,load as load_lowbit
from quantization import export_q4,load_q4
from tasks import compile_expr
from train import attach_qat,set_qat,checkpoint,plain_copy


def renamed(row,permutation):
    names=['R0','R1','R2','R3'];mapping=dict(zip(names,permutation))
    def expr(x):return mapping[x]if isinstance(x,str)else[x[0],*(expr(c)for c in x[1:])]
    value=expr(row['expression'])
    return {**row,'task':re.sub(r'R[0-3]',lambda m:mapping[m.group()],row['task']),
      'expression':value,'reference_code':compile_expr(value)+[0x50]}


def example_loss(logits,labels):
    logits=logits[:,:-1].float();target=labels[:,1:];mask=target!=-100
    ce=F.cross_entropy(logits.reshape(-1,logits.shape[-1]),target.reshape(-1),ignore_index=-100,reduction='none').reshape_as(target)
    return ((ce*mask).sum(1)/mask.sum(1).clamp_min(1)).mean()


def main():
    p=argparse.ArgumentParser();p.add_argument('--initial',type=Path,required=True);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--level',type=int,default=1)
    p.add_argument('--steps',type=int,default=4000);p.add_argument('--lr',type=float,default=6e-5)
    p.add_argument('--micro',type=int,default=16);p.add_argument('--format',choices=['q4','q3','q2','mixed'],default='q4')
    p.add_argument('--seed',type=int,default=6110820);p.add_argument('--eval-every',type=int,default=500)
    p.add_argument('--replay-fraction',type=float,default=.1);p.add_argument('--replay-file',type=Path)
    p.add_argument('--device',default='cuda');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);lock=(a.output/'training.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX)
    signature={'initial_sha256':hashlib.sha256((a.initial/'model.safetensors').read_bytes()).hexdigest(),
               'level':a.level,'steps':a.steps,'format':a.format,'lr':a.lr,'seed':a.seed,
               'course_sha256':hashlib.sha256((a.root/f'course-level{a.level}/train.jsonl').read_bytes()).hexdigest(),
               'replay_fraction':a.replay_fraction,
               'replay_sha256':hashlib.sha256((a.replay_file or a.root/f'course-level{a.level}/formal-replay.jsonl').read_bytes()).hexdigest(),
               'training_source_sha256':{n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest()
                  for n in ['capacity_train.py','course_common.py','course_eval.py','lowbit.py']}}
    if(a.output/'training.json').exists():
        previous=json.loads((a.output/'training.json').read_text())
        if previous['signature']!=signature:raise ValueError('Mismatched completed experiment')
        print('Reusing complete matching experiment',flush=True);return
    source=a.output/'source';source.mkdir(exist_ok=True)
    for name in ['capacity_train.py','course_common.py','course_eval.py','lowbit.py','quantization.py','train.py']:
        shutil.copyfile(Path(__file__).parent/name,source/name)
    torch.set_num_threads(2);torch.manual_seed(a.seed);rng=random.Random(a.seed)
    if a.device=='cuda':
        torch.cuda.set_per_process_memory_fraction(.025);torch.backends.cuda.matmul.allow_tf32=True
    tokenizer=AutoTokenizer.from_pretrained(a.initial,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(a.initial,local_files_only=True,trust_remote_code=False).to(a.device)
    if model.config.max_position_embeddings!=512:raise ValueError('Preserve native context')
    # Ordinary language embeddings move slowly, while operation/register binding
    # and the expanded FFN can learn. Both sizes use exactly the same policy.
    embed=model.get_input_embeddings().weight
    others=[v for v in model.parameters()if v is not embed]
    optimizer=torch.optim.AdamW([{'params':others,'lr':a.lr,'factor':1.},
                                {'params':[embed],'lr':a.lr*.1,'factor':.1}],weight_decay=.01)
    if a.format=='q4':attach_qat(model);set_qat(model,True)
    else:attach_lowbit(model,a.format)
    optimizer_ids={id(v)for g in optimizer.param_groups for v in g['params']}
    assert optimizer_ids=={id(v)for v in model.parameters()}
    course=a.root/f'course-level{a.level}'
    bylevel={a.level:read_tasks(course/'train.jsonl')}
    if a.level>1:bylevel[1]=read_tasks(a.root/'course-level1/train.jsonl')
    pools={};pairs={}
    for level,rows in bylevel.items():
        groups=collections.defaultdict(list);companions=collections.defaultdict(list)
        for i,row in enumerate(rows):groups[row['expression'][0]].append(i);companions[row['pair_id']].append(i)
        pools[level]=dict(groups);pairs[level]=dict(companions)
    replay=read_tasks(a.replay_file or course/'formal-replay.jsonl')
    partitions={'manual':read_tasks(a.root/f'level{a.level}-validation-manual.jsonl'),
                'teacher':read_tasks(course/'validation.jsonl')}
    formal=read_tasks(course/'formal-validation.jsonl')
    @lru_cache(maxsize=16384)
    def encode(level,index,permutation,kind):
        row=renamed(bylevel[level][index],permutation)
        prompt=calc_prompt(row['task'])if kind=='parse'else program_prompt(row)
        target='<calc>'+prefix(row['expression'])+'</calc>'if kind=='parse'else answer(row)
        x=tokenizer.encode(prompt,add_special_tokens=False);y=tokenizer.encode(target,add_special_tokens=False)+[tokenizer.eos_token_id]
        if len(x)+len(y)>512:raise ValueError('A curriculum task exceeds native context')
        return x+y,[-100]*len(x)+y
    def raw_encode(row):
        x=tokenizer.encode(row['prompt'],add_special_tokens=False);y=tokenizer.encode(row['answer'],add_special_tokens=False)+[tokenizer.eos_token_id]
        x=x[-(512-len(y)):]
        return x+y,[-100]*len(x)+y
    replay=[raw_encode(r)for r in replay]
    sample_counts=collections.Counter()
    def batch():
        # Quota is in examples, not sampling draws: one curriculum draw may
        # append a two-example pair, so a draw probability underweights replay.
        count=a.replay_fraction*a.micro
        replay_count=int(count)+(rng.random()<count-int(count))
        rows=[rng.choice(replay)for _ in range(replay_count)]
        sample_counts['formal_replay']+=replay_count
        while len(rows)<a.micro:
            level=1 if a.level>1 and rng.random()<1/3 else a.level
            op=rng.choice(sorted(pools[level]));index=rng.choice(pools[level][op]);row=bylevel[level][index]
            other=rng.choice(pairs[level][row['pair_id']]);permutation=tuple(rng.sample(['R0','R1','R2','R3'],4))
            kind='parse'if rng.random()<.5 else'program'
            rows.append(encode(level,index,permutation,kind))
            if len(rows)<a.micro:rows.append(encode(level,other,permutation,kind))
        sample_counts['new_course']+=a.micro-replay_count
        rng.shuffle(rows)
        length=max(len(r[0])for r in rows)
        ids=torch.full((len(rows),length),tokenizer.pad_token_id or 0,dtype=torch.long)
        labels=torch.full_like(ids,-100);mask=torch.zeros_like(ids)
        for i,(x,y)in enumerate(rows):
            ids[i,:len(x)]=torch.tensor(x);labels[i,:len(y)]=torch.tensor(y);mask[i,:len(x)]=1
        return ids.to(a.device),mask.to(a.device),labels.to(a.device)
    start=time.monotonic();history=[];best=None;beststep=0;losses=[];gradient_checks=[]
    def dev(step):
        nonlocal best,beststep
        replica=plain_copy(model);path=a.output/('development.mkq4'if a.format=='q4'else'development.mkqb')
        if a.format=='q4':packed=export_q4(replica,path);load_q4(replica,path)
        else:packed=export_lowbit(replica,path,a.format);load_lowbit(replica,path)
        result=assess(replica.to(a.device),tokenizer,partitions,formal);key=selection(result)
        detail={'step':step,'metrics':result,'summary':short(result),'key':key,'gate':gate(result),'packed':packed}
        (a.output/f'development-{step}.json').write_text(json.dumps(detail,ensure_ascii=False,indent=2)+'\n')
        history.append({k:v for k,v in detail.items()if k!='metrics'})
        if best is None or key>best:
            best=key;beststep=step;checkpoint(model,tokenizer,a.output/'best')
        print(json.dumps({'validation':step,'summary':short(result),'best_step':beststep,'gate':gate(result)},ensure_ascii=False),flush=True)
        del replica
        assert optimizer_ids=={id(v)for v in model.parameters()}
    # Keep a zero-step candidate so low-bit adaptation cannot force a worse
    # checkpoint merely because every subsequent step degraded validation.
    dev(0)
    accumulation=32//a.micro
    if accumulation*a.micro!=32:raise ValueError('Effective batch32 required')
    original_width=384 if model.config.intermediate_size==768 else None
    for step in range(1,a.steps+1):
        model.train();optimizer.zero_grad(set_to_none=True)
        rate=a.lr*min(1.,step/min(100,max(1,a.steps//10)))*(.2+.8*(1+math.cos(math.pi*step/a.steps))/2)
        for group in optimizer.param_groups:group['lr']=rate*group['factor']
        value=0.
        for _ in range(accumulation):
            ids,mask,labels=batch()
            with torch.autocast(device_type='cuda',dtype=torch.bfloat16,enabled=a.device=='cuda'):
                output=model(input_ids=ids,attention_mask=mask,use_cache=False)
                loss=example_loss(output.logits,labels)/accumulation
            if not torch.isfinite(loss):raise ValueError('Nonfinite course loss')
            value+=float(loss.detach());loss.backward();del output,loss,ids,mask,labels
        if original_width and step in [1,2,10]:
            norms={}
            for name,pv in model.named_parameters():
                if 'layers.0.mlp.'in name and pv.grad is not None:
                    g=pv.grad[:,original_width:]if'down_proj'in name else pv.grad[original_width:]
                    norms[name]=float(g.float().norm())
            gradient_checks.append({'step':step,'new_block_grad_norms':norms})
            if step==10 and any(v==0 for v in norms.values()):raise ValueError('Expanded FFN is not learning')
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step();losses.append(value)
        if step==1 or step%50==0:
            status={'phase':'training','step':step,'steps':a.steps,'format':a.format,
              'parameters':sum(v.numel()for v in model.parameters()),'loss':sum(losses[-50:])/len(losses[-50:]),
              'best_step':beststep,'seconds':time.monotonic()-start}
            (a.output/'status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status),flush=True)
        if step%a.eval_every==0 or step==a.steps:dev(step)
    checkpoint(model,tokenizer,a.output/'last')
    report={'signature':signature,'history':history,'best_step':beststep,'selection_key':best,
      'parameters':sum(v.numel()for v in model.parameters()),'steps':a.steps,'seconds':time.monotonic()-start,
      'effective_batch':32,'micro':a.micro,'loss':'mean target CE within example, then batch mean',
      'minimal_pairs_share_register_bijection':True,'embedding_lr_factor':.1,'qat_from_step':1,
      'replay_fraction':a.replay_fraction,'replay_file':str(a.replay_file),
      'actual_example_counts':dict(sample_counts),
      'expanded_gradients':gradient_checks,'fresh_audit_used_for_selection':False,
      'compiler_used_at_inference':False,'new_train_descriptions':len(bylevel[a.level])}
    (a.output/'training.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (a.output/'status.json').write_text(json.dumps({'phase':'complete','best_step':beststep,'key':best})+'\n')


if __name__=='__main__':main()
