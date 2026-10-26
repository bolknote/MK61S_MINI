"""Original153 actual pow pilot with all three Qfplib compositions retained."""
from collections import Counter
import json,sys,time
sys.dont_write_bytecode=True
from harness import *
from unicorn.arm_const import UC_ARM_REG_SP
assert not (HERE/'probe.json').exists()
jobs=json.loads((PARENT/'original153.json').read_bytes())['rows']
machines={n:machine(n)for n in ['parent','control','candidate','Qfplib']}
captures={n:[]for n in ['control','candidate']};seeds=[]
for label in captures:
 m=machines[label];e=division_images[label];address=e.symbols['mk61_m0_hint_ddiv']&~1
 def entry(uc,pc,unused,user,label=label):
  a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32)
  b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
  assert a==bits(1.)
  captures[label].append(dict(numerator=f'{a:016X}',denominator=f'{b:016X}'))
 m.uc.hook_add(UC_HOOK_CODE,entry,begin=address,end=address)
m=machines['candidate'];address=division_images['candidate'].symbols['mk61_m0_ddiv_seed17']&~1
def seed(uc,pc,unused,user):
 assert uc.reg_read(UC_ARM_REG_SP)%8==0
 seeds.append(uc.reg_read(UC_ARM_REG_R1))
m.uc.hook_add(UC_HOOK_CODE,seed,begin=address,end=address)
oracle=Oracle();rows=[];start=time.monotonic()
references=['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']
for i,row in enumerate(jobs):
 if i%32==0:print('reciprocal-soft-pilot',i,'/',len(jobs),flush=True)
 x,y=int(row['x'],16),int(row['y'],16);expected=oracle.reference('pow',x,y)
 for state_name,state in states.items():
  outputs,counts,correct={},{},{}
  for values in captures.values():values.clear()
  seeds.clear()
  for label in ['parent','control','candidate',*references]:
   m=machines[label if label in machines else 'Qfplib'];m.uc.mem_write(0xd0000060,state)
   got,_,cost=m.call(label if label in references else '_ZN12compact_math3powEdd',x,y,count=True)
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64);state_after(m,state)
  assert all(correct[n]for n in ['parent','control','candidate'])
  assert outputs['parent']==outputs['control']==outputs['candidate']
  assert counts['parent']==counts['control']
  assert counts['parent']==next(v['candidate']for v in row['states']if v['SIO']==state_name)
  assert captures['control']==captures['candidate']
  assert counts['candidate']<=counts['parent']
  if state_name=='READY':assert counts['candidate']==counts['parent']and not seeds
  rows.append(dict(x=row['x'],y=row['y'],stream=row['stream'],reference=row['reference'],SIO=state_name,
   expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,
   reciprocal_calls=list(captures['candidate']),software_seed_divisors=list(seeds)))
def loss(row,label):return row['correct'][row['reference']]and row['instructions'][label]>row['instructions'][row['reference']]
old={(r['x'],r['y'])for r in rows if loss(r,'parent')};new={(r['x'],r['y'])for r in rows if loss(r,'candidate')}
assert not new-old
out=dict(status='EXPERIMENTAL_DIRTY_RECIPROCAL_ORIGINAL153_PILOT_NOT_FULL_QUALIFICATION',
 candidate_ELF_sha256=sha(HERE/'candidate.elf'),actual_ARM_calls=6*len(rows),actual_directed_MPFR_inputs=len(jobs),
 candidate_wrong=0,parent_remaining=len(old),candidate_remaining=len(new),fixed_pairs=sorted(old-new),new_raw_losses=0,
 READY_instruction_counts_identical=True,all_reciprocal_operands_and_parent_raw_bits_identical=True,
 software_seed_calls=sum(len(r['software_seed_divisors'])for r in rows),
 cost_delta_histogram=dict(sorted(Counter(r['instructions']['candidate']-r['instructions']['parent']for r in rows).items())),
 parent_cost_increase_states=0,wrong_Qfplib_variants_retained=sum(not r['correct'][q]for r in rows for q in references),
 observed_stacks={n:SP-m.stack_lowest for n,m in machines.items()if n!='Qfplib'},
 rows=rows,elapsed_seconds=time.monotonic()-start,hardware_accessed=False,goal_complete=False)
(HERE/'probe.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items()if k!='rows'},indent=2))
