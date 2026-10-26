"""Recount raw public and scalar records with all reference/ABI scopes intact."""
from pathlib import Path
from collections import Counter
import ast,gzip,json,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-lut-20261025'
fn=next(n for n in ast.parse((W/'trace.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='expected_saving')
exec(compile(ast.Module(body=[fn],type_ignores=[]),__file__,'exec'),globals())
q=json.loads((W/'qualification.json').read_bytes());fresh=json.loads((W/'new-qualification.json').read_bytes());direct=json.loads((W/'direct-proof.json').read_bytes())
controls={(r['x'],r['y'],r['SIO']):r for r in fresh['rows']};assert len(controls)==10254
original_rows=json.loads((P/'original153.json').read_bytes())['rows'];original_pairs={(r['x'],r['y'])for r in original_rows};original={}
pairs={};old_loss=set();new_loss=set();counts=Counter();deltas=Counter();by_state=Counter();wrong=variants=cases=0
def equal(a,b):
 a,b=int(a,16),int(b,16)
 return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if(b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
with gzip.open(W/'qualification-records.jsonl.gz','rt')as stream:
 for line in stream:
  r=json.loads(line);key=r['x'],r['y'],r['SIO'];pair=key[:2];c,p=r['candidate_instructions'],r['parent_reciprocal_instructions'];cases+=1
  assert equal(r['candidate'],r['expected'])and c<=p
  tr=[r['reciprocal_calls'],r['software_seed_divisors'],r['first_product_reciprocals']];assert p-c==expected_saving(tr)
  deltas[c-p]+=1
  if c<p:by_state[r['SIO']]+=1
  cls=pairs.setdefault(pair,dict(equal=False))
  for label,ref in r['references'].items():
   variants+=1;assert ref['correct_Qfplib']==equal(ref['output'],r['expected'])
   if not ref['correct_Qfplib']:wrong+=1;continue
   v=ref['instructions'];counts['faster'if c<v else'equal'if c==v else'slower']+=1;cls['equal']|=c==v
   if p>v:old_loss.add(pair)
   if c>v:new_loss.add(pair)
  if pair in original_pairs:original[key]=dict(parent=p,candidate=c,references=r['references'])
  if key in controls:
   f=controls.pop(key);assert f['expected']==r['expected']and f['outputs']['candidate']==r['candidate']
   assert f['instructions']['parent']==f['instructions']['control']==p and f['instructions']['candidate']==c
   for name in ['reciprocal_calls','software_seed_divisors','first_product_reciprocals']:assert f[name]==r[name]
   for label,ref in r['references'].items():assert(ref['output'],ref['instructions'],ref['correct_Qfplib'])==(f['outputs'][label],f['instructions'][label],f['correct'][label])
assert not controls and cases==241960 and len(pairs)==120980 and variants==279522 and wrong==77106
assert len(old_loss)==11377 and len(new_loss)==11372 and not new_loss-old_loss
assert sorted(old_loss-new_loss)==[tuple(x)for x in q['fixed_pairs']]
assert counts==q['correct_Qfplib_comparison']and by_state==q['accelerated_states_by_SIO']
hist={n:Counter()for n in ['parent','candidate']};observations=[]
for r in original_rows:
 states=[]
 for state in ['READY','DIRTY']:
  v=original[r['x'],r['y'],state];ref=v['references'][r['reference']];assert ref['correct_Qfplib']
  states.append(dict(SIO=state,parent=v['parent'],candidate=v['candidate'],Qfplib=ref['instructions']))
 for label in hist:
  kind='slower'if any(v[label]>v['Qfplib']for v in states)else'equal'if any(v[label]==v['Qfplib']for v in states)else'strict'
  hist[label][kind]+=1
 observations.append(dict(x=r['x'],y=r['y'],stream=r['stream'],reference=r['reference'],states=states))
assert hist['parent']==dict(slower=34,strict=119)
direct_counts={n:Counter()for n in ['parent','candidate']};direct_wrong=direct_rows=0
with gzip.open(W/'direct-records.jsonl.gz','rt')as stream:
 for line in stream:
  r=json.loads(line);direct_rows+=1;refs=r['results'];qfp=refs['Qfplib'];assert qfp['correct']==equal(qfp['output'],r['expected'])
  if not qfp['correct']:direct_wrong+=1;continue
  for label in direct_counts:
   cost=refs[label]['instructions'];v=qfp['instructions'];direct_counts[label]['faster'if cost<v else'equal'if cost==v else'slower']+=1
assert direct_rows==25536 and{n:dict(v)for n,v in direct_counts.items()}==direct['correct_Qfplib_comparisons']
fresh_calls=q['total_fresh_public_ARM_calls']+fresh['fresh_ARM_calls']+direct['actual_ARM_calls'];assert fresh_calls==406406
strict=sum(not pairs[p]['equal']for p in old_loss-new_loss)
out=dict(status='PASS_ALL_PUBLIC_SCALAR_ACCOUNTING_AND_FRESH_OVERLAPS',unique_pairs=120980,states=cases,reference_state_variants=variants,
 parent_loss_pairs=len(old_loss),candidate_loss_pairs=len(new_loss),fixed_pairs=5,strict_fixed_pairs=strict,equal_fixed_pairs=5-strict,new_raw_losses=0,candidate_wrong=0,
 correct_Qfplib_comparison=dict(counts),wrong_public_Qfplib_variants_retained=wrong,accelerated_states_by_SIO=dict(by_state),public_instruction_reduction_range=[-max(d for d in deltas if d<0),-min(deltas)],
 instruction_delta_histogram=dict(sorted(deltas.items())),all10254_fresh_public_controls_match_full_records=True,original153={n:dict(v)for n,v in hist.items()},
 total_qualified_fresh_ARM_calls=fresh_calls,fresh_full_public_calls=q['total_fresh_public_ARM_calls'],fresh_public_MPFR_control_reference_calls=fresh['fresh_ARM_calls'],fresh_scalar_calls=direct['actual_ARM_calls'],
 actual_directed_MPFR_inputs=fresh['actual_directed_MPFR_inputs']+direct['actual_directed_MPFR_inputs'],sNaN_policy_shortcuts=fresh['sNaN_policy_shortcuts']+direct['sNaN_policy_shortcuts'],
 direct_correct_Qfplib_comparisons={n:dict(v)for n,v in direct_counts.items()},wrong_direct_Qfplib_variants_retained=direct_wrong,direct_remaining_loss_states=216,
 v1_superseded102144_ARM12734_MPFR34sNaN_excluded=True,failed_trace308_completed_ARM2partial23_oracles_excluded=True,parent_qualification_and_seed_units_not_fresh=True,
 numerator_one_private_contract_not_general_ddiv=True,no_nominal_reference_domain_filter=True,goal_complete=False)
(W/'summary.json').write_text(json.dumps(out,indent=2)+'\n');(W/'original153.json').write_text(json.dumps(dict(rows=observations),indent=2)+'\n')
print(json.dumps(out,indent=2))
