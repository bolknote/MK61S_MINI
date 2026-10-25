"""Fresh directed MPFR and real Qfplib public controls without domain filtering."""
from collections import Counter
import copy,json,sys,time
sys.dont_write_bytecode=True
from harness import *
from trace import reciprocal_trace,clear,equivalent,saving,public_trace
assert not(HERE/'FROZEN.json').exists()and not(HERE/'new-qualification.json').exists()
jobs={}
for r in json.loads((PARENT/'new-qualification.json').read_bytes())['rows']:jobs.setdefault((int(r['x'],16),int(r['y'],16)),r['group'])
assert len(jobs)==5127
machines={n:machine(n)for n in ['parent','control','candidate','Qfplib']};traces={n:reciprocal_trace(m,n)for n,m in machines.items()if n!='Qfplib'}
refs=['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer'];oracle=Oracle();rows=[];shortcuts=0;t=time.monotonic()
for i,((x,y),group)in enumerate(jobs.items()):
 if i%64==0:print('reciprocal-bound3-new',i,'/',len(jobs),round(time.monotonic()-t,1),flush=True)
 expected=oracle.reference('pow',x,y);shortcuts+=any((v&0x7fffffffffffffff)>0x7ff0000000000000 and not v&(1<<51)for v in [x,y])
 for state_name,sio in states.items():
  outputs,counts,correct,args={},{},{},{}
  for label in ['parent','control','candidate',*refs]:
   m=machines[label if label in machines else'Qfplib']
   if label not in refs:clear(traces[label])
   m.uc.mem_write(0xd0000060,sio);got,_,cost=m.call(label if label in refs else'_ZN12compact_math3powEdd',x,y,count=True);state_after(m,sio)
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
   if label not in refs:assert correct[label];args[label]=copy.deepcopy(traces[label])
  assert len({outputs[n]for n in ['parent','control','candidate']})==1 and counts['parent']==counts['control']
  equivalent(args['parent'],args['control'],seed_correction_changed=False);equivalent(args['control'],args['candidate'])
  assert counts['candidate']==counts['parent']-saving(args['candidate'])
  rows.append(dict(x=f'{x:016X}',y=f'{y:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,**public_trace(args['candidate'])))
def loss(row,label):return any(row['correct'][q]and row['instructions'][label]>row['instructions'][q]for q in refs)
old={(r['x'],r['y'])for r in rows if loss(r,'parent')};new={(r['x'],r['y'])for r in rows if loss(r,'candidate')}
out=dict(status='PASS_FRESH_MPFR_PRIVATE_BOUND3_SEED_PUBLIC_CONTROLS',candidate_ELF_sha256=sha(HERE/'candidate.elf'),unique_pairs=len(jobs),state_rows=len(rows),fresh_ARM_calls=6*len(rows),
 fresh_candidate_calls=len(rows),fresh_parent_calls=len(rows),fresh_layout_control_calls=len(rows),fresh_Qfplib_calls=3*len(rows),oracle_evaluations=len(jobs),actual_directed_MPFR_inputs=len(jobs)-shortcuts,sNaN_policy_shortcuts=shortcuts,MPFR_version=oracle.version,
 all_parent_control_candidate_return_bits_and_live_join_states_equal=True,all_actual_costs_match_removed_zero_operation_counts=True,
 parent_raw_loss_pairs=len(old),candidate_raw_loss_pairs=len(new),fixed_raw_pairs=len(old-new),new_raw_loss_pairs=sorted(new-old),candidate_wrong=0,
 wrong_Qfplib_state_variants_retained=sum(not r['correct'][q]for r in rows for q in refs),strict_quiet_NaN_reference_policy=True,no_nominal_reference_domain_filter=True,
 instruction_delta_histogram=dict(sorted(Counter(r['instructions']['candidate']-r['instructions']['parent']for r in rows).items())),
 observed_stacks={n:SP-m.stack_lowest for n,m in machines.items()if n!='Qfplib'},rows=rows,elapsed_seconds=time.monotonic()-t,hardware_accessed=False,goal_complete=False)
(HERE/'new-qualification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='rows'},indent=2))
