"""Bounded independent IEEE/forwarding ABI and public MPFR controls."""
from pathlib import Path
from collections import Counter
import json,struct,sys,hashlib
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-ln-raw-cold-entry-20261024';O=Path(__file__).resolve().parent;Q=R/'.build/m0-float-fma-qualification-20261023';V=R/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_SP,UC_ARM_REG_LR
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
b=read(O/'binding.json');assert sha(P/'candidate.elf')==b['target']['candidate.elf']['sha256']
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
def kind(raw):
 if raw&0x7fffffffffffffff==0:return 'zero'
 if raw==0x7ff0000000000000:return 'positive_infinity'
 if raw>>63==0 and 1<=((raw>>52)&2047)<=2046:return 'normal'
 return 'special'
def register_raw(uc):return uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32)
# Bare exact-source classifier. Tags distinguish target AND preserve all64 bits.
unit=Machine(P/'entry-unit.elf',True,stack_bytes=64);e=ElfImage(P/'entry-unit.elf');current={};forwards=[];sio=[0];entry_checks=[0]
ranges=[(v&~1,e.sizes[n]) for n,v in e.symbols.items() if (v&1) and e.sizes.get(n)]
def bare_pc(uc,a,size,u):assert any(lo<=a<a+size<=lo+length for lo,length in ranges),hex(a)
unit.uc.hook_add(UC_HOOK_CODE,bare_pc)
unit.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda *a:sio.__setitem__(0,sio[0]+1),begin=0xd0000060,end=0xd000007b)
def at_entry(uc,a,size,u):
 assert register_raw(uc)==current['raw'];current['entry_SP']=uc.reg_read(UC_ARM_REG_SP);current['entry_LR']=uc.reg_read(UC_ARM_REG_LR);assert current['entry_SP']%8==0;entry_checks[0]+=1
unit.uc.hook_add(UC_HOOK_CODE,at_entry,begin=e.symbols['mk61_m0_ln']&~1,end=e.symbols['mk61_m0_ln']&~1)
for name,expected_kind in [('mk61_m0_ln_positive','normal'),('mk61_m0_ln_special','special')]:
 address=e.symbols[name]&~1
 def target(uc,a,size,u,expected_kind=expected_kind):
  assert kind(current['raw'])==expected_kind and register_raw(uc)==current['raw']
  assert uc.reg_read(UC_ARM_REG_SP)==current['entry_SP'] and uc.reg_read(UC_ARM_REG_LR)==current['entry_LR']
  current['forwarded']+=1
 unit.uc.hook_add(UC_HOOK_CODE,target,begin=address,end=address)
bare=[]
for field in [0,1,2,0x3fe,0x3ff,0x400,0x7fd,0x7fe,0x7ff,0x800,0x801,0xffe,0xfff]:
 for fraction_hi in [0,1,1<<19,(1<<20)-1]:
  for low in [0,1,1<<31,(1<<32)-1]:
   raw=(field<<52)|(fraction_hi<<32)|low;k=kind(raw)
   expected=0xfff0000000000000 if k=='zero' else raw if k=='positive_infinity' else raw^(0x13579bdf2468ace0 if k=='normal' else 0xfdb97531eca86420)
   for sn,state in states.items():
    current.clear();current.update(raw=raw,forwarded=0);unit.uc.mem_write(0xd0000060,state);got,_,cost=unit.call('mk61_m0_ln',raw,count=True)
    assert got==expected and bytes(unit.uc.mem_read(0xd0000060,28))==state
    assert current['forwarded']==int(k in ['normal','special'])
    bare.append(dict(x=f'{raw:016X}',kind=k,SIO=sn,output=f'{got:016X}',instructions=cost))
assert sio[0]==0 and entry_checks[0]==len(bare)
# Actual public linked entry, not the tagged unit; MPFR reference is fresh.
machines={};images={};trace=Counter();active={};forward_trace=[]
for label,name in [('candidate','candidate.elf'),('parent','control.elf')]:
 m=Machine(V/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin');im=ElfImage(P/name);im.load(m.uc);m.elf.symbols['review_ln']=im.symbols['mk61_m0_ln'];machines[label]=m;images[label]=im
machines['Qfplib']=Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
candidate=machines['candidate'];im=images['candidate']
def public_entry(uc,a,size,u):
 assert register_raw(uc)==active['raw'];active['SP']=uc.reg_read(UC_ARM_REG_SP);active['LR']=uc.reg_read(UC_ARM_REG_LR);active['forwarded']=0;assert active['SP']%8==0
address=im.symbols['mk61_m0_ln']&~1;candidate.uc.hook_add(UC_HOOK_CODE,public_entry,begin=address,end=address)
for name,expected_kind in [('mk61_m0_ln_positive','normal'),('mk61_m0_ln_special','special')]:
 address=im.symbols[name]&~1
 def public_target(uc,a,size,u,name=name,expected_kind=expected_kind):
  assert kind(active['raw'])==expected_kind and register_raw(uc)==active['raw']
  assert uc.reg_read(UC_ARM_REG_SP)==active['SP'] and uc.reg_read(UC_ARM_REG_LR)==active['LR']
  active['forwarded']+=1;trace[name]+=1
 candidate.uc.hook_add(UC_HOOK_CODE,public_target,begin=address,end=address)
for name in ['ln_main_raw','ln_refine']:
 address=im.symbols[name]&~1
 def entered(uc,a,size,u,name=name):trace[name]+=1
 candidate.uc.hook_add(UC_HOOK_CODE,entered,begin=address,end=address)
jobs={}
def add(raw,group):jobs.setdefault(raw,group)
for field in [0,1,0x7fe,0x7ff,0x800,0x801,0xffe,0xfff]:
 for payload in [0,1,1<<51,(1<<52)-1]:add((field<<52)|payload,'IEEE_payload_sign_and_endpoint_classes')
for raw in [0,1,0x000fffffffffffff,0x0010000000000000,0x7fefffffffffffff]:
 for d in [-1,0,1]:
  if 0<=raw+d<1<<64:add(raw+d,'normal_subnormal_boundary_neighbors')
for row in read(V/'slower-inputs.json')['rows']:
 if row['operation']=='ln':add(int(row['x'],16),'historical_ln10')
for raw in [0x3fef808000000001,0x3ff0400000000000,0x4000000000000000,0x400ffe7effffffbf]:
 for d in [-1,0,1]:add(raw+d,'normal_near_or_speed_boundary')
saved=read(P/'qualification.json')['rows'];index={(x['x'],x['SIO']):x for x in saved};reg_seen=set()
for row in read(P/'regressions.json')['rows']:
 delta=row['instructions']['candidate']-row['instructions']['parent']
 if delta not in reg_seen:add(int(row['x'],16),'each_saved_regression_cost_witness');reg_seen.add(delta)
assert reg_seen=={1,4,5,6}
oracle=Oracle();rows=[]
for raw,group in jobs.items():
 expected=oracle.reference('ln',raw)
 for sn,state in states.items():
  outputs={};costs={};correct={};before=dict(trace);active.clear();active['raw']=raw
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state);got,_,cost=m.call('qfp_dln' if label=='Qfplib' else 'review_ln',raw,count=True);outputs[label]=f'{got:016X}';costs[label]=cost;correct[label]=equal(got,expected,64)
   if label!='Qfplib':assert correct[label],(label,hex(raw),hex(got),hex(expected))
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if sn=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
  assert outputs['candidate']==outputs['parent']
  assert active['forwarded']==int(kind(raw) in ['normal','special'])
  if kind(raw)=='zero':assert costs['candidate']==6
  if kind(raw)=='positive_infinity':assert costs['candidate']==8
  original=index.get((f'{raw:016X}',sn))
  if original:
   for label in machines:assert outputs[label]==original['outputs'][label] and costs[label]==original['instructions'][label]
  rows.append(dict(x=f'{raw:016X}',group=group,SIO=sn,expected=f'{expected:016X}',outputs=outputs,instructions=costs,correct=correct,trace={k:trace[k]-before.get(k,0) for k in trace}))
assert trace['mk61_m0_ln_special'] and trace['mk61_m0_ln_positive'] and trace['ln_main_raw'] and trace['ln_refine']
result=dict(status='PASS_BOUNDED_EXACT_IEEE_ENTRY_AND_ACTUAL_PUBLIC_ARM_MPFR',MPFR=oracle.version,public_unique_raw=len(jobs),public_state_rows=len(rows),public_ARM_calls=3*len(rows),public_forwarding_exact_bits_SP_LR=True,public_candidate_wrong=0,raw_NaN_policy_equals_parent=True,public_trace=trace,public_stack_subset={k:SP-m.stack_lowest for k,m in machines.items()},producer_full_640B_public_stack_not_reswept=True,IEEE_early_actual_costs={f'{raw:016X}':[r['instructions'] for r in rows if r['x']==f'{raw:016X}'] for raw in [0,0x8000000000000000,0x7ff0000000000000]},bare_unique_raw=len(bare)//2,bare_ARM_calls=len(bare),bare_entry_exact_bits_SP_LR=True,bare_SIO_accesses=sio[0],bare_PC_limited_to_unit=True,bare_stack_bytes=SP-unit.stack_lowest,bare_tagged_stack_not_entry_stack=True,PCS_SP_bounded_writes_checked_every_call=True,DIRTY28bytes_preserved_READY_not_dirty=True,private_instructions_not_physical_cycles=True,hardware_accessed=False,public_rows=rows,bare_rows=bare)
(O/'focused-arm.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['public_rows','bare_rows']},indent=2))
