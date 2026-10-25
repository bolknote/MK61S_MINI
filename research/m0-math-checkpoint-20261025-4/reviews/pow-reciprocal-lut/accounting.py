"""Saved selected/all-variant timing, full parent raw and count exclusions."""
import gzip,hashlib,itertools,json
from collections import Counter
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-lut-20261025';P=R/'.build/m0-pow-reciprocal-soft-20261025';S=R/'.build/m0-ddiv-seed-lut-20261025'
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def equal(a,b):
 a,b=int(a,16),int(b,16)
 return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
unit={};hists={};unitrows=0
with gzip.open(S/'unit-records.jsonl.gz','rt')as f:
 for ln in f:
  r=json.loads(ln);d=r['D'];assert 65536<=d<131072 and 0<=r['NZCV']<16 and r['quotient']==0xffffffff//d
  if d in unit:assert unit[d]==r['instructions']
  unit[d]=r['instructions'];unitrows+=1
  for n,c in r['instructions'].items():hists.setdefault(n,Counter())[c]+=1
  u=(1<<32)//(65536+512*((d>>9)-128)+256);p=((d+1)>>1)*u;e=(p-(1<<31))//65536;q0=u-((u*e)>>15);error=q0-0xffffffff//d
  expected_cost=18+3*error if error>0 else 20+(4 if error==-1 else 0)
  assert r['instructions']['lut128_floor']==expected_cost
assert len(unit)==65536 and unitrows==77840
up=json.loads((S/'unit-proof.json').read_text());sel=json.loads((S/'selection.json').read_text());historical=json.loads((S/'selection-corpus-only.json').read_text())
for n,h in hists.items():assert dict(h)=={int(k):v for k,v in up['cost_histograms'][n].items()}
variants=[n for n in hists if n!='control'];metrics={n:dict(worst=max(v[n]for v in unit.values()),mean=sum(k*c for k,c in hists[n].items())/unitrows,bytes=up['code_and_allocated_sizes'][n]['allocated_bytes'])for n in variants}
selected=min(variants,key=lambda n:(metrics[n]['worst'],metrics[n]['mean'],metrics[n]['bytes']));assert selected==sel['selected']=='lut128_floor'
assert metrics[selected]['worst']==27 and sorted(v['worst']for v in metrics.values())==[27,34,42,86]
assert historical['selected']=='lut32_ceil_outer'and all(v['predicted_new_fixes']==9 for v in sel['results'].values())
fresh=json.loads((W/'new-qualification.json').read_text());fm={(r['x'],r['y'],r['SIO']):r for r in fresh['rows']};assert len(fm)==10254
q=json.loads((W/'qualification.json').read_text());fixes={tuple(v)for v in q['fixed_pairs']};assert len(fixes)==9
original=json.loads((P/'original153.json').read_text())['rows'];opairs={(r['x'],r['y'])for r in original};orig={}
loss=[set(),set()];equalpairs=set();counts=Counter();deltas=Counter();keys=set();pairs=Counter();wrong=refs=changed=overlap=0
jobs={p:dict(x=p[0],y=p[1],group='all9_new_strict_fixes')for p in sorted(fixes)};ends={}
with gzip.open(P/'qualification-records.jsonl.gz','rt')as old,gzip.open(W/'qualification-records.jsonl.gz','rt')as new:
 for a,b in itertools.zip_longest(old,new):
  assert a is not None and b is not None;p,r=json.loads(a),json.loads(b);key=r['x'],r['y'],r['SIO'];pair=key[:2];assert key not in keys;keys.add(key);pairs[pair]+=1
  assert all(r[n]==v for n,v in p.items()if n not in ['candidate_instructions','parent_reciprocal_instructions'])
  assert r['parent_reciprocal_instructions']==p['candidate_instructions']and equal(r['candidate'],r['expected'])
  c,pc=r['candidate_instructions'],r['parent_reciprocal_instructions'];delta=c-pc;assert delta<=0;deltas[delta]+=1
  expected_delta=sum(unit[d]['lut128_floor']-unit[d]['control']for d in r['software_seed_divisors']);assert delta==expected_delta
  if r['software_seed_divisors']:
   assert key[2]=='DIRTY'and delta<0;changed+=1
   for kind in ['min','max']:
    if kind not in ends or(delta<ends[kind][0]if kind=='min'else delta>ends[kind][0]):ends[kind]=(delta,r)
  else:assert delta==0
  if key[2]=='READY':assert delta==0
  for n,v in r['references'].items():
   refs+=1;good=equal(v['output'],r['expected']);assert good==v['correct_Qfplib']
   if not good:wrong+=1;continue
   rc=v['instructions'];counts['faster'if c<rc else'equal'if c==rc else'slower']+=1
   if pc>rc:loss[0].add(pair)
   if c>rc:loss[1].add(pair)
   if c==rc:equalpairs.add(pair)
  if key in fm:
   overlap+=1;f=fm[key];assert f['expected']==r['expected']and f['outputs']['parent']==f['outputs']['control']==f['outputs']['candidate']==r['candidate']
   assert f['instructions']['parent']==f['instructions']['control']==pc and f['instructions']['candidate']==c
   assert f['software_seed_divisors']==r['software_seed_divisors']and f['reciprocal_calls']==r['reciprocal_calls']
   for n,v in r['references'].items():assert [v['output'],v['instructions'],v['correct_Qfplib']]==[f['outputs'][n],f['instructions'][n],f['correct'][n]]
  if pair in opairs:orig[key]=r
assert len(keys)==241960 and len(pairs)==120980 and all(v==2 for v in pairs.values())and refs==279522 and wrong==77106
assert [len(x)for x in loss]==[11386,11377]and loss[1]<=loss[0]and loss[0]-loss[1]==fixes and not fixes&equalpairs
assert changed==377 and overlap==10254 and min(deltas)==-73 and max(x for x in deltas if x<0)==-59
assert dict(counts)==dict(slower=21044,faster=178667,equal=2705)
assert dict(deltas)=={int(k):v for k,v in q['parent_cost_delta_histogram'].items()}
for d,r in ends.values():p=r['x'],r['y'];jobs.setdefault(p,dict(x=p[0],y=p[1],group='public_seed_delta_endpoint'))
hist={n:Counter()for n in ['parent','candidate']}
for i,row in enumerate(original):
 rr=[orig[row['x'],row['y'],s]for s in ['READY','DIRTY']]
 for n,k in [('parent','parent_reciprocal_instructions'),('candidate','candidate_instructions')]:
  vv=[r['references'][row['reference']]for r in rr];assert all(v['correct_Qfplib']for v in vv)
  kind='slower'if any(r[k]>v['instructions']for r,v in zip(rr,vv))else'equal'if any(r[k]==v['instructions']for r,v in zip(rr,vv))else'strict';hist[n][kind]+=1
 if i<6:jobs.setdefault((row['x'],row['y']),dict(x=row['x'],y=row['y'],group='unchanged_original153_control'))
assert hist['parent']==hist['candidate']==dict(strict=119,slower=34)
direct=json.loads((W/'direct-proof.json').read_text());dw=0
for r in direct['rows']:
 assert r['results']['parent']==r['results']['control']and r['results']['candidate']['output']==r['results']['parent']['output']
 for n,v in r['results'].items():assert v['correct']==equal(v['output'],r['expected'])
 assert all(r['results'][n]['correct']for n in ['parent','control','candidate'])
 dw+=not r['results']['Qfplib']['correct']
 assert r['results']['candidate']['instructions']-r['results']['parent']['instructions']==sum(unit[d]['lut128_floor']-unit[d]['control']for d in r['seed_divisors'])
assert len(direct['rows'])==4148 and dw==936 and direct['actual_ARM_calls']==16592
assert 155680+241960+377+61524+16592==476133 and 77840*3==233520
assert direct['actual_directed_MPFR_inputs']+fresh['actual_directed_MPFR_inputs']==6761 and direct['sNaN_policy_shortcuts']+fresh['sNaN_policy_shortcuts']==184
save('selected-public-jobs.json',dict(status='BOUNDED_ALL9_SAVED_NEW_STRICT_FIXES_PLUS_ENDPOINTS_AND_CONTROLS',jobs=list(jobs.values())))
save('full-domain-unit-costs.json',dict(status='SAVED_MEASURED_SELECTED_VS_PARENT_COSTS_FOR_FULL_DIVISOR_DOMAIN',costs={str(d):[v['control'],v['lut128_floor']]for d,v in unit.items()}))
out=dict(status='PASS_FULL_DOMAIN_SELECTION_RAW_SEED_COST_LAW_AND_FULL_PUBLIC_RECOUNT',ARM_calls=0,MPFR_inputs=0,
 selected=selected,full_domain65536_and_all77840_rows_quotients_flags_and_costs_checked=True,selected_cost_formula='error>0:18+3*error; error==0:20; error==-1:24',
 measured_variant_metrics=metrics,selected_unique_best_worst_latency27=True,historical_sample_only_smaller_seed_choice=historical['selected'],
 current_public_forecast9_for_all_variants_not_selection_or_qualification=True,all_other3_variants233520_calls_excluded=True,selected_oldplusnew155680_only=True,
 pairs=120980,states=241960,reference_variants=279522,wrong_public_Qfp77106_retained=True,loss_pairs=[11386,11377],new_strict9=True,new_loss0_wrong0_increase0=True,
 faster_DIRTY_states377=True,public_instruction_savings=[59,73],READY_unchanged=True,every_delta_equals_actual_saved_selected_seed_delta=True,
 current_parent_cost_field='parent_reciprocal_instructions is overwritten with immediate soft parent candidate cost; old value retained only in parent stream',
 all10254_fresh_overlap_exact=True,strict_quietNaN_no_nominal_filter=True,correct_comparison=dict(counts),
 original153={n:dict(v)for n,v in hist.items()},direct4148_rows_all_timing_and_outputs_retained_wrong936=True,direct_cost_law_also_matches=True,
 author476133_partition=[155680,241960,377,61524,16592],author6761MPFR_plus184sNaN=True,author256exactdyadic_inputs_separate=True,
 author_failed24ARM3MPFR_wrong_parent_symbol_excluded=True,parent_qualification_old66288_seed_pilot_not_fresh=True,new_original153pilot_not_run=True,
 reviewed507_stays422_author437_not_promoted=True,device_IO=0)
print(json.dumps(save('accounting.json',out)),flush=True)
