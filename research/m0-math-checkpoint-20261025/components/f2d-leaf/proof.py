from pathlib import Path
from collections import Counter
import hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
q=json.loads((W/'qualification.json').read_text());assert q['candidate_ELF_sha256']==sha(W/'candidate.elf')
mask=(1<<32)-1;packing_checks=0
for sign in (0,1):
 for e in range(1,255):
  for high in (0,1,0x3ffff,0x40000,0x7ffff,0x80000,0xffffe,0xfffff):
   for low in range(8):
    x=(sign<<31)|(e<<23)|(high<<3)|low
    field=(x>>23)-1 if not sign else ((x-(1<<32))>>23)+255
    assert field==e-1
    upper=((x>>3)+0x38000000)&mask if not sign else (((x-(1<<32))>>3)+0xc8000000)&mask
    lower=(x<<29)&mask
    expected=(sign<<63)|((e+896)<<52)|(((high<<3)|low)<<29)
    assert lower|(upper<<32)==expected
    packing_checks+=1
subnormal_checks=0;shift_rows=[]
for width in range(1,24):
 first=1<<(width-1);last=(1<<width)-1;seen=set()
 values={first,last,(first+last)//2,*range(first,min(first+32,last+1)),*range(max(first,last-31),last+1)}
 for f in values:
  v=f<<9;s=0
  for boundary,shift in ((16,16),(24,8),(28,4),(30,2)):
   if not(v>>boundary):v<<=shift;s+=shift
  if not(v&(1<<31)):v<<=1;s+=1
  assert s==23-width and v.bit_length()==32 and v==f<<(32-width)
  assert 895-s==width+872
  for sign in (0,1):
   hi=(sign<<31)+(895-s)*(1<<20)+(v>>11);lo=(v<<21)&mask
   expected=(sign<<63)|((width+873)<<52)|((f-(1<<(width-1)))<<(53-width))
   assert lo|(hi<<32)==expected
   subnormal_checks+=1
  seen.add(s)
 assert seen=={23-width}
 shift_rows.append({'fraction_width':width,'normalizing_shift':23-width,'double_exponent':width+873})
nan_checks=0
for bit in range(23):
 for f in (1<<bit,((1<<23)-1)^(1<<bit),(1<<bit)|1):
  if not f:continue
  for sign in (0,1):
   x=(sign<<31)|0x7f800000|f;r2=(x<<9)&mask
   hi=(sign<<31)|(r2>>12)|0x7ff80000;lo=(x<<29)&mask
   assert lo|(hi<<32)==(sign<<63)|0x7ff0000000000000|(f<<29)|(1<<51)
   nan_checks+=1
costs={'zero':(5,8),'normal':(12,13),'infinity':(12,12)}
counts=Counter();observed={};parent_deltas=Counter();widths=set();wrong=[]
for row in q['rows']:
 x=int(row['x'],16);e=(x>>23)&255;f=x&0x7fffff
 kind='normal' if 0<e<255 else 'zero' if not(e or f) else 'infinity' if e==255 and not f else 'NaN' if e==255 else 'subnormal'
 counts[kind]+=1;pair=(row['instructions']['candidate'],row['instructions']['Qfplib']);observed.setdefault(kind,set()).add(pair)
 assert row['correct']['Qfplib']==(kind in costs)
 if kind in costs:assert pair==costs[kind] and pair[0]<=pair[1]
 else:wrong.append(row)
 if kind=='subnormal':widths.add(f.bit_length())
 parent_deltas[row['instructions']['candidate']-row['instructions']['parent']]+=1
assert widths==set(range(1,24)) and max(parent_deltas)<0
Q=ROOT/'.build/m0-float-fma-qualification-20261023';old=json.loads((Q/'float.json').read_text())['operations']['f2d']['instruction_sample'];by_x={r['x']:r for r in q['rows'] if r['SIO']=='READY'};samples=[]
for old_row in old:
 x=f"{int(old_row['arguments'][0],16):08X}";r=by_x[x]
 assert r['instructions']['parent']==old_row['own_instructions'] and r['instructions']['Qfplib']==old_row['reference_instructions']
 assert r['outputs']['parent']==old_row['own_result'] and r['outputs']['Qfplib']==old_row['reference_result']
 samples.append({'old_index':old_row['index'],'x':x,'correct_Qfplib':r['correct']['Qfplib'],'before':r['instructions']['parent'],'after':r['instructions']['candidate'],'Qfplib':r['instructions']['Qfplib']})
both=[r for r in samples if r['correct_Qfplib']]
assert len(samples)==256 and len(both)==249 and sum(r['before']>r['Qfplib'] for r in both)==1 and all(r['after']<=r['Qfplib'] for r in both)
(W/'old256-sample-reconciliation.json').write_text(json.dumps({'status':'PASS_OLD256_SAMPLE_COUNTS_RESULTS_AND_ONE_DEFICIT_FIXED','both_correct':249,'old_deficits':[1,0],'inherited_calls_not_added':True,'rows':samples},indent=2)+'\n')
out={'status':'AUTHOR_ALL_DOMAIN_EXACT_WIDENING_AND_CORRECT_REFERENCE_PATH_AUDIT','normal_packing_checks':packing_checks,'subnormal_normalization_packing_checks':subnormal_checks,'NaN_payload_bit_checks':nan_checks,'subnormal_widths':shift_rows,'reference_correct_classes':{k:{'candidate':v[0],'Qfplib':v[1],'state_rows':counts[k]} for k,v in costs.items()},'all_fresh_reference_correctness_flags_match_source_partition':True,'all_fresh_correct_reference_costs_match_complete_source_path_counts':True,'wrong_reference_state_rows_retained':len(wrong),'wrong_reference_observed_costs':{k:[list(x) for x in sorted(v)] for k,v in observed.items() if k not in costs},'observed_parent_cost_increase_rows':0,'all_candidate_state_rows_strictly_faster_parent':True,'parent_delta_counts':dict(sorted(parent_deltas.items())),'old_sample_comparable':249,'old_sample_deficits':[1,0],'candidate_ELF_sha256':sha(W/'candidate.elf'),'source_proof':'NUMERIC-PROOF.md','independent_review_pending':True,'whole_goal_or_physical_cycle_GO':False}
(W/'proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('subnormal_widths','parent_delta_counts')},indent=2))
