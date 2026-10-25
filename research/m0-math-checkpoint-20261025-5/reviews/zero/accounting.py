"""Saved raw recount: full public, same scalar, separate expanded seed scan."""
import ast,gzip,hashlib,itertools,json
from collections import Counter
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-zero-20261025';P=R/'.build/m0-pow-reciprocal-certificate-20261025'
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,j):
 with(O/n).open('x')as f:json.dump(j,f,indent=2);f.write('\n')
 return ref(O/n)
for name in ['equal','certificate']:
 f=next(n for n in ast.parse((R/'.build/m0-pow-reciprocal-certificate-independent-20261025/accounting.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name==name);exec(compile(ast.Module(body=[f],type_ignores=[]),'<accepted-exact-integer-certificate-and-quietNaN-policy>','exec'),globals())
MASK=(1<<32)-1
def verify_trace(r):
 cs=r['remainder_certificates']
 for c in cs:
  m=certificate(c['base'],c['u'],c['v']);m.pop('expected_saving');assert c==m
 z=r['removed_zero_operations'];assert z['first_product_calls']==len(r['first_product_reciprocals'])and 0<=z['half_normalization_calls']<=z['first_product_calls']
 assert z['fast_round_up_calls']==sum(c['fast']and c['decision']=='up'for c in cs)
 return sum(z.values())
fresh=json.loads((W/'new-qualification.json').read_text());fm={(r['x'],r['y'],r['SIO']):r for r in fresh['rows']};assert len(fm)==10254
original=json.loads((P/'original153.json').read_text())['rows'];opairs={(r['x'],r['y'])for r in original};orig={}
keys=set();pairs=Counter();loss=[set(),set()];deltas=Counter();counts=Counter();classes=Counter();jobs={};examples={};ancestry=[];anc_hist=Counter();refs=wrong=overlap=paths=unchanged=0;equal_transitions=[]
with gzip.open(P/'qualification-records.jsonl.gz','rt')as old,gzip.open(W/'qualification-records.jsonl.gz','rt')as new:
 for a,b in itertools.zip_longest(old,new):
  assert a is not None and b is not None;p,r=json.loads(a),json.loads(b);key=r['x'],r['y'],r['SIO'];pair=key[:2];assert key not in keys;keys.add(key);pairs[pair]+=1
  for k,v in p.items():
   if k not in ['candidate_instructions','parent_reciprocal_instructions','remainder_certificates']:assert r[k]==v
  assert r['parent_reciprocal_instructions']==p['candidate_instructions']and equal(r['candidate'],r['expected'])
  assert [{k:v for k,v in c.items()if k!='expected_saving'}for c in p['remainder_certificates']]==r['remainder_certificates']
  pc,c=r['parent_reciprocal_instructions'],r['candidate_instructions'];delta=c-pc;assert delta==-verify_trace(r)and delta<=0;deltas[delta]+=1
  if r['reciprocal_calls']:paths+=1;unchanged+=delta==0
  for cert in r['remainder_certificates']:
   cl=('fast'if cert['fast']else'full')+'_'+cert['decision']+('_cross'if cert['cross_overflow']else'_nocross');classes[cl]+=1
   if cl not in examples:examples[cl]=r;jobs.setdefault(pair,dict(x=pair[0],y=pair[1],group='actual_public_'+cl))
  for n,v in r['references'].items():
   refs+=1;good=equal(v['output'],r['expected']);assert good==v['correct_Qfplib']
   if not good:wrong+=1;continue
   rc=v['instructions'];counts['faster'if c<rc else'equal'if c==rc else'slower']+=1
   if pc>rc:loss[0].add(pair)
   if c>rc:loss[1].add(pair)
   if pc==rc and c<rc:equal_transitions.append(dict(x=pair[0],y=pair[1],SIO=key[2],reference=n,parent=pc,candidate=c,Qfplib=rc));jobs.setdefault(pair,dict(x=pair[0],y=pair[1],group='reference_equality_to_faster_not_new_pair_fix'))
  # Compare exactly the same public rows to Inline via Certificate's bound
  # immediate-parent field, never unrelated scalar campaign statistics.
  inline=p['parent_reciprocal_instructions']
  if pc>inline:
   assert c>inline;ancestry.append(dict(x=pair[0],y=pair[1],SIO=key[2],Inline=inline,Certificate=pc,Zero=c,has_correct_Qfp=any(v['correct_Qfplib']for v in r['references'].values())))
   anc_hist[c-inline]+=1
  if key in fm:
   overlap+=1;f=fm[key];assert f['expected']==r['expected']and f['outputs']['parent']==f['outputs']['control']==f['outputs']['candidate']==r['candidate']
   assert f['instructions']['parent']==f['instructions']['control']==pc and f['instructions']['candidate']==c
   for k in ['reciprocal_calls','software_seed_divisors','first_product_reciprocals','remainder_certificates','removed_zero_operations']:assert f[k]==r[k]
   for n,v in r['references'].items():assert[v['output'],v['instructions'],v['correct_Qfplib']]==[f['outputs'][n],f['instructions'][n],f['correct'][n]]
  if pair in opairs:orig[key]=r
assert len(keys)==241960 and len(pairs)==120980 and all(v==2 for v in pairs.values())and refs==279522 and wrong==77106
assert loss[0]==loss[1]and len(loss[0])==11369 and deltas=={0:241206,-2:612,-3:142}and counts==dict(slower=21026,faster=178686,equal=2704)
assert paths==778 and unchanged==24 and overlap==10254 and len(equal_transitions)==1
assert len(ancestry)==32 and anc_hist=={6:26,5:6}and sum(r['has_correct_Qfp']for r in ancestry)==2
hist={n:Counter()for n in ['parent','candidate']}
for i,r in enumerate(original):
 rr=[orig[r['x'],r['y'],s]for s in ['READY','DIRTY']]
 for n,k in [('parent','parent_reciprocal_instructions'),('candidate','candidate_instructions')]:
  vv=[x['references'][r['reference']]for x in rr];assert all(v['correct_Qfplib']for v in vv)
  kind='slower'if any(x[k]>v['instructions']for x,v in zip(rr,vv))else'equal'if any(x[k]==v['instructions']for x,v in zip(rr,vv))else'strict';hist[n][kind]+=1
 if i<4:jobs.setdefault((r['x'],r['y']),dict(x=r['x'],y=r['y'],group='original153_control'))
assert hist==dict(parent=dict(slower=33,strict=120),candidate=dict(slower=33,strict=120))
for r in ancestry:
 if r['has_correct_Qfp']:jobs.setdefault((r['x'],r['y']),dict(x=r['x'],y=r['y'],group='ancestral_already_losing_regression_still_losing'))
comp={n:Counter()for n in ['parent','candidate']};scalar_delta=Counter();wrong_s=rows=0;directexamples={};scalar_remaining=[];parent_remaining=[]
with gzip.open(P/'direct-records.jsonl.gz','rt')as old,gzip.open(W/'direct-records.jsonl.gz','rt')as new:
 for a,b in itertools.zip_longest(old,new):
  assert a is not None and b is not None;p,r=json.loads(a),json.loads(b);rows+=1;rr=r['results'];assert all(r[n]==p[n]for n in ['denominator','NZCV','SIO','expected'])
  assert rr['parent']==rr['control']==p['results']['candidate']and rr['candidate']['output']==rr['parent']['output']and rr['Qfplib']==p['results']['Qfplib']
  for n,v in rr.items():assert v['correct']==equal(v['output'],r['expected'])
  assert all(rr[n]['correct']for n in ['parent','control','candidate']);d=rr['candidate']['instructions']-rr['parent']['instructions'];assert d==-verify_trace(r)and d<=0;scalar_delta[d]+=1
  for cert in r['remainder_certificates']:
   cl=('fast'if cert['fast']else'full')+'_'+cert['decision']+('_cross'if cert['cross_overflow']else'_nocross');directexamples.setdefault(cl,r)
  if not rr['Qfplib']['correct']:wrong_s+=1;continue
  qc=rr['Qfplib']['instructions']
  for n in comp:comp[n]['faster'if rr[n]['instructions']<qc else'equal'if rr[n]['instructions']==qc else'slower']+=1
  if rr['candidate']['instructions']>qc:scalar_remaining.append(r)
  if rr['parent']['instructions']>qc:parent_remaining.append(r)
assert rows==41988 and wrong_s==9600 and scalar_delta=={-3:4974,-2:19754,0:17260}
assert comp==dict(parent=dict(faster=32382,equal=5,slower=1),candidate=dict(faster=32387,equal=1))and not scalar_remaining and len(parent_remaining)==1
ecomp={n:Counter()for n in ['parent','candidate']};edelta=Counter();Dseen=set();e_keys=set();esoft=set();eloss={n:set()for n in ecomp};remaining=[];ecalls=0
with gzip.open(W/'expanded-seed-records.jsonl.gz','rt')as source:
 for line in source:
  r=json.loads(line);D,pattern,sio=r['D'],r['pattern'],r['SIO'];key=D,pattern,sio;assert key not in e_keys;e_keys.add(key);Dseen.add(D)
  low=0 if pattern==0 else((D*0x9e3779b97f4a7c15)^(D>>3))&((1<<36)-1)|1
  assert 65536<=D<131072 and pattern in [0,1]and r['NZCV']==(D+pattern)&15 and int(r['denominator'],16)==(1023<<52)|((D-65536)<<36)|low
  rr=r['results'];assert all(v['output']==r['expected']and v['correct']for v in rr.values())and rr['parent']['output']==rr['candidate']['output']
  d=rr['candidate']['instructions']-rr['parent']['instructions'];assert d==-verify_trace(r)and d<=0;edelta[d]+=1
  for value in r['software_seed_divisors']:assert value==D;esoft.add(value)
  qc=rr['Qfplib']['instructions']
  for n in ecomp:
   cost=rr[n]['instructions'];ecomp[n]['faster'if cost<qc else'equal'if cost==qc else'slower']+=1
   if cost>qc:eloss[n].add(key)
  if key in eloss['candidate']:remaining.append(r)
assert len(e_keys)==262144 and Dseen==esoft==set(range(65536,131072))and eloss['candidate']<=eloss['parent']
assert ecomp==dict(parent=dict(faster=262096,equal=34,slower=14),candidate=dict(faster=262131,slower=2,equal=11))and edelta=={-3:53412,-2:208730,0:2}
assert [(r['denominator'],r['SIO'],r['results']['candidate']['instructions'],r['results']['Qfplib']['instructions'])for r in remaining]==[('3FF0CEE65125761B','DIRTY',149,146),('3FF10E0E8502C07D','DIRTY',147,146)]
assert 241960+778+61524+167952+201600==673814 and 673814+786432==1460246 and 20960+5051+131072==157083 and 34+76==110
save('selected-public-jobs.json',dict(jobs=list(jobs.values()),equal_to_faster_transition=equal_transitions,ancestry32=ancestry))
save('scalar-selection.json',dict(branch_class_examples=directexamples,parent_same_corpus_loss_now_fixed=parent_remaining,expanded_remaining=remaining))
out=dict(status='PASS_ALL_THREE_SAVED_CORPORA_WITH_EXPLICIT_ANCESTRAL_TRADEOFF',ARM_calls=0,MPFR_inputs=0,
 public_pairs120980_states241960_refs279522=True,wrong_public77106_retained=True,loss_pairs=[11369,11369],strict_pair_fixes=0,equality_pair_fixes=0,public_delta=dict(deltas),faster754_READY377_DIRTY377=True,
 public_current_parent_increases0_newloss0_wrong0=True,all10254_overlap=True,parent_replays778_include24unchanged=True,
 separate_reference_equality_to_faster_not_pair_fix=equal_transitions,original153={n:dict(v)for n,v in hist.items()},
 ancestral_Certificate32_increases_still_worse_than_Inline_hist=dict(anc_hist),ancestral_two_already_losing_Qfp_regressions=[r for r in ancestry if r['has_correct_Qfp']],corrigendum5cd5994f_still_binding=True,performance_adoption_GO=False,
 same_scalar20994cases41988states=True,same_scalar_comparison={n:dict(v)for n,v in comp.items()},same_scalar_wrong9600_retained=True,same_scalar_delta=dict(scalar_delta),same_scalar_loss1to0_not_universal=True,
 expanded131072inputs262144states65536D_two_patterns=True,all65536_actual_softD_observed=True,expanded_comparison={n:dict(v)for n,v in ecomp.items()},expanded_delta=dict(edelta),expanded_loss14to2_newloss0_wrong0=True,expanded_remaining=remaining,
 author1460246_additive_partition=[241960,778,61524,167952,201600,786432],author157083MPFR_plus110sNaN=True,overlapping_campaigns_NOT_unique_union=True,parent_campaigns_not_fresh=True,
 no_parent_increases_in_current_three_corpora_NOT_erasing_ancestral_regressions=True,reviewed507422_not_author438=True,devices=0)
print(json.dumps(save('accounting.json',out)),flush=True)
