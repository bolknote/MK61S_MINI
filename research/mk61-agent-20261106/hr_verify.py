"""Use the same native verification for the two corrected ASM students."""
import json
import torch
from transformers import AutoTokenizer
import ha_verify as base
from ha_runtime import Session
from ha_protocol import assemble
from full_isa_vm import FullVM,check_task
from hr_common import read,write


def probes(report):
    selected=[]
    for opcode in [0x1C,0xA4,0x53]:
        selected.append(next(r for r in report['isa']['details']if r.get('opcode')==opcode and r['angle']=='RAD'))
    for group in ['literal_copy','literal_function','composition','stack_source']:
        selected.append(next(r for r in report['language']['details']if r['group']==group))
    selected.append(next(r for r in report['observed_user_reproductions']['details']if r['id']=='user-repro:sin:DEG:22'))
    for kind in ['trace','patch','run','done']:
        found=next((h for t in report['tools']['details']for h in t['history']if h.get('kind')==kind and 'prompt'in h),None)
        if found:selected.append({'id':'tool:'+kind,**found})
    return selected


def agent_probes(root,models):
    tasks=read(root/'fresh.jsonl');groups={}
    for task in tasks:groups.setdefault(task['group'],[]).append(task)
    chosen=[t for values in groups.values()for t in values[:2]];result={};vm=FullVM()
    for strategy in ['slow','fast']:
        label=strategy+'-best';model=models[label];tokenizer=AutoTokenizer.from_pretrained(root/'export'/label/'hf',local_files_only=True,trust_remote_code=False);rows=[]
        for task in chosen:
            session=Session(task,'asm',vm=vm)
            for _ in range(5):
                try:reply=base.generate(model,tokenizer,session.request())['reply']
                except AssertionError:break
                session.apply(reply)
                if session.finished:break
            try:code=assemble(session.body,session.pool,'asm');correct=check_task(vm,code,task)['pass']
            except (ValueError,RuntimeError,ArithmeticError,TypeError):correct=False
            rows.append({'id':task['id'],'program_correct':bool(correct),'pass':bool(correct and session.finished),'finished':session.finished,'history':session.history})
        result[strategy]={'passed':sum(x['pass']for x in rows),'program_correct':sum(x['program_correct']for x in rows),'total':len(rows),
          'details':rows,'cpu_only':True,'used_for_selection':False,'oracle_answers_in_feedback':False}
        write(root/'agent-from-scratch.json',result)
    return result


if __name__=='__main__':
    base.LABELS=['asm-baseline','slow-best','fast-best'];base.probes=probes;base.agent_probes=agent_probes;base.main()
