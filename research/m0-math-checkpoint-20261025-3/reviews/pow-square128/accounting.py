"""Saved old/new corpus and parent-lineage accounting; no ARM/MPFR replay."""
import gzip,hashlib,json
from collections import Counter
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-square128-r2-20261025';BASE=R/'.build/m0-pow-exp-table-product-20261025';M64=(1<<64)-1;M32=(1<<32)-1
def ref(p):p=Path(p);d=p.read_bytes();return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
def equal(a,b):
 a,b=int(a,16),int(b,16)
 return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
def high32(a,b):return (a>>16)*(b>>16)+((a&65535)*(b>>16)>>16)+((a>>16)*(b&65535)>>16)
def approx(a,b):return ((a>>32)*(b>>32)+high32(a&M32,b>>32)+high32(a>>32,b&M32))&M64
classes={(False,False):(129,94),(False,True):(116,89),(True,False):(195,154),(True,True):(182,149)}
def check_calls(calls):
 delta=0
 for c in calls:
  h,l=int(c['high'],16),int(c['low'],16);p=(h*h+(2*approx(l,h)if l else 0))&((1<<128)-1)
  a,b=classes[bool(l),bool(p>>127)];assert (c['old_cost'],c['new_cost'])==(a,b);delta+=b-a
 return delta
new=json.loads((W/'new-qualification.json').read_text());fresh={}
for row in new['rows']:
 key=row['x'],row['y'],row['SIO'];assert key not in fresh;fresh[key]=row
assert len(fresh)==10254
original=[]
for r in json.loads((R/'.build/m0-asin-scaled-bound-v164-20261023/slower-inputs.json').read_text())['rows']:
 if r['operation']=='pow':
  name='qfp_composed_pow_exact'if r['stream']=='composed_exact_exponents'else 'qfp_composed_pow_integer'if r['stream'].startswith('composed_negative_')else 'qfp_composed_pow'
  original.append((r['x'],r['y'],name))
original_pairs={v[:2]for v in original};original_states={};cores={};variants={};union_keys=set()
old_parent_losses=set();old_losses=set();parent_losses=set();losses=set();compare=Counter();deltas=Counter();old_classes=Counter();old_variants=old_wrong=old_count=old_kernel_calls=overlap=wrong=total_variants=0
def tally(key,expected,output,cost,parent,refs):
 global wrong,total_variants
 assert key not in union_keys;union_keys.add(key)
 assert equal(output,expected)and cost<=parent;deltas[cost-parent]+=1
 for name,v in refs.items():
  total_variants+=1;good=equal(v['output'],expected);assert good==v['correct_Qfplib']
  if not good:wrong+=1;continue
  q=v['instructions'];compare['faster'if cost<q else 'slower'if cost>q else 'equal']+=1
  if parent>q:parent_losses.add(key[:2])
  if cost>q:assert parent>q;losses.add(key[:2])
 if key[:2]in original_pairs:original_states[key]=(cost,parent,refs)
with gzip.open(W/'parent-corpus.jsonl.gz','rt')as corpus,gzip.open(W/'qualification-records.jsonl.gz','rt')as raw,gzip.open(W/'union-records.jsonl.gz','rt')as union:
 for i,(a,b)in enumerate(zip(corpus,raw)):
  core=json.loads(a);row=json.loads(b);key=row['x'],row['y'],row['SIO']
  assert key not in cores and all(row[k]==v for k,v in core.items())
  cores[key]=(row['expected'],row['parent_output'],row['parent_cost'])
  assert row['candidate']==row['parent_output']and equal(row['candidate'],row['expected'])
  delta=check_calls(row['square_calls']);assert row['candidate_instructions']==row['parent_cost']+delta and delta<=0
  old_kernel_calls+=len(row['square_calls']);old_classes.update(str((c['old_cost'],c['new_cost']))for c in row['square_calls'])
  old_count+=1;refs={name:dict(v)for name,v in row['references'].items()}
  for name,v in refs.items():
   assert v['correct_Qfplib']==equal(v['output'],row['expected']);old_variants+=1
   variants[key+(name,)]=[v['output'],v['instructions'],v['correct_Qfplib'],False]
   if not v['correct_Qfplib']:old_wrong+=1;continue
   if row['parent_cost']>v['instructions']:old_parent_losses.add(key[:2])
   if row['candidate_instructions']>v['instructions']:old_losses.add(key[:2]);assert row['parent_cost']>v['instructions']
  if key in fresh:
   overlap+=1;r=fresh[key]
   assert r['outputs']['candidate']==row['candidate']and r['expected']==row['expected']and r['instructions']['parent']==row['parent_cost']and r['instructions']['candidate']==row['candidate_instructions']
   for n in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']:
    v=dict(output=r['outputs'][n],instructions=r['instructions'][n],correct_Qfplib=r['correct'][n])
    if n in refs:assert refs[n]==v
    refs[n]=v
  u=json.loads(next(union));assert (u['x'],u['y'],u['SIO'])==key and u['candidate']==row['candidate']and u['candidate_instructions']==row['candidate_instructions']and u['parent_instructions']==row['parent_cost']and u['references']==refs
  tally(key,row['expected'],row['candidate'],row['candidate_instructions'],row['parent_cost'],refs)
  if i%100000==0:print('saved-square-states',i,flush=True)
 assert next(corpus,None)is None and next(raw,None)is None
 assert old_count==232936 and old_variants==252450 and old_wrong==60686 and old_kernel_calls==756
 assert [len(old_parent_losses),len(old_losses)]==[10853,10850]and old_losses<=old_parent_losses
 for key,r in fresh.items():
  assert r['outputs']['parent']==r['outputs']['control']==r['outputs']['candidate']and r['instructions']['parent']==r['instructions']['control']
  assert all(equal(r['outputs'][n],r['expected'])for n in ['parent','control','candidate'])
  assert r['instructions']['candidate']-r['instructions']['parent']==check_calls(r['square_calls'])
  if key in cores:continue
  refs={n:dict(output=r['outputs'][n],instructions=r['instructions'][n],correct_Qfplib=r['correct'][n])for n in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']}
  u=json.loads(next(union));assert (u['x'],u['y'],u['SIO'])==key and u['candidate']==r['outputs']['candidate']and u['candidate_instructions']==r['instructions']['candidate']and u['parent_instructions']==r['instructions']['parent']and u['references']==refs
  tally(key,r['expected'],r['outputs']['candidate'],r['instructions']['candidate'],r['instructions']['parent'],refs)
 assert next(union,None)is None
# Independently bind the inherited complete parent union to its accepted raw
# streams, including all three references and the earlier corrected R lineage.
seen_keys=set()
def parent_check(key,expected,output,cost,refs):
 assert cores[key]==(expected,output,cost);seen_keys.add(key)
 for name,v in refs.items():
  a=variants[key+(name,)];assert a[:3]==[v['output'],v['instructions'],v['correct_Qfplib']];a[3]=True
with gzip.open(BASE/'old-records.jsonl.gz','rt')as f:
 for line in f:
  r=json.loads(line);refs={n:{k:v[k]for k in ['output','instructions','correct_Qfplib']}for n,v in r['references'].items()}
  parent_check((r['x'],r['y'],r['SIO']),r['expected'],r['candidate'],r['candidate_instructions'],refs)
for r in json.loads((BASE/'new-qualification.json').read_text())['rows']:
 refs={n:dict(output=r['outputs'][n],instructions=r['instructions'][n],correct_Qfplib=r['correct'][n])for n in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']}
 parent_check((r['x'],r['y'],r['SIO']),r['expected'],r['outputs']['candidate'],r['instructions']['candidate'],refs)
assert len(seen_keys)==232936 and all(v[3]for v in variants.values())
assert len(union_keys)==241960 and len({k[:2]for k in union_keys})==120980 and overlap==1230
assert total_variants==279522 and wrong==77106 and dict(compare)==dict(slower=21167,faster=178544,equal=2705)
assert [len(parent_losses),len(losses)]==[11449,11434]and losses<=parent_losses and len(parent_losses-losses)==15
assert len(parent_losses-old_parent_losses)==596 and max(deltas)==0
counts={n:Counter()for n in ['parent','candidate']};fixed=[]
for x,y,name in original:
 states=[original_states[x,y,s]for s in ['READY','DIRTY']]
 for n,index in [('candidate',0),('parent',1)]:
  assert all(v[2][name]['correct_Qfplib']for v in states)
  direction='slower'if any(v[index]>v[2][name]['instructions']for v in states)else 'equal'if any(v[index]==v[2][name]['instructions']for v in states)else 'strict';counts[n][direction]+=1
 if any(v[1]>v[2][name]['instructions']for v in states)and all(v[0]<v[2][name]['instructions']for v in states):fixed.append([x,y])
assert len(original)==153 and dict(counts['parent'])==dict(slower=35,strict=118)and dict(counts['candidate'])==dict(slower=34,strict=119)and len(fixed)==1
out=dict(status='PASS_SAVED_24BYTE_KERNEL_PUBLIC_COST_AND_REFERENCE_ACCOUNTING',ARM_calls=0,MPFR_inputs=0,
 actual_parent_streams_bound=True,parent_states232936_reference_variants252450=True,all_old_bits_identical=True,
 all_saved_kernel_trace_classes_recomputed=True,old_kernel_calls=old_kernel_calls,kernel_class_counts=dict(old_classes),
 old116468_pair_losses=[10853,10850],union120980_pair_states241960=True,union_reference_variants279522=True,
 expanded_losses=[11449,11434],additional_preexisting_loss_pairs596=True,new_raw_loss_pairs=0,parent_cost_increases=0,
 actual_cost_delta_histogram=dict(deltas),correct_Qfplib_comparison=dict(compare),wrong_Qfplib_reference_variants=77106,
 strict_quietNaN_all_reference_flags_checked=True,no_nominal_domain_filter=True,original153={n:dict(c)for n,c in counts.items()},new_original_strict_fix=fixed,
 pilot918_and_route70_not_in_qualified_counts=True,author330880_ARM_and5051_MPFR_plus76shortcuts_not_own_calls=True,
 r2_copy_not_new_numerical_execution=True,reviewed_whole507_stays422=True,author437_not_promoted=True,device_IO=0)
with (O/'accounting.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'accounting.json'),indent=2))
