"""Replay the frozen atan corpus and new residual-boundary inputs on ARM."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
BASE=ROOT/'.build/m0-atan-residual-geometry-20261024'
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from oracles import equal
from unicorn import UC_HOOK_CODE
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
ELF=P/'firmware/mk61s-picocalc-pico-h.elf';REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
assert sha(ELF)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
assert sha(REF)=='b66da3a6805ecd110580e6dd281e17c37bc4399bee0ba1fae86f8c8cf78bfc26'
assert sha(ROM)=='ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
build=json.loads((W/'candidate-build.json').read_text())
assert sha(W/'candidate.elf')==build['ELF_sha256']
assert sha(W/'native_eabi_m0_atan_fast.inc')==build['source_include_sha256']
assert sha(W/'control.elf')==sha(BASE/'candidate.elf')
assert sha(BASE/'qualification.json')=='3dcdbe6abf7aec1d07029c0cd2f47cf10052aea482f3a2d72c45d57d471189a6'
assert json.loads((W/'certificate.json').read_text())['status']=='PASS_EXACT_FRACTION_DIRECTIONAL_NINTH_ATAN'
historical=json.loads((BASE/'qualification.json').read_text())
previous={(r['x'],r['SIO']):r for r in historical['rows']}
jobs={int(r['x'],16):(r['group'],True) for r in historical['rows'] if r['SIO']=='READY'}
SIGN=1<<63
def add(raw,tag,profile=True):
 if raw not in jobs:jobs[raw]=(tag,profile)
 elif profile:jobs[raw]=(jobs[raw][0],True)
hard=[int(s,16) for s in ('3FE5D1004FC925B6','3FECB99548F4FA32')]
for raw in hard:
 for delta in range(-128,129):
  for sign in (0,SIGN):add((raw+delta)|sign,'residual_hard_neighbors')
for r in json.loads((W/'probe.json').read_text())['rows']:add(int(r['x'],16),'prototype_probe')
def around(value,tag,radius=4):
 raw=bits(float(value))
 for delta in range(-radius,radius+1):
  if raw+delta<0:continue
  for sign in (0,SIGN):add((raw+delta)|sign,tag)
for k in range(1,65):
 center=F(k,64)
 for side in (-1,1):
  h=side*(F(1,256)+F(1,1<<30))
  boundary=(center+h)/(1-center*h)
  if F(1,32)<boundary<1:around(boundary,'residual_h_cap_boundary')
for e in (-6,-5,-4,-3,-2,-1,0):around(2.**e,'residual_exponent_boundary',16)
for k in range(1,65):
 center=F(k,64)
 for cap,tag in [(F(1,250),'directional_small_cap'),(F(1,160),'directional_middle_cap'),(F(1,180),'inverse_half_cap'),(F(1,128),'global_cap')]:
  for side in (-1,1):
   h=side*cap;boundary=(center+h)/(1-center*h)
   if F(1,64)<boundary<1:
    around(boundary,tag)
    inverse=1/boundary
    if 1<inverse<64:around(inverse,tag+'_inverted')
machines={'resident':Machine(ELF,True,bootrom=ROM),'Qfplib':Machine(REF,True)}
for label in ('parent','candidate'):
 m=Machine(ELF,True,bootrom=ROM);image=ElfImage(W/(('control' if label=='parent' else label)+'.elf'))
 for n,s in image.named_sections.items():
  if s[2]&2 and s[5]:assert 0x10185000<=s[3]<s[3]+s[5]<=0x10200000,(n,s)
 image.load(m.uc);m.elf.symbols[label+'_atan']=image.symbols['mk61_m0_atan'];machines[label]=m
path_counts={'repair':0,'CORE':0}
candidate=machines['candidate'];image=ElfImage(W/'candidate.elf')
repair_name=next(n for n in image.symbols if n.startswith('atan_fast_tail_repair'))
def entered(uc,addr,size,key):path_counts[key]+=1
for key,address in [('repair',image.symbols[repair_name]),('CORE',candidate.elf.symbols['mk61_m0_cr_atan'])]:
 candidate.uc.hook_add(UC_HOOK_CODE,entered,key,begin=address&~1,end=address&~1)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
o=Oracle();rows=[];start=time.monotonic();calls=0;retained_count_checks=0
for raw,(tag,profile) in jobs.items():
 expected=o.reference('atan',raw)
 for state_name,state in states.items():
  outputs={};counts={};correct={};sio_after={};path_counts.update(repair=0,CORE=0)
  labels=('parent','candidate','Qfplib','resident') if profile else ('parent','candidate','Qfplib')
  for label in labels:
   machine=machines[label];machine.uc.mem_write(0xd0000060,state)
   name='mk61_m0_atan' if label=='resident' else 'audit_atan' if label=='Qfplib' else label+'_atan'
   got,_,n=machine.call(name,raw,count=profile);calls+=1
   after=bytes(machine.uc.mem_read(0xd0000060,28));sio_after[label]=after.hex()
   if state_name=='DIRTY':assert after==state,(label,hex(raw),state_name,'SIO')
   else:assert not (struct.unpack('<7I',after)[6]&2),(label,hex(raw),'left DIRTY')
   outputs[label]=f'{got:016X}';counts[label]=n if profile else None;correct[label]=equal(got,expected,64)
   if label!='Qfplib':assert correct[label],(label,hex(raw),hex(got),hex(expected),state_name)
  assert outputs['candidate']==outputs['parent'],(hex(raw),'NaN raw policy',outputs)
  old=previous.get((f'{raw:016X}',state_name))
  if old:
   assert outputs['parent']==old['outputs']['candidate']
   if profile and old['profiled']:
    assert counts['parent']==old['instructions']['candidate'],(hex(raw),state_name,'parent count',counts,old['instructions'])
    retained_count_checks+=1
  rows.append(dict(x=f'{raw:016X}',group=tag,SIO=state_name,SIO_after=sio_after,profiled=profile,
                   expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,
                   candidate_repair_entries=path_counts['repair'],candidate_CORE_entries=path_counts['CORE']))
 if len(rows)%4096==0:print('progress',len(rows),'/',2*len(jobs),flush=True)
groups=[]
for state in states:
 rs=[r for r in rows if r['SIO']==state];profiled=[r for r in rs if r['profiled']];both=[r for r in profiled if r['correct']['Qfplib']]
 changes=lambda name:dict(Counter('faster' if r['instructions']['candidate']<r['instructions'][name] else 'equal' if r['instructions']['candidate']==r['instructions'][name] else 'slower' for r in profiled))
 groups.append(dict(SIO=state,cases=len(rs),profiled=len(profiled),candidate_wrong=0,parent_wrong=0,
                    Qfplib_wrong=sum(not r['correct']['Qfplib'] for r in rs),vs_parent=changes('parent'),vs_V164=changes('resident'),
                    parent_slower_correct_Qfplib=sum(r['instructions']['parent']>r['instructions']['Qfplib'] for r in both),
                    candidate_slower_correct_Qfplib=sum(r['instructions']['candidate']>r['instructions']['Qfplib'] for r in both),
                    new_slower_correct_Qfplib=sum(r['instructions']['candidate']>r['instructions']['Qfplib'] and r['instructions']['parent']<=r['instructions']['Qfplib'] for r in both),
                    repair_rows=sum(r['candidate_repair_entries']!=0 for r in rs),CORE_rows=sum(r['candidate_CORE_entries']!=0 for r in rs)))
hard_raw={f'{raw|sign:016X}' for raw in hard for sign in (0,SIGN)}
hard_rows=[r for r in rows if r['x'] in hard_raw]
assert len(hard_rows)==8
assert all(r['correct']['Qfplib'] and r['instructions']['candidate']<r['instructions']['Qfplib'] and r['candidate_repair_entries']==1 and not r['candidate_CORE_entries'] for r in hard_rows)
slower=[r for r in rows if r['profiled'] and r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']]
report=dict(status='PASS_ATAN_DIRECTIONAL_NINTH_ALL_INPUTS_PROFILED_NOT_PRODUCTION',unique_inputs=len(jobs),cases=len(rows),ARM_calls=calls,profiled=sum(r['profiled'] for r in rows),groups=groups,
            hard4=hard_rows,remaining_slower_correct_Qfplib=slower,rows=rows,MPFR_version=o.version,
            source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),candidate_ELF_sha256=sha(W/'candidate.elf'),
            control_ELF_sha256=sha(W/'control.elf'),resident_ELF_sha256=sha(ELF),parent_corpus_sha256=sha(BASE/'qualification.json'),
            retained_parent_instruction_counts_checked=retained_count_checks,
            candidate_uses_pinned_resident_helpers_and_ROM=True,candidate_observed_stack_bytes=SP-candidate.stack_lowest,
            parent_observed_stack_bytes=SP-machines['parent'].stack_lowest,PCS_SP_bounded_writes_checked_every_call=True,
            DIRTY_SIO_preserved_every_call=True,READY_left_clean_every_call=True,raw_NaN_policy_parent_exact=True,
            instructions_are_not_cycles=True,all_public_inputs_profiled=True,unprofiled_not_used_for_speed_claims=True,independent_review=False,
            elapsed_seconds=time.monotonic()-start,canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False)
(W/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('rows','hard4','remaining_slower_correct_Qfplib')},indent=2),flush=True)
print('REMAINING_CORRECT_QFPLIB_LOSSES',len(slower),flush=True)
