"""Independent semantic parsing and model-written bytecode, no search or compiler."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import random

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from course_common import calc_prompt,canonical,parse_prefix
from evaluate import read_tasks
from evaluate_batched import generate_many,evaluate
from lowbit import export,load
from quantization import export_q4,load_q4
from harness import close_number
from tasks import registers_used,value_of


def grading_tasks(tasks):
    rows=[]
    for t in tasks:
        rng=random.Random(hashlib.sha256(('course-unused-registers:'+t['id']).encode()).hexdigest())
        fields={}
        for field in ['public_tests','hidden_tests']:
            cases=[]
            for c in t[field]:
                registers={f'R{i}':rng.choice([2,5,11,17,23])for i in range(4)}
                registers.update(c['registers'])
                cases.append({**c,'registers':registers,'expected_registers':registers})
            fields[field]=cases
        rows.append({**t,**fields})
    return rows


def parsing(model,tokenizer,tasks,batch_size=24):
    rows=[];model.eval()
    for offset in range(0,len(tasks),batch_size):
        group=tasks[offset:offset+batch_size]
        replies=generate_many(model,tokenizer,[calc_prompt(t['task'])for t in group],plan=False,max_new=64)
        for task,reply in zip(group,replies):
            match=re.search(r'<calc>(.*?)</calc>',reply,re.S)
            try:
                expression=parse_prefix(match.group(1))if match else None
                exact=expression is not None and canonical(expression)==canonical(task['expression'])
                # Algebraically equivalent forms, e.g. square(R1) and R1*R1,
                # are accepted. This evaluator never supplies code to the model.
                passed=expression is not None and registers_used(expression)<=registers_used(task['expression'])and all(
                    close_number(str(value_of(expression,c['registers'])),c['expected_X'])
                    for c in task['public_tests']+task['hidden_tests'])
            except (ValueError,TypeError,AttributeError,ArithmeticError):expression=None;passed=False;exact=False
            rows.append({'id':task['id'],'pass':passed,'exact_ast':exact,'reply':reply,'parsed':expression,'expected':task['expression']})
    passed=sum(r['pass']for r in rows)
    return {'passed':passed,'total':len(rows),'pass_rate':passed/max(1,len(rows)),'details':rows}


def assess(model,tokenizer,partitions,formal=None):
    result={};model.eval()
    for name,tasks in partitions.items():
        tasks=grading_tasks(tasks)
        result[name]={'parse':parsing(model,tokenizer,tasks),
          'program':evaluate(model,tokenizer,tasks,turns=1,plan=False,max_new=128,batch_size=24,
                             examples=False,hide_public_inputs=True)}
    if formal:
        result['formal']=evaluate(model,tokenizer,formal,plan=False,max_new=128,batch_size=20)
    return result


def selection(result):
    scores=[result[p][kind]['pass_rate']for p in ['manual','teacher']for kind in ['parse','program']]
    formal=result.get('formal',{}).get('pass_rate',0)
    return [formal>=.95,min(scores),sum(scores)/len(scores),formal]


def gate(result):
    key=selection(result)
    return bool(key[0]and key[1]>=.9)


def short(result):
    return {p:({k:{x:r[x]for x in ['passed','total','pass_rate']}for k,r in v.items()}if p!='formal'
               else{k:v[k]for k in ['passed','total','pass_rate']})for p,v in result.items()}


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--level',type=int,default=1);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--format',choices=['fp32','q4','q3','q2','mixed'],default='q4')
    p.add_argument('--split',choices=['validation','fresh'],default='validation');p.add_argument('--device',default='cuda')
    a=p.parse_args();torch.set_num_threads(2)
    if a.device=='cuda':torch.cuda.set_per_process_memory_fraction(.025)
    tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(a.model,local_files_only=True,trust_remote_code=False).eval()
    a.output.parent.mkdir(parents=True,exist_ok=True);packed=None
    if a.format=='q4':
        path=a.output.with_suffix('.mkq4');packed=export_q4(model,path);load_q4(model,path)
    elif a.format!='fp32':
        path=a.output.with_suffix('.mkqb');packed=export(model,path,a.format);load(model,path)
    model.to(a.device);course=a.root/f'course-level{a.level}'
    if a.split=='validation':
        paths={'manual':a.root/f'level{a.level}-validation-manual.jsonl','teacher':course/'validation.jsonl'}
    else:
        if not(a.root/'preselected.json').exists():raise ValueError('Freeze selection before fresh scoring')
        paths={'manual':a.root/f'level{a.level}-fresh.jsonl','teacher':course/'test.jsonl'}
    result=assess(model,tokenizer,{k:read_tasks(v)for k,v in paths.items()},read_tasks(course/'formal-validation.jsonl'))
    report={'metrics':result,'summary':short(result),'gate':gate(result),'key':selection(result),
      'model':str(a.model),'format':a.format,'packed':packed,'split':a.split,'level':a.level,
      'sources':{k:hashlib.sha256(v.read_bytes()).hexdigest()for k,v in paths.items()},
      'model_writes_bytecode_without_external_compiler':True,'automatic_repair':False,
      'host_activations_and_kv':'FP32','native_device_runtime_measured':False}
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items()if k!='metrics'},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
