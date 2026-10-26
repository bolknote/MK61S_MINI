"""Focused real public MPFR plus abstract exact-source coefficient/pack tests."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import json,hashlib,struct,sys
sys.dont_write_bytecode=True
from bounds import S,A,actual,emitted,bias,error_interval,predicate
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-ln-main-quarter-fifth-20261024';O=Path(__file__).resolve().parent;Q=R/'.build/m0-float-fma-qualification-20261023';V=R/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal,round_ratio
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
binding=read(O/'math-binding.json');assert sha(P/'candidate.elf')==binding['target']['candidate.elf']['sha256']
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
machines={};traces={n:Counter() for n in ['candidate','parent']}
for label,name in [('candidate','candidate.elf'),('parent','control.elf')]:
 m=Machine(V/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=R/'research/rp2040-memset-2026-10-21/capture/bootrom.bin');e=ElfImage(P/name);e.load(m.uc);m.elf.symbols['review_ln']=e.symbols['mk61_m0_ln'];machines[label]=m
 for name in ['ln_main_raw','ln_refine','ln_near_interval77']:
  a=e.symbols[name]&~1
  def hook(uc,a,s,u,label=label,name=name):traces[label][name]+=1
  m.uc.hook_add(UC_HOOK_CODE,hook,begin=a,end=a)
machines['Qfplib']=Machine(R/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
saved=read(P/'qualification.json')['rows'];index={(x['x'],x['SIO']):x for x in saved};jobs={}
def add(raw,group):jobs.setdefault(raw,group)
for row in saved:
 if row['correct']['Qfplib'] and row['instructions']['candidate']<=row['instructions']['Qfplib']<row['instructions']['parent']:add(int(row['x'],16),'all9_fixed_old_control_deficits')
for row in read(P/'remaining-slower.json')['rows']:add(int(row['x'],16),'all5_remaining_raw_deficits')
cost_seen=set()
for row in read(P/'regressions.json')['rows']:
 d=row['instructions']['candidate']-row['instructions']['parent']
 if d not in cost_seen:add(int(row['x'],16),'each_retained_regression_cost_witness');cost_seen.add(d)
for row in read(V/'slower-inputs.json')['rows']:
 if row['operation']=='ln':add(int(row['x'],16),'historical_ln10')
for cell in [8,31,32]:
 for offset_high in [1021,1022,1023]:
  for low in [0,0xffffffff]:add((1023<<52)+(cell<<42)+(offset_high<<32)+low,'cheap_endpoint_boundary')
for i,den in enumerate([2049,2079,2081,3583,3585,4095]):
 for offset in [(1<<41)-65,(1<<41)+64]:
  k=[-1022,-1,0,1,512,1023][i];add(((1023+k)<<52)+((den-2049)//2<<42)+offset,'den_band_and_sign_family_boundary')
for raw in [0,1,0x8000000000000000,0x8000000000000001,0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff8000000000042]:add(raw,'unchanged_IEEE_controls')
oracle=Oracle();rows=[]
for raw,group in jobs.items():
 expected=oracle.reference('ln',raw)
 for sn,state in states.items():
  before={n:dict(v) for n,v in traces.items()};outputs={};counts={};correct={}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state);got,_,cost=m.call('qfp_dln' if label=='Qfplib' else 'review_ln',raw,count=True);outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
   if label!='Qfplib':assert correct[label],(label,hex(raw),hex(got),hex(expected))
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if sn=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
  assert outputs['candidate']==outputs['parent']
  previous=index.get((f'{raw:016X}',sn))
  if previous:
   for label in machines:assert counts[label]==previous['instructions'][label] and outputs[label]==previous['outputs'][label]
  rows.append(dict(x=f'{raw:016X}',group=group,SIO=sn,expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,trace={label:{n:traces[label][n]-before[label].get(n,0) for n in traces[label]} for label in traces}))
(O/'public-results.json').write_text(json.dumps(dict(status='PASS_FOCUSED_PUBLIC_ONLY',MPFR=oracle.version,unique_raw=len(jobs),rows=rows),indent=2)+'\n')
# Exact frozen bare helpers. Fixtures are deliberately abstract enclosures,
# not claims of real full-polynomial input evaluations.
unit=Machine(P/'pack-unit.elf',True,stack_bytes=512);ue=ElfImage(P/'pack-unit.elf');ranges=[(v&~1,ue.sizes[n]) for n,v in ue.symbols.items() if v&1 and ue.sizes.get(n)];sio=[0]
unit.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda *a:sio.__setitem__(0,sio[0]+1),begin=0xd0000060,end=0xd000007b)
def pc(uc,a,s,u):assert any(lo<=a<a+s<=lo+length for lo,length in ranges),hex(a)
unit.uc.hook_add(UC_HOOK_CODE,pc)
bare=[];coefficient_calls=pack_calls=endpoints=equality=forced=0;sentinel=int(read(P/'pack-unit-build.json')['decline_bits'],16)
def xb(den,negative,n,sign,endpoint=False):
 exp=1023-n if sign else 1023+n;assert 1<=exp<=2046
 off=1022 if endpoint else 100 if negative else 700
 return (exp<<52)+((den-2049)//2<<42)+(off<<32)+0x7fffffc1
def fixture(raw,residue,f4,f5,d,above):
 den=2049+2*((raw&((1<<52)-1))>>42);neg=not bool(raw&(1<<41));lo=(raw<<29)&0xffffffff
 if neg:lo=(-lo)&0xffffffff
 h=((lo-residue)*pow(den,-1,1<<32))&0xffffffff
 return struct.pack('<8I',raw&0xffffffff,raw>>32,h,f4,f5,d,int(above),residue&0xffffffff)
def run(name,a,config,fx,expected,metadata):
 global coefficient_calls,pack_calls
 for sn,state in states.items():
  unit.uc.mem_write(0x20000000,fx);unit.uc.mem_write(0xd0000060,state);got,_,cost=unit.call(name,a,config,count=True)
  assert got==expected,(name,metadata,hex(got),hex(expected))
  assert bytes(unit.uc.mem_read(0xd0000060,28))==state and bytes(unit.uc.mem_read(0x20000000,32))==fx
  bare.append(dict(function=name,SIO=sn,output=f'{got:016X}',instructions=cost,**metadata))
  if name=='audit_coefficient':coefficient_calls+=1
  else:pack_calls+=1
for di,den in enumerate([2049,2079,2081,3583,3585,4095]):
 edge=(A*den).__ceil__()-1
 for f4 in range(4):
  for f5 in range(5):
   j=5*f4+f5;negative=bool(j&1);sign=bool(j&2);n=[0,1,512,1023][j%4]
   if sign and n in [0,1023]:n=1 if n==0 else 1022
   residue=[-edge,-den+1,-1,0,edge][j%5];above=bool((j+di)&1);L,U=emitted(den,negative);B=bias(f4,f5,negative)
   if sign:L,U=U,L;B=-B
   ori=-residue if negative!=sign else residue
   bound=U+B-F(ori,den) if above else L-B+F(ori,den)+F(n,2);critical=-((-bound.numerator)//bound.denominator)
   for d in sorted({max(0,critical-1),max(0,critical),max(0,critical+1)}):
    raw=xb(den,negative,n,sign);ok=predicate(d,above,sign,n,den,residue,negative,f4,f5)
    margin=(F(d)-bound);equality+=int(margin==0)
    run('audit_coefficient',(f5<<32)|f4,(n<<16)|(int(sign)<<26),fixture(raw,residue,f4,f5,d,above),int(ok),dict(den=den,n=n,negative=negative,sign=sign,residue=residue,fourth=f4,fifth=f5,distance=d,above=above,equality=margin==0))
# Explicit equality at the strongest positive upper band: U=2,bias=r=0.
den=3585;raw=xb(den,False,512,False);assert predicate(2,True,False,512,den,0,False,0,0)
run('audit_coefficient',0,512<<16,fixture(raw,0,0,0,2,True),1,dict(den=den,n=512,negative=False,sign=False,residue=0,fourth=0,fifth=0,distance=2,above=True,equality=True));equality+=1
def point(name,den,negative,sign,n,residue,f4,f5,d,above,endpoint=False,midpoint=False):
 global endpoints,forced
 raw=xb(den,negative,n,sign,endpoint);extra=(n+1)//2;inside=d<=(7+extra if name=='audit_exact' else 15+extra)
 coeff=bool(d and predicate(d,above,sign,n,den,residue,negative,f4,f5));ori=-residue if negative!=sign else residue
 if name=='audit_exact':
  cheap=bool(n and above and d>=8) or bool(not n and ((above and d>=(6 if negative else 7)) or (not above and (d>=4 or endpoint))))
 else:
  radius=7+extra if n else 6 if above else 3 if negative else 4
  if endpoint and not above and not n:radius=1
  cheap=bool(n and above and d>=14) or bool(d and (d-radius)*den+(ori if above else -ori)>=0)
 safe=not inside or cheap or coeff
 if not d:safe=False
 forced+=int(inside and not cheap and coeff)
 width=64 if n<=1 else 79 if n<1023 else 80;shift=width-53;half=1<<(shift-1);retained=(1<<52)+[0,1,1<<51,(1<<52)-1][(len(bare)//2)%4];q=(retained<<shift)+half+(d if above else -d);assert q.bit_length()==width
 expected=round_ratio(q,1,-70,64,sign) if safe else sentinel
 if safe:
  elo,ehi=error_interval(sign,n,den,residue,negative,f4,f5)
  if endpoint:elo+=F(binding['endpoint_raw_remainder'] if name=='audit_raw' else binding['endpoint_exact_remainder'])
  for error in [elo,ehi]:
   true=F(q)-error;assert round_ratio(true.numerator,true.denominator,-70,64,sign)==expected,(name,den,n,negative,sign,d,above,elo,ehi)
   endpoints+=1
 config=(q>>64)|(n<<16)|(int(sign)<<26)
 run(name,q&((1<<64)-1),config,fixture(raw,residue,f4,f5,d,above),expected,dict(den=den,n=n,negative=negative,sign=sign,residue=residue,fourth=f4,fifth=f5,distance=d,above=above,safe=safe,forced_coefficient=inside and not cheap and coeff,endpoint=endpoint))
for di,den in enumerate([2049,2079,2081,3583,3585,4095]):
 for negative in [False,True]:
  for sign in [False,True]:
   for name in ['audit_exact','audit_raw']:
    n=511+(di&1);residue=-den+1;f4=2;f5=3;L,U=emitted(den,negative);B=bias(f4,f5,negative)
    if sign:L,U=U,L;B=-B
    ori=-residue if negative!=sign else residue;critical=-((-(U+B-F(ori,den)).numerator)//(U+B-F(ori,den)).denominator)
    d=max(1,critical);point(name,den,negative,sign,n,residue,f4,f5,d,True)
    point(name,den,negative,sign,n,residue,f4,f5,0,False)
# n0 cheap thresholds, with/without the first32-cell endpoint exception.
for den in [2081,2111,2113]:
 for negative in [False,True]:
  for name in ['audit_exact','audit_raw']:
   for d in [1,3,4,6,7]:point(name,den,negative,False,0,-1,2,2,d,False)
for name in ['audit_exact','audit_raw']:
 for den in [2081,2111]:point(name,den,False,False,0,-1,2,2,1,False,endpoint=True)
assert sio[0]==0 and forced and equality
out=dict(status='PASS_FOCUSED_QUARTER_FIFTH_PUBLIC_AND_BARE_ARM',MPFR=oracle.version,public_unique_raw=len(jobs),public_state_rows=len(rows),public_ARM_calls=3*len(rows),public_candidate_wrong=0,raw_NaN_bits_equal_parent=True,all9_fixed_and5_remaining_raw_deficits_replayed_bothstates=True,retained_regression_cost_types_sampled=sorted(cost_seen),public_trace={k:dict(v) for k,v in traces.items()},public_stack_subset={k:SP-m.stack_lowest for k,m in machines.items()},full_author648_vs640_stack_cost_retained_not_reswept=True,coefficient_ARM_calls=coefficient_calls,pack_ARM_calls=pack_calls,total_bare_calls=coefficient_calls+pack_calls,coefficient_equality_controls=equality,forced_coefficient_pack_points=forced,exact_RNE_Fraction_endpoint_checks=endpoints,bare_stack_bytes=SP-unit.stack_lowest,bare_SIO_accesses=sio[0],bare_PC_limited_to_unit=True,bare_fixture_preserved=True,PCS_SP_boundedwrites_checked_every_call=True,DIRTY28bytes_preserved_READY_not_dirty=True,bare_fixtures_abstract_not_additional_public_polynomial_inputs=True,own_total_ARM_calls=3*len(rows)+coefficient_calls+pack_calls,counts_instructions_not_physical_cycles=True,hardware_accessed=False,bare_rows=bare)
(O/'focused-arm.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='bare_rows'},indent=2))
