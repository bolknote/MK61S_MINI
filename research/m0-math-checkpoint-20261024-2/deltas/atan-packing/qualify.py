"""MPFR/actual ARM atan delta checks with all raw reference outcomes kept."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json,random,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from oracles import equal
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
ELF=P/'firmware/mk61s-picocalc-pico-h.elf';REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
assert sha(ELF)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
assert sha(REF)=='b66da3a6805ecd110580e6dd281e17c37bc4399bee0ba1fae86f8c8cf78bfc26'
assert sha(W/'candidate.elf')==json.loads((W/'candidate-build.json').read_text())['ELF_sha256']
assert json.loads((W/'certificate.json').read_text())['status']=='PASS_EXACT_RATIONAL_ATAN_LOCAL_ENCLOSURES'
machines={'parent':Machine(ELF,True,bootrom=ROM),'Qfplib':Machine(REF,True)}
for label in ('control','candidate'):
 machine=Machine(ELF,True,bootrom=ROM);image=ElfImage(W/(label+'.elf'))
 for n,s in image.named_sections.items():
  if s[2]&2 and s[5]:assert 0x10185000<=s[3]<s[3]+s[5]<=0x10200000,(n,s)
 image.load(machine.uc);machine.elf.symbols[label+'_atan']=image.symbols['mk61_m0_atan'];machines[label]=machine
SIGN=1<<63;jobs={}
def add(raw,tag,profile=True):
 if raw not in jobs:jobs[raw]=(tag,profile)
 elif profile:jobs[raw]=(jobs[raw][0],True)
old=[r for r in json.loads((P/'slower-inputs.json').read_text())['rows'] if r['operation']=='atan'];assert len(old)==2
for r in old:add(int(r['x'],16),'old2_slower')
for r in old:
 raw=int(r['x'],16)&(SIGN-1)
 for delta in range(-32,33):
  for s in (0,SIGN):add((raw+delta)|s,'old2_neighbors')
def around(value,tag,radius=3):
 raw=bits(float(value))
 for delta in range(-radius,radius+1):
  if raw+delta<0:continue
  for sign in (0,SIGN):add((raw+delta)|sign,tag)
for k in range(1,65):
 center=F(k,64)
 around(center,'table_centers');around(F(2*k-1,128),'table_selection_midpoints')
 if k<64:around(F(1,1)/center,'reciprocal_centers')
 for side in (-1,1):
  for cap,tag in ((F(3,512),'old_normalized_n_boundary'),(F(49,8192),'normalized_n_boundary'),(F(1,1024),'tiny_n_boundary')):
   n_boundary=center+side*cap
   if F(1,64)<n_boundary<1:around(n_boundary,tag)
  for cap,tag in ((F(47,8192),'narrow_h_boundary'),(F(1,256),'small_h_boundary')):
   h=side*cap;h_boundary=(center+h)/(1-center*h)
   if F(1,64)<h_boundary<1:around(h_boundary,tag)
for e in (-28,-27,-7,-6,-5,-4,-3,-2,-1,0,1,5,6,7,54,55,56):around(2.**e,'dispatch_binade_boundaries',4)
for E in (0,1,995,996,1016,1017,1029,1030,1077,1078,2046,2047):
 for fraction in (0,1,(1<<51),(1<<52)-1):
  for sign in (0,SIGN):add((E<<52)|fraction|sign,'IEEE_and_unchanged_paths')
if '--all' in sys.argv:
 rng=random.Random(0xA7A62410)
 for i in range(8192):
  E=rng.randrange(1017,1030);raw=(E<<52)|rng.getrandbits(52)
  if raw>bits(64.):raw=bits(64.)
  for sign in (0,SIGN):add(raw|sign,'random_reduced',i%32==0)
 for i in range(2048):add(rng.getrandbits(64),'random_raw_fields',i%64==0)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
o=Oracle();rows=[];start=time.monotonic();calls=0
for raw,(tag,profile) in jobs.items():
 expected=o.reference('atan',raw)
 for state_name,state in states.items():
  outputs={};counts={};correct={};sio_after={}
  labels=('parent','candidate','Qfplib','control') if profile else ('parent','candidate','Qfplib')
  for label in labels:
   machine=machines[label];machine.uc.mem_write(0xd0000060,state)
   name='mk61_m0_atan' if label=='parent' else 'audit_atan' if label=='Qfplib' else label+'_atan'
   got,_,n=machine.call(name,raw,count=profile);calls+=1
   after=bytes(machine.uc.mem_read(0xd0000060,28));sio_after[label]=after.hex()
   if state_name=='DIRTY':assert after==state,(label,hex(raw),state_name,'SIO')
   # The unchanged math divider may use an idle READY divider. Its source
   # promises to preserve pending DIRTY work, not stale idle operands.
   else:assert not (struct.unpack('<7I',after)[6]&2),(label,hex(raw),'left DIRTY')
   outputs[label]=f'{got:016X}';counts[label]=n if profile else None;correct[label]=equal(got,expected,64)
   if label!='Qfplib':assert correct[label],(label,hex(raw),hex(got),hex(expected),state_name)
  assert outputs['candidate']==outputs['parent'],(hex(raw),'NaN raw policy',outputs)
  if profile:
   assert outputs['control']==outputs['parent'] and counts['control']==counts['parent'],(hex(raw),'component control',outputs,counts)
  rows.append(dict(x=f'{raw:016X}',group=tag,SIO=state_name,SIO_after=sio_after,profiled=profile,expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct))
 if len(rows)%4096==0:print('progress',len(rows),'/',2*len(jobs),flush=True)
groups=[]
for state in states:
 rs=[r for r in rows if r['SIO']==state];profiled=[r for r in rs if r['profiled']];both=[r for r in profiled if r['correct']['Qfplib']]
 groups.append(dict(SIO=state,cases=len(rs),profiled=len(profiled),candidate_wrong=0,parent_wrong=0,
                    Qfplib_wrong=sum(not r['correct']['Qfplib'] for r in rs),vs_parent=dict(Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in profiled)),
                    parent_slower_correct_Qfplib=sum(r['instructions']['parent']>r['instructions']['Qfplib'] for r in both),
                    candidate_slower_correct_Qfplib=sum(r['instructions']['candidate']>r['instructions']['Qfplib'] for r in both),
                    new_slower_correct_Qfplib=sum(r['instructions']['candidate']>r['instructions']['Qfplib'] and r['instructions']['parent']<=r['instructions']['Qfplib'] for r in both)))
oldrows=[r for r in rows if r['group']=='old2_slower'];assert len(oldrows)==4
assert all(r['correct']['Qfplib'] and r['instructions']['candidate']<r['instructions']['Qfplib'] for r in oldrows)
report=dict(status='PASS_ATAN_PUBLIC_MPFR_LOCAL_ENCLOSURES_NOT_PRODUCTION',unique_inputs=len(jobs),cases=len(rows),ARM_calls=calls,profiled=sum(r['profiled'] for r in rows),groups=groups,
            old2=oldrows,rows=rows,MPFR_version=o.version,source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),candidate_ELF_sha256=sha(W/'candidate.elf'),control_ELF_sha256=sha(W/'control.elf'),resident_ELF_sha256=sha(ELF),
            candidate_uses_pinned_resident_helpers_and_ROM=True,candidate_observed_stack_bytes=SP-machines['candidate'].stack_lowest,parent_observed_stack_bytes=SP-machines['parent'].stack_lowest,
            PCS_SP_bounded_writes_checked_every_call=True,DIRTY_SIO_preserved_every_call=True,READY_idle_SIO_use_allowed_by_parent_contract=True,READY_left_clean_every_call=True,
            raw_NaN_policy_parent_exact=True,instructions_are_not_cycles=True,unprofiled_not_used_for_speed_claims=True,
            elapsed_seconds=time.monotonic()-start,canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False)
filename='qualification.json' if '--all' in sys.argv else 'edges.json'
(W/filename).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
