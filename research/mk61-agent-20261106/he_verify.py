"""Exact Q4/native replay with new revision-aware, oracle-free prompts."""
import json
from pathlib import Path
import shutil
import sys

from transformers import AutoTokenizer
import ha_verify as base
from he_common import HERE,read,sha,write
from he_runtime import Session
from he_gate_check import verify as verify_gate
from ha_protocol import assemble
from full_isa_vm import FullVM,check_task


def probes(report):
    selected=[]
    for op in [0x1C,0xA4,0x53,0x50]:
        selected.append(next(r for r in report['isa']['details']if r.get('opcode')==op and r['angle']=='RAD'))
    for group in ['literal_copy','register_source','composition','algorithm_clamp']:
        selected.append(next(r for r in report['language']['details']if r['group']==group))
    selected.append(next(r for r in report['observed_user_reproductions']['details']if r['id']=='user-repro:sin:DEG:22'))
    for kind in ['trace','patch','run','done']:
        found=next((h for panel in ['tools','tools_gated']for t in report[panel]['details']for h in t['history']if h.get('kind')==kind and'prompt'in h),None)
        if found:selected.append({'id':'tool:'+kind,**found})
    return selected


def agent_probes(root,models):
    groups={}
    for task in read(root/'fresh.jsonl'):groups.setdefault(task['group'],[]).append(task)
    chosen=[t for values in groups.values()for t in values[:2]];vm=FullVM();result={}
    for arm in ['safe','active']:
        label=arm+'-best';model=models[label];tokenizer=AutoTokenizer.from_pretrained(root/'export'/label/'hf',local_files_only=True,trust_remote_code=False);rows=[]
        for task in chosen:
            s=Session(task,'asm',vm=vm,gate=False)
            for _ in range(6):
                try:reply=base.generate(model,tokenizer,s.request())['reply']
                except AssertionError:break
                s.apply(reply)
                if s.finished:break
            try:correct=check_task(vm,assemble(s.body,s.pool,'asm'),task)['pass']if s.body else False
            except (ValueError,RuntimeError,ArithmeticError,TypeError):correct=False
            rows.append({'id':task['id'],'program_correct':bool(correct),'finished':s.finished,'pass':bool(correct and s.finished),'history':s.history})
        result[arm]={'passed':sum(x['pass']for x in rows),'program_correct':sum(x['program_correct']for x in rows),'total':len(rows),
                     'details':rows,'cpu_only':True,'used_for_selection':False,'oracle_answers_in_feedback':False,'gate_enabled':False}
        write(root/'agent-from-scratch.json',result)
    return result


def main():
    root=Path(sys.argv[sys.argv.index('--root')+1]).resolve()
    prepared=json.loads((root/'prepared.json').read_text())
    for name,digest in prepared['source_hashes'].items():assert sha(HERE/name)==digest,name
    base.LABELS=['asm-baseline','safe-best','active-best'];base.probes=probes;base.agent_probes=agent_probes;base.main()
    result=verify_gate(root/'native-frontend')
    for label in base.LABELS+['selected-budget']:
        runtime=root/'export'/label/'runtime'
        shutil.copyfile(HERE/'he_gate.hpp',runtime/'he_gate.hpp');write(runtime/'debug-gate-verification.json',result)
    print(json.dumps({'native_done_gate':result}),flush=True)


if __name__=='__main__':main()
