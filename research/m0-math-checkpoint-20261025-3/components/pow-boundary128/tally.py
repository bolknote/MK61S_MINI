"""Recount the complete same corpus and verify all fresh overlap records."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1];BASE=ROOT/'.build/m0-pow-square128-r2-20261025'
q=json.loads((W/'qualification.json').read_bytes());fresh=json.loads((W/'new-qualification.json').read_bytes());unit=json.loads((W/'unit-proof.json').read_bytes())
states={};counts=Counter();deltas=Counter();old_loss=set();new_loss=set();wrong=variants=0
def equal(a,b):
 a,b=int(a,16),int(b,16)
 return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
with gzip.open(W/'qualification-records.jsonl.gz','rt')as stream:
 for line in stream:
  r=json.loads(line);key=r['x'],r['y'],r['SIO'];assert key not in states
  assert equal(r['candidate'],r['expected'])
  states[key]=r;c,p=r['candidate_instructions'],r['parent_boundary_instructions'];assert c<=p
  deltas[c-p]+=1
  for name,ref in r['references'].items():
   variants+=1;assert ref['correct_Qfplib']==equal(ref['output'],r['expected'])
   if not ref['correct_Qfplib']:wrong+=1;continue
   v=ref['instructions'];counts['faster'if c<v else'equal'if c==v else'slower']+=1
   if p>v:old_loss.add(key[:2])
   if c>v:new_loss.add(key[:2])
assert len(states)==241960 and variants==279522 and old_loss==new_loss and len(new_loss)==11434
for row in fresh['rows']:
 saved=states[row['x'],row['y'],row['SIO']]
 assert saved['expected']==row['expected']and saved['candidate']==row['outputs']['candidate']
 assert saved['candidate_instructions']==row['instructions']['candidate']
 assert saved['parent_boundary_instructions']==row['instructions']['parent']==row['instructions']['control']
 assert saved['boundary_calls']==row['boundary_calls']and saved['midpoint_operands']==row['midpoint_operands']
 for name in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']:
  ref=saved['references'][name]
  assert (ref['output'],ref['instructions'],ref['correct_Qfplib'])==(row['outputs'][name],row['instructions'][name],row['correct'][name])
original=[];hist={name:Counter()for name in ['parent','candidate']}
for row in json.loads((BASE/'original153.json').read_bytes())['rows']:
 observations=[]
 for state in ['READY','DIRTY']:
  s=states[row['x'],row['y'],state];ref=s['references'][row['reference']];assert ref['correct_Qfplib']
  observations.append(dict(SIO=state,parent=s['parent_boundary_instructions'],candidate=s['candidate_instructions'],Qfplib=ref['instructions']))
 for name in hist:
  kind='slower'if any(s[name]>s['Qfplib']for s in observations)else'equal'if any(s[name]==s['Qfplib']for s in observations)else'strict'
  hist[name][kind]+=1
 original.append(dict(x=row['x'],y=row['y'],stream=row['stream'],reference=row['reference'],states=observations))
assert hist['parent']==hist['candidate']==dict(slower=34,strict=119)
total=q['total_fresh_public_ARM_calls']+fresh['fresh_ARM_calls']+unit['actual_ARM_calls'];assert total==309938
out=dict(status='PASS_SAME_CORPUS_ACCOUNTING_AND_ALL_FRESH_OVERLAPS',unique_pairs=120980,states=len(states),reference_state_variants=variants,
 parent_raw_loss_pairs=len(old_loss),candidate_raw_loss_pairs=len(new_loss),fixed_pairs=0,new_raw_losses=0,candidate_wrong=0,
 all10254_fresh_control_state_rows_match_full_saved_actual_records=True,
 correct_Qfplib_comparison=dict(counts),wrong_Qfplib_state_variants_retained=wrong,
 strict_quiet_NaN_reference_classification_no_nominal_filter=True,
 parent_cost_delta_histogram=dict(sorted(deltas.items())),parent_cost_increase_states=0,
 accelerated_states=sum(c for d,c in deltas.items()if d<0),original153={n:dict(v)for n,v in hist.items()},
 total_qualified_fresh_ARM_calls=total,fresh_full_candidate_calls=q['fresh_candidate_ARM_calls'],
 fresh_full_changed_path_parent_calls=q['fresh_parent_changed_path_ARM_calls'],fresh_new_public_calls=fresh['fresh_ARM_calls'],fresh_bare_calls=unit['actual_ARM_calls'],
 actual_directed_MPFR_inputs=fresh['actual_directed_MPFR_inputs'],sNaN_shortcuts=fresh['sNaN_policy_shortcuts'],oracle_evaluations=fresh['oracle_evaluations'],
 pilot1836_failed_preflight0_and_rejected_bound80_all_excluded=True,
 inherited_Qfplib_parent_oldMPFR_not_fresh=True,goal_complete=False)
(W/'original153.json').write_text(json.dumps(dict(rows=original),indent=2)+'\n')
(W/'summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
