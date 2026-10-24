"""Freshly execute every previous pow state after the equivalent scalar kernel change."""
import gzip,json,time,sys
from collections import Counter
sys.dont_write_bytecode=True
from harness import *

binding=json.loads((HERE/'corpus-binding.json').read_text())
assert sha(HERE/'parent-corpus.jsonl.gz')==binding['corpus_sha256']
m=square_machine('candidate');calls=square_trace(m)
parent_losses=set();candidate_losses=set();fixed_pairs=set();remaining=[];comparison=Counter();deltas=Counter();class_hist=Counter()
wrong=variants=total_square_calls=0;start=time.monotonic();cases=0
with gzip.open(HERE/'parent-corpus.jsonl.gz','rt') as src,gzip.GzipFile(filename=str(HERE/'qualification-records.jsonl.gz'),mode='wb',mtime=0) as out:
 for i,line in enumerate(src):
  row=json.loads(line);state=states[row['SIO']];calls.clear();m.uc.mem_write(0xd0000060,state)
  value,_,cost=m.call('_ZN12compact_math3powEdd',int(row['x'],16),int(row['y'],16),count=True)
  state_after(m,state)
  assert value==int(row['parent_output'],16),(i,row,hex(value))
  delta=sum(c['new_cost']-c['old_cost'] for c in calls)
  assert cost==row['parent_cost']+delta and delta<=0,(i,row,cost,delta,calls)
  total_square_calls+=len(calls);deltas[delta]+=1
  for c in calls:class_hist[c['old_cost'],c['new_cost']]+=1
  pair=(row['x'],row['y'])
  for name,reference in row['references'].items():
   variants+=1
   if not reference['correct_Qfplib']:wrong+=1;continue
   q=reference['instructions'];comparison['faster' if cost<q else 'equal' if cost==q else 'slower']+=1
   if row['parent_cost']>q:parent_losses.add(pair)
   if cost>q:
    assert row['parent_cost']>q
    candidate_losses.add(pair);remaining.append(dict(x=row['x'],y=row['y'],SIO=row['SIO'],reference=name,
      candidate=cost,parent=row['parent_cost'],Qfplib=q,expected=row['expected'],candidate_output=f'{value:016X}',Qfplib_output=reference['output']))
  record=dict(row,candidate=f'{value:016X}',candidate_instructions=cost,square_calls=list(calls))
  out.write((json.dumps(record,separators=(',',':'))+'\n').encode());cases=i+1
  if i%1024==0:
   progress=dict(completed_states=cases,total_states=binding['states'],elapsed_seconds=time.monotonic()-start,candidate_wrong=0,observed_loss_pairs=len(candidate_losses))
   (HERE/'progress.json').write_text(json.dumps(progress,indent=2)+'\n')
   print('square128-full',cases,'/',binding['states'],'elapsed',round(progress['elapsed_seconds'],1),flush=True)
assert cases==232936 and variants==252450 and len(parent_losses)==10853
fixed_pairs=parent_losses-candidate_losses
result=dict(status='PASS_FULL_PARENT_POW_UNION_AFTER_EXACT_KERNEL_REPLACEMENT',candidate_ELF_sha256=sha(HERE/'candidate.elf'),
 unique_pairs=116468,profiled_states=cases,reference_state_variants=variants,fresh_candidate_ARM_calls=cases,
 fresh_parent_Qfplib_or_MPFR_calls=0,all_parent_raw_output_bits_identical=True,all_actual_costs_match_universal_kernel_delta=True,
 no_nominal_reference_domain_filter=True,wrong_Qfplib_state_variants_retained=wrong,correct_Qfplib_comparison=dict(comparison),
 parent_raw_loss_pairs=len(parent_losses),candidate_raw_loss_pairs=len(candidate_losses),fixed_raw_pairs=len(fixed_pairs),
 fixed_pair_values=sorted(fixed_pairs),new_raw_losses=0,candidate_wrong=0,actual_kernel_calls=total_square_calls,
 kernel_class_counts={str(k):v for k,v in class_hist.items()},parent_cost_delta_histogram=dict(sorted(deltas.items())),
 observed_candidate_stack_bytes=SP-m.stack_lowest,record_sha256=sha(HERE/'qualification-records.jsonl.gz'),
 elapsed_seconds=time.monotonic()-start,remaining=remaining,hardware_accessed=False)
(HERE/'qualification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['remaining','fixed_pair_values']},indent=2))
