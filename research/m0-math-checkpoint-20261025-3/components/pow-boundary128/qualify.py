"""Fresh whole-union replay; reexecute parent on every changed boundary path."""
import gzip,json,sys,time
from collections import Counter
sys.dont_write_bytecode=True
from harness import *
assert not (HERE/'FROZEN.json').exists() and not (HERE/'qualification.json').exists()
parent=machine('parent');candidate=machine('candidate')
pt,ct=trace_boundaries(parent,'parent'),trace_boundaries(candidate,'candidate')
binding=json.loads((PARENT/'FROZEN.json').read_bytes())['files']['union-records.jsonl.gz']
assert sha(PARENT/'union-records.jsonl.gz')==binding['sha256']
old_losses=set();new_losses=set();comparisons=Counter();deltas=Counter();remaining=[]
wrong=variants=cases=parent_calls=entry_calls=0;start=time.monotonic()
with gzip.open(PARENT/'union-records.jsonl.gz','rt')as source,gzip.GzipFile(filename=str(HERE/'qualification-records.jsonl.gz'),mode='wb',mtime=0)as output:
 for i,line in enumerate(source):
  row=json.loads(line);x,y=int(row['x'],16),int(row['y'],16);state=states[row['SIO']]
  ct[0].clear();ct[1].clear();candidate.uc.mem_write(0xd0000060,state)
  got,_,cost=candidate.call('_ZN12compact_math3powEdd',x,y,count=True);state_after(candidate,state)
  assert got==int(row['candidate'],16),(i,row,hex(got))
  previous=row['candidate_instructions'];entries=list(ct[0]);operands=list(ct[1]);entry_calls+=len(entries)
  if entries:
   pt[0].clear();pt[1].clear();parent.uc.mem_write(0xd0000060,state)
   pgot,_,pcost=parent.call('_ZN12compact_math3powEdd',x,y,count=True);parent_calls+=1;state_after(parent,state)
   assert pgot==got and pcost==previous
   assert pt[0]==entries and pt[1]==operands,(i,entries,pt[0],operands,pt[1])
  else:assert cost==previous,(i,row,cost)
  deltas[cost-previous]+=1;pair=row['x'],row['y']
  for name,ref in row['references'].items():
   variants+=1
   if not ref['correct_Qfplib']:wrong+=1;continue
   q=ref['instructions'];comparisons['faster'if cost<q else'equal'if cost==q else'slower']+=1
   if previous>q:old_losses.add(pair)
   if cost>q:
    new_losses.add(pair);remaining.append(dict(x=row['x'],y=row['y'],SIO=row['SIO'],reference=name,parent=previous,candidate=cost,Qfplib=q,
     candidate_output=f'{got:016X}',Qfplib_output=ref['output'],new_loss=previous<=q))
  saved=dict(row,parent_boundary_instructions=previous,candidate=f'{got:016X}',candidate_instructions=cost,
             boundary_calls=entries,midpoint_operands=operands)
  output.write((json.dumps(saved,separators=(',',':'))+'\n').encode());cases=i+1
  if i%1024==0:
   progress=dict(completed_states=cases,total_states=241960,elapsed_seconds=time.monotonic()-start,parent_boundary_path_replays=parent_calls)
   (HERE/'progress.json').write_text(json.dumps(progress,indent=2)+'\n');print('boundary128-full',cases,'/241960',round(progress['elapsed_seconds'],1),flush=True)
assert cases==241960 and variants==279522 and len(old_losses)==11434
result=dict(status='FULL_PREVIOUS_POW_UNION_EXACT_BOUNDARY_REPLAY',candidate_ELF_sha256=sha(HERE/'candidate.elf'),
 unique_pairs=120980,profiled_states=cases,reference_state_variants=variants,fresh_candidate_ARM_calls=cases,
 fresh_parent_changed_path_ARM_calls=parent_calls,total_fresh_public_ARM_calls=cases+parent_calls,
 inherited_Qfplib_or_MPFR_not_fresh=True,all_parent_raw_return_bits_identical=True,
 all_changed_paths_fresh_parent_costs_and24byte_midpoint_operands_identical=True,
 parent_raw_loss_pairs=len(old_losses),candidate_raw_loss_pairs=len(new_losses),fixed_pairs=sorted(old_losses-new_losses),
 new_raw_loss_pairs=sorted(new_losses-old_losses),correct_Qfplib_comparison=dict(comparisons),
 wrong_Qfplib_state_variants_retained=wrong,parent_cost_delta_histogram=dict(sorted(deltas.items())),
 parent_cost_increase_states=sum(c for d,c in deltas.items()if d>0),candidate_wrong=0,
 boundary_calls=entry_calls,observed_stacks=dict(candidate=SP-candidate.stack_lowest,parent_changed_paths=SP-parent.stack_lowest),
 record_sha256=sha(HERE/'qualification-records.jsonl.gz'),elapsed_seconds=time.monotonic()-start,remaining=remaining,hardware_accessed=False)
(HERE/'qualification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items()if k not in ['remaining','fixed_pairs','new_raw_loss_pairs']},indent=2))
