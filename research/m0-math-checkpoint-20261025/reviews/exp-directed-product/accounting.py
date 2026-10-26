"""Independently recount every frozen row, no ARM/MPFR re-execution or pooling."""
from collections import Counter
from pathlib import Path
import gzip,hashlib,json,struct,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent
W=R/'.build/m0-exp-directed-product-20261024';P=R/'.build/m0-exp-dyadic-product-20261024'
def equal(x,y):return bool(x&0x7fffffffffffffff>0x7ff0000000000000 and x&(1<<51))if y&0x7fffffffffffffff>0x7ff0000000000000 else x==y
meta=json.loads((W/'qualification.json').read_bytes());result=json.loads((W/'result.json').read_bytes())
audit=json.loads((W/'remaining-parent-audit.json').read_bytes());aud={(r['x'],r['SIO']):r for r in audit['rows']};assert len(aud)==732
expected_inputs=list(struct.iter_unpack('<Q',(W/'qualification-inputs.bin').read_bytes()));assert len(expected_inputs)==467366
seen=set();losses=set();oldloss=set();oldparentloss=set();old48763=set();fixed=set();reg=[];newlossgroups=Counter()
qcounts=Counter();deltas=Counter();regdelta=Counter();regclasses=Counter();wrong=0;freshq=0;rows=0;old=0;previous=None
with gzip.open(W/'qualification-records.jsonl.gz','rt')as new,gzip.open(P/'qualification-records.jsonl.gz','rt')as parent:
 for row in map(json.loads,new):
  x=int(row['x'],16);state='READY'if rows%2==0 else'DIRTY'
  assert row['SIO']==state and x==expected_inputs[rows//2][0]
  if state=='READY':assert x not in seen;seen.add(x)
  else:assert row['x']==previous['x']and row['expected']==previous['expected']and row['candidate']==previous['candidate']and row['Qfplib']==previous['Qfplib']
  expected=int(row['expected'],16);candidate=int(row['candidate'],16);qfp=int(row['Qfplib'],16)
  assert equal(candidate,expected)and equal(qfp,expected)==row['Qfplib_correct']
  loss=row['Qfplib_correct']and row['candidate_instructions']>row['Qfplib_instructions']
  if rows<913500:
   prior=json.loads(next(parent));old+=1
   for k in('x','SIO','expected','candidate','Qfplib','Qfplib_instructions','Qfplib_correct'):assert row[k]==prior[k],(rows,k)
   assert row['parent_instructions']==prior['candidate_instructions']and row['Qfplib_acquisition']=='inherited dyadic-exp corpus'
   delta=row['candidate_instructions']-prior['candidate_instructions'];deltas[delta]+=1
   ploss=prior['Qfplib_correct']and prior['candidate_instructions']>prior['Qfplib_instructions']
   if ploss:oldparentloss.add(row['x'])
   if loss:assert ploss;oldloss.add(row['x'])
   if ploss and not loss:fixed.add(row['x'])
   if loss and 'old48763:'in prior['group']:old48763.add(row['x'])
  else:
   assert row['Qfplib_acquisition']=='fresh';freshq+=1
   if loss:
    ar=aud[row['x'],state]
    for k in('x','SIO','expected','candidate','candidate_instructions','Qfplib','Qfplib_instructions','Qfplib_correct'):assert row[k]==ar[k]
    assert ar['parent_instructions']>ar['Qfplib_instructions']
    if state=='READY':newlossgroups[row['group']]+=1
  if row['Qfplib_correct']:qcounts['faster'if row['candidate_instructions']<row['Qfplib_instructions']else'equal'if not loss else'slower']+=1
  else:wrong+=1
  if loss:losses.add(row['x'])
  if row['parent_instructions']is not None and row['candidate_instructions']>row['parent_instructions']:
   reg.append(row);regdelta[row['candidate_instructions']-row['parent_instructions']]+=1
   regclasses['wrong_Qfplib'if not row['Qfplib_correct']else'already_losing_correct_Qfplib'if row['parent_instructions']>row['Qfplib_instructions']else'still_no_slower_correct_Qfplib']+=1
  rows+=1;previous=row
 assert next(parent,None)is None
assert(rows,len(seen),old,freshq)==(934732,467366,913500,21232)
assert(len(oldparentloss),len(oldloss),len(fixed),len(old48763),len(losses))==(1541,1530,11,88,1896)
assert losses-oldloss=={r['x']for r in audit['rows']}and len(losses-oldloss)==366
assert dict(qcounts)=={'faster':536584,'slower':3792}and wrong==394356
assert reg==json.loads((W/'retained-parent-regressions.json').read_bytes())and len(reg)==3448
assert dict(regdelta)=={1:3348,2:34,4:6,5:22,7:34,50:4}
assert dict(regclasses)=={'wrong_Qfplib':2022,'already_losing_correct_Qfplib':1392,'still_no_slower_correct_Qfplib':34}
assert dict(deltas)=={int(k):v for k,v in meta['old_parent_cost_deltas'].items()}
assert fixed=={r['x']for r in json.loads((W/'same-corpus-fixed11.json').read_bytes())['rows']}
# Expanded pow retained-loss replay is a different denominator and not fresh MPFR.
powreport=json.loads((W/'pow-loss-replay.json').read_bytes());pr=powreport['rows'];unique={};ploss=set();remaining=[]
for row in pr:
 key=row['x'],row['y'],row['SIO'];f=row['fresh_candidate'];assert f['candidate']==row['expected']
 assert f['candidate_instructions']==row['previous_candidate_instructions']-2*f['product_calls']
 if key in unique:assert unique[key]==f
 unique[key]=f
 if row['correct_Qfplib']and f['candidate_instructions']>row['instructions']['Qfplib']:
  remaining.append(row);ploss.add((row['x'],row['y']))
assert(len(pr),len(unique),len(remaining),len(ploss))==(10085,10081,10078,7901)
assert remaining==powreport['remaining']and not powreport['new_raw_losses']and powreport['fresh_MPFR_calls']==0
assert 955964+732+141320+275672+2048+1134+10081==1386951
assert result['total_qualified_fresh_ARM_calls']==1386951 and result['total_actual_directed_MPFR_validation_inputs']==467364+189
union=result['original507_author_separate_union'];assert union==dict(no_slower=423,strictly_faster=417,equal=6,remaining=84,by_operation={'pow':48,'exp':0,'sin':22,'cos':14},not_one_integrated_binary=True)
out=dict(status='PASS_INDEPENDENT_ALL_FROZEN_ROW_ACCOUNTING_WITHOUT_NEW_EXECUTIONS',
 exp_unique=467366,exp_states=934732,old_same_corpus_inputs=456750,old_parent_losses1541_to_candidate1530=True,
 same_corpus_fixed11=True,expanded_losses1896_old1530_plus_new366=True,new_loss_groups=dict(newlossgroups),
 every_current_remaining_loss_bound_to_already_losing_parent=True,correct_Qfplib_state_comparison=dict(qcounts),wrong_Qfplib_states_retained=wrong,
 cost_regressions3448_retained=True,regression_delta_counts=dict(regdelta),regression_classes=dict(regclasses),
 pow_historical_reference_state_variants=10085,pow_current_losing_variants=10078,pow_fresh_distinct_candidate_states=10081,pow_remaining_raw_pairs=7901,
 old_full111912_pow_oracles_inherited_not_reacquired=True,
 author_total_fresh_ARM=1386951,author_fresh_MPFR_validation=467553,author_sNaN_shortcuts=2,author_separate_log_preimage_MPFR_generations=1919,
 author_bare141320_calls_reused_from_rejected_CPP_layout_by_exact_unchanged77instruction_kernel_binding=True,
 author_original507_separate_component_union=union,prior_independent_count422_unchanged_here=True,
 no_counts_from_rejected_trials_initial_failed_pow_scope_or_own_failed_harness_attempts_added=True,
 own_new_ARM_or_MPFR_calls_in_this_accounting=0,hardware=False)
with(O/'accounting.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(out,indent=2))
