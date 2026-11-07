"""Q4-aware preference training on executable correct/incorrect calculator programs."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import time

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM,AutoTokenizer

from evaluate import read_tasks
from evaluate_batched import evaluate
from quantization import export_q4,load_q4
from train import attach_qat,set_qat,plain_copy,checkpoint,strip_plan


def encode(tokenizer,prompt,answer):
    p=tokenizer.encode(strip_plan(prompt),add_special_tokens=False)[-352:]
    a=tokenizer.encode(strip_plan(answer),add_special_tokens=False)+[tokenizer.eos_token_id]
    if len(p)+len(a)>512:raise ValueError('Preference row exceeds trained context')
    return p+a,[-100]*len(p)+a


def scores(model,rows,pad,device):
    length=max(len(x[0])for x in rows)
    ids=torch.full((len(rows),length),pad,dtype=torch.long,device=device);labels=torch.full_like(ids,-100);mask=torch.zeros_like(ids)
    for i,(x,y)in enumerate(rows):
        ids[i,:len(x)]=torch.tensor(x,device=device);labels[i,:len(y)]=torch.tensor(y,device=device);mask[i,:len(x)]=1
    logits=model(input_ids=ids,attention_mask=mask,use_cache=False).logits[:,:-1].float()
    targets=labels[:,1:];active=targets!=-100
    logps=F.log_softmax(logits,dim=-1).gather(-1,targets.clamp_min(0).unsqueeze(-1)).squeeze(-1)
    return (logps*active).sum(-1),active.sum(-1).clamp_min(1)


def main():
    p=argparse.ArgumentParser();p.add_argument('--initial',type=Path,required=True);p.add_argument('--data',type=Path,required=True)
    p.add_argument('--pairs',type=Path,required=True);p.add_argument('--tasks',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--steps',type=int,default=2000);p.add_argument('--batch',type=int,default=16);p.add_argument('--micro-batch',type=int,default=4)
    p.add_argument('--lr',type=float,default=3e-5);p.add_argument('--beta',type=float,default=.1);p.add_argument('--preference-weight',type=float,default=.5)
    p.add_argument('--eval-every',type=int,default=250);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    if(args.output/'training.json').exists():print('Reusing completed contrastive run');return
    torch.set_num_threads(2);torch.manual_seed(6110613);torch.cuda.set_per_process_memory_fraction(.025)
    rng=random.Random(6110613);device='cuda'
    model=AutoModelForCausalLM.from_pretrained(args.initial,local_files_only=True,trust_remote_code=False).to(device)
    tokenizer=AutoTokenizer.from_pretrained(args.initial,local_files_only=True,trust_remote_code=False)
    pairs=[json.loads(x)for x in args.pairs.read_text().splitlines()]
    data=[json.loads(x)for x in args.data.read_text().splitlines()]
    encoded=[(encode(tokenizer,r['prompt'],r['chosen']),encode(tokenizer,r['prompt'],r['rejected']))for r in pairs]
    sft=[encode(tokenizer,r['prompt'],r['answer'])for r in data]
    optimizer=torch.optim.AdamW(model.parameters(),lr=args.lr,weight_decay=.01)
    attach_qat(model);set_qat(model,True);model.eval();pad=tokenizer.pad_token_id or 0
    references=[];start=time.monotonic()
    with torch.no_grad():
        for offset in range(0,len(encoded),args.micro_batch):
            group=encoded[offset:offset+args.micro_batch]
            with torch.autocast(device_type='cuda',dtype=torch.bfloat16):
                logp,_=scores(model,[r[0]for r in group]+[r[1]for r in group],pad,device)
            n=len(group);references.extend((logp[:n]-logp[n:]).float().cpu().tolist())
    (args.output/'reference.json').write_text(json.dumps({'initial_sha256':hashlib.sha256((args.initial/'model.safetensors').read_bytes()).hexdigest(),
        'pairs_sha256':hashlib.sha256(args.pairs.read_bytes()).hexdigest(),'reference_margins':references})+'\n')
    actual=[i for i,r in enumerate(pairs)if r['kind']=='actual_student_error'];all_indices=list(range(len(pairs)))
    tasks=read_tasks(args.tasks);best_key=None;best_step=0;history=[];losses=[]
    for step in range(1,args.steps+1):
        model.train();optimizer.zero_grad(set_to_none=True);step_loss=0;preference=rng.random()<.6
        accum=args.batch//args.micro_batch
        for _ in range(accum):
            if preference:
                indices=[rng.choice(actual if actual and rng.random()<.6 else all_indices)for _ in range(args.micro_batch)]
                batch=[encoded[i]for i in indices];n=len(batch)
                with torch.autocast(device_type='cuda',dtype=torch.bfloat16):
                    ll,count=scores(model,[r[0]for r in batch]+[r[1]for r in batch],pad,device)
                    margin=ll[:n]-ll[n:]-torch.tensor([references[i]for i in indices],device=device)
                    ce=-(ll[:n]/count[:n]).mean();pref=-F.logsigmoid(args.beta*margin).mean()
                    loss=(ce+args.preference_weight*pref)/accum
            else:
                batch=rng.choices(sft,k=args.micro_batch)
                with torch.autocast(device_type='cuda',dtype=torch.bfloat16):
                    ll,count=scores(model,batch,pad,device);loss=-(ll/count).mean()/accum
            if not bool(torch.isfinite(loss)):raise ValueError('Non-finite preference loss')
            step_loss+=float(loss.detach());loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
        rate=args.lr*min(1,step/100)*(.2+.8*(1+math.cos(math.pi*step/args.steps))/2)
        for group in optimizer.param_groups:group['lr']=rate
        optimizer.step();losses.append(step_loss)
        if step==1 or step%50==0:
            value={'step':step,'steps':args.steps,'loss':sum(losses[-50:])/len(losses[-50:]),'seconds':time.monotonic()-start,'qat':True}
            (args.output/'status.json').write_text(json.dumps(value)+'\n');print(json.dumps(value),flush=True)
        if step%args.eval_every==0 or step==args.steps:
            replica=plain_copy(model);export_q4(replica,args.output/'development.mkq4');load_q4(replica,args.output/'development.mkq4')
            result=evaluate(replica,tokenizer,tasks,plan=False,batch_size=16)
            n=result['by_kind']['natural_language'];ft=result['total']-n['total'];fp=result['passed']-n['passed']
            key=(fp/max(1,ft)>=.95,n['passed']/n['total'],fp/max(1,ft))
            (args.output/f'development-{step}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            history.append({'step':step,'selection_key':key,'natural':n,'formal_passed':fp,'formal_total':ft})
            if best_key is None or key>best_key:best_key=key;best_step=step;checkpoint(model,tokenizer,args.output/'best')
            print(json.dumps({'development_step':step,'selection_key':key,'best_step':best_step}),flush=True);del replica
    checkpoint(model,tokenizer,args.output/'last')
    report={'mode':'Q4-aware DPO plus SFT','steps':args.steps,'best_step':best_step,'selection_key':best_key,'history':history,
       'seconds':time.monotonic()-start,'pairs':len(pairs),'actual_error_pairs':len(actual),'batch':args.batch,'micro_batch':args.micro_batch,
       'beta':args.beta,'preference_weight':args.preference_weight,'initial':str(args.initial),'initial_fresh_audit_opened_for_training':False,
       'source_sha256':hashlib.sha256(args.data.read_bytes()).hexdigest(),'pairs_sha256':hashlib.sha256(args.pairs.read_bytes()).hexdigest()}
    (args.output/'training.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
