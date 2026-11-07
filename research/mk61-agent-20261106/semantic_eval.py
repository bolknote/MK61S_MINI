"""Frozen Q4 semantic panels, conditional long-context checks and tool audit."""
import argparse
import collections
import json
import random
import re

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from semantic_common import ROOT,INITIAL,INITIAL_PACKET,read,sha,write_json,protocol,allowed_ids,compact_head
from codec_eval import language_cases,formal_eval,language_nll,generate_batch,summary
from course_common import program_prompt
from course_eval import grading_tasks
from emulator import Emulator
from harness import agent_run
from lowbit import load
from native_context import wrap
from tasks import BUILD


def development(model,tokenizer):
    p=protocol('hex');result={}
    for level in [1,2,3]:
        for label in ['new','observed']:
            result[label+str(level)]=language_cases(model,tokenizer,read(ROOT/f'validation-{label}{level}.jsonl'),p)
    result['formal']=formal_eval(model,tokenizer,read(ROOT/'formal-development.jsonl'),p)
    return result


def simple_rate(result):
    rows=[result[k]['program']for k in ['new1','observed1']]
    return sum(r['passed']for r in rows)/sum(r['total']for r in rows)


def selection(result,baseline_simple=None):
    program=lambda name:result[name]['program']['rate']
    guard=result['formal']['pass_rate']>=.95 and(baseline_simple is None or simple_rate(result)>=baseline_simple-.03)
    return [guard,(program('new2')+program('new3'))/2,
      (program('observed2')+program('observed3'))/2,(program('new1')+program('observed1'))/2,
      (result['new2']['parse']['rate']+result['new3']['parse']['rate'])/2,result['formal']['pass_rate']]


def audit(model,tokenizer,label,packet):
    p=protocol('hex');tasks=read(ROOT/'audit.jsonl');result={}
    for level in [1,2,3]:result['level'+str(level)]=language_cases(model,tokenizer,[t for t in tasks if t['level']==level],p,audit=True)
    initial={r['id']:r for v in result.values()for r in v['program']['details']}
    # Same tasks in short/long form: report retention conditional on the
    # model solving the short version, separately from mathematical accuracy.
    selected=[]
    for level in [1,2,3]:
        group=[t for t in tasks if t['level']==level]
        random.Random(6116011+level).shuffle(group);selected+=group[:12]
    context={}
    for length in [1024,2048]:
        measured=language_cases(model,tokenizer,selected,p,length,audit=True)
        eligible={t['id']for t in selected if initial[t['id']]['pass']}
        correct=sum(r['pass']for r in measured['program']['details']if r['id']in eligible)
        context[str(length)]={'all_tasks':measured,'solved_short':len(eligible),'retained_long':correct,
          'conditional_retention':correct/len(eligible)if eligible else None,'same_conditions_short_and_long':True}
    em=Emulator();rollouts=[];retries=[]
    for task in grading_tasks(tasks):
        consumed=False
        def generate(prompt):
            nonlocal consumed
            if not consumed:consumed=True;return initial[task['id']]['reply']
            row=generate_batch(model,tokenizer,[prompt],p,max_new=160,hide_public_inputs=True)[0]
            retries.append({'id':task['id'],**row});return row['reply']
        rollouts.append(agent_run(task,generate,em,turns=3,examples=False))
    full_formal=formal_eval(model,tokenizer,read(BUILD/'tasks/test-extended-v2.jsonl'),p)
    report={'label':label,'packed_sha256':sha(packet),'audit_sha256':sha(ROOT/'audit.jsonl'),
      'metrics':result,'summary':{k:{kind:{x:v[kind][x]for x in ['passed','total','rate']}for kind in ['parse','program']}for k,v in result.items()},
      'contexts':context,'formal':full_formal,'public_language':language_nll(model),
      'tool_rollouts':{'passed':sum(x['pass']for x in rollouts),'total':len(rollouts),'details':rollouts,'raw_retries':retries},
      'audit_used_for_checkpoint_selection':False,'hidden_tests_used_for_feedback':False,'automatic_search':False,
      'external_compiler_at_inference':False,'output_rows':len(allowed_ids('hex')),'physical_picocalc_measured':False}
    write_json(ROOT/'results'/(label+'.json'),report)
    print(json.dumps({'audit':label,'summary':report['summary'],'tools':report['tool_rollouts']['passed'],'formal':full_formal['passed']},ensure_ascii=False),flush=True)


def main():
    from native_quant import attach,packed_copy
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=['direct','auxiliary'],required=True);a=ap.parse_args()
    assert(ROOT/'preselected.json').exists(),'Freeze selections before opening audit'
    torch.set_num_threads(2);torch.cuda.set_per_process_memory_fraction(.1)
    paths=[(a.arm+'-best',ROOT/a.arm/'best',None),(a.arm+'-endpoint',ROOT/a.arm/'last',None)]
    if a.arm=='direct':paths.insert(0,('baseline',INITIAL,INITIAL_PACKET))
    for label,path,source_packet in paths:
        if(ROOT/'results'/(label+'.json')).exists():continue
        tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        model=AutoModelForCausalLM.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        packet=ROOT/'results'/(label+'.mkqb');packet.parent.mkdir(exist_ok=True)
        if source_packet:
            import shutil
            shutil.copyfile(source_packet,packet);load(model,packet)
        else:attach(model,'q4');model,_=packed_copy(model,packet,'q4')
        model.to('cuda').eval();compact_head(model,allowed_ids('hex'));audit(model,tokenizer,label,packet);del model


if __name__=='__main__':main()
