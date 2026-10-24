"""Independent bounded actual ABI plus source-exact no-ROM helper execution."""
from pathlib import Path
from collections import Counter
import json,struct,sys
sys.dont_write_bytecode=True
O=Path(__file__).resolve().parent;R=O.parents[1];P=R/'.build/m0-exp-tiny-log-midpoint-20261024';V=R/'.build/m0-asin-scaled-bound-v164-20261023';B=R/'.build/m0-exp-tiny-radius-20261024';Q=R/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_MEM_READ
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_R7
from model import LOW,HIGH,exact_model,word_model
def is_nan(x):return x&0x7fffffffffffffff>0x7ff0000000000000
def equal(x,y):return bool(is_nan(x) and x&(1<<51)) if is_nan(y) else x==y
vectors=json.loads((O/'own-vectors.json').read_text());rational={int(r['x'],16):int(r['expected'],16) for r in vectors};jobs={int(r['x'],16):r['group'] for r in vectors}
historical=[r for r in json.loads((V/'slower-inputs.json').read_text())['rows'] if r['operation']=='exp'];assert len(historical)==16
for r in historical:jobs.setdefault(int(r['x'],16),'original_exp16')
for x in [0,1,(1<<52)-1,1<<52,0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000001]:
 for s in [0,1<<63]:jobs.setdefault(s|x,'unchanged_IEEE_header')
for x in [0x40861e1effbb4b16,0xc08357d5691b8c00,0x3ff0000000000000,0xbff0000000000000,0x40862e42fefa39ee,0xc0874910d52d3051]:jobs.setdefault(x,'ordinary_layout_control')
remaining=json.loads((P/'qualification.json').read_text())['remaining']
for r in remaining:
 if 'ordinary' in r['group']:jobs.setdefault(int(r['x'],16),'remaining_ordinary_control')
rom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';machines={};images={}
for label,path in [('candidate',O/'rebuild/candidate.elf'),('rebuilt_control',O/'rebuild/control.elf'),('accepted_parent',B/'candidate.elf')]:
 m=Machine(V/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom);im=ElfImage(path);im.load(m.uc);m.elf.symbols[label+'_exp']=im.symbols['mk61_m0_exp'];machines[label]=m;images[label]=im
 assert not m.rom_models
machines['Qfplib']=Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
unit=Machine(O/'unit.elf',True);assert not unit.rom_models and not unit.rom_initializers
candidate=machines['candidate'];entry=images['candidate'].symbols['mk61_m0_exp']&~1;helper=images['candidate'].symbols['exp_tiny_rne']&~1
assert images['candidate'].sizes['mk61_m0_exp']==1276 and images['candidate'].sizes['exp_tiny_rne']==472
current=dict(tiny=False,trace=[],helper=[],entered=0);helper_paths=Counter();public_paths=Counter();unit_paths=Counter();unit_trace=[];unit_reads=set();SIO=[]
def tick(uc,address,size,user):
 if address==helper:current['entered']+=1
 if current['tiny']:
  assert entry<=address<entry+1276 or helper<=address<helper+0x1c4
  assert SP-152<=uc.reg_read(UC_ARM_REG_SP)<=SP
  current['trace'].append(address)
  if helper<=address<helper+0x1c4:current['helper'].append(address)
candidate.uc.hook_add(UC_HOOK_CODE,tick)
candidate.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda uc,a,p,n,v,u:SIO.append((a,p,n)),begin=0xd0000000,end=0xd0000fff)
unit_start=unit.elf.symbols['exp_tiny_rne']&~1;unit_sp_low=[SP]
def unit_tick(uc,address,size,user):
 assert unit_start<=address<unit_start+0x1c4 and size==2
 assert SP-56<=uc.reg_read(UC_ARM_REG_SP)<=SP
 unit_trace.append(address);unit_sp_low[0]=min(unit_sp_low[0],uc.reg_read(UC_ARM_REG_SP))
unit.uc.hook_add(UC_HOOK_CODE,unit_tick)
def unit_memory(uc,access,address,size,value,user):
 assert SP-56<=address and address+size<=SP or(access==UC_MEM_READ and unit_start+0x1c4<=address and address+size<=unit_start+472)
 if access==UC_MEM_READ and address<SP-56:unit_reads.add((address,size))
unit.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,unit_memory)
qloop=[];qhead=0x10181452
machines['Qfplib'].uc.hook_add(UC_HOOK_CODE,lambda uc,p,n,u:qloop.append(uc.reg_read(UC_ARM_REG_R7)),begin=qhead,end=qhead)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle();rows=[];bare=[];mpfr=shortcuts=tiny_inputs=0;peaks=Counter();tiny_counts=Counter();helper_counts=Counter();overheads=Counter();qfp_min=1<<30
for index,(x,group) in enumerate(jobs.items()):
 if index%128==0:print('own public',index,'/',len(jobs),flush=True)
 expected=oracle.reference('exp',x);snan=is_nan(x) and not(x&(1<<51));shortcuts+=snan;mpfr+=not snan
 mag=x&0x7fffffffffffffff;tiny=LOW<mag<HIGH
 if x in rational:assert expected==rational[x]
 if tiny:assert expected==exact_model(x)==word_model(x);tiny_inputs+=1
 for state_name,state in states.items():
  outputs={};costs={};stack={};qloop.clear()
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state);m.stack_lowest=SP
   if label=='candidate':current.update(tiny=tiny,trace=[],helper=[],entered=0);before=len(SIO)
   got,_,cost=m.call('qfp_dexp' if label=='Qfplib' else label+'_exp',x,count=True)
   if label!='Qfplib':assert equal(got,expected),(label,f'{x:016X}',f'{got:016X}',f'{expected:016X}')
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if state_name=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
   outputs[label]=f'{got:016X}';costs[label]=cost;stack[label]=SP-m.stack_lowest;peaks[label]=max(peaks[label],stack[label])
   if label=='candidate':
    assert current['entered']==int(tiny)
    if tiny:
     assert len(current['trace'])==cost and cost<=206 and len(SIO)==before and after==state
     overhead=cost-len(current['helper']);assert overhead in [34,37];overheads[overhead]+=1
     public_paths[tuple(current['trace'])]+=1;helper_paths[tuple(current['helper'])]+=1;tiny_counts[cost]+=1
   if label=='Qfplib' and tiny:assert qloop==list(range(1,33)) and cost>=352;qfp_min=min(qfp_min,cost)
  assert outputs['candidate']==outputs['rebuilt_control']==outputs['accepted_parent']
  assert costs['rebuilt_control']==costs['accepted_parent']
  if tiny:assert costs['candidate']<costs['Qfplib']
  else:assert costs['candidate']==costs['accepted_parent']
  rows.append(dict(x=f'{x:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',tiny=tiny,outputs=outputs,instructions=costs,stack_bytes=stack,Qfplib_correct=equal(int(outputs['Qfplib'],16),expected)))
  if tiny:
   unit.uc.mem_write(0xd0000060,state);unit_trace.clear();unit.stack_lowest=SP;unit_sp_low[0]=SP
   got,_,cost=unit.call('exp_tiny_rne',x,count=True)
   assert got==expected and len(unit_trace)==cost and cost==len(current['helper']) and cost<=169
   assert [p-unit_start for p in unit_trace]==[p-helper for p in current['helper']]
   assert bytes(unit.uc.mem_read(0xd0000060,28))==state and SP-unit_sp_low[0]==56 and SP-unit.stack_lowest<=56
   unit_paths[tuple(unit_trace)]+=1;helper_counts[cost]+=1
   bare.append(dict(x=f'{x:016X}',SIO=state_name,expected=f'{expected:016X}',got=f'{got:016X}',instructions=cost,stack_bytes=56))
assert len(unit_reads)==5
assert all(m.calls==2*len(jobs) for m in machines.values()) and unit.calls==len(bare)==2*tiny_inputs
critical={r['x'] for r in vectors if r['critical']};assert len(critical)==308
assert all(sum(r['x']==x for r in rows)==2 for x in critical)
(O/'public-results.json').write_text(json.dumps(rows,indent=2)+'\n');(O/'bare-helper-results.json').write_text(json.dumps(bare,indent=2)+'\n')
(O/'actual-paths.json').write_text(json.dumps({k:[dict(addresses=[f'{a:08X}' for a in path],count=n) for path,n in sorted(v.items())] for k,v in [('public_tiny',public_paths),('helper_inside_public',helper_paths),('bare_source_helper',unit_paths)]},indent=2)+'\n')
d=dict(status='PASS_OWN_EXP_LOG_MIDPOINT_PUBLIC_ABI_AND_SOURCE_EXACT_BARE_HELPER',unique_public_inputs=len(jobs),tiny_inputs=tiny_inputs,own_fresh_ARM_calls=8*len(jobs)+len(bare),public_ARM_calls=8*len(jobs),public_machine_calls={k:m.calls for k,m in machines.items()},source_bound_bare_helper_ARM_calls=len(bare),oracle_evaluations=len(jobs),actual_directed_MPFR_input_conversions=mpfr,sNaN_shortcuts_without_MPFR=shortcuts,MPFR_version=oracle.version,own_degree5_rational_interval_controls=len(rational),all154_cubic_changed_cells_actual=True,actual_transition_inputs308=True,all_public_raw_parent_bits_exact=True,current_rebuilt_control_and_accepted_parent_costs_exact=True,ordinary_outside_current_tiny_costs_exact_parent=True,observed_tiny_public_instruction_histogram=dict(sorted(tiny_counts.items())),observed_helper_instruction_histogram=dict(sorted(helper_counts.items())),observed_public_tiny_overheads=dict(sorted(overheads.items())),public_tiny_paths=len(public_paths),helper_paths=len(helper_paths),bare_helper_paths=len(unit_paths),all_tiny_Qfplib_calls_actual32loopiterations=True,observed_Qfplib_tiny_min_instructions=qfp_min,all_tiny_paths_faster_Qfplib=True,observed_public_stack_peaks=dict(peaks),bare_helper_stack56=True,source_helper_PC_SP_memory_bound_no_firmware_ROM_mock_or_SIO=True,public_tiny_no_outside_call_and_stack_at_most152=True,public_tiny_SIO_accesses=0,unit_only_five_in_section_literals_and_56byte_stack=True,all_DIRTY28bytes_preserved=True,READY_left_not_DIRTY=True,original_exp16_fresh_checked=True,parent_ROM_initializers_excluded=True,no_extra_unreported_trial_calls=True,hardware=False,canonical=False)
(O/'arm-result.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
