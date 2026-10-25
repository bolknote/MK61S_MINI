"""Calibrate the clone and compare exact software/hardware states and IEEE bits."""
from pathlib import Path
from collections import Counter
import json,random,struct,sys,time
sys.dont_write_bytecode=True
from harness import *
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR
W=Path(__file__).resolve().parent
machines={n:machine(n)for n in ['parent','control','candidate','Qfplib']}
oracle=Oracle();rng=random.Random(0x614DD17025)
image=division_images['candidate'];captures={'control':[],'candidate':[]};seed_calls=[];active={}
def add_trace(label):
 m=machines[label];e=division_images[label]
 registers=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R12,UC_ARM_REG_SP]
 for symbol in ['mk61_m0_hint_join','mk61_m0_sw_join']:
  address=e.symbols[symbol]&~1
  def join(uc,pc,unused,user,label=label):
   sp=uc.reg_read(UC_ARM_REG_SP)
   captures[label].append(dict(registers=[uc.reg_read(r)for r in registers],frame=bytes(uc.mem_read(sp,20)).hex()))
  m.uc.hook_add(UC_HOOK_CODE,join,begin=address,end=address)
 entry=e.symbols['mk61_m0_hint_ddiv']&~1
 def flags(uc,pc,unused,user):uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28))
 m.uc.hook_add(UC_HOOK_CODE,flags,begin=entry,end=entry)
 def write(uc,access,address,size,value,user):
  if active.get('state')=='DIRTY':assert not 0xd0000060<=address<0xd000007c
 m.uc.hook_add(UC_HOOK_MEM_WRITE,write)
 if label=='candidate':
  address=e.symbols['mk61_m0_ddiv_seed17']&~1
  def seed(uc,pc,unused,user):
   assert uc.reg_read(UC_ARM_REG_SP)%8==0
   assert uc.reg_read(UC_ARM_REG_R0)==0xffffffff
   d=uc.reg_read(UC_ARM_REG_R1);assert 65536<=d<131072
   seed_calls.append(d)
  m.uc.hook_add(UC_HOOK_CODE,seed,begin=address,end=address)
for label in ['control','candidate']:add_trace(label)
jobs=[]
for row in json.loads((ROOT/'.build/m0-pow-reciprocal-hint-20261025/profile.json').read_bytes())['rows']:
 jobs.append((bits(1.),int(row['denominator'],16),'real_reciprocal'))
edges=[0,1,2,0xfffffffffffff,0x10000000000000,0x10000000000001,0x3fefffffffffffff,0x3ff0000000000000,0x3ff0000000000001,0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000000,0x7fffffffffffffff]
edges +=[v|(1<<63)for v in edges]
jobs +=[(a,b,'IEEE_edge')for a in edges for b in edges]
for i in range(1024):
 ea=rng.randrange(1,2047);eb=max(1,min(2046,ea+rng.randrange(-1000,1001)))
 a=(ea<<52)|rng.getrandbits(52)|(rng.getrandbits(1)<<63)
 b=(eb<<52)|rng.getrandbits(52)|(rng.getrandbits(1)<<63)
 jobs.append((a,b,'random_normal'))
# Sample the private seed divisors on actual normal mantissas, with high/low
# leading fractions and signs varied independently. These receive an exact
# integer/dyadic oracle; the directed MPFR subset is counted separately.
for d in range(65536,131072,256):
 a=(1023<<52)|rng.getrandbits(52)|(rng.getrandbits(1)<<63)
 b=(1023<<52)|((d-65536)<<36)|rng.getrandbits(36)|(rng.getrandbits(1)<<63)
 jobs.append((a,b,'sample_seed_divisors'))
def exact_normal(a,b):
 # Both exponents are1023 here; all outputs lie in [0.5,2], with signs.
 ma=(1<<52)|(a&((1<<52)-1));mb=(1<<52)|(b&((1<<52)-1))
 exponent=0 if ma>=mb else -1
 shift=52-exponent;n=ma<<shift;q,r=divmod(n,mb)
 if 2*r>mb or (2*r==mb and q&1):q+=1
 if q==(1<<53):q>>=1;exponent+=1
 return ((a^b)&(1<<63))|((1023+exponent)<<52)|(q-(1<<52))
calls=mpfr=shortcuts=wrong_q=state_checks=0;hist=Counter();groups=Counter();rows=[];t=time.monotonic()
for i,(a,b,group)in enumerate(jobs):
 if i%4096==0:print('direct',i,'/',len(jobs),flush=True)
 if group=='sample_seed_divisors':expected=exact_normal(a,b)
 else:
  expected=oracle.reference('ddiv',a,b)
  if any(((v>>52)&2047)==2047 and v&((1<<52)-1) and not v&(1<<51)for v in [a,b]):shortcuts+=1
  else:mpfr+=1
 for state_name,state in states.items():
  active.update(flags=i&15,state=state_name)
  for traces in captures.values():traces.clear()
  seed_calls.clear();results={}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state)
   function='qfp_ddiv'if label=='Qfplib'else'__aeabi_ddiv'if label=='parent'else'mk61_m0_hint_ddiv'
   got,_,cost=m.call(function,a,b,count=True);state_after(m,state);calls+=1
   results[label]=dict(output=f'{got:016X}',instructions=cost,correct=equal(got,expected,64))
  assert all(results[n]['correct']for n in ['parent','control','candidate']),(i,hex(a),hex(b),results,hex(expected))
  assert results['parent']==results['control'],(i,results)
  assert results['candidate']['output']==results['parent']['output']
  if state_name=='READY':
   assert results['candidate']['instructions']==results['parent']['instructions']
   assert captures['control']==captures['candidate'] and not seed_calls
  elif seed_calls:
   # DIRTY parent uses its old general C++ fallback. Compare new software
   # continuation to the matching READY hardware join from the same input.
   assert captures['candidate']==ready_capture,(i,captures,ready_capture)
   state_checks+=1
  if state_name=='READY':ready_capture=list(captures['control'])
  delta=results['candidate']['instructions']-results['parent']['instructions'];hist[delta]+=1
  assert delta<=0,(i,hex(a),hex(b),state_name,delta)
  wrong_q+=not results['Qfplib']['correct'];groups[group]+=1
  rows.append(dict(a=f'{a:016X}',b=f'{b:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',results=results,seed_divisors=list(seed_calls)))
out=dict(status='PASS_EXACT_DIRTY_SOFTWARE_DIVISION_READY_COST_UNCHANGED',pairs=len(jobs),states=2*len(jobs),
 actual_ARM_calls=calls,sampled_seed_divisors=256,standalone_seed_domain_exhaustive_65536=True,exact_integer_oracle_inputs=256,
 actual_directed_MPFR_inputs=mpfr,sNaN_policy_shortcuts=shortcuts,groups=dict(groups),
 matched_software_and_READY_hardware_join_states=state_checks,READY_instructions_unchanged=True,
 old_control_output_and_cost_equal=True,all_parent_raw_bits_equal=True,no_parent_cost_increase=True,
 parent_instruction_delta_histogram=dict(sorted(hist.items())),wrong_Qfplib_variants_retained=wrong_q,
 all_DIRTY_SIO_words_preserved_and_no_writes=True,seed_call_SP_8aligned=True,
 join_R0_R6_R12_SP_and_saved20B_frame_equal=True,rows=rows,elapsed_seconds=time.monotonic()-t,
 candidate_ELF_sha256=sha(W/'candidate.elf'),hardware_accessed=False,goal_complete=False)
(W/'direct-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items()if k!='rows'},indent=2))
