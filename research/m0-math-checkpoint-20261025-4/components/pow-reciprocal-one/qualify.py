"""Full same-corpus pow replay; every changed path has a fresh parent control."""
import gzip,json,sys,time
from collections import Counter
sys.dont_write_bytecode=True
from harness import *
from trace import reciprocal_trace,expected_saving
assert not(HERE/'FROZEN.json').exists()and not(HERE/'qualification.json').exists()
direct=json.loads((HERE/'direct-proof.json').read_bytes());assert direct['status']=='PASS_PRIVATE_NUMERATOR1_RNE_EXACT_PRODUCT_JOINS_AND_ALL_DENOMINATOR_CLASSES'
assert direct['candidate_ELF_sha256']==sha(HERE/'candidate.elf')
parent=machine('parent');candidate=machine('candidate');pt=reciprocal_trace(parent,'parent');ct=reciprocal_trace(candidate,'candidate')
filename='qualification-records.jsonl.gz';binding=json.loads((PARENT/'FROZEN.json').read_bytes())['files'][filename];assert sha(PARENT/filename)==binding['sha256']
old_loss=set();new_loss=set();counts=Counter();deltas=Counter();accelerated=Counter();remaining=[]
cases=variants=wrong=parent_calls=reciprocals=seeds=products=0;t=time.monotonic()
with gzip.open(PARENT/filename,'rt')as source,gzip.GzipFile(filename=str(HERE/filename),mode='wb',mtime=0)as output:
 for i,line in enumerate(source):
  r=json.loads(line);state=states[r['SIO']];x,y=int(r['x'],16),int(r['y'],16)
  for a in ct:a.clear()
  candidate.uc.mem_write(0xd0000060,state);got,_,cost=candidate.call('_ZN12compact_math3powEdd',x,y,count=True);state_after(candidate,state)
  assert got==int(r['candidate'],16)
  old=r['candidate_instructions'];saving=expected_saving(ct)
  assert cost==old-saving,(i,r,cost,saving)
  if ct[0]:
   for a in pt:a.clear()
   parent.uc.mem_write(0xd0000060,state);pvalue,_,pcost=parent.call('_ZN12compact_math3powEdd',x,y,count=True);parent_calls+=1;state_after(parent,state)
   assert pvalue==got and pcost==old and pt==ct,(i,pt,ct)
  else:assert cost==old
  if saving:accelerated[r['SIO']]+=1
  deltas[cost-old]+=1;reciprocals+=len(ct[0]);seeds+=len(ct[1]);products+=len(ct[2]);pair=r['x'],r['y']
  for name,ref in r['references'].items():
   variants+=1
   if not ref['correct_Qfplib']:wrong+=1;continue
   q=ref['instructions'];counts['faster'if cost<q else'equal'if cost==q else'slower']+=1
   if old>q:old_loss.add(pair)
   if cost>q:new_loss.add(pair);remaining.append(dict(x=r['x'],y=r['y'],SIO=r['SIO'],reference=name,parent=old,candidate=cost,Qfplib=q,candidate_output=f'{got:016X}',Qfplib_output=ref['output']))
  saved=dict(r,parent_reciprocal_instructions=old,candidate=f'{got:016X}',candidate_instructions=cost,reciprocal_calls=list(ct[0]),software_seed_divisors=list(ct[1]),first_product_reciprocals=list(ct[2]))
  output.write((json.dumps(saved,separators=(',',':'))+'\n').encode());cases=i+1
  if i%1024==0:
   progress=dict(completed_states=cases,total_states=241960,elapsed_seconds=time.monotonic()-t,parent_changed_path_replays=parent_calls)
   (HERE/'progress.json').write_text(json.dumps(progress,indent=2)+'\n');print('reciprocal1-full',cases,'/241960',round(time.monotonic()-t,1),flush=True)
assert cases==241960 and variants==279522 and len(old_loss)==11377 and not new_loss-old_loss
out=dict(status='PASS_FULL_PRIVATE_RECIPROCAL1_CORPUS_AND_EXACT_COST_DELTAS',candidate_ELF_sha256=sha(HERE/'candidate.elf'),unique_pairs=120980,profiled_states=cases,reference_state_variants=variants,
 fresh_candidate_ARM_calls=cases,fresh_parent_changed_path_ARM_calls=parent_calls,total_fresh_public_ARM_calls=cases+parent_calls,
 all_actual_cost_deltas_match_guard_product_seed_savings=True,all_parent_return_bits_and_reciprocal_arguments_identical=True,
 all_changed_paths_fresh_parent_replayed=True,parent_raw_loss_pairs=len(old_loss),candidate_raw_loss_pairs=len(new_loss),fixed_pairs=sorted(old_loss-new_loss),new_raw_loss_pairs=[],candidate_wrong=0,
 correct_Qfplib_comparison=dict(counts),wrong_Qfplib_state_variants_retained=wrong,instruction_delta_histogram=dict(sorted(deltas.items())),accelerated_states_by_SIO=dict(accelerated),
 reciprocal_calls=reciprocals,software_seed_calls=seeds,first_product_calls=products,parent_cost_increase_states=0,
 observed_stacks=dict(candidate=SP-candidate.stack_lowest,parent_changed_paths=SP-parent.stack_lowest),records_sha256=sha(HERE/filename),remaining=remaining,
 inherited_Qfplib_or_MPFR_not_fresh=True,elapsed_seconds=time.monotonic()-t,hardware_accessed=False,goal_complete=False)
(HERE/'qualification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k not in['remaining','fixed_pairs']},indent=2))
