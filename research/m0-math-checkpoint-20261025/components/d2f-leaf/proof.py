"""Exact range/packing certificate and a complete Qfplib-correct path partition."""
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
q=json.loads((W/'qualification.json').read_text());assert not q['wrong']
assert q['candidate_ELF_sha256']==sha(W/'candidate.elf')
mask=(1<<32)-1;fraction=(1<<20)-1
zero_bound=873<<22;normal_bound=(24<<22)-1;ceiling_bound=(24<<22)-4
range_checks=0
for e in range(1024):
 for borrow in (0,1):
  lo=(e<<22)-zero_bound-borrow
  hi=lo+(fraction<<2)
  if e<873:assert hi<0
  elif e==873:assert lo==-borrow and hi>0
  else:assert lo>0
  if e<897:assert hi<normal_bound
  else:assert lo>=normal_bound
  if e<896:assert hi<ceiling_bound
  if e==896:assert hi==ceiling_bound-borrow
  range_checks+=1
for e in range(1024,2048):
 lo=(e-1024)<<22;hi=lo+(fraction<<2)
 if e<1151:assert hi<(127<<22)
 else:assert lo>=(127<<22)
 if e<2047:assert hi+(1<<22)<(1<<32)
 else:assert lo+(1<<22)==(1<<32)
 range_checks+=1
packing_checks=0
for e in range(897,1151):
 for sign in (0,1):
  for high_fraction in (0,1,fraction-1,fraction):
   raw=(sign<<31)|(e<<20)|high_fraction
   signed=raw-(1<<32) if sign else raw
   factor=(signed>>30)+(e<1024)
   assert factor==(1 if not sign else -1)
   for retained in range(9):
    got=((raw<<3)+(factor<<30)+retained)&mask
    expected=((sign<<31)+((e-896)<<23)+(high_fraction<<3)+retained)&mask
    assert got==expected
    # Tie parity is unchanged by adding raw_high<<3 before final ADC.
    assert (((raw<<3)+retained)&1)==(retained&1)
    packing_checks+=1
rounding_checks=0
for retained in range(8):
 for guard in (0,1):
  for sticky in (0,1,(1<<28)-1):
   low=(retained<<29)|(guard<<28)|sticky
   tail=low&((1<<29)-1)
   increment=guard and (sticky!=0 or retained&1)
   assert bool(increment)==(tail>(1<<28) or(tail==(1<<28) and retained&1))
   rounding_checks+=1
subnormal_checks=0
for shift in range(9,33):
 for guard in (0,1):
  for low_bits in (0,1,(1<<(shift-1))-1):
   for low_sticky in (0,1,(1<<21)-1):
    top=(1<<31)|(guard<<(shift-1))|low_bits
    actual_guard=(top>>(shift-1))&1
    below=((top<<(33-shift))&mask)|low_sticky
    assert bool(below)==bool((top&((1<<(shift-1))-1)) or low_sticky)
    full=(top<<21)|low_sticky
    assert full>>(shift+21)==top>>shift
    assert actual_guard==((full>>(shift+20))&1)
    subnormal_checks+=1
# The reference returns exact binary32 on precisely the following classes.
# Source proof in NUMERIC-PROOF.md derives this partition directly from
# the pinned qfp_double2float branch predicates; there is no domain filter.
costs={'zero':(9,9),'subnormal_to_normal':(19,20),'overflow':(13,13),'infinity':(13,13),
 'normal_low_truncate':(19,20),'normal_low_up':(22,22),'normal_low_tie_even':(22,23),'normal_low_tie_odd':(22,24),
 'normal_high_truncate':(14,20),'normal_high_up':(17,22),'normal_high_tie_even':(17,23),'normal_high_tie_odd':(17,24)}
counts=Counter();observed=defaultdict(set);regressions=[];wrong_reference=[]
for row in q['rows']:
 x=int(row['x'],16);e=(x>>52)&2047;f=x&((1<<52)-1)
 if e<873 or(e==873 and f==0):kind='zero'
 elif 897<=e<=1150:
  tail=x&((1<<29)-1)
  mode='truncate' if tail<(1<<28) else 'up' if tail>(1<<28) else 'tie_odd' if((x>>29)&1) else 'tie_even'
  kind=('normal_low_' if e<=1023 else 'normal_high_')+mode
 elif e==896 and f>=(1<<52)-(1<<29):kind='subnormal_to_normal'
 elif 1151<=e<=2046:kind='overflow'
 elif e==2047 and f==0:kind='infinity'
 elif e==2047:kind='NaN'
 else:kind='subnormal_Qfplib_flushes'
 correct=kind in costs
 assert correct==row['correct']['Qfplib'],(row['x'],kind)
 pair=(row['instructions']['candidate'],row['instructions']['Qfplib'])
 observed[kind].add(pair);counts[kind]+=1
 if correct:assert pair==costs[kind] and pair[0]<=pair[1]
 else:wrong_reference.append(row)
 if row['instructions']['candidate']>row['instructions']['parent']:regressions.append(row)
assert set(costs)<=set(counts)
assert len(regressions)==110782 and all(r['instructions']['candidate']-r['instructions']['parent']==1 for r in regressions)
with (W/'retained-parent-regressions.json').open('w') as f:json.dump({'status':'ALL_PARENT_COST_INCREASES_RETAINED','state_rows':len(regressions),'delta':1,'all_no_slower_than_correct_Qfplib':True,'rows':regressions},f,indent=2);f.write('\n')
# Reconcile both original instruction samples, without counting inherited
# ARM calls as fresh. All corresponding final calls were freshly executed.
by_input={r['x']:r for r in q['rows'] if r['SIO']=='READY'};samples=[]
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
for name in ('float.json','addendum.json'):
 old=json.loads((Q/name).read_text())['operations']['d2f']['instruction_sample']
 for old_row in old:
  row=by_input[f"{int(old_row['arguments'][0],16):016X}"]
  assert row['instructions']['parent']==old_row['own_instructions']
  assert row['instructions']['Qfplib']==old_row['reference_instructions']
  assert int(row['outputs']['parent'],16)==int(old_row['own_result'],16)
  assert int(row['outputs']['Qfplib'],16)==int(old_row['reference_result'],16)
  samples.append({'source':name,'old_index':old_row['index'],'x':row['x'],'reference_correct':row['correct']['Qfplib'],'before':row['instructions']['parent'],'after':row['instructions']['candidate'],'Qfplib':row['instructions']['Qfplib']})
both=[r for r in samples if r['reference_correct']]
old_losses=sum(r['before']>r['Qfplib'] for r in both);new_losses=sum(r['after']>r['Qfplib'] for r in both)
assert len(samples)==512 and len(both)==510 and old_losses==426 and new_losses==0
(W/'old512-sample-reconciliation.json').write_text(json.dumps({'status':'PASS_ALL512_OLD_COUNTS_RESULTS_REPRODUCED_AND426_DEFICITS_FIXED','rows':samples,'both_correct':510,'before_slower':426,'after_slower':0,'no_inherited_calls_added':True},indent=2)+'\n')
out={'status':'AUTHOR_EXACT_D2F_RANGE_RNE_AND_CORRECT_REFERENCE_PATH_AUDIT','range_interval_checks':range_checks,'normal_packing_and_tie_parity_checks':packing_checks,'guard_sticky_parity_classes':rounding_checks,'subnormal_shift_algebra_checks':subnormal_checks,'complete_IEEE_domain_partition_explained_in':'NUMERIC-PROOF.md','all_reference_correct_classes_covered':sorted(costs),'instruction_table':{k:{'candidate':v[0],'Qfplib':v[1],'state_rows':counts[k]} for k,v in costs.items()},'all_observed_reference_correctness_matches_source_partition':True,'all_observed_cost_pairs_match_source_path_counts':True,'wrong_reference_state_rows_retained':len(wrong_reference),'wrong_reference_observed_costs':{k:[list(p) for p in sorted(v)] for k,v in observed.items() if k not in costs},'parent_cost_increases_retained':len(regressions),'parent_cost_increase_delta':1,'old512_sample_comparable':510,'old512_sample_deficits':[426,0],'candidate_ELF_sha256':sha(W/'candidate.elf'),'qfp_ELF_sha256':sha(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'),'qfp_source_sha256':sha(ROOT/'.build/m0-v138-execution-20261023/sources/qfplib-linked.S'),'whole_goal_or_physical_cycle_GO':False,'independent_review_pending':True}
(W/'proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
