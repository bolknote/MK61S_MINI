"""Saved-record and lossless R-lineage recount; zero ARM or MPFR executions."""
import gzip,hashlib,json,re,struct,sys
from collections import Counter
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-exp-table-product-20261025';A=R/'.build/m0-pow-rsqrt-asm-20261024'
sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
image=ElfImage(W/'candidate.elf');table_address=image.symbols['_ZN7m0_eabiL9exp_tableE']
section=next(s for s in image.sections if s[1]!=8 and s[3]<=table_address<table_address+4096<=s[3]+s[5])
table=image.bytes_at(section)[table_address-section[3]:table_address-section[3]+4096]
actual_roots={f'{v:016X}'for v in struct.unpack('<512Q',table)}
def ref(p):p=Path(p);d=p.read_bytes();return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
def equiv(a,b):
 g,e=int(a,16),int(b,16)
 return bool((g&0x7fffffffffffffff)>0x7ff0000000000000 and g&(1<<51))if (e&0x7fffffffffffffff)>0x7ff0000000000000 else g==e
def source_rows(path):
 decoder=json.JSONDecoder()
 with path.open()as f:
  buffer=''
  while True:
   buffer+=f.read(65536);match=re.search(r'"rows"\s*:\s*\[',buffer)
   if match:buffer=buffer[match.end():];break
   assert len(buffer)<2000000,'rows array missing'
  while True:
   buffer=buffer.lstrip(' \t\r\n,')
   if not buffer:buffer=f.read(65536);assert buffer;continue
   if buffer[0]==']':return
   try:row,end=decoder.raw_decode(buffer)
   except json.JSONDecodeError:
    more=f.read(65536);assert more;buffer+=more;continue
   yield row;buffer=buffer[end:]
new=json.loads((W/'new-qualification.json').read_text());fresh={}
for row in new['rows']:
 key=row['x'],row['y'],row['SIO'];assert key not in fresh;fresh[key]=row
known={}
for row in json.loads((R/'.build/m0-exp-directed-product-20261024/pow-loss-replay.json').read_text())['rows']:
 key=row['x'],row['y'],row['SIO'];v=row['fresh_candidate'];value=v['candidate'],v['candidate_instructions'],v['product_calls']
 if key in known:assert known[key]==value
 known[key]=value
assert len(known)==10081
original=[]
for row in json.loads((R/'.build/m0-asin-scaled-bound-v164-20261023/slower-inputs.json').read_text())['rows']:
 if row['operation']=='pow':
  name='qfp_composed_pow_exact'if row['stream']=='composed_exact_exponents'else 'qfp_composed_pow_integer'if row['stream'].startswith('composed_negative_')else 'qfp_composed_pow'
  original.append((row['x'],row['y'],name))
assert len(original)==153
orig_pairs={p[:2]for p in original};orig_states={}
cores={};variants={};old_parent_losses=set();old_losses=set();old_wrong=old_variants=old_states=known_checked=0
parent_losses=set();losses=set();comparison=Counter();wrong=union_variants=overlap=0;increases=Counter();increase_scopes=Counter();roots=set();allrefs=set()
def tally(key,expected,output,cost,parent,refs):
 global wrong,union_variants
 assert equiv(output,expected)
 correct_costs=[]
 for name,v in refs.items():
  union_variants+=1;allrefs.add(name);q=v['instructions'];good=v['correct_Qfplib']
  assert good==equiv(v['output'],expected)
  if not good:wrong+=1;continue
  correct_costs.append(q);comparison['faster'if cost<q else 'slower'if cost>q else 'equal']+=1
  if parent>q:parent_losses.add(key[:2])
  if cost>q:
   losses.add(key[:2]);assert parent>q,('new reference loss',key,name)
 if cost>parent:
  increases[cost-parent]+=1
  scope='wrong_Qfplib_only'if not correct_costs else 'still_no_slower_than_all_correct_references'if cost<=min(correct_costs)else 'already_slower_than_a_correct_reference'
  increase_scopes[scope]+=1
 if key[:2]in orig_pairs:orig_states[key]=(cost,parent,refs)
with gzip.open(W/'old-corpus.jsonl.gz','rt')as corpus,gzip.open(W/'old-records.jsonl.gz','rt')as recorded:
 for i,(c_line,r_line)in enumerate(zip(corpus,recorded)):
  core=json.loads(c_line);row=json.loads(r_line);key=row['x'],row['y'],row['SIO']
  assert key not in cores and all(row[k]==v for k,v in core.items())
  cores[key]=(row['expected'],row['parent_R_output'],row['parent_R_cost'])
  assert row['candidate']==row['parent_R_output']and equiv(row['candidate'],row['expected'])
  products=row['products'];tables=[p for p in products if p['kind']=='table'];generals=[p for p in products if p['kind']=='general']
  assert all(p['a']in actual_roots for p in tables)
  d=sum(int(p['a'],16)==1<<62 for p in tables);g=len(tables)-d;n=len(generals)+d
  roots.update(p['a']for p in tables)
  assert row['table_dyadic_calls']==d and row['table_generic_calls']==g and row['logical_old_product_calls']==n
  parent=row['parent_C77_instructions'];cost=row['candidate_instructions']
  assert cost-parent==2*g-67*d and row['parent_R_cost']==parent+7*n and cost<=row['parent_R_cost']
  if 'known_C77_cost'in row:
   assert known[key]==(row['candidate'],parent,n);known_checked+=1
  old_states+=1;refs={}
  for name,v in row['references'].items():
   assert v['reference']==name and v['correct_Qfplib']==equiv(v['output'],row['expected'])
   variant_key=key+(name,);assert variant_key not in variants
   variants[variant_key]=[v['output'],v['instructions'],v['correct_Qfplib'],0]
   refs[name]={k:v[k]for k in ['output','instructions','correct_Qfplib']};old_variants+=1
   if not v['correct_Qfplib']:old_wrong+=1;continue
   if parent>v['instructions']:old_parent_losses.add(key[:2])
   if cost>v['instructions']:old_losses.add(key[:2]);assert parent>v['instructions']
  if key in fresh:
   overlap+=1;other=fresh[key]
   assert other['outputs']['candidate']==row['candidate']and other['instructions']['candidate']==cost and other['instructions']['parent']==parent and other['expected']==row['expected']
   for name in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']:
    v=dict(output=other['outputs'][name],instructions=other['instructions'][name],correct_Qfplib=other['correct'][name])
    if name in refs:assert refs[name]==v
    refs[name]=v
  tally(key,row['expected'],row['candidate'],cost,parent,refs)
  if i%100000==0:print('saved-old-states',i,flush=True)
 assert next(corpus,None)is None and next(recorded,None)is None
assert old_states==223824 and old_variants==223976 and old_wrong==51126 and known_checked==10081
assert [len(old_parent_losses),len(old_losses)]==[7901,7888]and old_losses<=old_parent_losses
new_seen_roots=set()
for key,row in fresh.items():
 assert row['outputs']['parent']==row['outputs']['control']==row['outputs']['candidate']
 assert row['instructions']['parent']==row['instructions']['control']
 calls=[p for p in row['products']if p['kind']=='table'];assert all(p['a']in actual_roots for p in calls)
 new_seen_roots.update(p['a']for p in calls);d=sum(int(p['a'],16)==1<<62 for p in calls);g=len(calls)-d
 assert row['instructions']['candidate']-row['instructions']['control']==2*g-67*d
 if key in cores:continue
 refs={n:dict(output=row['outputs'][n],instructions=row['instructions'][n],correct_Qfplib=row['correct'][n])for n in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']}
 tally(key,row['expected'],row['outputs']['candidate'],row['instructions']['candidate'],row['instructions']['parent'],refs)
# Reconstruct the actual three-source R union without loading the large JSON
# objects as a whole; each original row and reference variant is checked.
source_counts={}
for bit,name in [(1,'qualification.json'),(2,'targeted.json'),(4,'probe.json')]:
 count=0
 for row in source_rows(A/name):
  key=row['x'],row['y'],row['SIO'];assert cores[key]==(row['expected'],row['outputs']['candidate'],row['instructions']['candidate'])
  reference=row.get('reference','qfp_composed_pow_exact');v=variants[key+(reference,)]
  assert v[:3]==[row['outputs']['Qfplib'],row['instructions']['Qfplib'],row['correct']['Qfplib']]
  v[3]|=bit;count+=1
 source_counts[name]=dict(rows=count,ref=ref(A/name))
assert all(v[3]for v in variants.values())
without_probe=sum(bool(v[3]&3)for v in variants.values());probe_only=sum(v[3]==4 for v in variants.values())
assert without_probe==223826 and probe_only==150
raw_focus=gzip.decompress((W/'lineage/qualified-R-focused.json.gz').read_bytes())
assert raw_focus==(A/'probe.json').read_bytes()and hashlib.sha256(raw_focus).hexdigest()=='340318b19b6d4bae44d5317019af900ef06c00e88f1a6e23fb64691a589fc6a2'
assert len(raw_focus)==547596
assert overlap==610 and union_variants==252450 and wrong==60686
union_keys=cores.keys()|fresh.keys();assert len(union_keys)==232936 and len({key[:2]for key in union_keys})==116468
assert len(fresh)==9722 and new_seen_roots==actual_roots
assert set(comparison)=={'faster','equal','slower'}and dict(comparison)==dict(faster=170087,equal=2693,slower=18984)
assert [len(parent_losses),len(losses)]==[10866,10853]and len(parent_losses-losses)==13 and losses<=parent_losses
assert len(parent_losses-old_parent_losses)==len(losses-old_losses)==2965
assert dict(increases)=={2:8024}and dict(increase_scopes)==dict(already_slower_than_a_correct_reference=2293,still_no_slower_than_all_correct_references=2343,wrong_Qfplib_only=3388)
counts={n:Counter()for n in ['parent','candidate']};fixes=[]
for x,y,name in original:
 pairs=[orig_states[x,y,s]for s in ['READY','DIRTY']]
 for label,pos in [('candidate',0),('parent',1)]:
  assert all(v[2][name]['correct_Qfplib']for v in pairs)
  direction='slower'if any(v[pos]>v[2][name]['instructions']for v in pairs)else 'equal'if any(v[pos]==v[2][name]['instructions']for v in pairs)else 'strict'
  counts[label][direction]+=1
 if any(v[1]>v[2][name]['instructions']for v in pairs)and all(v[0]<v[2][name]['instructions']for v in pairs):fixes.append([x,y])
assert dict(counts['parent'])==dict(slower=48,strict=105)and dict(counts['candidate'])==dict(slower=35,strict=118)and len(fixes)==13
out=dict(status='PASS_COMPLETE_SAVED_REFERENCE_AND_LOSSLESS_LINEAGE_ACCOUNTING',ARM_calls=0,MPFR_inputs=0,
 old_states=223824,old_pairs=111912,old_reference_variants=223976,old_wrong_reference_variants=51126,
 old_losses=[7901,7888],all10081_cost_sensitive_states_bound_to_actual_directed_replay=True,
 union_pairs=116468,union_states=232936,union_reference_variants=252450,overlap_states610=True,
 union_losses=[10866,10853],new_loss_pairs=0,additional2965_losses_preexisting=True,wrong_reference_variants=60686,
 correct_reference_comparison=dict(comparison),cost_increase_states8024_plus2=True,increase_scopes=dict(increase_scopes),
 three_reference_symbols=sorted(allrefs),original153={n:dict(c)for n,c in counts.items()},thirteen_original_bothstate_strict_fixes=fixes,
 all512_actual_roots_seen_in_saved_new_public_calls=True,
 R_source_bindings=source_counts,without_R_qualified_probe_variants=without_probe,qualified_R_probe_only_variants150=True,
 lossless_R_focused_gzip=ref(W/'lineage/qualified-R-focused.json.gz'),uncompressed_bytes=547596,uncompressed_sha256=hashlib.sha256(raw_focus).hexdigest(),
 qualification_boundary='R/probe.json is qualified focused evidence; this packet probe3096 is a distinct excluded pilot. Earlier r5 archive omission is corrected additively; old frozen artifacts are unchanged.',
 reviewed_whole507_preserved422=True,author436_not_promoted=True,device_IO=0,Git=0,canonical=0,network=0)
with (O/'accounting.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'accounting.json'),indent=2))
