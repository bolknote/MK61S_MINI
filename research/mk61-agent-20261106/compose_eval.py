"""Text-only neural composition, standard emulator and explicit long-context probes."""
import argparse
import collections
import json

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from compose_common import ROOT,read,ARMS
from native_eval import language_cases
from native_quant import attach,restore_scales,packed_copy
from evaluate_batched import evaluate,generate_many
from course_eval import grading_tasks
from harness import agent_run
from emulator import Emulator
from tasks import BUILD


def panel(model,tokenizer,*,fresh=False):
    result={};sets={}
    for level in [1,2,3]:
        tasks=read(ROOT/(('fresh'if fresh else'development')+str(level)+'.jsonl'))
        sets['manual'+str(level)]=tasks
    teacher=read(ROOT/('course/test.jsonl'if fresh else'course/validation.jsonl'))
    for level in [2,3]:
        groups=collections.defaultdict(list)
        for t in teacher:
            if t['level']==level:groups[t['expression'][0]].append(t)
        sets['teacher'+str(level)]=[t for pool in groups.values()for t in pool[:7]]
    for name,tasks in sets.items():result[name]=language_cases(model,tokenizer,tasks,audit=fresh)
    formal=evaluate(model,tokenizer,read(ROOT/'course/formal-development.jsonl'),plan=False,max_new=160,batch_size=20)
    result['formal']={**formal,'rate':formal['pass_rate']}
    # Both arithmetic depths contribute to a common fourteen-condition context panel.
    tasks=[]
    for name in ['manual2','manual3']:
        groups=collections.defaultdict(list)
        for row in sets[name]:groups[row['expression'][0]].append(row)
        tasks += [pool[0]for pool in groups.values()][:7]
    for context in [1024,2048]:result['context'+str(context)]=language_cases(model,tokenizer,tasks,context,audit=fresh)
    return result


def summary(result):
    return {name:({kind:{k:value[kind][k]for k in ['passed','total','rate']}for kind in ['parse','program']}
       if name!='formal'else{k:value[k]for k in ['passed','total','rate']})for name,value in result.items()}


def key_for(result):
    required=[result[p][kind]['rate']for p in ['manual1','manual2','manual3','teacher2','teacher3']for kind in ['parse','program']]
    long=[result[p]['program']['rate']for p in ['context1024','context2048']]
    return [result['formal']['rate']>=.95,min(required),sum(required)/len(required),min(long),result['formal']['rate']]


def good(result):
    return bool(key_for(result)[0]and key_for(result)[1]>=.9 and min(result[p]['program']['rate']for p in ['context1024','context2048'])>=.8)


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=ARMS,required=True);p.add_argument('--model',required=True)
    p.add_argument('--label',required=True);a=p.parse_args()
    assert(ROOT/'preselected.json').exists(),'Keep fresh closed until all selections freeze'
    torch.set_num_threads(2);torch.cuda.set_per_process_memory_fraction(.025)
    tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(a.model,local_files_only=True,trust_remote_code=False)
    model.config.max_position_embeddings=2048;tokenizer.model_max_length=2048
    attach(model,'q4');restore_scales(model,a.model)
    packed=ROOT/'results'/(a.label+'.mkqb');packed.parent.mkdir(exist_ok=True)
    replica,packet=packed_copy(model,packed,'q4');replica.to('cuda')
    results=panel(replica,tokenizer,fresh=True)
    # Tool retries see only real public feedback, never hidden-case diagnostics.
    tasks=grading_tasks(read(ROOT/'fresh1.jsonl')+read(ROOT/'fresh2.jsonl')+read(ROOT/'fresh3.jsonl'))
    initial={row['id']:row['reply']for part in ['manual1','manual2','manual3']for row in results[part]['program']['details']}
    rollouts=[];em=Emulator()
    for task in tasks:
        consumed=False
        def generate(prompt):
            nonlocal consumed
            if not consumed:consumed=True;return initial[task['id']]
            return generate_many(replica,tokenizer,[prompt],plan=False,context=2048,max_new=128,hide_public_inputs=True)[0]
        rollouts.append(agent_run(task,generate,em,turns=3,examples=False))
    report={'metrics':results,'summary':summary(results),'packed':packet,'model':a.model,'arm':a.arm,
      'quality_gate_on_fresh':good(results),'key_on_fresh_not_used_for_selection':key_for(results),
      'tool_rollouts':{'passed':sum(r['pass']for r in rollouts),'total':len(rollouts),'details':rollouts,
        'automatic_search':False,'hidden_cases_used_as_feedback':False},
      'host_activations_and_kv':'FP32','native_device_measured':False}
    (ROOT/'results'/(a.label+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['summary']),flush=True)


if __name__=='__main__':main()
