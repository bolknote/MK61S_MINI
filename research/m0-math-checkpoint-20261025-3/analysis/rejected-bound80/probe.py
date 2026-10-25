"""Experimental public original153 pilot, all three Qfplib references retained."""
import json,sys,time
from collections import Counter
sys.dont_write_bytecode=True
from harness import *
jobs=json.loads((PARENT/'original153.json').read_bytes())['rows']
machines={n:machine(n)for n in ['parent','control','candidate','Qfplib']}
traces={n:trace_boundaries(m,n)for n,m in machines.items()if n!='Qfplib'}
oracle=Oracle();rows=[];start=time.monotonic()
references=['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']
for i,row in enumerate(jobs):
 if i%32==0:print('bound80-pilot',i,'/',len(jobs),'elapsed',round(time.monotonic()-start,1),flush=True)
 x,y=int(row['x'],16),int(row['y'],16);expected=oracle.reference('pow',x,y)
 for state_name,state in states.items():
  outputs,counts,correct,args,declines={},{},{},{},{}
  for label in ['parent','control','candidate',*references]:
   m=machines[label if label in machines else 'Qfplib']
   if label not in references:
    traces[label][0].clear();traces[label][1].clear()
   m.uc.mem_write(0xd0000060,state)
   got,_,cost=m.call(label if label in references else '_ZN12compact_math3powEdd',x,y,count=True)
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
   state_after(m,state)
   if label not in references:
    assert correct[label],(i,label,hex(x),hex(y),hex(got),hex(expected))
    args[label]=list(traces[label][0]);declines[label]=len(traces[label][1])
  assert outputs['parent']==outputs['control']==outputs['candidate']
  assert counts['parent']==counts['control']
  assert args['parent']==args['control']==args['candidate']
  assert counts['parent']==next(v['candidate']for v in row['states']if v['SIO']==state_name)
  rows.append(dict(x=row['x'],y=row['y'],stream=row['stream'],reference=row['reference'],SIO=state_name,
    expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,
    boundary_calls=args['candidate'],fallback_calls=declines['candidate']))
def loss(r,label):return r['correct'][r['reference']]and r['instructions'][label]>r['instructions'][r['reference']]
old={(r['x'],r['y'])for r in rows if loss(r,'parent')};new={(r['x'],r['y'])for r in rows if loss(r,'candidate')}
out=dict(status='EXPERIMENTAL_BOUND80_ORIGINAL153_PILOT',candidate_ELF_sha256=sha(HERE/'candidate.elf'),
 actual_ARM_calls=6*len(rows),actual_MPFR_inputs=len(jobs),candidate_wrong=0,parent_remaining=len(old),candidate_remaining=len(new),
 fixed_pairs=sorted(old-new),new_raw_loss_pairs=sorted(new-old),
 boundary_calls=sum(len(r['boundary_calls'])for r in rows),fallback_calls=sum(r['fallback_calls']for r in rows),
 cost_delta_histogram=dict(sorted(Counter(r['instructions']['candidate']-r['instructions']['parent']for r in rows).items())),
 stacks={n:SP-m.stack_lowest for n,m in machines.items()if n!='Qfplib'},rows=rows,hardware_accessed=False)
(HERE/'probe.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items()if k!='rows'},indent=2))
