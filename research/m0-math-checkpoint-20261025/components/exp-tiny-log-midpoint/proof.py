"""All odd midpoint classes: exact log-threshold floor certificates."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,random,struct
W=Path(__file__).resolve().parent;sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
limit=F(1,1<<32);guard=1<<20
assert F(guard)/(1-limit)<guard+1
certificates=[];corrected_cells=[]
for neg,cap in ((0,1<<21),(1,1<<22)):
 denominator=3*(1<<(52+neg));best=None;count=0
 for odd in range(1,cap,2):
  cubic,rem=divmod(odd**3,denominator)
  assert rem
  if neg:
   left=((denominator-rem)<<(55+neg))*((1<<(53+neg))-odd)
   right=3*odd**4*(1<<(53+neg))
  else:
   left=rem<<(55+neg);right=3*odd**4
  assert left>right,(neg,odd)
  e=odd.bit_length()-54-neg;q=e+55+2*neg
  sq=odd*odd;integer=sq>>q;tail=sq&((1<<q)-1)
  correction=int(tail+cubic>=1<<q) if neg else -int(tail<=cubic)
  if correction:corrected_cells.append((e,neg,odd,integer+correction))
  if best is None or left*best[1]<best[0]*right:best=(left,right,odd)
  count+=1
 certificates.append(dict(negative=bool(neg),odd_cap_exclusive=cap,classes=count,
                          strict_log_tail_separation_every_class=True,
                          worst_ratio=str(F(best[0],best[1])),worst_ratio_float=best[0]/best[1],worst_odd=best[2]))
for x in range(65536):assert (x*43691)>>17==x//3

def threshold(odd,e,neg):
 square=odd*odd;q=e+55+2*neg
 integer=square>>q;tail=square&((1<<q)-1)
 cubic=((odd**3)>>(52+neg))//3
 out=integer+int(tail+cubic>=1<<q) if neg else integer-int(tail<=cubic)
 if odd<65536:
  assert cubic==0 and out==square>>q
 # Exact source-bound uint32/uint64 split arithmetic, including all
 # intermediate widths and the reciprocal /3 multiply.
 low=square&0xffffffff;high=square>>32
 q0=(low>>q)|(high<<(32-q))
 cube_low=low*odd;cube_high=high*odd+(cube_low>>32)
 assert cube_high<1<<64 and cube_high>>20<1<<32
 scaled=(cube_high>>20)>>neg
 assert scaled<65536
 b=(scaled*43691)>>17;assert b==cubic
 result=q0+int(tail+b>=1<<q) if neg else q0-int(tail<=b)
 assert result==out and 0<=result<=guard
 return out

jobs={};checks=0;classes=[];rng=random.Random(0xE10C32)
def add(raw,group):jobs.setdefault(raw,group)
for e in range(-54,-32):
 for neg in (0,1):
  s=-e-neg;q=e+55+2*neg
  assert 32<=s<=54 and 1<=q<=24
  first=max(0,((1<<52)>>s)-1);last=((1<<53)-1)>>s
  values={first,first+1,first+2,last,last-1,last-2}
  values.add((certificates[neg]['worst_odd']-1)//2)
  for bit in range(23):
   for d in (-2,-1,0,1,2):values.add((1<<bit)+d)
  samples=2048 if e>=-38 else 32
  for _ in range(samples):values.add(rng.randrange(first,last+1))
  count=0
  for ce,cn,co,ct in corrected_cells:
   if ce==e and cn==neg:values.add((co-1)//2)
  for retained in sorted(values):
   if not first<=retained<=last:continue
   odd=2*retained+1;M0=odd<<(s-1)
   if M0<(1<<52)-guard or M0>(1<<53):continue
   t=threshold(odd,e,neg);count+=1
   for d in sorted({0,1,max(0,t-1),t,t+1,t+2,16384,16385,guard,guard+1}):
    M=M0+d if neg else M0-d
    if not 1<<52<=M<1<<53:continue
    raw=(neg<<63)|((e+1023)<<52)|(M-(1<<52))
    if (raw&((1<<63)-1))<=0x3c90000000000000:continue
    add(raw,'log_midpoint_actual_transition_neighbors_and_guard_edges');checks+=1
  classes.append(dict(e=e,negative=bool(neg),sampled_midpoints=count))
for exponent in (-54,-53,-40,-39,-38,-37,-36,-35,-34,-33,-32):
 center=(exponent+1023)<<52
 for d in range(-256,257):
  for sign in (0,1<<63):add(sign|(center+d),'dense_extended_domain_edges')
for _ in range(8192):add((rng.getrandbits(1)<<63)|rng.randrange(0x3c90000000000001,0x3df0000000000000),'new_uniform_tiny_raw')
data=b''.join(struct.pack('<Q',x) for x in jobs)
(W/'tiny-inputs.bin').write_bytes(data)
(W/'tiny-input-groups.json').write_text(json.dumps(list(jobs.values()))+'\n')
out=dict(status='AUTHOR_EXACT_LOG_MIDPOINT_ALL_BINARY64_INPUTS_IN_TINY_DOMAIN',source_sha256=sha(W/'candidate/native_eabi_m0.cpp'),
 domain='2^-54 < abs(x) < 2^-32',input_exponents=[-54,-33],sign_classes=certificates,
 exhaustive_odd_class_certificates=sum(c['classes'] for c in certificates),
 integer_reciprocal_divide3_certificates=65536,
 strict_log_correction_input_ulp_upper_bound=str(F(guard)/(1-limit)),guarded_input_displacement=guard,
 square_max_bits=44,cube_max_bits=66,source_square_cube_split_exact=True,
 quadratic_shift_range=[1,24],linear_fraction_shift_range=[32,54],
 sampled_cell_source_arithmetic_controls=checks,actual_midpoint_samples=classes,
 every_odd_class_mathematically_certified_but_not_every_class_rerun_in_ARM=True,
 prepared_new_inputs=len(jobs),tiny_inputs_sha256=sha(W/'tiny-inputs.bin'),
 source_proof_pending_independent_review=True,all_cubic_threshold_correction_cells=len(corrected_cells),
 every_cubic_threshold_correction_cell_in_actual_ARM_corpus=True,hardware_accessed=False)
(W/'corrected-midpoint-cells.json').write_text(json.dumps(corrected_cells)+'\n')
(W/'proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='actual_midpoint_samples'},indent=2))
