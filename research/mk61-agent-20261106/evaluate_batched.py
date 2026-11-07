"""Batch independent generations while retaining the exact existing tool controller."""
import argparse
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
import hashlib
import json
from pathlib import Path
from queue import Queue, Empty
import threading
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from emulator import Emulator
from evaluate import read_tasks
import harness
from harness import agent_run
from quantization import export_q4, load_q4
from prompt_variants import without_public_examples


def generate_many(model,tokenizer,prompts,*,plan=True,context=512,max_new=160,hide_public_inputs=False):
    ids=[]
    for prompt in prompts:
        if hide_public_inputs:prompt=without_public_examples(prompt)
        if not plan:
            prompt=prompt.replace('<plan>краткий план</plan>','').replace('<plan>взять R0 и R1; сложить</plan>','')
        ids.append(tokenizer.encode(prompt,add_special_tokens=False)[-(context-max_new):])
    length=max(map(len,ids));device=next(model.parameters()).device
    inputs=torch.full((len(ids),length),tokenizer.pad_token_id or 0,dtype=torch.long,device=device)
    mask=torch.zeros_like(inputs)
    for i,row in enumerate(ids):
        inputs[i,-len(row):]=torch.tensor(row,device=device);mask[i,-len(row):]=1
    with torch.inference_mode():
        output=model.generate(input_ids=inputs,attention_mask=mask,max_new_tokens=max_new,do_sample=False,use_cache=True,
                              pad_token_id=tokenizer.pad_token_id or 0,eos_token_id=tokenizer.eos_token_id)
    return [tokenizer.decode(row[length:],skip_special_tokens=True) for row in output]


class LockedEmulator:
    def __init__(self):self.emulator=Emulator();self.lock=threading.Lock()
    def run(self,*args,**kwargs):
        # The production calculator core is global. Keep reset/load/run/read atomic.
        with self.lock:return self.emulator.run(*args,**kwargs)


def evaluate(model,tokenizer,tasks,*,turns=3,plan=True,max_new=160,batch_size=16,examples=True,hide_public_inputs=False):
    em=LockedEmulator();queue=Queue();stop=threading.Event();start=time.monotonic()
    def generate(prompt):
        if stop.is_set():raise RuntimeError('Generation stopped')
        response=Future();queue.put((prompt,response))
        while not stop.is_set():
            try:return response.result(timeout=1)
            except TimeoutError:continue
        raise RuntimeError('Generation stopped')
    with ThreadPoolExecutor(max_workers=batch_size) as pool:
        futures=[pool.submit(agent_run,task,generate,em,turns=turns,examples=examples) for task in tasks]
        try:
            previous=-1
            while not all(f.done() for f in futures):
                for f in futures:
                    if f.done() and f.exception():raise f.exception()
                try:first=queue.get(timeout=.05)
                except Empty:continue
                batch=[first];deadline=time.monotonic()+.012
                while len(batch)<batch_size:
                    try:batch.append(queue.get(timeout=max(.001,deadline-time.monotonic())))
                    except Empty:break
                    if time.monotonic()>deadline:break
                replies=generate_many(model,tokenizer,[x[0] for x in batch],plan=plan,max_new=max_new,hide_public_inputs=hide_public_inputs)
                for (_,future),reply in zip(batch,replies):future.set_result(reply)
                count=sum(f.done() for f in futures)
                if count//32!=previous:
                    previous=count//32
                    print(json.dumps({'evaluated':count,'total':len(tasks),'seconds':time.monotonic()-start}),flush=True)
            rows=[f.result() for f in futures]
        finally:stop.set()
    kinds={}
    for row in rows:
        item=kinds.setdefault(row['kind'],{'total':0,'passed':0});item['total']+=1;item['passed']+=row['pass']
    return {'total':len(rows),'passed':sum(r['pass'] for r in rows),'pass_rate':sum(r['pass'] for r in rows)/max(1,len(rows)),
            'valid_tool_tasks':sum(r['valid_tool_calls']>0 for r in rows),'by_kind':kinds,'seconds':time.monotonic()-start,
            'turn_budget':turns,'max_new_tokens_per_turn':max_new,'generation_batch_size':batch_size,
            'few_shot_example':examples,
            'public_examples_hidden_from_model_prompt':hide_public_inputs,
            'protocol_sha256':hashlib.sha256(Path(harness.__file__).read_bytes()).hexdigest(),
            'method':'Unchanged agent_run and microcode core; batched FP32 host generations; public plus hidden tests',
            'details':rows}


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--tasks',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--device',default='cpu');p.add_argument('--q4',action='store_true')
    p.add_argument('--no-plan',action='store_true');p.add_argument('--limit',type=int);p.add_argument('--batch-size',type=int,default=16)
    p.add_argument('--no-examples',action='store_true')
    p.add_argument('--hide-public-inputs',action='store_true')
    p.add_argument('--turns',type=int,default=3);p.add_argument('--max-new',type=int,default=160)
    args=p.parse_args();torch.set_num_threads(2)
    if args.device=='cuda':torch.cuda.set_per_process_memory_fraction(.025)
    tokenizer=AutoTokenizer.from_pretrained(args.model,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(args.model,local_files_only=True,trust_remote_code=False).to(args.device).eval()
    packed=None
    if args.q4:
        packed=export_q4(model,args.output.with_suffix('.mkq4'));load_q4(model,args.output.with_suffix('.mkq4'))
    tasks=read_tasks(args.tasks)
    if args.limit:tasks=tasks[:args.limit]
    result=evaluate(model,tokenizer,tasks,turns=args.turns,plan=not args.no_plan,max_new=args.max_new,batch_size=args.batch_size,examples=not args.no_examples,hide_public_inputs=args.hide_public_inputs)
    result.update(model=str(args.model),q4=args.q4,packed=packed,tasks_sha256=hashlib.sha256(args.tasks.read_bytes()).hexdigest())
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k!='details'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
