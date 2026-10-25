"""Three complete saved-corpus recounts, including rejected author run."""
import ast,gzip,hashlib,itertools,json
from collections import Counter
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-bound3-20261025';P=R/'.build/m0-pow-reciprocal-zero-20261025'
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,j):
 with(O/n).open('x')as f:json.dump(j,f,indent=2);f.write('\n')
 return ref(O/n)
fn=next(n for n in ast.parse((R/'.build/m0-pow-reciprocal-certificate-independent-20261025/accounting.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='equal');exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-quietNaN-policy>','exec'),globals())
domain=json.loads((O/'integer-domain.json').read_text());errors={r['D']:r['error']for r in domain['rows']}
def saving(r):
 ds=[D for D in r['software_seed_divisors']if errors[D]==3];assert r['bound3_seed_divisors']==ds;return 3*len(ds)
fresh=json.loads((W/'new-qualification.json').read_text());fm={(r['x'],r['y'],r['SIO']):r for r in fresh['rows']};assert len(fm)==10254
anc_old=json.loads((R/'.build/m0-pow-reciprocal-zero-independent-20261025/selected-public-jobs.json').read_text())['ancestry32'];ancmap={(r['x'],r['y'],r['SIO']):r for r in anc_old}
keys=set();pairs=Counter();loss=[set(),set()];deltas=Counter();counts=Counter();refs=wrong=overlap=paths=unchanged=0;ancestry=[];anc_hist=Counter();jobs={};speedrows=[]
original=json.loads((P/'original153.json').read_text())['rows'];opairs={(r['x'],r['y'])for r in original};orig={}
with gzip.open(P/'qualification-records.jsonl.gz','rt')as old,gzip.open(W/'qualification-records.jsonl.gz','rt')as new:
 for a,b in itertools.zip_longest(old,new):
  assert a is not None and b is not None;p,r=json.loads(a),json.loads(b);key=r['x'],r['y'],r['SIO'];pair=key[:2];assert key not in keys;keys.add(key);pairs[pair]+=1
  assert all(r[k]==v for k,v in p.items()if k not in ['candidate_instructions','parent_reciprocal_instructions'])
  pc,c=r['parent_reciprocal_instructions'],r['candidate_instructions'];assert pc==p['candidate_instructions']and equal(r['candidate'],r['expected'])and c==pc-saving(r)
  deltas[c-pc]+=1
  if r['reciprocal_calls']:paths+=1;unchanged+=pc==c
  if c<pc:speedrows.append(r);jobs.setdefault(pair,dict(x=pair[0],y=pair[1],group='actual_bound3_public_speedup'))
  for n,v in r['references'].items():
   refs+=1;good=equal(v['output'],r['expected']);assert good==v['correct_Qfplib']
   if not good:wrong+=1;continue
   q=v['instructions'];counts['faster'if c<q else'equal'if c==q else'slower']+=1
   if pc>q:loss[0].add(pair)
   if c>q:loss[1].add(pair)
  if key in ancmap:
   a=ancmap[key];assert pc==a['Zero']and c>a['Inline'];ancestry.append(dict(a,Bound3=c));anc_hist[c-a['Inline']]+=1
   if a['has_correct_Qfp']:jobs.setdefault(pair,dict(x=pair[0],y=pair[1],group='ancestral_already_losing_regression'))
  if key in fm:
   overlap+=1;f=fm[key];assert f['outputs']['parent']==f['outputs']['control']==f['outputs']['candidate']==r['candidate']and f['expected']==r['expected']
   assert f['instructions']['parent']==f['instructions']['control']==pc and f['instructions']['candidate']==c
   for k in ['reciprocal_calls','software_seed_divisors','first_product_reciprocals','remainder_certificates','removed_zero_operations','bound3_seed_divisors']:assert f[k]==r[k]
   for n,v in r['references'].items():assert[v['output'],v['instructions'],v['correct_Qfplib']]==[f['outputs'][n],f['instructions'][n],f['correct'][n]]
  if pair in opairs:orig[key]=r
assert len(keys)==241960 and len(pairs)==120980 and all(v==2 for v in pairs.values())and refs==279522 and wrong==77106 and overlap==10254
assert loss[0]==loss[1]and len(loss[0])==11369 and deltas=={-3:10,0:241950}and counts==dict(slower=21026,faster=178686,equal=2704)
assert paths==778 and unchanged==768 and len(ancestry)==32 and sum(r['has_correct_Qfp']for r in ancestry)==2
hist={n:Counter()for n in ['parent','candidate']}
for i,r in enumerate(original):
 rr=[orig[r['x'],r['y'],s]for s in ['READY','DIRTY']]
 for n,k in [('parent','parent_reciprocal_instructions'),('candidate','candidate_instructions')]:
  vv=[x['references'][r['reference']]for x in rr];assert all(v['correct_Qfplib']for v in vv)
  kind='slower'if any(x[k]>v['instructions']for x,v in zip(rr,vv))else'equal'if any(x[k]==v['instructions']for x,v in zip(rr,vv))else'strict';hist[n][kind]+=1
 if i<4:jobs.setdefault((r['x'],r['y']),dict(x=r['x'],y=r['y'],group='original153_control'))
assert hist==dict(parent=dict(slower=33,strict=120),candidate=dict(slower=33,strict=120))
comp={n:Counter()for n in ['parent','candidate']};sdelta=Counter();rows=wrong_s=0;examples={};directloss=[]
with gzip.open(P/'direct-records.jsonl.gz','rt')as old,gzip.open(W/'direct-records.jsonl.gz','rt')as new:
 for a,b in itertools.zip_longest(old,new):
  assert a is not None and b is not None;p,r=json.loads(a),json.loads(b);rows+=1;rr=r['results'];assert all(r[k]==p[k]for k in ['denominator','NZCV','SIO','expected','software_seed_divisors','first_product_reciprocals','remainder_certificates','removed_zero_operations'])
  assert rr['parent']==rr['control']==p['results']['candidate']and rr['candidate']['output']==rr['parent']['output']and rr['Qfplib']==p['results']['Qfplib']
  for n,v in rr.items():assert v['correct']==equal(v['output'],r['expected'])
  d=rr['candidate']['instructions']-rr['parent']['instructions'];assert d==-saving(r)and d<=0;sdelta[d]+=1
  for D in r['software_seed_divisors']:examples.setdefault(str(errors[D]),r)
  if not rr['Qfplib']['correct']:wrong_s+=1;continue
  q=rr['Qfplib']['instructions']
  for n in comp:comp[n]['faster'if rr[n]['instructions']<q else'equal'if rr[n]['instructions']==q else'slower']+=1
  if rr['candidate']['instructions']>q:directloss.append(r)
assert rows==41988 and wrong_s==9600 and not directloss and sdelta=={-3:271,0:41717}and comp==dict(parent=dict(faster=32387,equal=1),candidate=dict(faster=32387,equal=1))
ecomp={n:Counter()for n in ['parent','candidate']};edelta=Counter();seen=set();soft=set();eloss={n:set()for n in ecomp};fixed=[]
with gzip.open(P/'expanded-seed-records.jsonl.gz','rt')as old,gzip.open(W/'expanded-seed-records.jsonl.gz','rt')as new:
 for a,b in itertools.zip_longest(old,new):
  assert a is not None and b is not None;p,r=json.loads(a),json.loads(b);key=r['D'],r['pattern'],r['SIO'];assert key not in seen;seen.add(key);rr=r['results']
  assert all(r[k]==p[k]for k in ['D','pattern','denominator','NZCV','SIO','expected','software_seed_divisors','first_product_reciprocals','remainder_certificates','removed_zero_operations'])
  assert rr['parent']==p['results']['candidate']and rr['Qfplib']==p['results']['Qfplib']and all(v['correct']and v['output']==r['expected']for v in rr.values())
  d=rr['candidate']['instructions']-rr['parent']['instructions'];assert d==-saving(r)and d<=0;edelta[d]+=1
  for D in r['software_seed_divisors']:assert D==r['D'];soft.add(D)
  q=rr['Qfplib']['instructions']
  for n in ecomp:
   cost=rr[n]['instructions'];ecomp[n]['faster'if cost<q else'equal'if cost==q else'slower']+=1
   if cost>q:eloss[n].add(key)
  if key in eloss['parent']:fixed.append(r)
assert len(seen)==262144 and soft==set(range(65536,131072))and not eloss['candidate']and len(eloss['parent'])==2
assert ecomp==dict(parent=dict(faster=262131,slower=2,equal=11),candidate=dict(faster=262132,equal=12))and edelta=={-3:2324,0:259820}
failure=json.loads((W/'HOST-PREFLIGHT-001.json').read_text());assert[failure[k]for k in ['completed_ARM_calls','partial_aborted_ARM_calls','directed_MPFR_input_evaluations','sNaN_policy_shortcuts']]==[14184,0,1106,76]and 6*(failure['first_state_index']+1)==14184
old=(W/'trace-preflight-001.py').read_text();new=(W/'trace.py').read_text();assert new==old.replace('def equivalent(parent,candidate):','def equivalent(parent,candidate,seed_correction_changed=True):').replace('delta=D if D in SEED_ERRORS','delta=D if seed_correction_changed and D in SEED_ERRORS')
old=(W/'qualify-new-preflight-001.py').read_text();new=(W/'qualify-new.py').read_text();assert new==old.replace("equivalent(args['parent'],args['control'])","equivalent(args['parent'],args['control'],seed_correction_changed=False)")
assert 2097152+241960+778+61524+167952+786432==3355798 and 20960+5051+131072==157083
save('selected-public-jobs.json',dict(jobs=list(jobs.values()),ancestry32=ancestry,actual_speedup_rows=speedrows))
save('scalar-selection.json',dict(all5_error_class_examples=examples,expanded_two_old_losses_now_fixed=fixed))
out=dict(status='PASS_ALL_SAVED_RAW_CORPORA_AND_HONEST_REJECTED_TRACE_ACCOUNTING',ARM_calls=0,MPFR_inputs=0,
 public120980pairs241960states279522refs_wrong77106=True,public_loss11369_unchanged_no_pair_fixes=True,public_delta=dict(deltas),correctQfp=dict(counts),all10254_fresh_overlap=True,
 parent778replays_include768unchanged10changed=True,all_correct_wrong_outputs_costs_and_saving3_only_error3_kept=True,
 original153={n:dict(v)for n,v in hist.items()},ancestral32_regressions_still_worse_than_Inline_hist=dict(anc_hist),ancestral2_already_losing=[r for r in ancestry if r['has_correct_Qfp']],
 scalar20994cases41988states0loss_9600wrongkept=True,scalar_comparison={n:dict(v)for n,v in comp.items()},scalar_delta=dict(sdelta),
 expanded131072inputs262144states_all65536actualD_seen=True,expanded_comparison={n:dict(v)for n,v in ecomp.items()},expanded_delta=dict(edelta),expanded2loss_to0_finite_not_universal=True,
 additive_fresh_author3355798_partition=[2097152,241960,778,61524,167952,786432],author157083MPFR_plus110sNaN=True,overlapping_campaigns_not_unique=True,
 rejected_author_trace=failure,rejected14184ARM1106MPFR76sNaN_0partial_excluded=True,
 corrected_trace_defaultTrue_semantics_exactly_unchanged=True,only_parent_control_role_False_in_repeated_terminal_publiccontrol=True,
 failed_run_NOT_fresh_qualified_or_doubled=True,cycle_effect_error1_branch_reversal_unmeasured=True,performance_adoption_GO=False,
 reviewed507422_not_author438=True,devices=0)
print(json.dumps(save('accounting.json',out)),flush=True)
