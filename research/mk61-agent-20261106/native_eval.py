"""Actual packed-model parsing, first-turn bytecode, long context and regression."""
import argparse
import collections
import fcntl
import json
from pathlib import Path
import re

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from course_common import calc_prompt,program_prompt,parse_prefix
from course_eval import grading_tasks
from emulator import Emulator
from evaluate_batched import generate_many,evaluate
from harness import check_program,extract_code,close_number,agent_run
from native_context import wrap
from native_quant import attach,restore_scales,packed_copy
from tasks import BUILD,registers_used,value_of


def read(path):return [json.loads(x)for x in path.read_text().splitlines()]


def language_cases(model,tokenizer,tasks,context=512,*,audit=False):
    tasks=grading_tasks(tasks);em=Emulator();parse_rows=[];program_rows=[]
    texts=[wrap(t['task'],tokenizer,context,6111901+i,audit=audit)for i,t in enumerate(tasks)]
    model.eval()
    for start in range(0,len(tasks),8):
        group=tasks[start:start+8];text_group=texts[start:start+8]
        prompts=[calc_prompt(x)for x in text_group]
        assert all(len(tokenizer.encode(x,add_special_tokens=False))+64<=2048 for x in prompts)
        parsed=generate_many(model,tokenizer,prompts,plan=False,context=2048,max_new=64)
        prompts=[program_prompt({**t,'task':x})for t,x in zip(group,text_group)]
        assert all(len(tokenizer.encode(x,add_special_tokens=False))+128<=2048 for x in prompts)
        programs=generate_many(model,tokenizer,prompts,plan=False,context=2048,max_new=128)
        for task,preply,reply,prompt in zip(group,parsed,programs,prompts):
            match=re.search(r'<calc>(.*?)</calc>',preply,re.S)
            try:
                expr=parse_prefix(match.group(1))if match else None
                correct=expr is not None and registers_used(expr)<=registers_used(task['expression'])and all(
                    close_number(str(value_of(expr,c['registers'])),c['expected_X'])for c in task['public_tests']+task['hidden_tests'])
            except (ValueError,TypeError,ArithmeticError,AttributeError):expr=None;correct=False
            parse_rows.append({'id':task['id'],'pass':correct,'reply':preply,'parsed':expr})
            code=extract_code(reply)
            result=check_program(em,code,task['public_tests']+task['hidden_tests'])if code and'<run/>'in reply else{'pass':False}
            program_rows.append({'id':task['id'],'pass':result['pass'],'prompt':prompt,'reply':reply,'code':code,'result':result})
    def summary(rows):return {'passed':sum(x['pass']for x in rows),'total':len(rows),'rate':sum(x['pass']for x in rows)/max(1,len(rows)),'details':rows}
    return {'parse':summary(parse_rows),'program':summary(program_rows),'context_window':context}


def panel(model,tokenizer,root,*,fresh=False,long_context=True,include_compound=False):
    manual=read(root/('fresh-level1.jsonl'if fresh else'development-manual.jsonl'))
    teacher=read(root/('course/test.jsonl'if fresh else'course/teacher-development.jsonl'))
    if fresh:
        byop=collections.defaultdict(list)
        for task in teacher:byop[task['expression'][0]].append(task)
        teacher=[x for values in byop.values()for x in values[:20]]
    result={'manual':language_cases(model,tokenizer,manual,audit=fresh),
            'teacher':language_cases(model,tokenizer,teacher,audit=fresh)}
    formal=evaluate(model,tokenizer,read(root/'course/formal-development.jsonl'),plan=False,max_new=160,batch_size=20)
    result['formal']={**formal,'rate':formal['pass_rate']}
    if include_compound or fresh:
        result['composed']=language_cases(model,tokenizer,read(root/('fresh-level2.jsonl'if fresh else'development-level2.jsonl')),audit=fresh)
    if long_context:
        byop=collections.defaultdict(list)
        for task in manual:byop[task['expression'][0]].append(task)
        chosen=[x for values in byop.values()for x in values[:2]]
        for context in [1024,2048]:result['context'+str(context)]=language_cases(model,tokenizer,chosen,context,audit=fresh)
    return result


def summary(result):
    return {k:({x:{z:v[x][z]for z in ['passed','total','rate']}for x in ['parse','program']}if k!='formal'
               else{z:v[z]for z in ['passed','total','rate']})for k,v in result.items()}


def key_for(result):
    rates=[result[p][kind]['rate']for p in ['manual','teacher',*(['composed']if'composed'in result else[])]for kind in ['parse','program']]
    long=[result[p]['program']['rate']for p in ['context1024','context2048']if p in result]
    all_rates=rates+long
    return [result['formal']['rate']>=.95,min(all_rates),sum(all_rates)/len(all_rates),min(long)if long else 0.,result['formal']['rate']]


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['q4','mixed'],required=True);p.add_argument('--split',choices=['development','fresh'],required=True)
    a=p.parse_args();root=BUILD/'native-mixed-v1';torch.set_num_threads(2);torch.cuda.set_per_process_memory_fraction(.025)
    if a.split=='fresh'and not(root/'preselected.json').exists():raise ValueError('Freeze selection first')
    if a.split=='fresh':
        lock=(root/'selection.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX)
        if not(root/'winner-before-fresh.json').exists():
            choices=json.loads((root/'preselected.json').read_text())['choices']
            chosen=max(choices,key=lambda arm:(choices[arm]['key'],arm=='mixed'))
            (root/'winner-before-fresh.json').write_text(json.dumps({'arm':chosen,'rule':'Max frozen validation key; exact ties prefer smaller mixed payload',
                'choices':choices,'fresh_opened_for_selection':False},indent=2)+'\n')
        fcntl.flock(lock,fcntl.LOCK_UN)
    source=root/(a.arm+'-sft/best');tokenizer=AutoTokenizer.from_pretrained(source,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False);attach(model,a.arm);restore_scales(model,source)
    replica,packed=packed_copy(model,root/(a.arm+'-final.mkqb'),a.arm)
    result=panel(replica.to('cuda'),tokenizer,root,fresh=a.split=='fresh')
    # Reuse first replies, then let only the neural model react to public tool
    # feedback. Hidden failures never guide retries; no automatic search.
    cases=grading_tasks(read(root/('fresh-level1.jsonl'if a.split=='fresh'else'development-manual.jsonl')))
    first={r['id']:r['reply']for r in result['manual']['program']['details']};rollouts=[];em=Emulator()
    for task in cases:
        consumed=False
        def generate(prompt):
            nonlocal consumed
            if not consumed:consumed=True;return first[task['id']]
            return generate_many(replica,tokenizer,[prompt],plan=False,context=2048,max_new=128,hide_public_inputs=True)[0]
        rollouts.append(agent_run(task,generate,em,turns=3,examples=False))
    tools={'passed':sum(x['pass']for x in rollouts),'total':len(rollouts),'details':rollouts,
      'automatic_search':False,'hidden_tests_used_for_feedback':False,'turns':3}
    full=evaluate(replica,tokenizer,read(BUILD/'tasks/test-extended-v2.jsonl'),plan=False,max_new=160,batch_size=24)
    report={'summary':summary(result),'metrics':result,'packed':packed,'full_formal':full,'tool_rollouts':tools,'model':str(source),
      'target_format_used_throughout_training':True,'host_activations_and_kv':'FP32','native_device_measured':False}
    (root/(a.arm+'-'+a.split+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report['summary']),flush=True)


if __name__=='__main__':main()
