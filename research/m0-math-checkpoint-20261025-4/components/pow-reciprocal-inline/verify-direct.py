"""Private1/x contract, exact state joins and all binary64 denominator classes."""
from collections import Counter
import gzip,json,random,struct,sys,time
sys.dont_write_bytecode=True
from harness import *
from model import expected_cost
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR
assert not(HERE/'direct-proof.json').exists()
machines={n:machine(n)for n in ['parent','control','candidate','Qfplib']}
active={};traces={n:dict(first=[],after=[],seed=[])for n in ['control','candidate']};rng=random.Random(0x6141C1)
regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR]
for label in traces:
 m=machines[label];image=division_images[label]
 for tag in ['mk61_m0_reciprocal1','mk61_m0_reciprocal1_sw']:
  address=image.symbols[tag+'_first_product']&~1
  def first(uc,pc,unused,user,label=label):
   assert uc.reg_read(UC_ARM_REG_R0)==0
   traces[label]['first'].append(uc.reg_read(UC_ARM_REG_R6))
  m.uc.hook_add(UC_HOOK_CODE,first,begin=address,end=address)
  address=image.symbols[tag+'_after_second_product']&~1
  def after(uc,pc,unused,user,label=label):
   sp=uc.reg_read(UC_ARM_REG_SP);values=[uc.reg_read(r)for r in regs];values[-1]&=0xf0000000
   traces[label]['after'].append(dict(registers=values,frame=bytes(uc.mem_read(sp,28)).hex()))
  m.uc.hook_add(UC_HOOK_CODE,after,begin=address,end=address)
 address=image.symbols[linked['images'][label]['entry_symbol']]&~1
 def entry(uc,pc,unused,user):
  assert uc.reg_read(UC_ARM_REG_R0)==0 and uc.reg_read(UC_ARM_REG_R1)==0x3ff00000
  uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,active['r12'])
 m.uc.hook_add(UC_HOOK_CODE,entry,begin=address,end=address)
 address=image.symbols[linked['images'][label]['seed_symbol']]&~1
 def seed(uc,pc,unused,user,label=label):
  assert uc.reg_read(UC_ARM_REG_SP)%8==0 if label=='control'else uc.reg_read(UC_ARM_REG_SP)==SP-20
  d=uc.reg_read(UC_ARM_REG_R1);assert 65536<=d<131072
  traces[label]['seed'].append(d)
 m.uc.hook_add(UC_HOOK_CODE,seed,begin=address,end=address)
 def writes(uc,access,address,size,value,user):
  if active['state']=='DIRTY':assert not 0xd0000060<=address<0xd000007c
 m.uc.hook_add(UC_HOOK_MEM_WRITE,writes)
jobs=[]
edges=[0,1,2,0x80000,0xfffffffffffff,0x10000000000000,0x10000000000001,0x3fefffffffffffff,0x3ff0000000000000,0x3ff0000000000001,0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000000,0x7fffffffffffffff]
edges +=[v|(1<<63)for v in edges]
for b in edges:
 for flags in range(16):jobs.append((b,flags,'all16_flags_IEEE_edges'))
for exponent in range(2048):
 for sign in [0,1]:jobs.append(((sign<<63)|(exponent<<52)|rng.getrandbits(52),rng.randrange(16),'all_exponents_signs'))
for i in range(4096):jobs.append((rng.getrandbits(64),i&15,'random_bits'))
for i in range(4096):
 d=65536+(i*65536//4096);b=(1023<<52)|((d-65536)<<36)|rng.getrandbits(36)
 jobs.append((b,i&15,'normal_seed_samples'))
for magnitude in range((1<<50)-1024,(1<<50)+1025):
 for sign in [0,1]:jobs.append(((sign<<63)|magnitude,magnitude&15,'overflow_threshold_neighbours'))
for magnitude in range((1<<50)-32,(1<<50)+33):
 for sign in [0,1]:
  for flags in range(16):jobs.append(((sign<<63)|magnitude,flags,'all16_flags_overflow_threshold'))
for i in range(2048):jobs.append((rng.randrange(1,1<<52)|(rng.getrandbits(1)<<63),i&15,'random_subnormal'))
oracle=Oracle();rows=[];hist=Counter();comparisons={n:Counter()for n in ['parent','candidate']};calls=shortcuts=first_calls=0;t=time.monotonic()
with gzip.GzipFile(filename=str(HERE/'direct-records.jsonl.gz'),mode='wb',mtime=0)as output:
 for i,(b,flags,group)in enumerate(jobs):
  if i%1024==0:print('reciprocal1-direct',i,'/',len(jobs),round(time.monotonic()-t,1),flush=True)
  expected=oracle.reference('ddiv',bits(1.),b);shortcuts+=((b&0x7fffffffffffffff)>0x7ff0000000000000 and not b&(1<<51))
  for state_name,state in states.items():
   active.update(flags=flags,r12=rng.getrandbits(32),state=state_name)
   for tr in traces.values():
    for values in tr.values():values.clear()
   results={}
   for label,m in machines.items():
    function='qfp_ddiv'if label=='Qfplib'else linked['images']['candidate'if label=='candidate'else'control']['entry_symbol']
    m.uc.mem_write(0xd0000060,state);got,_,cost=m.call(function,bits(1.),b,count=True);state_after(m,state);calls+=1
    results[label]=dict(output=f'{got:016X}',instructions=cost,correct=equal(got,expected,64))
   assert all(results[n]['correct']for n in ['parent','control','candidate']),(i,hex(b),results,hex(expected))
   assert results['parent']==results['control']
   assert results['candidate']['output']==results['parent']['output']
   assert traces['control']==traces['candidate'],(i,hex(b),traces)
   count=len(traces['candidate']['first']);seed=len(traces['candidate']['seed']);first_calls+=count
   delta=results['candidate']['instructions']-results['parent']['instructions'];predicted_cost=expected_cost(b,results['parent']['instructions'],traces['candidate']['first'],traces['candidate']['seed'])
   assert results['candidate']['instructions']==predicted_cost,(i,hex(b),state_name,delta,predicted_cost,results)
   hist[delta]+=1
   if results['Qfplib']['correct']:
    q=results['Qfplib']['instructions']
    for n in comparisons:
     cost=results[n]['instructions'];comparisons[n]['faster'if cost<q else'equal'if cost==q else'slower']+=1
   row=dict(denominator=f'{b:016X}',NZCV=flags,group=group,SIO=state_name,expected=f'{expected:016X}',results=results,first_product_calls=count,software_seed_divisors=list(traces['candidate']['seed']))
   output.write((json.dumps(row,separators=(',',':'))+'\n').encode())
   if group=='all16_flags_IEEE_edges':rows.append(row)
out=dict(status='PASS_PRIVATE_INLINE_SEED_TINY_OVERFLOW_ALL_DENOMINATOR_CLASSES',pairs=len(jobs),states=2*len(jobs),actual_ARM_calls=calls,
 actual_directed_MPFR_inputs=len(jobs)-shortcuts,sNaN_policy_shortcuts=shortcuts,MPFR_version=oracle.version,
 numerator_contract='exact positive1 only; denominator any binary64',all_parent_return_bits_equal=True,
 all_after_second_product_R0_R7_R12_SP_NZCV_frame28B_identical=True,
 direct_first_product_calls=first_calls,all_actual_costs_match_special_guard_sign_and_inline_model=True,
 instruction_delta_histogram=dict(sorted(hist.items())),correct_Qfplib_comparisons={n:dict(v)for n,v in comparisons.items()},
 all_Qfplib_raw_outputs_costs_and_flags_retained=True,DIRTY_SIO_preserved_no_writes=True,old_seed_call_SP8aligned_new_inline_live_SP20_checked=True,
 observed_stacks={n:SP-m.stack_lowest for n,m in machines.items()if n!='Qfplib'},rows=rows,
 candidate_ELF_sha256=sha(HERE/'candidate.elf'),records_sha256=sha(HERE/'direct-records.jsonl.gz'),elapsed_seconds=time.monotonic()-t,hardware_accessed=False,goal_complete=False)
(HERE/'direct-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='rows'},indent=2))
