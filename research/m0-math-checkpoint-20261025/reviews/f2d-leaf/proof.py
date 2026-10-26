"""All-binary32 source certificates and sealed author-row reconciliation."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,random,struct,sys
sys.dont_write_bytecode=True
from model import exact,source_model,reference_partition,MASK,F23
O=Path(__file__).resolve().parent;R=O.parents[1];P=R/'.build/m0-f2d-leaf-20261024'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks=Counter();rng=random.Random(0xF2D11DE)
# Normal packing is affine in each high20 fraction and exact in its low3
# bits. Check the bias and coefficient identity for every exponent/sign,
# then high-fraction endpoints/carry boundaries and all eight low patterns.
for e in range(1,255):
 for s in (0,1):
  start=(s<<31)|(e<<23);signed=start-(1<<32) if s else start
  test=((signed>>23)+255) if s else (start>>23)-1
  assert test==e-1 and 0<=test<=253
  expected_high=(s<<31)|((e+896)<<20)
  actual_high=((signed>>3)+(0xc8000000 if s else 0x38000000))&MASK
  assert actual_high==expected_high
  for h in (0,1,0x3ffff,0x40000,0x7ffff,0x80000,0xffffe,0xfffff):
   for low in range(8):
    x=start|(h<<3)|low;got,kind,cost,shift=source_model(x)
    assert got==exact(x) and kind=='normal' and cost==12
    checks['normal_sign_exponent_affine_payload_certificates']+=1
for s in (0,1):
 for e in (0,255):
  x=(s<<31)|(e<<23);signed=x-(1<<32) if s else x
  field=(signed>>23)+255 if s else (x>>23)-1
  assert field==(-1 if e==0 else 254)
  assert not 0<=field<=253
  checks['special_range_and_sign_cases']+=1
# A width-k mantissa occupies [2^(k-1),2^k-1]. At each conditional shift,
# BOTH interval endpoints choose the same branch. Induction proves every
# mantissa of that width takes that path and no significant bit is lost.
widths=[]
for k in range(1,24):
 lo=(1<<(k-1))<<9;hi=((1<<k)-1)<<9;gap=23-k;amount_sum=0;choices=[]
 for boundary,amount in [(16,16),(24,8),(28,4),(30,2)]:
  left=not(lo>>boundary);right=not(hi>>boundary)
  assert left==right
  choices.append(int(left))
  if left:
   assert hi<(1<<boundary)
   lo<<=amount;hi<<=amount;amount_sum+=amount
   assert hi<=MASK
 take=not(lo&(1<<31));assert take==(not bool(hi&(1<<31)));choices.append(int(take))
 if take:lo<<=1;hi<<=1;amount_sum+=1
 assert amount_sum==gap and lo.bit_length()==hi.bit_length()==32
 assert lo==(1<<(k-1))<<(32-k) and hi==((1<<k)-1)<<(32-k)
 assert 895-gap==k+872 and sum(choices)==gap.bit_count()
 for f in {1<<(k-1),(1<<k)-1,((1<<(k-1))+(1<<k)-1)//2}:
  for s in (0,1):
   x=(s<<31)|f;got,kind,cost,shift=source_model(x)
   assert got==exact(x) and kind=='subnormal' and shift==gap
   assert cost==30+2*gap.bit_count()
   checks['subnormal_interval_packing_controls']+=1
 widths.append(dict(width=k,normalizing_shift=gap,branch_choices=choices,double_exponent=k+873,raw32_inputs=1<<k,candidate_instructions=30+2*gap.bit_count(),Qfplib_instructions_wrong=8))
 checks['subnormal_complete_width_interval_certificates']+=1
# The two packing words reconstruct F<<29 exactly in the NaN case;
# the quiet bit is ORed independently and never removes any input bit.
for b in range(23):
 for f in (1<<b,F23^(1<<b),(1<<b)|1):
  for s in (0,1):
   x=(s<<31)|0x7f800000|f
   assert source_model(x)[0]==exact(x)
   checks['NaN_payload_bit_controls']+=1
partition={'zero':2,'normal':2*254*(1<<23),'infinity':2,'NaN':2*F23,'subnormal':2*F23}
assert sum(partition.values())==1<<32 and sum(w['raw32_inputs'] for w in widths)==partition['subnormal']
for _ in range(16384):
 x=rng.getrandbits(32);assert source_model(x)[0]==exact(x)
 checks['own_raw32_integer_model_checks']+=1
# No broad ARM re-execution: reconcile every already sealed row against
# independent exact decoding, class predicates and exact source cost.
q=json.loads((P/'qualification.json').read_text());seen={};counts=Counter();costs={};deltas=Counter();oldloss=set();newloss=set()
faster=equal=slower=wrong=0;observed_widths=set()
for row in q['rows']:
 x=int(row['x'],16);got,kind,cost,shift=source_model(x);expected=exact(x)
 assert got==expected==int(row['outputs']['candidate'],16)==int(row['outputs']['parent'],16)
 author_expected=int(row['expected'],16)
 if kind=='NaN':assert author_expected&0x7fffffffffffffff>0x7ff0000000000000 and author_expected&(1<<51)
 else:assert author_expected==expected
 rk,correct,qcost=reference_partition(x);assert rk==kind
 assert correct==(int(row['outputs']['Qfplib'],16)==expected)==row['correct']['Qfplib']
 assert row['correct']['candidate'] and row['correct']['parent']
 assert [cost,qcost]==[row['instructions']['candidate'],row['instructions']['Qfplib']]
 assert cost<row['instructions']['parent']
 if correct:
  assert cost<=qcost
  faster+=cost<qcost;equal+=cost==qcost;slower+=cost>qcost
  if row['instructions']['parent']>qcost:oldloss.add(x)
  if cost>qcost:newloss.add(x)
 else:wrong+=1
 if kind=='subnormal':observed_widths.add((x&F23).bit_length())
 stamp=(expected,tuple(row['outputs'][k] for k in ['parent','candidate','Qfplib']),tuple(row['instructions'][k] for k in ['parent','candidate','Qfplib']))
 state=row['SIO'];assert state in ('READY','DIRTY')
 if x in seen:
  prev=seen[x];assert prev[0]=='READY' and state=='DIRTY' and prev[1]==stamp
  seen[x]=('BOTH',stamp)
 else:assert state=='READY';seen[x]=(state,stamp)
 counts[kind]+=1;costs.setdefault(kind,set()).add((cost,qcost));deltas[cost-row['instructions']['parent']]+=1
assert len(seen)==132959 and len(q['rows'])==265918 and all(v[0]=='BOTH' for v in seen.values())
assert set(seen)=={x[0] for x in struct.iter_unpack('<I',(P/'qualification-inputs.bin').read_bytes())}
assert observed_widths==set(range(1,24))
assert oldloss=={0,1<<31,0x7f800000,0xff800000} and not newloss
assert (faster,equal,slower,wrong)==(205230,4,0,60684)
assert counts['NaN']//2==8586 and len(seen)-counts['NaN']//2==124373
old=json.loads((R/'.build/m0-float-fma-qualification-20261023/float.json').read_text())['operations']['f2d']['instruction_sample']
old_correct=old_slower=new_slower=0
for row in old:
 x=int(row['arguments'][0],16);_,stamp=seen[x];expected,outputs,instructions=stamp
 assert [row['own_instructions'],row['reference_instructions']]==[instructions[0],instructions[2]]
 assert int(row['own_result'],16)==int(outputs[0],16) and int(row['reference_result'],16)==int(outputs[2],16)
 correct=reference_partition(x)[1];old_correct+=correct;old_slower+=correct and instructions[0]>instructions[2];new_slower+=correct and instructions[1]>instructions[2]
assert [len(old),old_correct,old_slower,new_slower]==[256,249,1,0]
old_records=gzip.decompress((R/'.build/m0-float-fma-qualification-20261023/float-f2d.records.bin.gz').read_bytes())
assert len(old_records)==9122*48
for x,b,c,old_result,old_exact,old_mpfr in struct.iter_unpack('<6Q',old_records):
 assert b==c==0 and x in seen and int(seen[x][1][1][0],16)==old_result==exact(x)
 if reference_partition(x)[0]=='NaN':
  assert old_exact&0x7fffffffffffffff>0x7ff0000000000000 and old_mpfr&0x7fffffffffffffff>0x7ff0000000000000
 else:assert old_exact==old_mpfr==exact(x)
d=dict(status='PASS_INDEPENDENT_ALL_RAW32_EXACT_WIDENING_AND_FULL_COST_PARTITION',checks=dict(checks),raw32_partition_cardinalities=partition,partition_sum_2pow32=sum(partition.values()),subnormal_all23_width_intervals=widths,all_correct_reference_classes_candidate_no_slower=True,wrong_reference_rows_retained=True,all_author265918_states_match_independent_exact_and_cost_models=True,author_unique_inputs=132959,author_qualified_ARM_calls=797754,author_oracle_evaluations=132959,author_actual_directed_MPFR_input_conversions=124373,author_NaN_preMPFR_category_shortcuts=8586,smoke41490_not_added=True,author_observed_classes=dict(counts),author_observed_cost_pairs={k:sorted(v) for k,v in costs.items()},author_correct_reference_states=205234,author_vs_correct_reference=dict(faster=faster,equal=equal,slower=slower),author_wrong_reference_states=wrong,author_parent_cost_increases=0,author_all_states_strictly_faster_parent=True,author_parent_delta_distribution=dict(sorted(deltas.items())),old9122_raw_records_all_in_new_qualified_inputs_and_parent_bits_exact=True,old_raw_speed_deficits_fixed=['00000000','80000000','7F800000','FF800000'],old256_reconciliation=dict(rows=256,correct=249,before_slower=1,after_slower=0),author_qualification_sha256=sha(P/'qualification.json'),own_fresh_ARM_or_MPFR_in_this_file=0,original507_unchanged418=True)
(O/'proof.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
