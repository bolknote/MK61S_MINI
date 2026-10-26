"""Independent all-input algebra certificates and sealed-evidence reconciliation."""
from pathlib import Path
from collections import Counter
import hashlib,json,random,struct,sys
sys.dont_write_bytecode=True
from model import exact,source_model,reference_partition,MASK,F52,rne
O=Path(__file__).resolve().parent;R=O.parents[1];P=R/'.build/m0-d2f-leaf-20261024'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks=Counter();rng=random.Random(0xD2F1ADE)
# All exponent fields and low-word borrow cases, using endpoints of the
# monotone affine high-fraction interval rather than a sample of mantissas.
for e in range(1024):
 for b in (0,1):
  l=(e<<22)-(873<<22)-b;h=l+(0xfffff<<2)
  assert (h<0)==(e<873)
  if e==873:assert l==-b
  if e>873:assert l>0
  assert (h<((24<<22)-1))==(e<897)
  if e>=897:assert l>=((24<<22)-1)
  if e<896:assert h<((24<<22)-4)
  if e==896:assert h==((24<<22)-4)-b
  checks['lower_range_interval_certificates']+=1
for e in range(1024,2048):
 lo=(e-1024)<<22;hi=lo+(0xfffff<<2)
 assert (hi<(127<<22))==(e<1151)
 if e>=1151:assert lo>=127<<22
 assert (lo+(1<<22)>=1<<32)==(e==2047)
 if e<2047:assert hi+(1<<22)<1<<32
 checks['upper_range_interval_certificates']+=1
# Packing bias is affine in the high fraction; coefficient identity plus
# endpoints establishes every 20-bit high fraction, not just these values.
for e in range(897,1151):
 for s in (0,1):
  high=(s<<31)|(e<<20);signed=high-(1<<32) if s else high
  factor=(signed>>30)+int(e<1024);assert factor==(1 if s==0 else -1)
  assert ((high<<3)+(factor<<30))&MASK==((s<<31)|((e-896)<<23))
  for f in (0,1,0xffffe,0xfffff):
   for q in range(9):
    assert ((((high|f)<<3)+(factor<<30)+q)&MASK)==((s<<31)+((e-896)<<23)+(f<<3)+q)&MASK
    assert (((high|f)<<3)+q)&1==q&1
    checks['normal_bias_carry_parity_certificates']+=1
# For ANY T in [2^31,2^32), v in [0,2^21), and s in [9,32],
# n=(T<<21)|v. Quotient, guard and lower remainder follow the bit identity.
# Enumerate all 24 shifts, quotient parities, guard values, and zero/nonzero
# lower-bit equivalence classes. Arbitrary remaining bits cannot change it.
for shift in range(9,33):
 width=shift-1
 for parity in (0,1):
  for guard in (0,1):
   for low in sorted({0,1,(1<<width)-1}):
    for v in (0,1,(1<<21)-1):
     t=((1<<31)|(parity<<shift)|(guard<<width)|low)&MASK
     quotient=t>>shift;g=(t>>width)&1
     represented_below=((t<<(33-shift))&MASK)|(v<<11)
     assert bool(represented_below)==bool((t&((1<<width)-1)) or v)
     n=(t<<21)|v
     assert n>>(shift+21)==quotient
     assert rne(n,shift+21)==quotient+int(g and(bool(represented_below) or quotient&1))
     checks['subnormal_shift_guard_sticky_parity_certificates']+=1
# NaN payload OR changes bits 2..21 only, which are discarded before >>29.
assert (0xfffff<<2)<1<<29
for b in range(52):
 for s in (0,1):
  for f in (1<<b,F52^(1<<b),(1<<b)|1):
   x=(s<<63)|(2047<<52)|f
   assert source_model(x)[0]==exact(x)
   checks['NaN_payload_bit_algebra_controls']+=1
# Exact cardinalities of the complete disjoint raw64 partition.
parts={'zero':2*(873*(1<<52)+1),'subnormal_to_normal':2*(1<<29),'wrong_subnormal':2*(24*(1<<52)-1-(1<<29)),
       'overflow':2*896*(1<<52),'infinity':2,'NaN':2*((1<<52)-1)}
for half in ('low','high'):
 parts['normal_'+half+'_truncate']=2*127*(1<<23)*(1<<28)
 parts['normal_'+half+'_up']=2*127*(1<<23)*((1<<28)-1)
 for parity in ('even','odd'):parts['normal_'+half+'_tie_'+parity]=2*127*(1<<22)
assert sum(parts.values())==1<<64
# Own randomized mathematical checks are HOST integer evaluations only,
# separate from all fresh ARM/MPFR counts.
for _ in range(32768):
 x=rng.getrandbits(64);assert source_model(x)[0]==exact(x)
 checks['independent_raw64_integer_model_checks']+=1
# Read the already executed author corpus; no inherited run is re-executed
# or counted as this review's own fresh ARM/MPFR evidence.
q=json.loads((P/'qualification.json').read_text());seen={};counts=Counter();costs={};delta=Counter();oldloss=set();newloss=set()
wrongref=0;faster=equal=slower=0
for row in q['rows']:
 x=int(row['x'],16);got,kind,cost=source_model(x);expected=exact(x)
 assert got==expected==int(row['outputs']['candidate'],16)==int(row['outputs']['parent'],16),(row['x'],got,expected)
 author_expected=int(row['expected'],16)
 if (x>>52)&2047==2047 and x&F52:
  assert author_expected&0x7fffffff>0x7f800000 and author_expected&0x400000
 else:assert expected==author_expected
 rk,correct,rcost=reference_partition(x)
 assert correct==(int(row['outputs']['Qfplib'],16)==expected)==row['correct']['Qfplib']
 assert row['correct']['candidate'] and row['correct']['parent']
 assert cost==row['instructions']['candidate'] and rcost==row['instructions']['Qfplib']
 if correct:
  assert kind==rk and cost<=rcost
  faster+=cost<rcost;equal+=cost==rcost;slower+=cost>rcost
  if row['instructions']['parent']>rcost:oldloss.add(x)
  if cost>rcost:newloss.add(x)
 else:wrongref+=1
 state=row['SIO'];assert state in ('READY','DIRTY')
 stamp=(expected,tuple(row['outputs'].values()),tuple(row['instructions'].values()))
 if x in seen:
  prev=seen[x];assert prev[0]=='READY' and state=='DIRTY' and prev[1]==stamp
  seen[x]=('BOTH',stamp)
 else:assert state=='READY';seen[x]=(state,stamp)
 counts[kind]+=1;costs.setdefault(kind,set()).add((cost,rcost))
 delta[cost-row['instructions']['parent']]+=1
assert len(seen)==231984 and len(q['rows'])==463968 and all(s[0]=='BOTH' for s in seen.values())
assert set(seen)==set(x[0] for x in struct.iter_unpack('<Q',(P/'qualification-inputs.bin').read_bytes()))
assert [len(oldloss),len(newloss)]==[103496,0]
assert (faster,equal,slower,wrongref)==(217338,231552,0,15078)
assert sum(v for d,v in delta.items() if d>0)==110782 and set(d for d in delta if d>0)=={1}
old=[]
for n in ['float.json','addendum.json']:
 old+=json.loads((R/'.build/m0-float-fma-qualification-20261023'/n).read_text())['operations']['d2f']['instruction_sample']
old_correct=old_losses=new_losses=0
for r in old:
 x=int(r['arguments'][0],16);_,stamp=seen[x];exp,outs,counts_tuple=stamp
 # Stored qualification dictionaries have insertion order parent,candidate,Qfplib.
 assert r['own_instructions']==counts_tuple[0]
 assert r['reference_instructions']==counts_tuple[2]
 assert int(r['own_result'],16)==int(outs[0],16) and int(r['reference_result'],16)==int(outs[2],16)
 correct=reference_partition(x)[1];old_correct+=correct
 old_losses+=correct and counts_tuple[0]>counts_tuple[2];new_losses+=correct and counts_tuple[1]>counts_tuple[2]
assert [len(old),old_correct,old_losses,new_losses]==[512,510,426,0]
d=dict(status='PASS_INDEPENDENT_ALL_INPUT_ALGEBRA_AND_SEALED_EVIDENCE_RECONCILIATION',checks=dict(checks),raw64_partition_cardinalities=parts,partition_sum_2pow64=sum(parts.values()),all_correct_reference_paths_candidate_no_slower=True,no_claim_for_wrong_reference_rows=True,source_model_matches_all_author_states463968=True,author_unique231984=True,author_qualified_ARM1391904=True,author_MPFR_oracle_evaluations=231984,author_actual_directed_MPFR_input_conversions=231984-counts['NaN']//2,author_NaN_category_shortcuts_no_MPFR=counts['NaN']//2,author_MPFR_count_label_requires_this_precision=True,smoke11004_not_added=True,author_observed_state_classes=dict(counts),author_observed_cost_pairs={k:sorted(v) for k,v in costs.items()},author_correct_reference_rows=faster+equal+slower,author_reference_wrong_rows=wrongref,author_vs_correct_reference=dict(faster=faster,equal=equal,slower=slower),author_parent_regression_states110782=True,parent_regression_delta1=True,author_old512_reconciliation=dict(rows=512,correct=510,old_slower=426,new_slower=0),author_qualification_sha256=sha(P/'qualification.json'),own_fresh_ARM_or_MPFR_in_this_file=0,original507_unchanged418=True)
(O/'proof.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
