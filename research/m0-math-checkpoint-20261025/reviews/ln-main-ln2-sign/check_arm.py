"""Own small directed ln2-gate ARM/MPFR controls; no hardware."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-ln-main-ln2-sign-20261024';O=Path(__file__).resolve().parent;Q=R/'.build/m0-float-fma-qualification-20261023';V=R/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal,round_ratio
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
b=read(O/'math-binding.json');assert sha(P/'candidate.elf')==b['target']['candidate.elf']['sha256']
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
machines={};traces={label:Counter() for label in ['candidate','parent']}
for label,name in [('candidate','candidate.elf'),('parent','control.elf')]:
 m=Machine(V/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin');e=ElfImage(P/name);e.load(m.uc);m.elf.symbols['review_ln']=e.symbols['mk61_m0_ln'];machines[label]=m
 for n in ['ln_refine','ln_main_raw','ln_near_interval77']:
  address=e.symbols[n]&~1
  def entered(uc,a,size,u,label=label,n=n):traces[label][n]+=1
  m.uc.hook_add(UC_HOOK_CODE,entered,begin=address,end=address)
machines['Qfplib']=Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
jobs={}
def add(raw,group):jobs.setdefault(raw,group)
for raw in [0x5ffa5b2647e9e2c7]:
 for d in [-1,0,1]:add(raw+d,'new_fixed_gate_counterexample_neighbors')
for row in read(P/'regressions.json')['rows']:add(int(row['x'],16),'all7_retained_parent_regression_states')
for row in read(P/'remaining-slower.json')['rows']:add(int(row['x'],16),'all3_remaining_raw_deficits')
for row in read(V/'slower-inputs.json')['rows']:
 if row['operation']=='ln':add(int(row['x'],16),'historical_ln10')
for k in [-1022,-1,0,1,1023]:
 for index,delta in [(0,-64),(511,65),(1023,-65)]:
  raw=((k+1023)<<52)+(index<<42)+(1<<41)+delta;add(raw,'exponent_sign_family_raw_and_n0_controls')
for raw in [0,1,0x000fffffffffffff,0x8000000000000000,0x8000000000000001,0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff8000000001234]:add(raw,'unchanged_IEEE_cold_controls')
saved={(x['x'],x['SIO']):x for x in read(P/'qualification.json')['rows']};oracle=Oracle();rows=[]
for raw,group in jobs.items():
 expected=oracle.reference('ln',raw)
 for sn,state in states.items():
  outputs={};counts={};correct={};before={n:dict(c) for n,c in traces.items()}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state);got,_,cost=m.call('qfp_dln' if label=='Qfplib' else 'review_ln',raw,count=True);outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
   if label!='Qfplib':assert correct[label],(label,hex(raw),hex(got),hex(expected))
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if sn=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
  assert outputs['candidate']==outputs['parent']
  trace={label:{n:traces[label][n]-before[label].get(n,0) for n in ['ln_refine','ln_main_raw','ln_near_interval77']} for label in traces}
  if raw==0x5ffa5b2647e9e2c7:
   assert trace['candidate']['ln_refine']==0 and trace['parent']['ln_refine']==1
   assert counts['candidate']==(595 if sn=='READY' else 655) and counts['Qfplib']==776
  original=saved.get((f'{raw:016X}',sn))
  if original:
   for label in machines:assert counts[label]==original['instructions'][label] and outputs[label]==original['outputs'][label]
  rows.append(dict(x=f'{raw:016X}',group=group,SIO=sn,expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,trace=trace))
regressions=read(P/'regressions.json')['rows'];actual={(r['x'],r['SIO']):r for r in rows}
for old in regressions:
 r=actual[(old['x'],old['SIO'])];assert r['instructions']['candidate']-r['instructions']['parent']==old['instructions']['candidate']-old['instructions']['parent']
# Exact-source bare packers, including threshold-1, n0, below-midpoint,
# equality threshold, former guard edge, parity and binade carries.
unit=Machine(P/'pack-unit.elf',True,stack_bytes=160);e=ElfImage(P/'pack-unit.elf');ranges=[(v&~1,e.sizes[n]) for n,v in e.symbols.items() if v&1 and e.sizes.get(n)]
sio=[0]
def guard(uc,a,size,u):assert any(lo<=a<a+size<=lo+length for lo,length in ranges),hex(a)
unit.uc.hook_add(UC_HOOK_CODE,guard);unit.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda *a:sio.__setitem__(0,sio[0]+1),begin=0xd0000060,end=0xd000007b)
exact=F(b['exact_main_polynomial_bound']);raw_bound=F(b['raw_main_polynomial_bound']);residual_base=F(read(R/'.build/m0-ln-main-raw-split-family-independent-20261024/math-binding.json')['nonlinear_and_rounding_base']);errlo=F(b['ln2_Q70_error_lower']);errhi=F(b['ln2_Q70_error_upper']);decline=int(read(P/'pack-unit-build.json')['decline_bits'],16)
pack_rows=[];endpoints=0;configs=0;labels=Counter();new_shortcuts=0
for n,width in [(0,64),(1,64),(2,65),(512,79),(1023,80)]:
 extra=(n+1)//2;shift=width-53;half=1<<(shift-1)
 for name,bound,radius,maxd in [('audit_exact',exact,8,7+extra),('audit_raw',raw_bound,14,15+extra)]:
  for sign in [False,True]:
   for side in [-1,1]:
    for distance in sorted({0,radius-1,radius,radius+1,maxd,maxd+1}):
     retained=(1<<52)+[0,1,1<<51,(1<<52)-1][configs%4];q=(retained<<shift)+half+side*distance;assert q.bit_length()==width
     inside=distance<=maxd;new_gate=bool(inside and n>0 and side>0 and distance>=radius)
     if name=='audit_exact':safe=not inside or new_gate
     else:safe=not inside or new_gate or bool(distance and distance>=7+extra) # exact unit residue0
     expected=round_ratio(q,1,-70,64,sign) if safe else decline
     if safe:
      # The raw unit's old directed branch has exact residue0; its symmetric
      # base is6.90006. New shortcut uses the full13.40012 independently.
      B=bound if new_gate or not inside or name=='audit_exact' else residual_base
      for error in [-B+n*errlo,B+n*errhi]:
       true=F(q)-error;assert round_ratio(true.numerator,true.denominator,-70,64,sign)==expected,(n,name,side,distance,new_gate)
       endpoints+=1
     if new_gate:new_shortcuts+=1
     labels['accept' if safe else 'decline']+=1;labels['n0' if n==0 else 'npositive']+=1
     if side<0:labels['below_midpoint']+=1
     if distance==radius-1:labels['threshold_minus1']+=1
     if distance==0:labels['midpoint']+=1
     high,low=q>>64,q&((1<<64)-1);config=high|(n<<16)|(int(sign)<<26);assert high<1<<16
     for sn,state in states.items():
      unit.uc.mem_write(0xd0000060,state);got,_,cost=unit.call(name,low,config,count=True)
      assert got==expected and bytes(unit.uc.mem_read(0xd0000060,28))==state
      pack_rows.append(dict(n=n,width=width,packer=name,sign=sign,side=side,distance=distance,inside_old_guard=inside,new_shortcut=new_gate,safe=safe,SIO=sn,output=f'{got:016X}',instructions=cost))
     configs+=1
assert sio[0]==0 and labels['decline'] and labels['n0'] and new_shortcuts
result=dict(status='PASS_FOCUSED_LN2_SIGN_PUBLIC_MPFR_AND_SOURCE_PACK_ARM',MPFR=oracle.version,public_unique_raw=len(jobs),public_state_rows=len(rows),public_ARM_calls=3*len(rows),candidate_MPFR_errors=0,raw_NaN_bits_equal_parent=True,all7_saved_parent_regressions_replayed=True,all3_remaining_raws_replayed_bothstates=True,fixed_case_fallback_removed_bothstates=True,public_trace={k:dict(v) for k,v in traces.items()},PCS_SP_bounded_writes_every_call=True,DIRTY28bytes_preserved_READY_not_dirty=True,public_stack_subset={k:SP-m.stack_lowest for k,m in machines.items()},producer_640B_full_stack_not_reswept=True,bare_pack_configurations=configs,bare_ARM_calls=len(pack_rows),bare_new_upper_shortcut_configurations=new_shortcuts,bare_labels=labels,bare_RNE_Fraction_endpoint_checks=endpoints,bare_zero_SIO_accesses=True,bare_PC_limited_to_unit=True,bare_stack_bytes=SP-unit.stack_lowest,abstract_pack_points_not_real_polynomial_evaluations=True,counts_synthetic_not_cycles=True,hardware_accessed=False,public_rows=rows,bare_rows=pack_rows)
(O/'focused-arm.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['public_rows','bare_rows']},indent=2))
