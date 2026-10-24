"""Bounded adversarial frozen main-raw public/pack controls, not hardware."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
ROOT=Path('/Users/bolk/Projects/MK61S_MINI');P=ROOT/'.build/m0-ln-main-raw-split-family-20261024';O=Path(__file__).resolve().parent;Q=ROOT/'.build/m0-float-fma-qualification-20261023';V=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal,round_ratio
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP
H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
math=read(O/'math-binding.json');assert H(P/'candidate.elf')==math['target']['candidate.elf']['sha256']
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
resident=V/'firmware/mk61s-picocalc-pico-h.elf';rom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
machines={};seen=Counter()
for label,name in [('candidate','candidate.elf'),('parent','control.elf')]:
 m=Machine(resident,True,bootrom=rom);e=ElfImage(P/name);e.load(m.uc);m.elf.symbols['review_ln']=e.symbols['mk61_m0_ln'];machines[label]=m
 if label=='candidate':
  for n in ['ln_main_raw','ln_refine','mk61_m0_log_ratio70']:
   address=e.symbols[n]&~1
   def entered(uc,a,s,u,n=n):seen[n]+=1
   m.uc.hook_add(UC_HOOK_CODE,entered,begin=address,end=address)
machines['Qfplib']=Machine(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
saved=read(P/'qualification.json')['rows'];jobs={};saved_index={(r['x'],r['SIO']):r for r in saved}
def add(raw,group):jobs.setdefault(raw,group)
for row in read(V/'slower-inputs.json')['rows']:
 if row['operation']=='ln':add(int(row['x'],16),'historical_ln10')
for r in saved:
 if r['correct']['Qfplib'] and r['instructions']['candidate']<=r['instructions']['Qfplib']<r['instructions']['parent']:add(int(r['x'],16),'all24_fixed_raw_deficits')
for r in read(P/'remaining-slower.json')['rows']:add(int(r['x'],16),'all49_remaining_deficits')
for delta in [-65,-64,-63,63,64,65]:
 for index,exponent,side in [(0,-1,-1),(511,1,1),(1023,1023,-1)]:
  add(((exponent+1023)<<52)+(index<<42)+(1<<41)+side*((255<<32)+delta),'family_signed_boundary')
for index,k,offset in [(0,-1022,65),(0,-1,(1<<41)+65),(1023,0,(1<<41)-65),(511,1,0x12345),(1023,1023,(1<<42)-65)]:add(((k+1023)<<52)+(index<<42)+offset,'raw_extreme_normal')
for raw in [0x4000000000000000,0x400FFE7EFFFFFFBF,0x3FEF808000000001,0x3FF0400000000000]:
 for delta in [-1,0,1]:add(raw+delta,'known_speed_or_domain_neighbors')
for raw in [0,1,0x000fffffffffffff,0x0010000000000000,0x3ff0000000000000,0x8000000000000000,0x8000000000000001,0xbff0000000000000,0x7fefffffffffffff,0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0x7ff8000000001234,0xfff0000000004321]:add(raw,'unchanged_IEEE_entry_controls')
oracle=Oracle();rows=[];branch_counts=Counter()
for raw,group in jobs.items():
 expected=oracle.reference('ln',raw)
 for sn,state in states.items():
  before=dict(seen);outputs={};counts={};correct={}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state);got,_,cost=m.call('qfp_dln' if label=='Qfplib' else 'review_ln',raw,count=True)
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
   if label!='Qfplib':assert correct[label],(label,hex(raw),hex(got),hex(expected))
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if sn=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
  assert outputs['candidate']==outputs['parent']
  trace={n:seen[n]-before.get(n,0) for n in ['ln_main_raw','ln_refine','mk61_m0_log_ratio70']}
  expected_raw=bool(sn=='DIRTY' and 0x0010000000000000<=raw<0x7ff0000000000000 and not 0x3fef808000000001<=raw<=0x3ff0400000000000 and ((raw+64)&0xffffffff)>128)
  assert trace['ln_main_raw']==int(expected_raw),(hex(raw),sn,trace,expected_raw)
  if expected_raw:assert trace['mk61_m0_log_ratio70']==0
  branch_counts['raw' if expected_raw else 'old']+=1
  if trace['ln_refine']:branch_counts['fallback']+=1
  original=saved_index.get((f'{raw:016X}',sn))
  if original:
   for n in ['candidate','parent','Qfplib']:assert counts[n]==original['instructions'][n] and outputs[n]==original['outputs'][n]
  rows.append(dict(x=f'{raw:016X}',group=group,SIO=sn,expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,trace=trace))
assert branch_counts['raw'] and branch_counts['old'] and branch_counts['fallback']
(O/'public-results.json').write_text(json.dumps(dict(status='PASS_FOCUSED_PUBLIC_ONLY',MPFR=oracle.version,unique_inputs=len(jobs),rows=rows),indent=2)+'\n')
# Exact inline source (already independently rebuilt) in a bare unit.
pm=Machine(P/'pack-unit.elf',True,stack_bytes=128);unit=ElfImage(P/'pack-unit.elf');ranges=[(v&~1,unit.sizes[n]) for n,v in unit.symbols.items() if unit.sizes.get(n,0) and (v&1)]
sio=[0]
def pc_guard(uc,a,s,u):assert any(start<=a<a+s<=start+length for start,length in ranges),hex(a)
pm.uc.hook_add(UC_HOOK_CODE,pc_guard);pm.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda *a:sio.__setitem__(0,sio[0]+1),begin=0xd0000060,end=0xd000007b)
A=F(math['total_argument_bound']);B=F(math['nonlinear_and_rounding_base']);decline=int(read(P/'pack-unit-build.json')['decline_bits'],16);configs=[];pack_rows=[];endpoint_checks=0
for wi,(width,k) in enumerate([(64,-1),(64,0),(65,0),(70,1),(79,-1022),(80,1023)]):
 for variant in range(4):
  index=[0,1,511,1023][variant];den=2049+2*index;extra=(abs(k)+1)//2;offset=(1<<41)+[-0x1234567,-65,65,0x2345678][variant];negative=offset<(1<<41);delta=abs(offset-(1<<41));Hq=F(delta<<29,den)
  h=Hq.__floor__()+[-6,-1,0,6][variant];assert h>=0 and abs(h-Hq)<A
  sign=k<0;orientation=-1 if negative!=sign else 1;residue=(delta<<29)-h*den;assert abs(residue)<32768
  shift=width-53;half=1<<(shift-1);side=-1 if variant&1 else 1;retained=(1<<52)+[0,1,17,(1<<52)-1][variant]
  for distance in sorted({0,1,6+extra,7+extra,8+extra,15+extra,16+extra}):
   tail=half+side*distance;assert 0<=tail<2*half;q=(retained<<shift)+tail;assert q.bit_length()==width
   configs.append((q,k,index,offset,h,extra,orientation,residue,side,distance))
  # Both exact binade starts and the just-before-carry integer.
  for q in [1<<(width-1),(1<<width)-1]:
   tail=q&((1<<shift)-1);distance=abs(tail-half);configs.append((q,k,index,offset,h,extra,orientation,residue,1 if tail>half else -1,distance))
# Equality boundary of directed gate: actual zero residual, d=7+extra.
# delta=den*2^19 gives H=2^48 exact and remains within the main domain.
for sign in [False,True]:
 for negative in [False,True]:
  index=1023;den=4095;k=-1 if sign else 1;extra=1
  delta=den<<19;offset=(1<<41)+(-delta if negative else delta);h=1<<48
  for side in [-1,1]:
   width=70;shift=17;distance=8;q=((1<<52)+1)<<shift;q+=(1<<(shift-1))+side*distance
   configs.append((q,k,index,offset,h,extra,-1 if negative!=sign else 1,0,side,distance))
for q,k,index,offset,h,extra,orientation,residue,side,distance in configs:
 width=q.bit_length();den=2049+2*index;sign=k<0;safe=distance>=16+extra or bool(distance and den*(distance-7-extra)+side*orientation*residue>=0)
 expected=round_ratio(q,1,-70,64,sign) if safe else decline
 if safe:
  center_error=-orientation*F(residue,den)
  for error in [center_error-B-extra,center_error+B+extra]:
   exact=F(q)-error;assert round_ratio(exact.numerator,exact.denominator,-70,64,sign)==expected,(width,den,residue,extra,distance)
   endpoint_checks+=1
 payload=struct.pack('<QQQIIII',q&((1<<64)-1),((k+1023)<<52)+(index<<42)+offset,int(sign)<<63,q>>64,extra,h&0xffffffff,0)
 for sn,state in states.items():
  pm.uc.mem_write(0x20001000,payload);pm.uc.mem_write(0xd0000060,state);got,_,cost=pm.call('audit_main_pack',0x20001000,count=True)
  assert got==expected and bytes(pm.uc.mem_read(0xd0000060,28))==state and bytes(pm.uc.mem_read(0x20001000,40))==payload
  pack_rows.append(dict(width=width,k=k,index=index,offset=offset,h=h,residue=residue,extra=extra,orientation=orientation,side=side,distance=distance,SIO=sn,safe=safe,output=f'{got:016X}',instructions=cost))
assert sio[0]==0
fixed_x={r['x'] for r in saved if r['correct']['Qfplib'] and r['instructions']['candidate']<=r['instructions']['Qfplib']<r['instructions']['parent']}
assert len(fixed_x)==24
fixed_rows=[r for r in rows if r['x']in fixed_x and r['SIO']=='DIRTY'];assert len(fixed_rows)==24 and all(r['instructions']['candidate']<=r['instructions']['Qfplib'] for r in fixed_rows)
result=dict(status='PASS_FOCUSED_MAIN_RAW_PUBLIC_ARM_MPFR_AND_EXACT_PACK_ENDPOINTS',MPFR=oracle.version,unique_public_inputs=len(jobs),public_state_rows=len(rows),public_ARM_calls=3*len(rows),public_machine_calls={k:m.calls for k,m in machines.items()},actual_dispatch_and_fallback=seen,branch_cases=branch_counts,all24_fixed_raw_deficits_replayed_both_states=True,all49_remaining_raw_deficits_replayed_both_states=True,raw_NaN_same_parent=True,PCS_SP_bounded_writes_every_call=True,public_stack_observed={k:SP-m.stack_lowest for k,m in machines.items()},own_subset_not_full_stackproof=True,pack_configurations=len(configs),pack_ARM_calls=len(pack_rows),pack_accepted_configs=sum(r['safe'] for r in pack_rows)//2,pack_declined_configs=sum(not r['safe'] for r in pack_rows)//2,pack_endpoint_Fraction_RNE_checks=endpoint_checks,pack_source_and_entire_ELF_bound=True,pack_SIO_accesses=sio[0],pack_stack_observed=SP-pm.stack_lowest,pack_PC_limited_to_bare_unit=True,pack_input_unchanged=True,pack_rows=pack_rows,synthetic_instructions_not_cycles=True,hardware_accessed=False,later_children_not_qualified=True)
(O/'focused-arm.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='pack_rows'},indent=2))
