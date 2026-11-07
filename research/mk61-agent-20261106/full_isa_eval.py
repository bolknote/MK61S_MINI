"""Exact Q4, all instructions and state transitions; no expression decoder."""
import argparse
import collections
import json
from pathlib import Path
import random
import re

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from full_isa_common import ROOT,INITIAL,INITIAL_PACKET,HexProtocol,read,sha,write,allowed,compact_head,task_prompt
from full_isa_protocol import decode,hex_code,REGISTERS
from full_isa_vm import FullVM,check_task
from codec_eval import generate_batch,language_nll
from tasks import BUILD
from harness import close_number,extract_code


def generate(model,tokenizer,prompts,*,prime=False,max_new=352):
    replies=generate_batch(model,tokenizer,prompts,HexProtocol(),max_new=max_new)
    for row in replies:
        row['fixed_reply_prefix']='<write>'if prime else''
        row['reply']=row['fixed_reply_prefix']+row['raw_reply']
    return replies


def failed_feedback(task,result):
    for i,case in enumerate(result['details']):
        for j,segment in enumerate(case['segments']):
            if segment['pass']:continue
            expected=task['public_tests'][i]['segments'][j]['expected'];actual=segment['actual']
            initial=task['public_tests'][i]['segments'][j]['inputs']
            names=['X',*[r for r in REGISTERS if actual['raw'][r]!=expected['raw'][r]]]
            changes='; '.join(f'{r}: ожидалось {expected["raw"][r]}, получено {actual["raw"][r]}'for r in names[:3])
            values=', '.join(f'{k}={v}'for k,v in initial.items()if k in names or k in ['X','Y'])
            return f'FAIL: шаг продолжения {j}; {values}; {changes}; IP={actual["pc"]}, ожидался IP={expected["pc"]}; статус {actual["status"]}, ожидался {expected["status"]}'
    return 'FAIL'


def evaluate(model,tokenizer,tasks,*,keep_prompts=True):
    vm=FullVM();rows=[]
    for at in range(0,len(tasks),16):
        batch=tasks[at:at+16];prompts=[task_prompt(t)for t in batch]
        outputs=generate(model,tokenizer,prompts)
        for task,text,row in zip(batch,prompts,outputs):
            try:
                code=decode(row['reply']);result=check_task(vm,code,task);passed=result['pass'];valid=True
                checked=[{'pass':c['pass'],'segments':[s['pass']for s in c['segments']]}for c in result['details']]
            except (ValueError,TypeError,ArithmeticError,RuntimeError)as e:
                code=None;passed=False;valid=False;checked=[]
            item={'id':task['id'],'kind':task['kind'],'group':task['group'],'angle':task['angle'],'opcode':task.get('opcode'),
              'catalog_risk':task.get('catalog_risk'),'pass':bool(passed),'valid_call':valid,'code':code,
              'exact_reference':code==task['reference_code'],'case_checks':checked,**row}
            if keep_prompts:item['prompt']=text
            rows.append(item)
    groups=collections.defaultdict(list);kinds=collections.defaultdict(list);angles=collections.defaultdict(list);opcodes=collections.defaultdict(list)
    for row in rows:
        groups[row['group']].append(row);kinds[row['kind']].append(row);angles[row['angle']].append(row)
        if row.get('opcode')is not None:opcodes[f'{row["opcode"]:02X}'].append(row)
    def stat(values):return {'passed':sum(r['pass']for r in values),'exact':sum(r['exact_reference']for r in values),
      'total':len(values),'rate':sum(r['pass']for r in values)/len(values)}
    documented=[r for r in rows if r['kind']=='primitive'and r['catalog_risk']=='documented']
    result={'passed':sum(r['pass']for r in rows),'total':len(rows),'valid_calls':sum(r['valid_call']for r in rows),
      'by_group':{k:stat(v)for k,v in groups.items()},'by_kind':{k:stat(v)for k,v in kinds.items()},
      'by_angle':{k:stat(v)for k,v in angles.items()},'by_opcode':{k:stat(v)for k,v in opcodes.items()},
      'documented_instructions':stat(documented)if documented else None,'details':rows}
    return result


def old_formal(model,tokenizer):
    tasks=read(BUILD/'tasks/test-extended-v2.jsonl');vm=FullVM();rows=[]
    for at in range(0,len(tasks),16):
        batch=tasks[at:at+16];outputs=generate(model,tokenizer,[task_prompt({**t,'angle':'RAD'})for t in batch])
        for task,row in zip(batch,outputs):
            try:code=decode(row['reply'])
            except ValueError:code=None
            ok=bool(code)
            if code:
                for case in task['public_tests']+task['hidden_tests']:
                    state,_=vm.execute(code,case['registers'],max_commands=256)
                    ok &= state['status']=='stopped'and close_number(state['numeric']['X'],case['expected_X'])
                    ok &= all(close_number(state['numeric'][r],v)for r,v in case.get('expected_registers',{}).items())
            rows.append({'id':task['id'],'pass':bool(ok),'reply':row['reply']})
    return {'passed':sum(r['pass']for r in rows),'total':len(rows),'rate':sum(r['pass']for r in rows)/len(rows),'details':rows}


def development(model,tokenizer):
    result=evaluate(model,tokenizer,read(ROOT/'development.jsonl'));legacy=old_formal(model,tokenizer)
    return {'panel':result,'legacy':legacy}


def selection(result):
    panel=result['panel'];doc=panel['documented_instructions'];kinds=panel['by_kind']
    numeric=kinds['numeric_synthesis']['rate'];control=kinds['programming']['rate'];interactive=kinds['interactive_game']['rate']
    doc_groups=collections.defaultdict(list)
    for r in panel['details']:
        if r['kind']=='primitive'and r['catalog_risk']=='documented':doc_groups[r['group']].append(r['pass'])
    scores=[sum(x)/len(x)for x in doc_groups.values()];macro=sum(scores)/len(scores)
    total=.4*macro+.25*numeric+.15*control+.1*interactive+.1*result['legacy']['rate']
    return [total,min(scores),macro,numeric,control,interactive,doc['exact']/doc['total'],result['legacy']['rate']]


def brief(result):
    return {'key':selection(result),'documented':result['panel']['documented_instructions'],
      'kinds':result['panel']['by_kind'],'groups':result['panel']['by_group'],
      'legacy':{k:result['legacy'][k]for k in ['passed','total','rate']}}


def tools(model,tokenizer,tasks,initial):
    vm=FullVM();rows=[]
    for task in tasks:
        current=None;reply=initial[task['id']]['reply'];history=[];passed=False
        for turn in range(3):
            code=extract_code(reply)
            if code and'<run/>'in reply:
                current=code;public=check_task(vm,code,task,public=True)
                history.append({'turn':turn,'reply':reply,'public_pass':public['pass']})
                if public['pass']:passed=check_task(vm,code,task)['pass'];break
                observation=failed_feedback(task,public)
            elif'<trace/>'in reply and current:
                first=task['public_tests'][0]['segments'][0]
                actual,_=vm.execute(current,first['inputs'],angle=task['angle'])
                observation='TRACE '+ '; '.join(f'{s["pc"]:02}:{s["opcode"]:02X}'for s in actual['trace'][:10])+'; X='+actual['raw']['X']
                history.append({'turn':turn,'reply':reply,'trace':True})
            else:
                observation='FAIL: нужен полный вызов <write>HEX</write><run/>'
                history.append({'turn':turn,'reply':reply,'valid':False})
            request=task_prompt(task,initial_code=current,observation=observation)
            reply=generate(model,tokenizer,[request],prime=False)[0]['reply']
        rows.append({'id':task['id'],'pass':bool(passed),'history':history})
    return {'passed':sum(x['pass']for x in rows),'total':len(rows),'details':rows,'hidden_cases_used_for_feedback':False,'automatic_search':False}


def audit(model,tokenizer,label,packet):
    main=evaluate(model,tokenizer,read(ROOT/'audit.jsonl'));natural=evaluate(model,tokenizer,read(ROOT/'closed-natural.jsonl'))
    user=evaluate(model,tokenizer,read(ROOT/'observed-user-reproductions.jsonl'));legacy=old_formal(model,tokenizer)
    lookup={r['id']:r for r in main['details']}
    chosen=set(json.loads((ROOT/'tool-probe-ids.json').read_text()));tool_tasks=[t for t in read(ROOT/'audit.jsonl')if t['id']in chosen]
    tool=tools(model,tokenizer,tool_tasks,lookup)
    report={'label':label,'packed_sha256':sha(packet),'main':main,'natural':natural,'observed_user_reproductions':user,
      'legacy':legacy,'tools':tool,'language':language_nll(model),'new_audit_used_for_selection':False,
      'all_hex_bytes_allowed':True,'numeric_constants_allowed':True,'fixed_initial_reply_prefix':'',
      'reference_covers_all_256_opcodes':True,'raw_undocumented_separate_from_documented':True,'physical_picocalc_measured':False}
    write(ROOT/'results'/(label+'.json'),report)
    print(json.dumps({'label':label,'documented':main['documented_instructions'],'kinds':main['by_kind'],
      'natural':[natural['passed'],natural['total']],'legacy':[legacy['passed'],legacy['total']],
      'tools':[tool['passed'],tool['total']],'user_repros':[user['passed'],user['total']]}),flush=True)


def main():
    from lowbit import load
    from native_quant import attach,packed_copy
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=['full','protected'],required=True);a=ap.parse_args()
    assert(ROOT/'preselected.json').exists(),'Select models before opening audit'
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.2)
    paths=[(a.arm+'-best',ROOT/a.arm/'best',None),(a.arm+'-endpoint',ROOT/a.arm/'last',None)]
    if a.arm=='full':paths.insert(0,('baseline',INITIAL,INITIAL_PACKET))
    for label,path,source in paths:
        if(ROOT/'results'/(label+'.json')).exists():continue
        tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        model=AutoModelForCausalLM.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        packet=ROOT/'results'/(label+'.mkqb');packet.parent.mkdir(exist_ok=True)
        if source:
            import shutil
            shutil.copyfile(source,packet);load(model,packet)
        else:attach(model,'q4');model,_=packed_copy(model,packet,'q4')
        model.to('cuda').eval();compact_head(model,allowed());audit(model,tokenizer,label,packet);del model


if __name__=='__main__':main()
