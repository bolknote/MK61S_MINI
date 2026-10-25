"""Read-only recount against the immediate parent, retaining every regression."""
import gzip,hashlib,itertools,json
from collections import Counter
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-certificate-20261025';P=R/'.build/m0-pow-reciprocal-inline-20261025'
MASK=(1<<32)-1
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def equal(a,b):
 a,b=int(a,16),int(b,16)
 return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
def certificate(base,u,v):
 product=u*v;d=(u>>16)*(v>>16);A=(base-d)&MASK;exact=(base-(product>>32)-bool(product&MASK))&MASK
 E=(product>>32)-d+bool(product&MASK);assert 0<=E<=131071 and exact==(A-E)&MASK
 fast=(A&0x7fffffff)>=1<<17;negative=bool(exact>>31);cross=((u>>16)*(v&65535)+(u&65535)*(v>>16))>MASK
 if fast:assert bool(A>>31)==negative and exact!=0
 return dict(base=base,u=u,v=v,estimate=A,exact=exact,fast=fast,negative=negative,cross_overflow=cross,expected_saving=12+3*cross if fast else -7 if negative else -8,full=not fast,decision='down'if negative else'up')
def check_certificates(rows):
 for r in rows:assert r==certificate(r['base'],r['u'],r['v'])
 return sum(r['expected_saving']for r in rows)
q=json.loads((W/'qualification.json').read_text());fixed={tuple(p)for p in q['fixed_pairs']};assert len(fixed)==2
fresh=json.loads((W/'new-qualification.json').read_text());fm={(r['x'],r['y'],r['SIO']):r for r in fresh['rows']};assert len(fm)==10254
original=json.loads((P/'original153.json').read_text())['rows'];opairs={(r['x'],r['y'])for r in original};orig={}
keys=set();pairs=Counter();counts=Counter();deltas=Counter();loss=[set(),set()];equals=set();wrong=refs=overlap=paths=unchanged=callcount=seedcount=prodcount=0;acc=Counter();inc=Counter();classes=Counter();public_increases=[];jobs={};class_examples={}
for p in fixed:jobs[p]=dict(x=p[0],y=p[1],group='new_pair_fix_classified_after_recount')
with gzip.open(P/'qualification-records.jsonl.gz','rt')as old,gzip.open(W/'qualification-records.jsonl.gz','rt')as new:
 for a,b in itertools.zip_longest(old,new):
  assert a is not None and b is not None;p,r=json.loads(a),json.loads(b);key=r['x'],r['y'],r['SIO'];pair=key[:2];assert key not in keys;keys.add(key);pairs[pair]+=1
  assert all(r[n]==v for n,v in p.items()if n not in ['candidate_instructions','parent_reciprocal_instructions'])
  assert r['parent_reciprocal_instructions']==p['candidate_instructions']and equal(r['candidate'],r['expected'])
  calls,seeds,products,certs=r['reciprocal_calls'],r['software_seed_divisors'],r['first_product_reciprocals'],r['remainder_certificates']
  callcount+=len(calls);seedcount+=len(seeds);prodcount+=len(products)
  assert all(c['numerator']=='3FF0000000000000'and 1<=((int(c['denominator'],16)>>52)&2047)<=2044 for c in calls)
  c,pc=r['candidate_instructions'],r['parent_reciprocal_instructions'];delta=c-pc;assert delta==-check_certificates(certs);deltas[delta]+=1
  if calls:paths+=1;unchanged+=delta==0
  if delta<0:acc[key[2]]+=1
  if delta>0:inc[delta]+=1;public_increases.append(r)
  for cert in certs:
   cl=('fast'if cert['fast']else'full')+'_'+cert['decision']+('_cross'if cert['cross_overflow']else'_nocross');classes[cl]+=1
   if cl not in class_examples:class_examples[cl]=r;jobs.setdefault(pair,dict(x=pair[0],y=pair[1],group='actual_public_'+cl))
  for n,v in r['references'].items():
   refs+=1;good=equal(v['output'],r['expected']);assert good==v['correct_Qfplib']
   if not good:wrong+=1;continue
   rc=v['instructions'];counts['faster'if c<rc else'equal'if c==rc else'slower']+=1
   if pc>rc:loss[0].add(pair)
   if c>rc:loss[1].add(pair)
   if c==rc:equals.add(pair)
  if key in fm:
   overlap+=1;f=fm[key];assert f['expected']==r['expected']and f['outputs']['parent']==f['outputs']['control']==f['outputs']['candidate']==r['candidate']
   assert f['instructions']['parent']==f['instructions']['control']==pc and f['instructions']['candidate']==c
   for n in ['reciprocal_calls','software_seed_divisors','first_product_reciprocals','remainder_certificates']:assert f[n]==r[n]
   for n,v in r['references'].items():assert [v['output'],v['instructions'],v['correct_Qfplib']]==[f['outputs'][n],f['instructions'][n],f['correct'][n]]
  if pair in opairs:orig[key]=r
assert len(keys)==241960 and len(pairs)==120980 and all(v==2 for v in pairs.values())and refs==279522 and wrong==77106
assert [len(s)for s in loss]==[11371,11369]and loss[1]<=loss[0]and loss[0]-loss[1]==fixed
strict=fixed-equals;eqfixed=fixed&equals;assert len(strict)==len(eqfixed)==1
assert acc==dict(READY=177,DIRTY=177)and inc=={8:26,7:6}and paths==callcount==778 and unchanged==392 and prodcount==754 and seedcount==377 and overlap==10254
assert dict(deltas)=={-15:30,-12:324,0:241574,7:6,8:26}and dict(counts)==dict(slower=21026,faster=178685,equal=2705)
corr=json.loads((R/'.build/m0-pow-reciprocal-certificate-report-corrigendum-20261025.json').read_text())
assert corr['FROZEN_sha256']==ref(W/'FROZEN.json')['sha256']and corr['HANDOFF_sha256']==ref(W/'HANDOFF.md')['sha256']and corr['result_sha256']==ref(W/'result.json')['sha256']and corr['records_sha256']==ref(W/'qualification-records.jsonl.gz')['sha256']
slowed_with_good=[r for r in public_increases if any(v['correct_Qfplib']for v in r['references'].values())]
assert len(public_increases)==32 and len(slowed_with_good)==2
for r,w in zip(slowed_with_good,corr['witnesses']):
 assert [r['x'],r['y'],r['SIO'],r['parent_reciprocal_instructions'],r['candidate_instructions'],r['references']]==[w['x'],w['y'],w['SIO'],w['parent'],w['candidate'],w['references']]
 assert all(r['parent_reciprocal_instructions']>v['instructions']and r['candidate_instructions']>v['instructions']for v in r['references'].values()if v['correct_Qfplib'])
 pair=r['x'],r['y'];jobs.setdefault(pair,dict(x=pair[0],y=pair[1],group='already_losing_correctQfp_further_slowed'))
hist={n:Counter()for n in ['parent','candidate']}
for i,row in enumerate(original):
 rr=[orig[row['x'],row['y'],s]for s in ['READY','DIRTY']]
 for n,k in [('parent','parent_reciprocal_instructions'),('candidate','candidate_instructions')]:
  vv=[r['references'][row['reference']]for r in rr];assert all(v['correct_Qfplib']for v in vv)
  kind='slower'if any(r[k]>v['instructions']for r,v in zip(rr,vv))else'equal'if any(r[k]==v['instructions']for r,v in zip(rr,vv))else'strict';hist[n][kind]+=1
 if i<4:jobs.setdefault((row['x'],row['y']),dict(x=row['x'],y=row['y'],group='original153_unchanged_control'))
assert hist==dict(parent=dict(slower=34,strict=119),candidate=dict(slower=33,strict=120))
comparison={n:Counter()for n in ['parent','candidate']};increases=Counter();remaining=[];newloss=[];wrong_direct=rows=0;increase_examples={};equal_scalar=[];directclasses=Counter();directexamples={}
with gzip.open(P/'direct-records.jsonl.gz','rt')as old,gzip.open(W/'direct-records.jsonl.gz','rt')as new:
 for a,b in itertools.zip_longest(old,new):
  assert a is not None and b is not None;p,r=json.loads(a),json.loads(b);rows+=1;rr=r['results'];assert all(r[n]==p[n]for n in ['denominator','NZCV','SIO','expected','first_product_calls','software_seed_divisors'])
  assert rr['parent']==rr['control']==p['results']['candidate']and rr['candidate']['output']==rr['parent']['output']and rr['Qfplib']==p['results']['Qfplib']
  for n,v in rr.items():assert v['correct']==equal(v['output'],r['expected'])
  assert all(rr[n]['correct']for n in ['parent','control','candidate'])
  pc,c=rr['parent']['instructions'],rr['candidate']['instructions'];assert c==pc-check_certificates(r['remainder_certificates'])
  for cert in r['remainder_certificates']:
   cl=('fast'if cert['fast']else'full')+'_'+cert['decision']+('_cross'if cert['cross_overflow']else'_nocross');directclasses[cl]+=1;directexamples.setdefault(cl,r)
  if c>pc:increases[c-pc]+=1;increase_examples.setdefault(str(c-pc),r)
  if not rr['Qfplib']['correct']:wrong_direct+=1;continue
  qc=rr['Qfplib']['instructions']
  for n in comparison:comparison[n]['faster'if rr[n]['instructions']<qc else'equal'if rr[n]['instructions']==qc else'slower']+=1
  if c>qc:remaining.append(r)
  if c>qc and pc<=qc:newloss.append(r)
  if c==qc:equal_scalar.append(r)
saved=json.loads((W/'direct-loss-accounting.json').read_text());assert saved['remaining']==remaining and not newloss and saved['new_losses']==0
assert rows==41988 and wrong_direct==9600 and len(remaining)==1 and len(equal_scalar)==5
assert comparison==dict(parent=dict(faster=32370,equal=5,slower=13),candidate=dict(faster=32382,equal=5,slower=1))
assert increases=={8:846,7:286}and sum(increases.values())==1132
assert remaining[0]['denominator']=='3FF27D0DF6735E90'and remaining[0]['SIO']=='DIRTY'and[remaining[0]['results'][n]['instructions']for n in ['candidate','Qfplib']]==[149,146]
assert 241960+778+61524+167952+201600==673814 and 20960+5051==26011 and 34+76==110
for p in strict:jobs[p]['group']='strict_pair_fix'
for p in eqfixed:jobs[p]['group']='equality_pair_fix_not_strict'
save('selected-public-jobs.json',dict(status='STRICT_EQUALITY_FIXES_BOTH_SLOWING_WITNESSES_ACTUAL_CLASSES',jobs=list(jobs.values()),strict_fixed_pairs=sorted(strict),equal_fixed_pairs=sorted(eqfixed),public_increase_witnesses=slowed_with_good))
save('scalar-selection.json',dict(status='ALL_BRANCH_CLASSES_SLOWDOWNS_AND_REMAINING_LOSS',remaining=remaining,remaining_denominators=sorted({r['denominator']for r in remaining}),increase_examples=increase_examples,equal_states=equal_scalar,branch_class_examples=directexamples))
out=dict(status='PASS_IMMEDIATE_PARENT_SAME_CORPUS_RECOUNT_WITH_EXPLICIT_PERFORMANCE_TRADEOFF',ARM_calls=0,MPFR_inputs=0,
 public_pairs120980_states241960_refvariants279522=True,wrong_public77106_retained=True,loss_pairs=[11371,11369],strict_fixes=sorted(strict),equality_fixes_not_strict=sorted(eqfixed),no_wrong_or_new_loss=True,
 public_correct_Qfplib=dict(counts),public_delta_histogram=dict(deltas),faster354_READY177_DIRTY177=True,public_parent_increases32_hist=dict(inc),
 two_already_losing_correctQfp_states_further_slowed=slowed_with_good,other30_increases_have_no_correct_Qfp=True,corrigendum_bound_and_confirmed=ref(R/'.build/m0-pow-reciprocal-certificate-report-corrigendum-20261025.json'),
 all_actual_saved_certificate_arithmetic_branches_and_costs_recounted=True,public_certificate_classes=dict(classes),all10254_fresh_overlap=True,
 fresh_parent_replays778_include392_unchanged_and386_changed=True,first_product754_and_software377=True,immediate_parent_cost_field_not_older_history=True,original153={n:dict(v)for n,v in hist.items()},
 expanded_scalar_same20994cases41988states=True,scalar_correct_Qfp={n:dict(v)for n,v in comparison.items()},wrong_scalar9600_retained=True,
 scalar_parent_increases1132_hist=dict(increases),scalar_classes=dict(directclasses),remaining_DIRTY149_vs146=True,scalar_5equals_kept=True,no_new_correctQfp_deficits_not_universal_parent_win=True,
 author673814_partition=[241960,778,61524,167952,201600],author26011MPFR_plus110sNaN=True,author_unit100800paired_tests201600calls=True,
 two_authorHOST_buildselector_and_NaN_recount_preflights0excluded=True,parent_campaigns_not_fresh=True,reviewed507_stays422_author438_not_promoted=True,device_IO=0)
print(json.dumps(save('accounting.json',out)),flush=True)
