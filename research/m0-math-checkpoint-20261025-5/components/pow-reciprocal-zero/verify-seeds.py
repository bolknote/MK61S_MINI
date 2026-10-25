"""Expand scalar qualification across every seed divisor and full mantissas."""
from collections import Counter
import gzip,json,sys,time
sys.dont_write_bytecode=True
from harness import *
from trace import reciprocal_trace,clear,equivalent,saving,public_trace
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R12,UC_ARM_REG_XPSR
assert not(HERE/'FROZEN.json').exists()and not(HERE/'expanded-seed-proof.json').exists()
machines={n:machine(n)for n in ['parent','candidate','Qfplib']}
traces={n:reciprocal_trace(machines[n],n,root=False)for n in ['parent','candidate']};active={}
for label in traces:
 m=machines[label];image=division_images['candidate'if label=='candidate'else'control']
 address=image.symbols['mk61_m0_reciprocal1']&~1
 def entry(uc,pc,unused,user):
  uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,active['r12'])
 m.uc.hook_add(UC_HOOK_CODE,entry,begin=address,end=address)
 def writes(uc,access,address,size,value,user):
  if active['state']=='DIRTY':assert not 0xd0000060<=address<0xd000007c
 m.uc.hook_add(UC_HOOK_MEM_WRITE,writes)
oracle=Oracle();calls=cases=wrong=0;comparisons={n:Counter()for n in ['parent','candidate']};hist=Counter();classes=Counter();losses={n:set()for n in comparisons};observed=set();remaining=[];t=time.monotonic()
with gzip.GzipFile(filename=str(HERE/'expanded-seed-records.jsonl.gz'),mode='wb',mtime=0)as output:
 for D in range(65536,131072):
  low_words=[0,((D*0x9e3779b97f4a7c15)^(D>>3))&((1<<36)-1)|1]
  for pattern,low in enumerate(low_words):
   b=(1023<<52)|((D-65536)<<36)|low
   expected=oracle.reference('ddiv',bits(1.),b);cases+=1
   for state_name,sio in states.items():
    active.update(flags=(D+pattern)&15,r12=0xa5a50000|D,state=state_name)
    for trace in traces.values():clear(trace)
    results={}
    for label,m in machines.items():
     m.uc.mem_write(0xd0000060,sio);got,_,cost=m.call('qfp_ddiv'if label=='Qfplib'else'mk61_m0_reciprocal1',bits(1.),b,count=True);state_after(m,sio);calls+=1
     results[label]=dict(output=f'{got:016X}',instructions=cost,correct=got==expected)
    assert results['parent']['correct']and results['candidate']['correct'],(D,pattern,state_name,results)
    assert results['parent']['output']==results['candidate']['output'];equivalent(traces['parent'],traces['candidate'])
    delta=results['candidate']['instructions']-results['parent']['instructions']
    assert delta==-saving(traces['candidate'])and delta<=0,(D,pattern,state_name,delta,traces)
    hist[delta]+=1
    for v in traces['candidate']['seeds']:observed.add(v);assert v==D
    for cert in traces['candidate']['certificates']:classes['certified'if cert['fast']else'full']+=1
    qfp=results['Qfplib'];key=(D,pattern,state_name)
    if not qfp['correct']:wrong+=1
    else:
     for label in comparisons:
      c,v=results[label]['instructions'],qfp['instructions'];comparisons[label]['faster'if c<v else'equal'if c==v else'slower']+=1
      if c>v:losses[label].add(key)
    row=dict(D=D,pattern=pattern,denominator=f'{b:016X}',NZCV=active['flags'],SIO=state_name,expected=f'{expected:016X}',results=results,**public_trace(traces['candidate']))
    output.write((json.dumps(row,separators=(',',':'))+'\n').encode())
    if key in losses['candidate']:remaining.append(row)
  if D%2048==0:
   progress=dict(completed_seed_divisors=D-65535,total_seed_divisors=65536,completed_inputs=cases,actual_ARM_calls=calls,elapsed_seconds=time.monotonic()-t)
   (HERE/'seed-progress.json').write_text(json.dumps(progress,indent=2)+'\n');print('reciprocal-zero-seeds',D-65535,'/65536',round(time.monotonic()-t,1),flush=True)
assert cases==131072 and calls==786432 and not losses['candidate']-losses['parent']
out=dict(status='PASS_EXPANDED_ALL_SEED_DIVISORS_TWO_MANTISSA_PATTERNS',candidate_ELF_sha256=sha(HERE/'candidate.elf'),input_seed_divisors=65536,patterns_per_divisor=2,
 fresh_scalar_inputs=cases,states=2*cases,actual_ARM_calls=calls,actual_directed_MPFR_inputs=cases,sNaN_policy_shortcuts=0,MPFR_version=oracle.version,
 actual_software_seed_divisors_observed=len(observed),correct_Qfplib_comparisons={n:dict(v)for n,v in comparisons.items()},
 parent_loss_states=len(losses['parent']),candidate_loss_states=len(losses['candidate']),new_loss_states=0,wrong_Qfplib_variants_retained=wrong,
 parent_instruction_delta_histogram=dict(sorted(hist.items())),certificate_calls_by_class=dict(classes),all_parent_costs_no_lower_than_candidate=True,
 all_live_joins_full_after_y_residual_and_certificate_decisions_checked=True,DIRTY_SIO_preserved_no_writes=True,
 observed_stacks={n:SP-m.stack_lowest for n,m in machines.items()if n!='Qfplib'},records_sha256=sha(HERE/'expanded-seed-records.jsonl.gz'),
 remaining=remaining,elapsed_seconds=time.monotonic()-t,hardware_accessed=False,goal_complete=False)
(HERE/'expanded-seed-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='remaining'},indent=2))
