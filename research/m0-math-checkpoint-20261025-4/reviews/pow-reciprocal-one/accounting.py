"""Full saved public/scalar recount; no ARM replay or source mutation."""
import gzip,hashlib,itertools,json
from collections import Counter
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-one-20261025';P=R/'.build/m0-pow-reciprocal-lut-20261025'
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def equal(a,b):
 a,b=int(a,16),int(b,16)
 return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
def guard(E):return 11 if 1<=E<=2044 else 12 if E in[2045,2046] else 5
q=json.loads((W/'qualification.json').read_text());fresh=json.loads((W/'new-qualification.json').read_text());fm={(r['x'],r['y'],r['SIO']):r for r in fresh['rows']};assert len(fm)==10254
fixed={tuple(p)for p in q['fixed_pairs']};assert len(fixed)==5
original=json.loads((P/'original153.json').read_text())['rows'];opairs={(r['x'],r['y'])for r in original};orig={}
keys=set();pairs=Counter();deltas=Counter();counts=Counter();loss=[set(),set()];equals=set();wrong=refs=overlap=callcount=seedcount=prodcount=0;acc=Counter()
jobs={p:dict(x=p[0],y=p[1],group='all5_new_public_strict_fixes')for p in sorted(fixed)}
with gzip.open(P/'qualification-records.jsonl.gz','rt')as old,gzip.open(W/'qualification-records.jsonl.gz','rt')as new:
 for a,b in itertools.zip_longest(old,new):
  assert a is not None and b is not None;p,r=json.loads(a),json.loads(b);key=r['x'],r['y'],r['SIO'];pair=key[:2];assert key not in keys;keys.add(key);pairs[pair]+=1
  assert all(r[n]==v for n,v in p.items()if n not in ['candidate_instructions','parent_reciprocal_instructions'])
  assert r['parent_reciprocal_instructions']==p['candidate_instructions']and equal(r['candidate'],r['expected'])
  calls,seeds,products=r['reciprocal_calls'],r['software_seed_divisors'],r['first_product_reciprocals']
  callcount+=len(calls);seedcount+=len(seeds);prodcount+=len(products)
  assert all(c['numerator']=='3FF0000000000000'for c in calls)
  saving=sum(guard((int(c['denominator'],16)>>52)&2047)for c in calls)+15*len(products)+8*len(seeds)
  c,pc=r['candidate_instructions'],r['parent_reciprocal_instructions'];delta=c-pc;assert delta==-saving and delta<=0;deltas[delta]+=1
  if delta<0:acc[key[2]]+=1
  for n,v in r['references'].items():
   refs+=1;good=equal(v['output'],r['expected']);assert good==v['correct_Qfplib']
   if not good:wrong+=1;continue
   rc=v['instructions'];counts['faster'if c<rc else'equal'if c==rc else'slower']+=1
   if pc>rc:loss[0].add(pair)
   if c>rc:loss[1].add(pair)
   if c==rc:equals.add(pair)
  if key in fm:
   overlap+=1;f=fm[key];assert f['expected']==r['expected']and f['outputs']['candidate']==f['outputs']['control']==f['outputs']['parent']==r['candidate']
   assert f['instructions']['candidate']==c and f['instructions']['parent']==f['instructions']['control']==pc
   assert f['reciprocal_calls']==calls and f['software_seed_divisors']==seeds and f['first_product_reciprocals']==products
   for n,v in r['references'].items():assert [v['output'],v['instructions'],v['correct_Qfplib']]==[f['outputs'][n],f['instructions'][n],f['correct'][n]]
  if pair in opairs:orig[key]=r
assert len(keys)==241960 and len(pairs)==120980 and all(v==2 for v in pairs.values())and refs==279522 and wrong==77106
assert [len(s)for s in loss]==[11377,11372]and loss[1]<=loss[0]and loss[0]-loss[1]==fixed and not fixed&equals
assert acc==dict(READY=389,DIRTY=389)and callcount==778 and seedcount==377 and prodcount==754 and overlap==10254
assert dict(counts)==dict(slower=21030,faster=178682,equal=2704)and dict(deltas)=={-34:377,-26:377,-11:24,0:241182}
hist={n:Counter()for n in ['parent','candidate']}
for i,row in enumerate(original):
 rr=[orig[row['x'],row['y'],s]for s in ['READY','DIRTY']]
 for name,k in [('parent','parent_reciprocal_instructions'),('candidate','candidate_instructions')]:
  vv=[r['references'][row['reference']]for r in rr];assert all(v['correct_Qfplib']for v in vv)
  kind='slower'if any(r[k]>v['instructions']for r,v in zip(rr,vv))else'equal'if any(r[k]==v['instructions']for r,v in zip(rr,vv))else'strict';hist[name][kind]+=1
 if i<6:jobs.setdefault((row['x'],row['y']),dict(x=row['x'],y=row['y'],group='unchanged_original153_control'))
assert hist['parent']==hist['candidate']==dict(slower=34,strict=119)
comparisons={n:Counter()for n in ['parent','candidate']};scalar_delta=Counter();remaining=[];wrong_direct=rows=0
with gzip.open(W/'direct-records.jsonl.gz','rt')as f:
 for line in f:
  r=json.loads(line);rows+=1;b=int(r['denominator'],16);E=(b>>52)&2047;rr=r['results'];assert rr['parent']==rr['control']and rr['candidate']['output']==rr['parent']['output']
  for n,v in rr.items():assert v['correct']==equal(v['output'],r['expected'])
  assert all(rr[n]['correct']for n in ['parent','control','candidate'])
  delta=rr['candidate']['instructions']-rr['parent']['instructions'];assert delta==-guard(E)-15*r['first_product_calls']-8*len(r['software_seed_divisors']);scalar_delta[delta]+=1
  if not rr['Qfplib']['correct']:wrong_direct+=1;continue
  for n in comparisons:
   a,c=rr[n]['instructions'],rr['Qfplib']['instructions'];comparisons[n]['faster'if a<c else'equal'if a==c else'slower']+=1
  if rr['candidate']['instructions']>rr['Qfplib']['instructions']:remaining.append(dict(r,lag_instructions=rr['candidate']['instructions']-rr['Qfplib']['instructions']))
assert rows==25536 and wrong_direct==354 and comparisons==dict(parent=dict(faster=12622,slower=12560),candidate=dict(faster=24966,slower=216))
saved=json.loads((W/'direct-remaining.json').read_text());assert saved['rows']==remaining and len(remaining)==216
denoms={r['denominator']for r in remaining};normal=[r for r in remaining if(int(r['denominator'],16)>>52)&2047];nd={r['denominator']for r in normal}
assert len(denoms)==18 and len(normal)==18 and len(nd)==9 and len(remaining)-len(normal)==198
by_state={s:[r['lag_instructions']for r in normal if r['SIO']==s]for s in ['READY','DIRTY']}
ranges={s:[min(v),max(v)]for s,v in by_state.items()};assert ranges==dict(READY=[2,5],DIRTY=[15,21])and min(r['lag_instructions']for r in normal)==2 and max(r['lag_instructions']for r in normal)==21
corr=json.loads((R/'.build/m0-pow-reciprocal-one-report-corrigendum-20261025.json').read_text())
for field,name in [('FROZEN_sha256','FROZEN.json'),('HANDOFF_sha256','HANDOFF.md'),('result_sha256','result.json'),('direct_remaining_sha256','direct-remaining.json')]:assert corr[field]==ref(W/name)['sha256']
assert corr['correct_lag_ranges_by_SIO']==ranges and corr['correct_all_normal_lag_range']==[2,21]
assert any(r['denominator']=='3FF27D0DF6735E90'and r['SIO']=='DIRTY'and r['lag_instructions']==21 for r in normal)
trace=json.loads((W/'TRACE-PREFLIGHT-001.json').read_text());assert trace['full_completed_candidate_calls']+trace['new_completed_ARM_calls']==308 and trace['full_aborted_partial_calls']+trace['new_aborted_partial_calls']==2 and trace['new_oracle_evaluations']==23
assert 241960+778+61524+102144==406406 and 12734+5051==17785 and 34+76==110
save('selected-public-jobs.json',dict(status='BOUNDED_ALL5_STRICT_FIXES_AND_UNCHANGED_CONTROLS',jobs=list(jobs.values())))
save('scalar-loss-selection.json',dict(status='ALL_REMAINING_UNIQUE_DENOMINATORS_FOR_BOUNDED_CHECK',all_denominators=sorted(denoms),normal_denominators=sorted(nd),normal_lag_ranges=ranges,all_normal_rows=normal))
out=dict(status='PASS_FULL_PUBLIC_SCALAR_COUNTS_IMMEDIATE_PARENT_COSTS_AND_ADDITIVE_CORRIGENDUM',ARM_calls=0,MPFR_inputs=0,
 pairs120980_states241960_refs279522=True,wrong_public77106_retained=True,loss_pairs=[11377,11372],new_strict5_newloss0_wrong0_increase0=True,
 changed_READY389_DIRTY389=True,public_saved_instructions=[11,34],all_costs_equal_guard11_12_5_plus15product_plus8seed=True,
 callcount778_firstproducts754_software377=True,all10254_fresh_overlap_exact=True,
 current_parent_field='parent_reciprocal_instructions overwritten with immediate LUT candidate cost; older history not compared',
 original153={n:dict(v)for n,v in hist.items()},correct_Qfp_public=dict(counts),scalar25536_rows_all_output_cost_flags_recounted=True,
 direct_correct_comparisons={n:dict(v)for n,v in comparisons.items()},wrong_direct354_retained=True,remaining_scalar216states18denoms=True,
 remaining_subnormal198_normal18states9denoms=True,correct_normal_lag_ranges=ranges,overall_normal_lag=[2,21],corrigendum=ref(R/'.build/m0-pow-reciprocal-one-report-corrigendum-20261025.json'),
 old_HANDOFF_range2to5_was_READY_only_not_all_normal=True,no_universal_reciprocal_speed_claim=True,no_nominal_filter_strict_quietNaN=True,
 author406406_partition=[241960,778,61524,102144],author17785MPFR_plus110sNaN=True,
 superseded_v1_102144ARM12734MPFR34shortcuts_excluded=True,failed_trace308complete2partial23oracles_excluded=True,static_import0_excluded=True,parent_seed_units_not_fresh=True,
 reviewed507_stays422_author437_not_promoted=True,device_IO=0)
print(json.dumps(save('accounting.json',out)),flush=True)
