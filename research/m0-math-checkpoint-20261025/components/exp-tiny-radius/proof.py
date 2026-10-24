"""Exact rational cell proof and complete tiny-midpoint input preparation."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,random,struct
W=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def power(e):return F(2)**e
limit=power(-38);guard=1<<14
remainder_bound=power(14)/(1-limit)
assert remainder_bound<guard+1
square_perturbation=F(guard*((1<<54)+guard))*power(-39-53)
cubic_perturbation=power(-23)/(6*(1-limit))
total=square_perturbation+cubic_perturbation
assert total<power(-22)<power(-18)
jobs={};midpoints=0;checks=0;q_values=set();max_odd=0;per_class=[]
def add(x,group):jobs.setdefault(x,group)
def code_model(raw):
 negative=bool(raw>>63);e=((raw>>52)&2047)-1023
 shift=-e-int(negative)-32;hi=((raw>>32)&0xfffff)|0x100000;lo=raw&0xffffffff
 tail=hi&((1<<shift)-1);half=1<<(shift-1);r=hi>>shift
 if negative:
  up=tail>half or (tail==half and bool(lo))
  if tail==half and 0<lo<16385:up=lo>((2*r+1)**2>>(e+57))
  return 0x3ff0000000000000-r-int(up)
 up=tail>=half
 if tail+1==half and lo>2**32-16385:up=(2**32-lo)<=((2*r+1)**2>>(e+55))
 return 0x3ff0000000000000+r+int(up)

for e in range(-54,-38):
 for neg in (0,1):
  s=-e-neg;q=e+55+2*neg
  assert 1<=q<=18 and 6<=s-32<=22
  q_values.add(q);count=0
  for retained in range(max(0,((1<<52)>>s)-1),((1<<53)-1>>s)+2):
   odd=2*retained+1;M0=odd<<(s-1)
   if M0<(1<<52)-guard or M0>(1<<53)+guard:continue
   if M0>(1<<53):continue
   assert odd<=65535 and odd*odd<1<<32
   k=(odd*odd)>>q
   frac=F(odd*odd,1<<q)-k
   assert power(-18)<=frac<=1-power(-18)
   assert frac>total and 1-frac>total
   max_odd=max(max_odd,odd);midpoints+=1;count+=1
   # Every possible result transition within this linear midpoint cell.
   for d in sorted({0,1,k,max(0,k-1),k+1,k+2,4096,4097,guard,guard+1}):
    M=M0+d if neg else M0-d
    if not 1<<52<=M<1<<53:continue
    raw=(neg<<63)|((e+1023)<<52)|(M-(1<<52))
    if (raw&((1<<63)-1))<=0x3c90000000000000:continue
    # Quadratic correction has the certified same floor k throughout
    # every guarded displacement. Outside it, R<16385 decides safely.
    if d<=guard:
     up=(d>k) if neg else (d<=k)
     expected=0x3ff0000000000000+(-1 if neg else 1)*(retained+up)
     assert code_model(raw)==expected,(e,neg,retained,d,k)
     checks+=1
    # Both integer thresholds k and k+1 get actual ARM+MPFR execution
    # for every cell; other distances are sampled, plus dense corners.
    if d in (k,k+1) or retained%257==0 or retained in (0,1,2,3):
     add(raw,'all_linear_midpoint_cells_transition_neighbors')
  per_class.append(dict(e=e,negative=bool(neg),midpoints=count))

# Dense domain edges, every exponent's head/tail and new raw tiny controls.
for center in (0x3c90000000000000,0x3ca0000000000000,0x3ca8000000000000,
               0x3d70000000000000,0x3d80000000000000,0x3d90000000000000):
 for d in range(-256,257):
  for sign in (0,1<<63):add(sign|(center+d),'dense_domain_edges')
rng=random.Random(0xE44C0DE)
for _ in range(8192):add((rng.getrandbits(1)<<63)|rng.randrange(0x3c90000000000001,0x3d90000000000000),'new_uniform_tiny_raw')
data=b''.join(struct.pack('<Q',x) for x in jobs)
(W/'tiny-inputs.bin').write_bytes(data)
(W/'tiny-input-groups.json').write_text(json.dumps([jobs[x] for x in jobs])+'\n')
out=dict(status='AUTHOR_EXACT_RATIONAL_WHOLE_TINY_DOMAIN_MIDPOINT_PROOF',
 source_sha256=sha(W/'candidate/native_eabi_m0.cpp'),domain='2^-54 < abs(x) < 2^-38',
 input_exponents=[-54,-39],remainder_input_ulp_upper_bound=str(remainder_bound),
 guarded_input_displacement=guard,quadratic_displacement_error=str(square_perturbation),
 cubic_remainder_error=str(cubic_perturbation),total_error=str(total),
 total_error_strictly_below='2^-22',midpoint_quadratic_minimum_integer_distance='2^-18',
 all_midpoint_cells=midpoints,all_guard_transition_model_checks=checks,
 quadratic_shifts=sorted(q_values),max_odd=max_odd,odd_square_fits_uint32=True,
 every_midpoint_transition_neighbors_in_ARM_corpus=True,per_class=per_class,
 prepared_new_tiny_inputs=len(jobs),tiny_inputs_sha256=hashlib.sha256(data).hexdigest(),
 author_source_proof_not_independent_review=True,hardware_accessed=False)
(W/'proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
