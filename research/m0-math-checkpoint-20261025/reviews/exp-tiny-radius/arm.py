"""Own bounded actual public ABI, exact source-isolated helper and layout audit."""
from pathlib import Path
from collections import Counter
import hashlib,json,re,struct,sys
sys.dont_write_bytecode=True
O=Path(__file__).resolve().parent;R=O.parents[1];P=R/'.build/m0-exp-tiny-radius-20261024';V=R/'.build/m0-asin-scaled-bound-v164-20261023';B=R/'.build/m0-exp-cached-product-20261024';Q=R/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_MEM_READ
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_R7
from model import LOW,HIGH,midpoint_model,taylor_bits,helper_cost,public_tiny_cost
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def is_nan(x):return x&0x7fffffffffffffff>0x7ff0000000000000
def equal(x,y):return bool(is_nan(x) and x&(1<<51)) if is_nan(y) else x==y
jobs={int(r['x'],16):r['group'] for r in json.loads((O/'own-tiny-inputs.json').read_text())}
historical=[r for r in json.loads((V/'slower-inputs.json').read_text())['rows'] if r['operation']=='exp']
assert len(historical)==16
for r in historical:jobs.setdefault(int(r['x'],16),'original_exp16')
for x in [0,1,(1<<52)-1,1<<52,0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000001]:
 for s in [0,1<<63]:jobs.setdefault(s|x,'unchanged_IEEE_header')
for x in [0x40861e1effbb4b16,0xc08357d5691b8c00,0x3ff0000000000000,0xbff0000000000000,0x40862e42fefa39ee,0xc0874910d52d3051]:jobs.setdefault(x,'ordinary_layout_or_remaining_control')
rom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';machines={};images={}
for label,path in [('candidate',O/'rebuild/candidate.elf'),('rebuilt_control',O/'rebuild/control.elf'),('accepted_parent',B/'candidate.elf')]:
 m=Machine(V/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom);im=ElfImage(path);im.load(m.uc)
 m.elf.symbols[label+'_exp']=im.symbols['mk61_m0_exp'];machines[label]=m;images[label]=im
 assert not m.rom_models
machines['Qfplib']=Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
unit=Machine(O/'unit.elf',True);assert not unit.rom_models and not unit.rom_initializers
candidate=machines['candidate'];entry=images['candidate'].symbols['mk61_m0_exp']&~1;helper=images['candidate'].symbols['exp_tiny_rne']&~1
current=dict(tiny=False,trace=[],helper=[],entered=0);helper_paths=Counter();public_paths=Counter();unit_paths=Counter();unit_trace=[];unit_reads=set();SIO=[]
def tick(uc,address,size,user):
 if address==helper:current['entered']+=1
 if current['tiny']:
  assert entry<=address<entry+images['candidate'].sizes['mk61_m0_exp'] or helper<=address<helper+0xae
  assert SP-116<=uc.reg_read(UC_ARM_REG_SP)<=SP
  current['trace'].append(address)
  if helper<=address<helper+0xae:current['helper'].append(address)
candidate.uc.hook_add(UC_HOOK_CODE,tick)
candidate.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda uc,a,p,n,v,u:SIO.append((a,p,n)),begin=0xd0000000,end=0xd0000fff)
unit_start=unit.elf.symbols['exp_tiny_rne']&~1
def unit_tick(uc,address,size,user):
 assert unit_start<=address<unit_start+0xae and size==2
 assert SP-20<=uc.reg_read(UC_ARM_REG_SP)<=SP
 unit_trace.append(address)
unit.uc.hook_add(UC_HOOK_CODE,unit_tick)
def unit_memory(uc,access,address,size,value,user):
 assert SP-20<=address and address+size<=SP or(access==UC_MEM_READ and unit_start+0xb0<=address and address+size<=unit_start+196)
 if access==UC_MEM_READ and address<SP-20:unit_reads.add((address,size))
unit.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,unit_memory)
qloop=[];loop_match=re.search(r'^([0-9a-f]+):.*\bldmia\s+r6!,', (O/'reference.dis').read_text(),re.M);assert loop_match
qhead=int(loop_match[1],16)
machines['Qfplib'].uc.hook_add(UC_HOOK_CODE,lambda uc,p,n,u:qloop.append(uc.reg_read(UC_ARM_REG_R7)),begin=qhead,end=qhead)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle();rows=[];bare=[];mpfr=shortcuts=tiny_inputs=0;peaks=Counter();tiny_counts=Counter();helper_counts=Counter();qfp_min=1<<30
for index,(x,group) in enumerate(jobs.items()):
 if index%128==0:print('own public',index,'/',len(jobs),flush=True)
 expected=oracle.reference('exp',x);snan=is_nan(x) and not(x&(1<<51));shortcuts+=snan;mpfr+=not snan
 mag=x&0x7fffffffffffffff;tiny=LOW<mag<HIGH
 if mag<0x3da0000000000000:assert expected==taylor_bits(x)
 if tiny:assert expected==midpoint_model(x);tiny_inputs+=1
 for state_name,state in states.items():
  outputs={};costs={};stack={};qloop.clear()
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state);m.stack_lowest=SP
   if label=='candidate':
    current.update(tiny=tiny,trace=[],helper=[],entered=0);before=len(SIO)
   got,_,cost=m.call('qfp_dexp' if label=='Qfplib' else label+'_exp',x,count=True)
   if label!='Qfplib':assert equal(got,expected),(label,f'{x:016X}',f'{got:016X}',f'{expected:016X}')
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if state_name=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
   outputs[label]=f'{got:016X}';costs[label]=cost;stack[label]=SP-m.stack_lowest;peaks[label]=max(peaks[label],stack[label])
   if label=='candidate':
    assert current['entered']==int(tiny)
    if tiny:
     assert cost==public_tiny_cost(x) and len(current['trace'])==cost
     assert len(current['helper'])==helper_cost(x) and len(SIO)==before and after==state
     public_paths[tuple(current['trace'])]+=1;helper_paths[tuple(current['helper'])]+=1;tiny_counts[cost]+=1
   if label=='Qfplib' and tiny:
    assert qloop==list(range(1,33)) and cost>=352;qfp_min=min(qfp_min,cost)
  assert outputs['candidate']==outputs['rebuilt_control']==outputs['accepted_parent']
  assert costs['rebuilt_control']==costs['accepted_parent']
  if tiny:assert costs['candidate']<costs['Qfplib']
  rows.append(dict(x=f'{x:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',tiny=tiny,outputs=outputs,instructions=costs,stack_bytes=stack,Qfplib_correct=equal(int(outputs['Qfplib'],16),expected)))
  if tiny:
   unit.uc.mem_write(0xd0000060,state);unit_trace.clear()
   got,_,cost=unit.call('exp_tiny_rne',x,count=True)
   assert got==expected and cost==helper_cost(x) and len(unit_trace)==cost
   assert bytes(unit.uc.mem_read(0xd0000060,28))==state and SP-unit.stack_lowest==20
   unit_paths[tuple(unit_trace)]+=1;helper_counts[cost]+=1
   bare.append(dict(x=f'{x:016X}',SIO=state_name,expected=f'{expected:016X}',got=f'{got:016X}',instructions=cost,stack_bytes=20))
assert set(tiny_counts)=={74,77,79,80,83,84,87,93,96}
assert len(helper_paths)==len(unit_paths)==8 and len(public_paths)==11
assert len(unit_reads)==5
# One bounded rejected-layout execution explains the final outlining choice;
# it is excluded from the accepted-candidate qualification call total.
trial=Machine(V/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom);im=ElfImage(P/'trial-r1/candidate.elf');im.load(trial.uc);trial.elf.symbols['trial_exp']=im.symbols['mk61_m0_exp']
layout=[];layout_x=0x40861e1effbb4b16
for state_name,state in states.items():
 trial.uc.mem_write(0xd0000060,state);got,_,cost=trial.call('trial_exp',layout_x,count=True)
 r=next(r for r in rows if r['x']==f'{layout_x:016X}' and r['SIO']==state_name)
 assert got==int(r['expected'],16) and cost==561 and r['instructions']['candidate']==r['instructions']['accepted_parent']==556 and r['instructions']['Qfplib']==559
 layout.append(dict(x=r['x'],SIO=state_name,parent=556,rejected_inline=561,final_outlined=556,Qfplib=559,returned_bits_unchanged=True))
assert all(m.calls==2*len(jobs) for m in machines.values()) and unit.calls==len(bare)==2*tiny_inputs and trial.calls==2
(O/'public-results.json').write_text(json.dumps(rows,indent=2)+'\n');(O/'bare-helper-results.json').write_text(json.dumps(bare,indent=2)+'\n')
(O/'layout-result.json').write_text(json.dumps(dict(status='PASS_FINAL_OUTLINING_RESTORES_HISTORICAL_TRIAL_NEW_LOSS',rows=layout,extra_rejected_trial_ARM_calls2_excluded=True),indent=2)+'\n')
(O/'actual-paths.json').write_text(json.dumps({k:[dict(addresses=[f'{a:08X}' for a in path],count=n) for path,n in sorted(v.items())] for k,v in [('public_tiny',public_paths),('helper_inside_public',helper_paths),('bare_source_helper',unit_paths)]},indent=2)+'\n')
d=dict(status='PASS_OWN_EXP_TINY_PUBLIC_ABI_BARE_HELPER_AND_LAYOUT',unique_public_inputs=len(jobs),tiny_inputs=tiny_inputs,own_qualified_ARM_calls=8*len(jobs)+len(bare),public_ARM_calls=8*len(jobs),public_machine_calls={k:m.calls for k,m in machines.items()},source_bound_bare_helper_ARM_calls=len(bare),extra_rejected_trial_ARM_calls_not_qualified=2,oracle_evaluations=len(jobs),actual_directed_MPFR_input_conversions=mpfr,sNaN_shortcuts_without_MPFR=shortcuts,MPFR_version=oracle.version,own_rational_cubic_interval_controls=934,all_public_raw_parent_bits_exact=True,current_rebuilt_control_and_accepted_parent_costs_exact=True,all_tiny_public_costs_match_source=dict(sorted(tiny_counts.items())),all_helper_costs_match_source=dict(sorted(helper_counts.items())),public_tiny_paths=11,helper_paths=8,bare_helper_paths=8,all_tiny_Qfplib_calls_actual32loopiterations=True,observed_Qfplib_tiny_min_instructions=qfp_min,all_tiny_paths_faster_Qfplib=True,observed_public_stack_peaks=dict(peaks),bare_helper_stack20=True,source_helper_PC_SP_memory_bound_no_firmware_ROM_mock_or_SIO=True,public_tiny_no_outside_call_and_stack_at_most116=True,public_tiny_SIO_accesses=0,unit_only_five_in_section_literals_and_20byte_stack=True,all_DIRTY28bytes_preserved=True,READY_left_not_DIRTY=True,original_exp16_fresh_checked=True,rejected_layout_561_final556_Q559=True,parent_ROM_initializers_excluded=True,hardware=False,canonical=False)
(O/'arm-result.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
