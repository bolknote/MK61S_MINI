"""Independent read-only recount against accepted parent raw; no ARM replay."""
import gzip,hashlib,itertools,json
from collections import Counter
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent
W=R/'.build/m0-pow-boundary128-20261025';SQ=R/'.build/m0-pow-square128-r2-20261025'
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def equal(a,b):
 a,b=int(a,16),int(b,16)
 return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
q=json.loads((W/'qualification.json').read_text());fresh=json.loads((W/'new-qualification.json').read_text())
fm={}
for row in fresh['rows']:
 k=row['x'],row['y'],row['SIO'];assert k not in fm;fm[k]=row
assert len(fm)==10254
original=json.loads((SQ/'original153.json').read_text())['rows'];opairs={(r['x'],r['y'])for r in original}
keys=set();pairs=Counter();deltas=Counter();cmp=Counter();losses=[set(),set()];orig={};jobs={};coverage={};boundary_modes=Counter()
states=variants=wrong=overlap=entries=changed=0;extremes={};freshloss=[set(),set()]
def add(row,why):
 p=row['x'],row['y'];jobs.setdefault(p,dict(x=p[0],y=p[1],group=why))
with gzip.open(SQ/'union-records.jsonl.gz','rt')as parent,gzip.open(W/'qualification-records.jsonl.gz','rt')as current:
 for a,b in itertools.zip_longest(parent,current):
  assert a is not None and b is not None
  p,r=json.loads(a),json.loads(b);k=r['x'],r['y'],r['SIO'];assert k not in keys;keys.add(k);pairs[k[:2]]+=1
  assert all(r[n]==v for n,v in p.items()if n not in ['candidate_instructions','square_calls'])
  assert r['parent_boundary_instructions']==p['candidate_instructions']
  assert r['candidate']==p['candidate']and equal(r['candidate'],r['expected'])
  c,pc=r['candidate_instructions'],r['parent_boundary_instructions'];delta=c-pc;assert delta<=0;deltas[delta]+=1
  if r['boundary_calls']:
   changed+=1;assert delta<0
   assert len(r['boundary_calls'])==len(r['midpoint_operands'])==1
  else:assert delta==0 and r['midpoint_operands']==[]
  for call,oper in zip(r['boundary_calls'],r['midpoint_operands']):
   entries+=1;assert len(bytes.fromhex(call['power']))==24 and len(call['cell'])==16
   d,inv=call['denominator'],call['inverse'];assert d in [1<<i for i in range(8)]and inv in [0,1]
   assert len(bytes.fromhex(oper['a']))==len(bytes.fromhex(oper['b']))==24
   assert oper['kind']==('multiply'if inv else'compare')
   assert oper['b'if inv else'a']==call['power']
   boundary_modes[str((d,inv))]+=1
   if (d,inv)not in coverage:
    coverage[d,inv]=True;add(r,'each_actual_boundary_denominator_inverse_mode')
  if delta<0:
   ext=extremes.get('min')
   if ext is None or delta<ext['delta']:extremes['min']=dict(delta=delta,row=r)
   ext=extremes.get('max')
   if ext is None or delta>ext['delta']:extremes['max']=dict(delta=delta,row=r)
  for name,v in r['references'].items():
   variants+=1;good=equal(v['output'],r['expected']);assert v['correct_Qfplib']==good
   if not good:wrong+=1;continue
   rc=v['instructions'];cmp['faster'if c<rc else'equal'if c==rc else'slower']+=1
   if pc>rc:losses[0].add(k[:2])
   if c>rc:losses[1].add(k[:2])
  if k in fm:
   overlap+=1;f=fm[k]
   assert f['expected']==r['expected']and f['outputs']['candidate']==r['candidate']
   assert f['outputs']['candidate']==f['outputs']['parent']==f['outputs']['control']
   assert f['instructions']['candidate']==c and f['instructions']['parent']==f['instructions']['control']==pc
   assert f['boundary_calls']==r['boundary_calls']and f['midpoint_operands']==r['midpoint_operands']
   assert all(equal(f['outputs'][n],f['expected'])for n in ['parent','control','candidate'])
   for name in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']:
    v=r['references'][name]
    assert [v['output'],v['instructions'],v['correct_Qfplib']]==[f['outputs'][name],f['instructions'][name],f['correct'][name]]
   for i,n in enumerate(['parent','candidate']):
    if any(f['correct'][v]and f['instructions'][n]>f['instructions'][v]for v in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']):freshloss[i].add(k[:2])
  if k[:2]in opairs:orig[k]=r
  states+=1
assert states==241960 and len(pairs)==120980 and all(v==2 for v in pairs.values())
assert variants==279522 and wrong==77106 and changed==entries==454 and overlap==10254
assert losses[0]==losses[1]and len(losses[0])==11434
assert freshloss[0]==freshloss[1]and len(freshloss[0])==632
assert dict(cmp)==dict(slower=21167,faster=178544,equal=2705)
assert dict(deltas)=={int(k):v for k,v in q['parent_cost_delta_histogram'].items()}
original_counts={n:Counter()for n in ['parent','candidate']}
for index,row in enumerate(original):
 rr=[orig[row['x'],row['y'],s]for s in ['READY','DIRTY']]
 for n,key in [('parent','parent_boundary_instructions'),('candidate','candidate_instructions')]:
  refs=[v['references'][row['reference']]for v in rr];assert all(v['correct_Qfplib']for v in refs)
  direction='slower'if any(v[key]>r['instructions']for v,r in zip(rr,refs))else'equal'if any(v[key]==r['instructions']for v,r in zip(rr,refs))else'strict'
  original_counts[n][direction]+=1
 if index<6:add(rr[0],'original153_bounded_control')
assert original_counts['parent']==original_counts['candidate']==dict(slower=34,strict=119)
for row in extremes.values():add(row['row'],'full_corpus_reduction_endpoint')
corr=json.loads((R/'.build/m0-pow-boundary128-report-corrigendum-20261025.json').read_text())
assert corr['FROZEN_sha256']==ref(W/'FROZEN.json')['sha256']and corr['result_sha256']==ref(W/'result.json')['sha256']
assert corr['qualification_sha256']==ref(W/'qualification.json')['sha256']and corr['records_sha256']==ref(W/'qualification-records.jsonl.gz')['sha256']
assert [min(deltas),max(v for v in deltas if v<0)]==[-180,-4]and deltas[-180]==2
witnesses=[]
with gzip.open(W/'qualification-records.jsonl.gz','rt')as f:
 for ln in f:
  r=json.loads(ln)
  if r['candidate_instructions']-r['parent_boundary_instructions']==-180:
   witnesses.append({k:r[k]for k in ['x','y','SIO','parent_boundary_instructions','candidate_instructions']})
assert witnesses==corr['witnesses']
reject=json.loads((R/'.build/m0-pow-bound80-20261025/REJECTED.json').read_text())
assert ref(R/'.build/m0-pow-bound80-20261025/REJECTED.json')['sha256']=='3fd5422793687964e73f43b1cd0fc63b8312766cc587a3055ab7bc5c69311e07'
unit=json.loads((W/'unit-proof.json').read_text())
assert q['total_fresh_public_ARM_calls']==241960+454
assert fresh['fresh_ARM_calls']==61524 and unit['actual_ARM_calls']==6000
assert sum([q['total_fresh_public_ARM_calls'],fresh['fresh_ARM_calls'],unit['actual_ARM_calls']])==309938
save('selected-public-jobs.json',dict(status='BOUNDED_SELECTION_FROM_SAVED_ACTUAL_RAW_NOT_NEW_CAMPAIGN',jobs=list(jobs.values()),mode_coverage=sorted(coverage)))
out=dict(status='PASS_INDEPENDENT_SAME_CORPUS_RAW_LINEAGE_AND_REPORT_CORRECTION',
 zero_new_ARM_calls=True,zero_new_MPFR_inputs=True,parent_raw=ref(SQ/'union-records.jsonl.gz'),current_raw=ref(W/'qualification-records.jsonl.gz'),
 every_parent_row_same_output_expected_references_and_correct_current_parent_cost=True,
 parent_instructions_field_is_inherited_preSquare_history_not_current_comparator=True,current_comparator='parent_boundary_instructions',
 unique_pairs=120980,states=241960,reference_variants=279522,wrong_Qfplib_variants_retained=77106,
 strict_quietNaN_flags_independently_recounted=True,no_nominal_filter=True,
 loss_pairs_parent_candidate=[11434,11434],new_raw_loss_pairs=0,candidate_wrong=0,
 all10254_fresh_control_rows_overlap_exact=True,all_three_real_Qfplib_reference_outputs_and_costs_bound=True,
 fresh_control_loss_pairs=[632,632],original153={n:dict(v)for n,v in original_counts.items()},
 cost_comparisons=dict(cmp),cost_delta_histogram=dict(sorted(deltas.items())),accelerated_public_states=454,
 corrected_public_instruction_reduction_range=[4,180],corrigendum=ref(R/'.build/m0-pow-boundary128-report-corrigendum-20261025.json'),witnesses=witnesses,
 original169_upper_bound_only_historical_pilot=True,no_frozen_source_or_raw_rewritten=True,
 actual_boundary_mode_counts=dict(boundary_modes),midpoint_and_input_operand_byte_shapes_checked=True,
 author_qualified_fresh_ARM=309938,author_counts_partition=[241960,454,61524,6000],author_MPFR5051_plus76sNaN=True,
 rejected_bound80=reject,rejected_bound80_not_candidate_or_in_qualified_counts=True,
 author_pilot1836_syntax_preflight0_and_rejected_bare19221_excluded=True,
 stack_limits=dict(author_bare=[212,156],same_complete_corpus=[2284,2284],parent_changed716_subset_not_comparator=True,fresh_control2148_all3=True),
 no_fresh_qualifications_for_inherited_MPFR_and_Qfplib=True,reviewed507_stays422=True,device_IO=0)
print(json.dumps(save('accounting.json',out)),flush=True)
