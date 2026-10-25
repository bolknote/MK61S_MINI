"""Measure actual reciprocal call operands, IEEE divide and integer seed costs."""
from pathlib import Path
from collections import Counter
import json,sys,time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.build/m0-pow-boundary128-20261025'))
from harness import *
from unicorn.arm_const import UC_ARM_REG_LR
OUT=Path(__file__).resolve().parent
m=machine('candidate');reference=machine('Qfplib')
captures=[];entry=m.elf.symbols['__aeabi_ddiv']&~1
root_begin=m.elf.symbols['pow_root128']&~1;root_end=root_begin+m.elf.sizes['pow_root128']
def capture(uc,pc,size,user):
 a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32)
 b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
 captures.append(dict(numerator=f'{a:016X}',denominator=f'{b:016X}',caller=f'{uc.reg_read(UC_ARM_REG_LR):08X}'))
handle=m.uc.hook_add(UC_HOOK_CODE,capture,begin=entry,end=entry)
jobs=json.loads((HERE/'probe.json').read_bytes())['rows'];public=[]
for i,row in enumerate(jobs):
 if i%64==0:print('reciprocal-public-profile',i,'/',len(jobs),flush=True)
 captures.clear();state=states[row['SIO']];m.uc.mem_write(0xd0000060,state)
 got,_,cost=m.call('_ZN12compact_math3powEdd',int(row['x'],16),int(row['y'],16),count=True)
 state_after(m,state)
 assert f'{got:016X}'==row['outputs']['candidate'] and cost==row['instructions']['candidate']
 public.append(dict(x=row['x'],y=row['y'],SIO=row['SIO'],output=f'{got:016X}',instructions=cost,divisions=list(captures)))
m.uc.hook_del(handle)
all_calls=[r for row in public for r in row['divisions']]
target=[r for r in all_calls if r['numerator']=='3FF0000000000000' and root_begin<=(int(r['caller'],16)&~1)<root_end]
denominators=sorted({int(r['denominator'],16)for r in target})
assert denominators
oracle=Oracle();rows=[]
for denominator in denominators:
 expected=oracle.reference('ddiv',bits(1.),denominator)
 significand=(denominator&((1<<52)-1))|(1<<52);top16=significand>>37
 for state_name,state in states.items():
  m.uc.mem_write(0xd0000060,state)
  got,_,cost=m.call('__aeabi_ddiv',bits(1.),denominator,count=True);state_after(m,state)
  assert equal(got,expected,64)
  m.uc.mem_write(0xd0000060,state)
  quotient,_,seedcost=m.call('mk61_m0_math_udiv32',0x80000000|(top16<<32),count=True);state_after(m,state)
  assert quotient&0xffffffff==0x80000000//top16
  reference.uc.mem_write(0xd0000060,state)
  qvalue,_,qcost=reference.call('qfp_ddiv',bits(1.),denominator,count=True);state_after(reference,state)
  rows.append(dict(denominator=f'{denominator:016X}',SIO=state_name,expected=f'{expected:016X}',
   native_output=f'{got:016X}',native_instructions=cost,Qfplib_output=f'{qvalue:016X}',
   Qfplib_instructions=qcost,Qfplib_correct=equal(qvalue,expected,64),
   seed_denominator=top16,seed_quotient=quotient&0xffffffff,seed_instructions=seedcost))
summary={}
for state_name in states:
 r=[r for r in rows if r['SIO']==state_name]
 summary[state_name]={}
 for name in ['native_instructions','Qfplib_instructions','seed_instructions']:
  values=[x[name]for x in r]
  summary[state_name][name]=dict(min=min(values),max=max(values),mean=sum(values)/len(values),histogram=dict(Counter(values)))
out=dict(status='MEASURED_REAL_POW_RECIPROCAL_HINT_AND_UINT32_SEED_COSTS',
 source_parent='.build/m0-pow-boundary128-20261025',source_parent_FROZEN_sha256=sha(HERE/'FROZEN.json'),
 public_profile_calls=len(public),all_actual_division_calls=len(all_calls),target_root_reciprocal_calls=len(target),
 target_normalized_denominators=len(denominators),fresh_direct_profile_ARM_calls=3*len(rows),
 actual_directed_MPFR_inputs=len(denominators),summary=summary,rows=rows,public=public,
 no_implementation_or_qualification_claim=True,hardware_accessed=False)
(OUT/'profile.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items()if k not in ['rows','public']},indent=2))
