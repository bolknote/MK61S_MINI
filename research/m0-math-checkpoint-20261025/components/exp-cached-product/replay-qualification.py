"""Fresh candidate ARM+MPFR run on a pinned, unchanged public exp corpus.

Resident/control/Qfplib counts are inherited, not counted as fresh executions.
The four-machine54-input smoke independently rechecks the original16 and IEEE.
"""
from pathlib import Path
from collections import Counter
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
T=ROOT/'.build/m0-exp-tight-firstpass-20261024'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=json.loads((W/'build.json').read_text());old=json.loads((T/'qualification.json').read_text())
assert sha(W/'candidate/native_eabi_m0.cpp')==b['source_sha256']==old['source_sha256']
assert sha(W/'candidate.elf')==b['candidate_ELF_sha256']
assert sha(T/'candidate.elf')==old['candidate_ELF_sha256']
assert old['unique_inputs']==48763 and old['public_state_cases']==97526
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
ELF=P/'firmware/mk61s-picocalc-pico-h.elf'
REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
assert sha(ELF)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
assert sha(REF)=='b66da3a6805ecd110580e6dd281e17c37bc4399bee0ba1fae86f8c8cf78bfc26'
assert sha(ROM)=='ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
m=Machine(ELF,True,bootrom=ROM);image=ElfImage(W/'candidate.elf');image.load(m.uc)
m.elf.symbols['candidate_exp']=image.symbols['mk61_m0_exp']
# Wrapper remains at its original Flash address and points to the shorter
# product loaded at the original RAM address; no code-placement speed trick.
cert=json.loads((W/'certificate.json').read_text())
assert hashlib.sha256(bytes(m.uc.mem_read(0x20038ee4,cert['runtime_product_bytes']))).hexdigest()==cert['runtime_product_sha256']
assert hashlib.sha256(bytes(m.uc.mem_read(int(cert['Flash_wrapper_address'],16),16))).hexdigest()==cert['Flash_wrapper_sha256']
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle();expected_by_input={};rows=[];delta_counts=Counter();regressions=Counter()
for previous in old['rows']:
    if len(rows)%4096==0:print('progress',len(rows),'/',len(old['rows']),flush=True)
    raw=int(previous['x'],16)
    if raw not in expected_by_input:expected_by_input[raw]=oracle.reference('exp',raw)
    expected=expected_by_input[raw]
    assert equal(int(previous['expected'],16),expected,64)
    state=states[previous['SIO']];m.uc.mem_write(0xd0000060,state)
    got,_,cost=m.call('candidate_exp',raw,count=True)
    assert equal(got,expected,64),(previous['x'],previous['SIO'],hex(got),hex(expected))
    assert got==int(previous['outputs']['candidate'],16),(previous['x'],'changed returned bits')
    after=bytes(m.uc.mem_read(0xd0000060,28))
    if previous['SIO']=='DIRTY':assert after==state
    else:assert not(struct.unpack('<7I',after)[6]&2)
    delta=cost-previous['instructions']['candidate']
    assert delta in (0,-7),(previous['x'],previous['SIO'],delta)
    delta_counts[delta]+=1
    row=dict(previous)
    row['outputs']=dict(previous['outputs'],tight_trial=previous['outputs']['candidate'],candidate=f'{got:016X}')
    row['instructions']=dict(previous['instructions'],tight_trial=previous['instructions']['candidate'],candidate=cost)
    row['correct']=dict(previous['correct'],candidate=True)
    rows.append(row)
    regressions[cost-previous['instructions']['control']]+=1
loss=lambda r,n:r['correct']['Qfplib'] and r['instructions'][n]>r['instructions']['Qfplib']
assert len(expected_by_input)==old['unique_inputs']
remaining=[r for r in rows if loss(r,'candidate')]
new=[r for r in remaining if not loss(r,'control')]
new_vs_tight=[r for r in remaining if not loss(r,'tight_trial')]
historical=[r for r in rows if r['group']=='historical16']
report=dict(status='AUTHOR_CANDIDATE_EXP_CACHED_RAM_PRODUCT_ALL_PROFILED',
 source_sha256=b['source_sha256'],product_source_sha256=b['product_source_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],
 unique_inputs=len(expected_by_input),public_state_cases=len(rows),actual_fresh_public_ARM_calls=len(rows),
 actual_fresh_MPFR_reference_calls=len(expected_by_input),MPFR_version=oracle.version,
 inherited_resident_control_Qfplib_count_rows=len(rows),inherited_baseline_ARM_calls_added=0,
 pinned_tight_trial_qualification_sha256=sha(T/'qualification.json'),
 resident_ELF_sha256=sha(ELF),Qfplib_ELF_sha256=sha(REF),bootrom_file_sha256=sha(ROM),
 candidate_wrong=0,candidate_returned_bits_identical_tight_trial=True,
 tight_trial_instruction_delta_counts=dict(delta_counts),
 correct_Qfplib_resident_raw_losses=len({r['x'] for r in rows if loss(r,'control')}),
 correct_Qfplib_tight_trial_raw_losses=len({r['x'] for r in rows if loss(r,'tight_trial')}),
 correct_Qfplib_candidate_raw_losses=len({r['x'] for r in remaining}),
 new_correct_Qfplib_raw_losses_vs_resident=len({r['x'] for r in new}),
 new_correct_Qfplib_raw_losses_vs_tight_trial=len({r['x'] for r in new_vs_tight}),
 original16_fixed=16-len({r['x'] for r in historical if loss(r,'candidate')}),
 original16_remaining=len({r['x'] for r in historical if loss(r,'candidate')}),
 candidate_stack_bytes=SP-m.stack_lowest,control_stack_bytes_inherited=old['control_stack_bytes'],
 regressions_vs_control_instruction_histogram=dict(sorted((k,v) for k,v in regressions.items() if k>0)),
 vs_control=dict(faster=sum(v for k,v in regressions.items() if k<0),equal=regressions[0],slower=sum(v for k,v in regressions.items() if k>0)),
 RAM_product_address_and_Flash_wrapper_unchanged=True,
 PCS_SP_bounded_writes_SIO_every_call=True,all_cases_profiled=True,hardware_accessed=False,
 whole_math_GO=False,production_GO=False,rows=rows,remaining_slower_correct_Qfplib=remaining,
 new_slower_correct_Qfplib_vs_resident=new)
(W/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('rows','remaining_slower_correct_Qfplib','new_slower_correct_Qfplib_vs_resident')},indent=2))
for r in historical:
 if r['SIO']=='READY':print(r['x'],r['instructions'],flush=True)
