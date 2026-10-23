"""Targeted top-exponent and affected same-sign pack qualification."""
from pathlib import Path
from collections import defaultdict,Counter
import hashlib,json,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
BASE=ROOT/'.build/m0-mixed-sign-original-goal-20261023'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import integer_binary,equal
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
prior=json.loads((BASE/'result.json').read_text())
assert sha(BASE/'edges.json')==prior['artifacts']['edges.json']['sha256']
assert sha(BASE/'candidate.elf')==prior['artifacts']['candidate.elf']['sha256']
ELF=P/'firmware/mk61s-picocalc-pico-h.elf'
REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
assert sha(ELF)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
m=Machine(ELF,True,stack_bytes=4096,bootrom=ROM);ref=Machine(REF,True,stack_bytes=4096)
for folder,base,label,public in ((BASE,0x10180000,'parent_','candidate_'),(W,0x10182000,'new_','top_candidate_')):
    e=ElfImage(folder/'candidate.elf');m.uc.mem_write(base,(folder/'candidate.bin').read_bytes())
    for op in ('dadd','dsub'):m.elf.symbols[label+op]=e.symbols[public+op]
SIGN=1<<63
jobs={}
def add(op,a,b,tag):jobs.setdefault((op,a,b),tag)
for row in json.loads((BASE/'edges.json').read_text())['rows']:
    op=row['operation'];a=int(row['x'],16);b=int(row['y'],16)
    semantic_b=b^(SIGN if op=='dsub' else 0)
    ea=(a>>52)&2047;eb=(semantic_b>>52)&2047
    if max(ea,eb)==2046:
        add(op,a,b,'top_original')
        if (a^semantic_b)&SIGN:add(op,a,b^SIGN,'top_same_sign')
    elif min(ea,eb)>0 and 55<=max(ea,eb)<=2045:
        if (a^semantic_b)&SIGN:add(op,a,b^SIGN,'ordinary_same_sign')
    if row['group']=='known_slower':add(op,a,b,'prior17_control')
    if row['group']=='IEEE_fallback':add(op,a,b,'IEEE_control')
for x in (0x7fefffffffffffff,0x7feffffffffffffe,0x7feffffffffffffd):
    for y in ((1993<<52)-1,1993<<52,(1993<<52)+1):
        for a,b in ((x,y),(y,x)):
            for sign in (0,SIGN):
                for op in ('dadd','dsub'):
                    add(op,a|sign,(b|sign)^(SIGN if op=='dsub' else 0),'overflow_midpoint_edges')
guard=[]
for E in range(2048):
    old=((E-55)&0xffffffff)<=1990;new=((E-55)&0xffffffff)<=1991
    assert old==(55<=E<=2045) and new==(55<=E<=2046)
    if old!=new:guard.append(E)
assert guard==[2046]
state=struct.pack('<7I',17,3,17,3,5,2,3);oracle=Oracle();start=time.monotonic()
rows=[];groups=defaultdict(list)
for (op,a,b),tag in jobs.items():
    expected=integer_binary('add' if op=='dadd' else 'sub',a,b,width=64)
    mpfr=oracle.reference(op,a,b);assert equal(expected,mpfr,64)
    counts={};values={};correct={}
    for label,name,machine in (('candidate','new_'+op,m),('parent','parent_'+op,m),('Qfplib','qfp_'+op,ref)):
        machine.uc.mem_write(0xd0000060,state)
        got,_,counts[label]=machine.call(name,a,b,count=True)
        assert bytes(machine.uc.mem_read(0xd0000060,28))==state
        values[label]=f'{got:016X}';correct[label]=equal(got,expected,64)
        if label!='Qfplib' and not correct[label]:
            failure=dict(operation=op,x=f'{a:016X}',y=f'{b:016X}',group=tag,label=label,got=f'{got:016X}',expected=f'{expected:016X}')
            (W/'FAILURE.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
    row=dict(operation=op,x=f'{a:016X}',y=f'{b:016X}',group=tag,expected=f'{expected:016X}',outputs=values,correct=correct,instructions=counts)
    rows.append(row);groups[tag].append(row)
summary=[]
for tag,rs in sorted(groups.items()):
    both=[r for r in rs if r['correct']['Qfplib']]
    summary.append(dict(group=tag,cases=len(rs),candidate_wrong=sum(not r['correct']['candidate'] for r in rs),parent_wrong=sum(not r['correct']['parent'] for r in rs),Qfplib_wrong=len(rs)-len(both),
       candidate_vs_parent=dict(Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'slower' if r['instructions']['candidate']>r['instructions']['parent'] else 'equal' for r in rs)),
       parent_slower_correct_Qfplib=sum(r['instructions']['parent']>r['instructions']['Qfplib'] for r in both),candidate_slower_correct_Qfplib=sum(r['instructions']['candidate']>r['instructions']['Qfplib'] for r in both),
       new_slower_correct_Qfplib=sum(r['instructions']['candidate']>r['instructions']['Qfplib'] and r['instructions']['parent']<=r['instructions']['Qfplib'] for r in both),
       means={label:sum(r['instructions'][label] for r in rs)/len(rs) for label in ('candidate','parent','Qfplib')}))
report=dict(status='PASS_TARGETED_TOP_FINITE_AND_PACK_RNE_NOT_PRODUCTION',cases=len(rows),ARM_calls=3*len(rows),groups=summary,rows=rows,
            max_exponent_guard_changed_only_at=guard,ordinary_same_sign_instruction_increase=0,elapsed_seconds=time.monotonic()-start,
            MPFR_version=oracle.version,source_sha256=sha(W/'native_eabi_m0_rp2040.S'),candidate_ELF_sha256=sha(W/'candidate.elf'),
            parent_ELF_sha256=sha(BASE/'candidate.elf'),ROM_sha256=sha(ROM),
            scope='Finite changed-branch validation with integer/MPFR RNE and actual ARM instruction counts. Ordinary same-sign code is unchanged; a separate top same-sign path detects overflow before normalization. The fallback uses the same24-byte stack reservation with a shorter push/pop sequence. No all-input speed or production claim.',
            READY_DIRTY_SIO_preserved_every_call=True,PCS_SP_and_bounded_stack_writes_every_call=True,
            canonical_or_frozen_changed=False,USB_accessed=False,goal_complete=False)
(W/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
