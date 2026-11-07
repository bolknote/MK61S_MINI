"""Measure bounded syntax/input coverage on development data, never fresh data."""
import argparse
import json
import re
import struct
import time

import torch
from transformers import AutoConfig,AutoModelForCausalLM,AutoTokenizer

from compose_common import ROOT,read,sha
from compose_constraint import processor
from course_common import program_prompt,parse_prefix
from course_eval import grading_tasks
from emulator import Emulator
from harness import extract_code,check_program,close_number
from lowbit import load
from tasks import value_of


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['champion','small'],required=True)
    p.add_argument('--phase',type=int,default=4);p.add_argument('--snapshot-step',type=int);a=p.parse_args()
    folder=ROOT/f'{a.arm}-phase{a.phase}'
    source=ROOT/'diagnostics'/f'constraint-{a.arm}-phase{a.phase}-step{a.snapshot_step}.mkqb'if a.snapshot_step is not None else folder/'development.mkqb'
    data=source.read_bytes()
    import hashlib
    digest=hashlib.sha256(data).hexdigest()
    records=[json.loads(f.read_text())for f in folder.glob('development-*.json')]
    record=next((x for x in records if x['packet']['sha256']==digest),None)
    if record is None:raise RuntimeError('Wait for current development evaluation to finish')
    name=f'constraint-{a.arm}-phase{a.phase}-step{record["step"]}';out=ROOT/'diagnostics';out.mkdir(exist_ok=True)
    packet=out/(name+'.mkqb');packet.write_bytes(data)
    n=struct.unpack('<I',data[8:12])[0];c=json.loads(data[12:12+n])['config'];kind=c.pop('model_type')
    torch.set_num_threads(2);torch.cuda.set_per_process_memory_fraction(.025)
    model=AutoModelForCausalLM.from_config(AutoConfig.for_model(kind,**c),trust_remote_code=False)
    load(model,packet);model.to('cuda').eval()
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'initial'/a.arm,local_files_only=True,trust_remote_code=False)
    results={};em=Emulator();started=time.monotonic()
    for level in [2,3]:
        tasks=grading_tasks(read(ROOT/f'development{level}.jsonl'));rows=[]
        for at in range(0,len(tasks),4):
            batch=tasks[at:at+4];prompts=[program_prompt(t)for t in batch]
            ids=[tokenizer.encode(x,add_special_tokens=False)for x in prompts];length=max(map(len,ids))
            inputs=torch.full((len(ids),length),tokenizer.pad_token_id or 0,dtype=torch.long,device='cuda');mask=torch.zeros_like(inputs)
            for i,x in enumerate(ids):inputs[i,-len(x):]=torch.tensor(x,device='cuda');mask[i,-len(x):]=1
            # This is the only task-derived information given to the grammar.
            sets=[set(re.findall(r'\bR[0-3]\b',t['task']))for t in batch]
            constraint=processor(tokenizer,sets,length)
            with torch.inference_mode():generated=model.generate(input_ids=inputs,attention_mask=mask,max_new_tokens=128,
              do_sample=False,use_cache=True,pad_token_id=tokenizer.pad_token_id or 0,eos_token_id=tokenizer.eos_token_id,
              logits_processor=[constraint])
            replies=[tokenizer.decode(x[length:],skip_special_tokens=True)for x in generated]
            for task,reply in zip(batch,replies):
                code=extract_code(reply);passed=bool(code and'<run/>'in reply and check_program(em,code,task['public_tests']+task['hidden_tests'])['pass'])
                m=re.search(r'<calc>(.*?)</calc>',reply,re.S)
                try:
                    expr=parse_prefix(m.group(1))if m else None
                    parsed=expr is not None and all(close_number(str(value_of(expr,c['registers'])),c['expected_X'])for c in task['public_tests']+task['hidden_tests'])
                except (ValueError,TypeError,ArithmeticError):parsed=False
                rows.append({'id':task['id'],'reply':reply,'parse_pass':parsed,'program_pass':passed})
        results[f'manual{level}']={'program_passed':sum(x['program_pass']for x in rows),'parse_passed':sum(x['parse_pass']for x in rows),
          'total':len(rows),'plain_program_passed':record['summary'][f'manual{level}']['program']['passed'],'details':rows}
        print(json.dumps({k:v for k,v in results[f'manual{level}'].items()if k!='details'}),flush=True)
    report={'metrics':results,'source_packet_sha256':sha(packet),'arm':a.arm,'phase':a.phase,'step':record['step'],
      'seconds':time.monotonic()-started,'fresh_opened':False,'no_gradient_updates':True,'external_compiler_at_inference':False,
      'reference_expression_used_for_generation':False,'numeric_tests_used_for_generation':False,
      'grammar_input':'Only names R0-R3 mentioned in task text; all assumed relevant; at most three operations',
      'pure_model_accuracy':False,'adopted_for_primary_evaluation':False}
    (out/(name+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
