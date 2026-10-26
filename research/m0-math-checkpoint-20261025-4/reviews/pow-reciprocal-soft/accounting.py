"""Recount saved parent/current raw and bounded direct/public evidence."""
import gzip,hashlib,itertools,json
from collections import Counter
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-soft-20261025';B=R/'.build/m0-pow-boundary128-20261025'
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def equal(a,b):
 a,b=int(a,16),int(b,16)
 return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
fresh=json.loads((W/'new-qualification.json').read_text());fm={}
for row in fresh['rows']:
 k=row['x'],row['y'],row['SIO'];assert k not in fm;fm[k]=row
assert len(fm)==10254
original=json.loads((B/'original153.json').read_text())['rows'];opairs={(r['x'],r['y'])for r in original};original_states={}
q=json.loads((W/'qualification.json').read_text());fixed={tuple(v)for v in q['fixed_pairs']};jobs={p:dict(x=p[0],y=p[1],group='all48_full_union_strict_fixes')for p in sorted(fixed)}
keys=set();pairs=Counter();deltas=Counter();counts=Counter();loss=[set(),set()];correct_equal=set();wrong=variants=overlap=changed=seedcalls=recipcalls=0
freshloss=[set(),set()];extremes={};changed_rows=[]
with gzip.open(B/'qualification-records.jsonl.gz','rt')as old,gzip.open(W/'qualification-records.jsonl.gz','rt')as new:
 for a,b in itertools.zip_longest(old,new):
  assert a is not None and b is not None;p,r=json.loads(a),json.loads(b);key=r['x'],r['y'],r['SIO'];pair=key[:2]
  assert key not in keys;keys.add(key);pairs[pair]+=1
  assert all(r[n]==v for n,v in p.items()if n!='candidate_instructions')
  assert r['parent_reciprocal_instructions']==p['candidate_instructions']and equal(r['candidate'],r['expected'])
  c,pc=r['candidate_instructions'],r['parent_reciprocal_instructions'];d=c-pc;assert d<=0;deltas[d]+=1
  calls,seeds=r['reciprocal_calls'],r['software_seed_divisors'];recipcalls+=len(calls);seedcalls+=len(seeds)
  assert len(calls)<=1 and len(seeds)<=1
  if seeds:
   assert key[2]=='DIRTY'and d<0 and len(calls)==1;changed+=1
   raw=int(calls[0]['denominator'],16);assert calls[0]['numerator']=='3FF0000000000000'
   assert seeds[0]==(((raw>>32)&0xfffff)|0x100000)>>4 and 65536<=seeds[0]<131072
   ea=1023;eb=(raw>>52)&2047;assert 1<=eb<=2046 and 0<=ea-eb+1021<=2043
   changed_rows.append(dict(x=pair[0],y=pair[1],SIO=key[2],parent=pc,candidate=c,delta=d,call=calls[0],D=seeds[0]))
   if 'min'not in extremes or d<extremes['min']['d']:extremes['min']=dict(d=d,row=r)
   if 'max'not in extremes or d>extremes['max']['d']:extremes['max']=dict(d=d,row=r)
  else:assert d==0
  if key[2]=='READY':assert d==0 and not seeds
  for name,v in r['references'].items():
   variants+=1;good=equal(v['output'],r['expected']);assert v['correct_Qfplib']==good
   if not good:wrong+=1;continue
   rc=v['instructions'];counts['faster'if c<rc else'equal'if c==rc else'slower']+=1
   if pc>rc:loss[0].add(pair)
   if c>rc:loss[1].add(pair)
   if c==rc:correct_equal.add(pair)
  if key in fm:
   overlap+=1;f=fm[key];assert f['expected']==r['expected']and f['outputs']['parent']==f['outputs']['control']==f['outputs']['candidate']==r['candidate']
   assert f['instructions']['parent']==f['instructions']['control']==pc and f['instructions']['candidate']==c
   assert f['reciprocal_calls']==calls and f['software_seed_divisors']==seeds
   for name in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']:
    v=r['references'][name];assert [v['output'],v['instructions'],v['correct_Qfplib']]==[f['outputs'][name],f['instructions'][name],f['correct'][name]]
   for i,n in enumerate(['parent','candidate']):
    if any(f['correct'][v]and f['instructions'][n]>f['instructions'][v]for v in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']):freshloss[i].add(pair)
  if pair in opairs:original_states[key]=r
assert len(keys)==241960 and len(pairs)==120980 and all(v==2 for v in pairs.values())
assert variants==279522 and wrong==77106 and changed==seedcalls==377 and recipcalls==778 and overlap==10254
assert len(loss[0])==11434 and len(loss[1])==11386 and loss[1]<=loss[0]and loss[0]-loss[1]==fixed and len(fixed)==48
assert not fixed&correct_equal
assert dict(counts)==dict(slower=21064,faster=178647,equal=2705)
assert dict(deltas)=={int(k):v for k,v in q['parent_cost_delta_histogram'].items()}and min(deltas)==-380 and max(d for d in deltas if d<0)==-311
assert [len(s)for s in freshloss]==[632,588]
for v in extremes.values():
 r=v['row'];p=r['x'],r['y'];jobs.setdefault(p,dict(x=p[0],y=p[1],group='public_reduction_endpoint'))
original_counts={n:Counter()for n in ['parent','candidate']}
for i,row in enumerate(original):
 observations=[original_states[row['x'],row['y'],s]for s in ['READY','DIRTY']]
 for label,key in [('parent','parent_reciprocal_instructions'),('candidate','candidate_instructions')]:
  refs=[r['references'][row['reference']]for r in observations];assert all(v['correct_Qfplib']for v in refs)
  kind='slower'if any(r[key]>v['instructions']for r,v in zip(observations,refs))else'equal'if any(r[key]==v['instructions']for r,v in zip(observations,refs))else'strict';original_counts[label][kind]+=1
 if i<6:jobs.setdefault((row['x'],row['y']),dict(x=row['x'],y=row['y'],group='original153_unchanged_control'))
assert original_counts['parent']==original_counts['candidate']==dict(slower=34,strict=119)
direct=json.loads((W/'direct-proof.json').read_text());dw=seedrows=0;groups=Counter()
for r in direct['rows']:
 groups[r['group']]+=1;assert all(equal(r['results'][n]['output'],r['expected'])for n in ['parent','control','candidate'])
 assert r['results']['parent']==r['results']['control']and r['results']['candidate']['output']==r['results']['parent']['output']
 for name,v in r['results'].items():assert v['correct']==equal(v['output'],r['expected'])
 dw+=not r['results']['Qfplib']['correct'];seedrows+=bool(r['seed_divisors'])
 if r['SIO']=='READY':assert not r['seed_divisors']and r['results']['parent']['instructions']==r['results']['candidate']['instructions']
 assert r['results']['candidate']['instructions']<=r['results']['parent']['instructions']
assert len(direct['rows'])==3636 and dw==936 and seedrows+65536==66624
assert sum(direct['parent_instruction_delta_histogram'].values())==134708 and direct['actual_ARM_calls']==538832==134708*4
assert direct['groups']['all_seed_divisors']==131072 and groups=={k:v for k,v in direct['groups'].items()if k!='all_seed_divisors'}
assert 241960+377+61524+538832==842693 and direct['actual_directed_MPFR_inputs']+fresh['actual_directed_MPFR_inputs']==6761
assert direct['sNaN_policy_shortcuts']+fresh['sNaN_policy_shortcuts']==184
save('selected-public-jobs.json',dict(status='BOUNDED_OWN_SELECTION_ALL48_SAVED_STRICT_FIXES_PLUS_CONTROLS',jobs=list(jobs.values())))
save('changed-public-paths.json',dict(status='SAVED_CHANGED_PATH_WITNESSES_NO_NEW_EXECUTION',rows=changed_rows))
out=dict(status='PASS_FULL_SAVED_RAW_CURRENT_PARENT_REFERENCE_AND_DIRECT_EXCLUSION_ACCOUNTING',ARM_calls=0,MPFR_inputs=0,
 parent_raw=ref(B/'qualification-records.jsonl.gz'),new_raw=ref(W/'qualification-records.jsonl.gz'),
 every_parent_output_expected_reference_and_old_metadata_retained=True,
 inherited_boundary_midpoint_traces_historical_not_freshly_claimed=True,current_parent_field='parent_reciprocal_instructions',
 pairs=120980,states=241960,reference_variants=279522,wrong_Qfplib_variants_retained=77106,strict_quietNaN_flags_recounted=True,no_nominal_filter=True,
 loss_pairs=[11434,11386],new_strict_fixed_pairs48=True,fixed_pairs_sorted=sorted(fixed),new_loss_pairs=0,candidate_wrong=0,
 accelerated_DIRTY_states=377,actual_reciprocal_calls=778,software_seed_calls=377,all_READY_costs_unchanged=True,
 instruction_reduction_range=[311,380],cost_delta_histogram=dict(sorted(deltas.items())),correct_Qfplib_comparison=dict(counts),
 every10254_fresh_control_overlap_exact=True,fresh_control_loss_pairs=[632,588],original153={n:dict(c)for n,c in original_counts.items()},
 direct_saved_rows3636_recounted=True,direct_saved_wrong_Qfp936_retained=True,direct_saved_seed_join_rows=seedrows,
 author_direct67354_is_jobs_not_asserted_unique=True,author_full_direct_seed_join_count66624=True,
 author_exhaustive65536_no_per_divisor_cost_rows_no_Qfp_speed_comparison_claim=True,
 author_qualified_ARM842693_partition=[241960,377,61524,538832],author_MPFR6761_plus184sNaN=True,author_exact_integer_oracle65536=True,
 inherited_seed66288_and_old_MPFR_Qfp_not_fresh=True,author_pilot1836_MPFR153_failed_import0_excluded=True,
 reviewed507_stays422_author437_not_promoted=True,device_IO=0)
print(json.dumps(save('accounting.json',out)),flush=True)
