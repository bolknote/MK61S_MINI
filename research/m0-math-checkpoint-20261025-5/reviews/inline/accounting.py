"""Read-only same-corpus public/scalar accounting including every slowdown."""
import gzip,hashlib,itertools,json
from collections import Counter
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-inline-20261025';P=R/'.build/m0-pow-reciprocal-one-20261025'
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def equal(a,b):
 a,b=int(a,16),int(b,16)
 return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
def inline_saved(D):
 u=(1<<32)//(65536+512*((D>>9)-128)+256);p=((D+1)>>1)*u;e=(p-(1<<31))//65536;q=u-(u*e//32768)
 return 5 if q<0xffffffff//D else 4
def expected(b,p,products,seeds):
 E=(b>>52)&2047;k=b&0x7fffffffffffffff
 if E==0:
  if k<=1<<50:return 22 if k>>32<1<<18 else 24
  return p+(8 if k>>32>1<<18 else 11)
 if E>2044:return p+2
 return p-2*products-sum(inline_saved(d)for d in seeds)
q=json.loads((W/'qualification.json').read_text());fixed={tuple(p)for p in q['fixed_pairs']};assert len(fixed)==1
fresh=json.loads((W/'new-qualification.json').read_text());fm={(r['x'],r['y'],r['SIO']):r for r in fresh['rows']};assert len(fm)==10254
original=json.loads((P/'original153.json').read_text())['rows'];opairs={(r['x'],r['y'])for r in original};orig={}
keys=set();pairs=Counter();counts=Counter();deltas=Counter();loss=[set(),set()];equals=set();equal_transitions=[];wrong=refs=overlap=callcount=seedcount=prodcount=parent_paths=unchanged_paths=0;acc=Counter()
jobs={p:dict(x=p[0],y=p[1],group='single_new_strict_pair_fix')for p in fixed};upcase=None
with gzip.open(P/'qualification-records.jsonl.gz','rt')as old,gzip.open(W/'qualification-records.jsonl.gz','rt')as new:
 for a,b in itertools.zip_longest(old,new):
  assert a is not None and b is not None;p,r=json.loads(a),json.loads(b);key=r['x'],r['y'],r['SIO'];pair=key[:2];assert key not in keys;keys.add(key);pairs[pair]+=1
  assert all(r[n]==v for n,v in p.items()if n not in ['candidate_instructions','parent_reciprocal_instructions'])
  assert r['parent_reciprocal_instructions']==p['candidate_instructions']and equal(r['candidate'],r['expected'])
  calls,seeds,products=r['reciprocal_calls'],r['software_seed_divisors'],r['first_product_reciprocals'];callcount+=len(calls);seedcount+=len(seeds);prodcount+=len(products)
  assert all(c['numerator']=='3FF0000000000000'and 1<=((int(c['denominator'],16)>>52)&2047)<=2044 for c in calls)
  c,pc=r['candidate_instructions'],r['parent_reciprocal_instructions'];delta=c-pc;assert delta==-2*len(products)-sum(inline_saved(d)for d in seeds);deltas[delta]+=1
  if calls:parent_paths+=1;unchanged_paths+=delta==0
  if delta<0:acc[key[2]]+=1
  if delta==-7 and upcase is None:upcase=r
  for n,v in r['references'].items():
   refs+=1;good=equal(v['output'],r['expected']);assert good==v['correct_Qfplib']
   if not good:wrong+=1;continue
   rc=v['instructions'];counts['faster'if c<rc else'equal'if c==rc else'slower']+=1
   if pc>rc:loss[0].add(pair)
   if c>rc:loss[1].add(pair)
   if c==rc:equals.add(pair)
   if pc>rc and c==rc:equal_transitions.append(dict(x=pair[0],y=pair[1],SIO=key[2],reference=n,parent=pc,candidate=c,Qfplib=rc))
  if key in fm:
   overlap+=1;f=fm[key];assert f['expected']==r['expected']and f['outputs']['parent']==f['outputs']['control']==f['outputs']['candidate']==r['candidate']
   assert f['instructions']['parent']==f['instructions']['control']==pc and f['instructions']['candidate']==c
   assert f['reciprocal_calls']==calls and f['software_seed_divisors']==seeds and f['first_product_reciprocals']==products
   for n,v in r['references'].items():assert [v['output'],v['instructions'],v['correct_Qfplib']]==[f['outputs'][n],f['instructions'][n],f['correct'][n]]
  if pair in opairs:orig[key]=r
assert len(keys)==241960 and len(pairs)==120980 and all(v==2 for v in pairs.values())and refs==279522 and wrong==77106
assert [len(s)for s in loss]==[11372,11371]and loss[1]<=loss[0]and loss[0]-loss[1]==fixed and not fixed&equals
assert acc==dict(READY=377,DIRTY=377)and parent_paths==778 and unchanged_paths==24 and callcount==778 and prodcount==754 and seedcount==377 and overlap==10254
assert dict(deltas)=={-7:3,-6:374,-2:377,0:241206}and dict(counts)==dict(slower=21028,faster=178683,equal=2705)
assert len(equal_transitions)==1 and tuple([equal_transitions[0]['x'],equal_transitions[0]['y']])not in fixed
for r in equal_transitions:jobs.setdefault((r['x'],r['y']),dict(x=r['x'],y=r['y'],group='separate_new_reference_state_equality_not_strict_fix'))
if upcase:jobs.setdefault((upcase['x'],upcase['y']),dict(x=upcase['x'],y=upcase['y'],group='one_up_inline_saving5_witness'))
hist={n:Counter()for n in ['parent','candidate']}
for i,row in enumerate(original):
 rr=[orig[row['x'],row['y'],s]for s in ['READY','DIRTY']]
 for n,k in [('parent','parent_reciprocal_instructions'),('candidate','candidate_instructions')]:
  vv=[r['references'][row['reference']]for r in rr];assert all(v['correct_Qfplib']for v in vv)
  kind='slower'if any(r[k]>v['instructions']for r,v in zip(rr,vv))else'equal'if any(r[k]==v['instructions']for r,v in zip(rr,vv))else'strict';hist[n][kind]+=1
 if i<6:jobs.setdefault((row['x'],row['y']),dict(x=row['x'],y=row['y'],group='unchanged_original153_control'))
assert hist['parent']==hist['candidate']==dict(slower=34,strict=119)
comparison={n:Counter()for n in ['parent','candidate']};increases=Counter();remaining=[];newloss=[];wrong_direct=rows=0;increase_examples={};equal_scalar=[]
with gzip.open(W/'direct-records.jsonl.gz','rt')as f:
 for line in f:
  r=json.loads(line);rows+=1;b=int(r['denominator'],16);rr=r['results'];assert rr['parent']==rr['control']and rr['candidate']['output']==rr['parent']['output']
  for n,v in rr.items():assert v['correct']==equal(v['output'],r['expected'])
  assert all(rr[n]['correct']for n in ['parent','control','candidate'])
  pc,c=rr['parent']['instructions'],rr['candidate']['instructions'];assert c==expected(b,pc,r['first_product_calls'],r['software_seed_divisors'])
  if c>pc:increases[c-pc]+=1;increase_examples.setdefault(str(c-pc),r)
  if not rr['Qfplib']['correct']:wrong_direct+=1;continue
  qc=rr['Qfplib']['instructions']
  for n in comparison:comparison[n]['faster'if rr[n]['instructions']<qc else'equal'if rr[n]['instructions']==qc else'slower']+=1
  if c>qc:remaining.append(r)
  if c>qc and pc<=qc:newloss.append(r)
  if c==qc:equal_scalar.append(r)
saved=json.loads((W/'direct-loss-accounting.json').read_text());assert saved['remaining']==remaining and saved['newloss']==newloss==[]
assert rows==41988 and wrong_direct==9600 and len(remaining)==13 and len(equal_scalar)==5
assert comparison==dict(parent=dict(faster=24966,slower=7422),candidate=dict(faster=32370,equal=5,slower=13))
assert increases=={8:3168,2:352,11:6144}and sum(increases.values())==9664
pre=json.loads((W/'PREFLIGHT-002.json').read_text());assert pre['full_completed_candidate_calls']+pre['full_completed_parent_calls']+pre['fresh_completed_ARM_calls']==318 and pre['full_partial_abort']+pre['fresh_partial_abort']==2 and pre['fresh_MPFR_evaluations']==23
assert 241960+778+61524+167952+143392==615606 and 20960+5051==26011 and 34+76==110
save('selected-public-jobs.json',dict(status='BOUNDED_STRICT_FIX_SEPARATE_EQUALITY_ONEUP_AND_CONTROLS',jobs=list(jobs.values()),strict_fixed_pair=list(fixed),separate_equal_transition=equal_transitions))
save('scalar-selection.json',dict(status='RETAINED_REMAINING_LOSSES_ALL_PARENT_SLOWDOWN_CLASSES',remaining=remaining,remaining_denominators=sorted({r['denominator']for r in remaining}),increase_examples=increase_examples,equal_states=equal_scalar))
out=dict(status='PASS_SAME_CORPUS_PUBLIC_AND_EXPANDED_SCALAR_RECOUNT_ALL_INCREASES_KEPT',ARM_calls=0,MPFR_inputs=0,
 public_pairs120980_states241960_refvariants279522=True,wrong_public77106_retained=True,loss_pairs=[11372,11371],one_new_strict_pair=True,
 separate_reference_state_equality_not_strict_fix=equal_transitions,public_correct_Qfplib=dict(counts),
 faster754_READY377_DIRTY377=True,public_savings=[2,7],parent_replays778_include24_unchanged_controls=True,no_public_increases_wrong_or_newloss=True,
 all_public_exact_sign_and_inline_saving_model=True,all10254_fresh_overlap=True,
 immediate_parent_field='parent_reciprocal_instructions overwritten with numerator-one candidate cost; older history excluded',original153={n:dict(v)for n,v in hist.items()},
 expanded_scalar_same_corpus_pairs20994_states41988=True,not_compared_to_parent_old25536state_score=True,
 scalar_correct_Qfplib_comparisons={n:dict(v)for n,v in comparison.items()},wrong_scalar9600_preserved=True,
 scalar_parent_increase_states=9664,scalar_parent_increase_histogram=dict(increases),all_increases_retained_even_wrong_references=True,
 no_new_correct_Qfp_deficits_not_universal_parent_speed_win=True,scalar_remaining13_and5equals_kept_not_strict_wins=True,
 strict_quietNaN_no_nominal_filter=True,author615606_partition=[241960,778,61524,167952,143392],author26011MPFR_plus110sNaN=True,
 author_bare71696oldplusnew143392_no_wrapper_speed_stack_claim=True,author_symbol_failure0_nestedSP318complete2partial23MPFR_excluded=True,
 parent_campaigns_not_fresh=True,reviewed507_stays422_author437_not_promoted=True,device_IO=0)
print(json.dumps(save('accounting.json',out)),flush=True)
