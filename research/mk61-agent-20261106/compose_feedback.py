"""Collect real failures on TRAINING conditions only for the next common replay."""
import argparse
import json
import random

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from compose_common import ROOT,ARMS,read
from course_common import program_prompt,answer
from emulator import Emulator
from evaluate_batched import generate_many
from harness import extract_code,check_program,feedback,trace_feedback
from native_quant import attach,packed_copy
from tasks import save_jsonl


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=ARMS,required=True);p.add_argument('--phase',type=int,required=True)
    a=p.parse_args();root=ROOT/'feedback';root.mkdir(exist_ok=True)
    if(root/f'{a.arm}-phase{a.phase}.json').exists()and(root/f'{a.arm}-phase{a.phase}.jsonl').exists():
        print('Reusing frozen training-only feedback');return
    source=ROOT/f'{a.arm}-phase{a.phase}/last';torch.set_num_threads(2);torch.cuda.set_per_process_memory_fraction(.025)
    model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False)
    tokenizer=AutoTokenizer.from_pretrained(source,local_files_only=True,trust_remote_code=False);attach(model,'q4')
    replica,packed=packed_copy(model,root/f'{a.arm}-phase{a.phase}.mkqb','q4');replica.to('cuda')
    pool=read(ROOT/'course/train.jsonl');rng=random.Random(6113100+a.phase)
    groups={level:[t for t in pool if t['level']==level and t['source']!='procedural']for level in [1,2,3]}
    tasks=[t for values in groups.values()for t in rng.sample(values,min(256,len(values)))];rng.shuffle(tasks)
    em=Emulator();rows=[];counts={'total':len(tasks),'public_failures':0,'reference_rechecks':0}
    for at in range(0,len(tasks),16):
        group=tasks[at:at+16];replies=generate_many(replica,tokenizer,[program_prompt(t)for t in group],plan=False,context=2048,max_new=128)
        for task,reply in zip(group,replies):
            code=extract_code(reply)
            checked=check_program(em,code,task['public_tests'])if code and'<run/>'in reply else{'pass':False}
            if checked['pass']:continue
            counts['public_failures']+=1
            assert check_program(em,task['reference_code'],task['public_tests']+task['hidden_tests'])['pass']
            counts['reference_rechecks']+=1
            observed=feedback(checked)if code and'details'in checked else'Неверный вызов. Нужны <write>байты HEX</write><run/>.'
            fixed={**task,'initial_code':code}if code else task
            rows.append({'id':task['id'],'prompt':program_prompt(fixed,observation=observed),'answer':answer(task),
                         'kind':'actual_training_failure','source_arm':a.arm,'source_reply':reply,'level':task['level']})
            if code:
                observed=trace_feedback(em,code,task['public_tests'][0])
                rows.append({'id':task['id']+':trace','prompt':program_prompt(fixed,observation=observed),'answer':answer(task),
                         'kind':'actual_training_trace','source_arm':a.arm,'source_reply':reply,'level':task['level']})
    save_jsonl(root/f'{a.arm}-phase{a.phase}.jsonl',rows)
    report={**counts,'rows':len(rows),'packed':packed,'all_inputs_from_training_only':True,
            'hidden_cases_never_shown_as_feedback':True,'manual_or_fresh_prompts_used':False}
    (root/f'{a.arm}-phase{a.phase}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':main()
