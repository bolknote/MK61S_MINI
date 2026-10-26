"""Recount all public records, original matrix and fresh/direct exclusions."""
from collections import Counter
from pathlib import Path
import gzip,json,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];BASE=ROOT/'.build/m0-pow-boundary128-20261025'
assert not (W/'FROZEN.json').exists()
q=json.loads((W/'qualification.json').read_bytes());fresh=json.loads((W/'new-qualification.json').read_bytes());direct=json.loads((W/'direct-proof.json').read_bytes())
controls={(r['x'],r['y'],r['SIO']):r for r in fresh['rows']};assert len(controls)==10254
original_rows=json.loads((BASE/'original153.json').read_bytes())['rows']
original_pairs={(r['x'],r['y'])for r in original_rows}
old_loss=set();new_loss=set();counts=Counter();deltas=Counter();wrong=variants=cases=0;original={};pairs={}
def equal(a,b):
 a,b=int(a,16),int(b,16)
 return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if(b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
with gzip.open(W/'qualification-records.jsonl.gz','rt')as stream:
 for line in stream:
  r=json.loads(line);key=r['x'],r['y'],r['SIO'];pair=key[:2];cases+=1
  c,p=r['candidate_instructions'],r['parent_reciprocal_instructions'];assert c<=p and equal(r['candidate'],r['expected'])
  assert (r['SIO']!='READY'and r['software_seed_divisors'])or c==p
  deltas[c-p]+=1
  cls=pairs.setdefault(pair,dict(old=False,new=False,equal=False,has_correct_reference=False))
  for label,ref in r['references'].items():
   variants+=1;assert ref['correct_Qfplib']==equal(ref['output'],r['expected'])
   if not ref['correct_Qfplib']:wrong+=1;continue
   v=ref['instructions'];counts['faster'if c<v else'equal'if c==v else'slower']+=1
   cls['has_correct_reference']=True;cls['equal']|=c==v;cls['old']|=p>v;cls['new']|=c>v
   if p>v:old_loss.add(pair)
   if c>v:new_loss.add(pair)
  if pair in original_pairs:original[key]=dict(parent=p,candidate=c,references=r['references'])
  if key in controls:
   f=controls.pop(key)
   assert f['expected']==r['expected']and f['outputs']['candidate']==r['candidate']
   assert f['instructions']['parent']==f['instructions']['control']==p and f['instructions']['candidate']==c
   assert f['reciprocal_calls']==r['reciprocal_calls']and f['software_seed_divisors']==r['software_seed_divisors']
   for name,ref in r['references'].items():
    assert(ref['output'],ref['instructions'],ref['correct_Qfplib'])==(f['outputs'][name],f['instructions'][name],f['correct'][name])
assert not controls and cases==241960 and variants==279522 and wrong==77106
assert len(pairs)==120980 and len(old_loss)==11434 and len(new_loss)==11386 and not new_loss-old_loss
assert counts==q['correct_Qfplib_comparison']and dict(sorted(deltas.items()))=={int(k):v for k,v in q['parent_cost_delta_histogram'].items()}
assert sorted(old_loss-new_loss)==[tuple(x)for x in q['fixed_pairs']]
hist={n:Counter()for n in ['parent','candidate']};observations=[]
for r in original_rows:
 states=[]
 for state in ['READY','DIRTY']:
  v=original[r['x'],r['y'],state];ref=v['references'][r['reference']];assert ref['correct_Qfplib']
  states.append(dict(SIO=state,parent=v['parent'],candidate=v['candidate'],Qfplib=ref['instructions']))
 for n in hist:
  kind='slower'if any(v[n]>v['Qfplib']for v in states)else'equal'if any(v[n]==v['Qfplib']for v in states)else'strict'
  hist[n][kind]+=1
 observations.append(dict(x=r['x'],y=r['y'],stream=r['stream'],reference=r['reference'],states=states))
assert hist['parent']==hist['candidate']==dict(slower=34,strict=119)
assert sum(not r['results']['Qfplib']['correct']for r in direct['rows'])==direct['wrong_Qfplib_variants_retained']==936
fresh_calls=q['total_fresh_public_ARM_calls']+fresh['fresh_ARM_calls']+direct['actual_ARM_calls'];assert fresh_calls==842693
strict=sum(not pairs[p]['equal']for p in old_loss-new_loss)
out=dict(status='PASS_PUBLIC_RAW_RECOUNT_ALL_FRESH_OVERLAPS_AND_DIRECT_EXCLUSIONS',unique_pairs=120980,states=cases,reference_state_variants=variants,
 parent_raw_loss_pairs=len(old_loss),candidate_raw_loss_pairs=len(new_loss),fixed_pairs=48,strict_fixed_pairs=strict,equal_fixed_pairs=48-strict,
 new_raw_losses=0,candidate_wrong=0,wrong_Qfplib_reference_state_variants_retained=wrong,correct_Qfplib_comparison=dict(counts),
 accelerated_states=sum(v for d,v in deltas.items()if d<0),public_instruction_reduction_range=[-max(d for d in deltas if d<0),-min(deltas)],
 parent_cost_delta_histogram=dict(sorted(deltas.items())),all10254_fresh_control_rows_match_full_records=True,
 original153={n:dict(v)for n,v in hist.items()},qualified_fresh_ARM_calls=fresh_calls,
 fresh_full_public_ARM_calls=q['total_fresh_public_ARM_calls'],fresh_MPFR_public_ARM_calls=fresh['fresh_ARM_calls'],fresh_direct_unit_calibration_ARM_calls=direct['actual_ARM_calls'],
 actual_directed_MPFR_inputs=fresh['actual_directed_MPFR_inputs']+direct['actual_directed_MPFR_inputs'],sNaN_policy_shortcuts=fresh['sNaN_policy_shortcuts']+direct['sNaN_policy_shortcuts'],
 fresh_exact_integer_dyadic_oracle_inputs=65536,original_seed66288_calls_inherited_not_fresh=True,
 pilot1836_calls153_MPFR_and_failed_preflight0_excluded=True,no_per_divisor_Qfplib_speed_comparison_claim_for_direct_exhaustive_part=True,
 no_nominal_reference_domain_filter=True,goal_complete=False)
(W/'summary.json').write_text(json.dumps(out,indent=2)+'\n');(W/'original153.json').write_text(json.dumps(dict(rows=observations),indent=2)+'\n')
print(json.dumps(out,indent=2))
