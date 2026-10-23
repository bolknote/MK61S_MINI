"""Measure the already-qualified target cases, retaining every reference failure."""
from pathlib import Path
from collections import defaultdict
import hashlib,json,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
from oracles import equal
ELF=P/'firmware/mk61s-picocalc-pico-h.elf'
REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
input_report=W/'edges.json';corpus=json.loads(input_report.read_text())
assert corpus['input_ELF_sha256']==sha(ELF)
assert corpus['candidate_ELF_sha256']==sha(W/'candidate.elf')
assert corpus['ROM_sha256']==sha(ROM)
m=Machine(ELF,True,stack_bytes=4096,bootrom=ROM)
ref=Machine(REF,True,stack_bytes=4096)
m.uc.mem_write(0x10180000,(W/'candidate.bin').read_bytes())
c=ElfImage(W/'candidate.elf')
for name in ('candidate_dadd','candidate_dsub'):m.elf.symbols[name]=c.symbols[name]
state=struct.pack('<7I',17,3,17,3,5,2,3)
records=[];groups=defaultdict(list);start=time.monotonic()
for old in corpus['rows']:
    op=old['operation'];a=int(old['x'],16);b=int(old['y'],16);expected=int(old['expected'],16)
    counts={};correct={}
    for label,name,machine in (('candidate','candidate_'+op,m),('baseline','__aeabi_'+op,m),('Qfplib','qfp_'+op,ref)):
        machine.uc.mem_write(0xd0000060,state)
        got,_,counts[label]=machine.call(name,a,b,count=True)
        correct[label]=equal(got,expected,64)
        assert bytes(machine.uc.mem_read(0xd0000060,28))==state
        if label!='Qfplib':assert correct[label],(label,op,old['x'],old['y'],hex(got),old['expected'])
    row=dict(operation=op,x=old['x'],y=old['y'],group=old['group'],instructions=counts,correct=correct)
    records.append(row);groups[(op,old['group'])].append(row)
summary=[]
for (op,group),rows in sorted(groups.items()):
    both=[r for r in rows if r['correct']['Qfplib']]
    summary.append(dict(operation=op,group=group,cases=len(rows),both_correct_cases=len(both),
        candidate_vs_baseline_faster=sum(r['instructions']['candidate']<r['instructions']['baseline'] for r in rows),
        candidate_vs_baseline_equal=sum(r['instructions']['candidate']==r['instructions']['baseline'] for r in rows),
        candidate_vs_baseline_slower=sum(r['instructions']['candidate']>r['instructions']['baseline'] for r in rows),
        baseline_vs_Qfplib_slower_both_correct=sum(r['instructions']['baseline']>r['instructions']['Qfplib'] for r in both),
        candidate_vs_Qfplib_slower_both_correct=sum(r['instructions']['candidate']>r['instructions']['Qfplib'] for r in both),
        means={label:sum(r['instructions'][label] for r in rows)/len(rows) for label in ('candidate','baseline','Qfplib')},
        minimum_baseline_minus_candidate=min(r['instructions']['baseline']-r['instructions']['candidate'] for r in rows)))
report=dict(status='PASS_TARGETED_INSTRUCTION_PROFILE_NOT_ALL_INPUT_PROOF',cases=len(records),ARM_calls=3*len(records),
            groups=summary,rows=records,elapsed_seconds=time.monotonic()-start,
            source_corpus_sha256=sha(input_report),candidate_ELF_sha256=sha(W/'candidate.elf'),
            instruction_counts_are_not_cycles=True,hardware_accessed=False,goal_complete=False)
(W/'profile.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
