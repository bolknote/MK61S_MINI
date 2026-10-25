"""Recount all saved rows; keep increased costs and wrong references."""
from pathlib import Path
from collections import Counter
import gzip,json,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;P=W.parent/'m0-pow-reciprocal-certificate-20261025'
load=lambda n:json.loads((W/n).read_bytes())
def equal(a,b):
 a,b=int(a,16),int(b,16)
 return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if(b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
q=load('qualification.json');f=load('new-qualification.json');d=load('direct-proof.json')
controls={(r['x'],r['y'],r['SIO']):r for r in f['rows']};assert len(controls)==10254
original=json.loads((P/'original153.json').read_bytes())['rows'];keys={(r['x'],r['y'],s)for r in original for s in ['READY','DIRTY']};observations={}
old=set();new=set();comp=Counter();delta=Counter();wrong=variants=cases=0;ties=set()
with gzip.open(W/'qualification-records.jsonl.gz','rt')as stream:
 for line in stream:
  r=json.loads(line);k=r['x'],r['y'],r['SIO'];p,c=r['parent_reciprocal_instructions'],r['candidate_instructions'];cases+=1;delta[c-p]+=1
  assert equal(r['candidate'],r['expected'])
  if k in keys:observations[k]=r
  for ref in r['references'].values():
   variants+=1
   assert ref['correct_Qfplib']==equal(ref['output'],r['expected'])
   if not ref['correct_Qfplib']:wrong+=1;continue
   v=ref['instructions'];comp['faster'if c<v else'equal'if c==v else'slower']+=1
   if p>v:old.add(k[:2])
   if c>v:new.add(k[:2])
   if c==v:ties.add(k[:2])
  if k in controls:
   row=controls.pop(k);assert row['instructions']['parent']==row['instructions']['control']==p and row['instructions']['candidate']==c
   for name,ref in r['references'].items():assert(ref['output'],ref['instructions'],ref['correct_Qfplib'])==(row['outputs'][name],row['instructions'][name],row['correct'][name])
   for name in ['reciprocal_calls','software_seed_divisors','first_product_reciprocals','remainder_certificates','removed_zero_operations']:assert row[name]==r[name]
assert cases==241960 and variants==279522 and wrong==77106 and not controls and not new-old
assert [len(old),len(new)]==[11369,11369]and comp==q['correct_Qfplib_comparison']
hist={n:Counter()for n in ['parent','candidate']};saved=[]
for r in original:
 states=[]
 for state in ['READY','DIRTY']:
  row=observations[r['x'],r['y'],state];ref=row['references'][r['reference']];assert ref['correct_Qfplib']
  states.append(dict(SIO=state,parent=row['parent_reciprocal_instructions'],candidate=row['candidate_instructions'],Qfplib=ref['instructions']))
 for label in hist:
  hist[label]['slower'if any(s[label]>s['Qfplib']for s in states)else'equal'if any(s[label]==s['Qfplib']for s in states)else'strict']+=1
 saved.append(dict(x=r['x'],y=r['y'],stream=r['stream'],reference=r['reference'],states=states))
(W/'original153.json').write_text(json.dumps(dict(rows=saved),indent=2)+'\n')
scalar={n:Counter()for n in ['parent','candidate']};losses={n:set()for n in scalar};inc=Counter();scases=swrong=0;remaining=[]
with gzip.open(W/'direct-records.jsonl.gz','rt')as stream:
 for i,line in enumerate(stream):
  row=json.loads(line);scases+=1;r=row['results'];change=r['candidate']['instructions']-r['parent']['instructions']
  if change>0:inc[change]+=1
  if not r['Qfplib']['correct']:swrong+=1;continue
  for name in scalar:
   c,v=r[name]['instructions'],r['Qfplib']['instructions'];scalar[name]['faster'if c<v else'equal'if c==v else'slower']+=1
   if c>v:losses[name].add(i)
  if i in losses['candidate']:remaining.append(row)
assert scases==41988 and swrong==9600 and[len(losses[n])for n in ['parent','candidate']]==[1,0]and not losses['candidate']-losses['parent']
assert{n:dict(v)for n,v in scalar.items()}==d['correct_Qfplib_comparisons']
u=json.loads((W.parent/'m0-ddiv-remainder-certificate-r3-20261025/unit-proof.json').read_bytes())
calls=q['total_fresh_public_ARM_calls']+f['fresh_ARM_calls']+d['actual_ARM_calls']+u['actual_ARM_calls'];assert calls==673814
out=dict(status='PASS_KNOWN_ZERO_PUBLIC_SCALAR_AND_UNIT_ACCOUNTING',same_corpus_pairs=120980,states=cases,loss_pairs=[len(old),len(new)],strict_fixes=len((old-new)-ties),equal_fixes=len((old-new)&ties),new_losses=0,
 correct_Qfplib_comparison=dict(comp),wrong_public_Qfplib_variants=wrong,public_instruction_delta_histogram=dict(sorted(delta.items())),original153={n:dict(v)for n,v in hist.items()},
 scalar_loss_states=[1,0],new_scalar_loss_states=0,scalar_correct_comparison={n:dict(v)for n,v in scalar.items()},wrong_scalar_Qfplib_variants=swrong,scalar_parent_increase_histogram=dict(inc),
 total_qualified_fresh_ARM_calls=calls,actual_directed_MPFR_inputs=f['actual_directed_MPFR_inputs']+d['actual_directed_MPFR_inputs'],sNaN_policy_shortcuts=f['sNaN_policy_shortcuts']+d['sNaN_policy_shortcuts'],
 new_ARM_or_MPFR_calls_in_this_recount=0,hardware_accessed=False,goal_complete=False)
e=load('expanded-seed-proof.json')
ecounts={n:Counter()for n in ['parent','candidate']};ewrong=ecases=0;eincrease=0
with gzip.open(W/'expanded-seed-records.jsonl.gz','rt')as stream:
 for line in stream:
  row=json.loads(line);ecases+=1;v=row['results'];eincrease+=v['candidate']['instructions']>v['parent']['instructions']
  assert v['parent']['correct']and v['candidate']['correct']and v['parent']['output']==v['candidate']['output']
  assert v['Qfplib']['correct']==equal(v['Qfplib']['output'],row['expected'])
  if not v['Qfplib']['correct']:ewrong+=1;continue
  for name in ecounts:
   c,q=v[name]['instructions'],v['Qfplib']['instructions'];ecounts[name]['faster'if c<q else'equal'if c==q else'slower']+=1
assert ecases==262144 and not eincrease and ewrong==e['wrong_Qfplib_variants_retained']
assert{n:dict(v)for n,v in ecounts.items()}==e['correct_Qfplib_comparisons']
out['same_corpus_qualified_fresh_ARM_calls']=calls
out['expanded_seed_scan']=dict(input_evaluations=131072,seed_divisors=65536,patterns=2,states=ecases,correct_Qfplib_comparison={n:dict(v)for n,v in ecounts.items()},wrong_Qfplib_variants=ewrong,parent_increases=0,loss_states=[e['parent_loss_states'],e['candidate_loss_states']],new_losses=0)
out['total_qualified_fresh_ARM_calls']+=e['actual_ARM_calls'];assert out['total_qualified_fresh_ARM_calls']==1460246
out['actual_directed_MPFR_input_evaluations']=out.pop('actual_directed_MPFR_inputs')+e['actual_directed_MPFR_inputs'];assert out['actual_directed_MPFR_input_evaluations']==157083
out['campaign_overlap_not_deduplicated_not_unique_input_count']=True
(W/'summary.json').write_text(json.dumps(out,indent=2)+'\n');(W/'direct-loss-accounting.json').write_text(json.dumps(dict(remaining=remaining,scalar_parent_increase_histogram=dict(inc),new_losses=0),indent=2)+'\n');print(json.dumps(out,indent=2))
