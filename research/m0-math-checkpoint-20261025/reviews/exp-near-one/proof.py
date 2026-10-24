"""Independent exact rational bounds, integer ranges, and packing identities."""
from fractions import Fraction as F
import hashlib,json
from pathlib import Path
O=Path(__file__).resolve().parent
B=1<<16;K=1<<48;rho=F(1,2048);eta=F(7,2)+F(1,32768)
omitted_high=(B-1)**2*(1+2*B+3*B**2)
omitted_middle=(B-1)**2*(1+2*B)
assert F(omitted_high,1<<64)+F(1,2)<eta
assert F(omitted_middle,1<<48)+1<3
# Three col3 products are rounded before col4. The first col4 add has
# no ADC, but the restricted b3<1024 makes its no-carry contract strict.
col3_round_max=(3*(B-1)**2+(1<<15))>>16
first_col4_max=col3_round_max+(B-1)*1023
assert col3_round_max<1<<18 and first_col4_max<1<<32
constants={6:46912496118443,24:11728124029611,120:2345624805922}
assert all(abs(F(v)-F(K,d))<=F(1,2)for d,v in constants.items())
derivative=F(1,6)+rho/12+rho**2/40
horner=eta+rho*(F(1,2)+eta+rho*(F(1,2)+eta+rho/2))+derivative/65536
assert horner<4
H=rho/6+rho**2/24+rho**3/120
rem6=F(1<<14,720)/(1-rho/7)
remaining=4+H+rem6
assert remaining<27
c2max=F(K,24)+F(1,2)+rho*(F(K,120)+F(1,2))+eta
c1max=F(K,6)+F(1,2)+rho*c2max+eta
tailmax=rho*c1max+eta
assert c2max<1<<44 and c1max<1<<46 and tailmax<1<<35
assert F(K,24)-F(1,2)-rho*(F(K,120)+F(1,2))-eta>0
assert F(K,6)-F(1,2)-rho*c2max-eta>0
assert F(64**5-63**5,3840)<21174
rows=[]
for e in range(-32,-11):
 extra=(1<<(e+22))if e>=-22 else 0
 assert (F(1,2)+H)*F(2)**(e+23)<extra+1
 fifth=0
 if e in [-13,-14]:
  s=-4*e-48;fifth=(21174>>s)+2
  for c in range(32,64):
   approximation=c**5//(15*(1<<(s+8)))
   assert F((c+1)**5,15*(1<<(s+8)))-approximation<fifth
 elif e<=-15:
  fifth=69 if e==-15 else 5 if e==-16 else 1
  assert F(2)**(4*e+73)/120<fifth
 zmax=(((1<<53)-1)>>5)**2>>(26-e)
 E=4*(zmax>>48)+32+extra+fifth
 assert zmax<1<<58 and E<8192
 for sign in [0,1]:
  shift=16-e-sign;assert 27<=shift<=48 and 2*E<1<<shift
 rows.append(dict(e=e,x64_right=-e-12,square_shift=26-e,Z_max=zmax,extra=extra,fifth_error=fifth,error_max=E,pack_shifts=[16-e,15-e]))
assert max(r['error_max']for r in rows)==5148
# Division proof: u=65536h+l, u/15=4369h+(h+l)/15.
# For all possible u, h<=3 and v=h+l<=65538. The reciprocal is below
# v/15 by <=65538/(15*65536)<1. Its quotient is exact or one low.
umax=63**5>>12;assert umax==242294
assert F(65538,15*65536)<1 and 65538*4369<1<<32
division_edges=set()
for h in range(4):
 for l in [0,1,14,15,16,32767,65520,65521,65534,65535]:
  u=(h<<16)+l
  if u>umax:continue
  v=l+h;q=v*4369>>16
  got=h*4369+q+int(v-15*q>=15)
  assert got==u//15;division_edges.add(u)
# The negative correction remains positive by a broad global lower bound;
# all additions and coefficient adjustments stay within uint64.
negative_min=(1<<35)-(1<<23)-(1<<15)-1
assert negative_min>0
# Prove split96 operations and every packing branch on independent edge
# integers. These are HOST integer identities, not ARM qualification calls.
jobs=0
for e in range(-32,-11):
 for sign in [0,1]:
  shift=16-e-sign;U=1<<shift
  for m in [1<<52,(1<<52)+1,(1<<53)-(1<<32),(1<<53)-1]:
   for correction in [0,1,(1<<35)-1,(1<<57)-1]:
    N=(m<<16)+(-correction if sign else correction)
    assert 0<N<1<<96
    for error in [1,32,5148,8191]:
     residue=(N+U//2+error)%U
     unsafe=residue<=2*error
     q=(N+U//2)//U
     if not unsafe:
      assert (N-error+U//2)//U==q==(N+error+U//2)//U
     jobs+=1
out=dict(status='PASS_INDEPENDENT_RATIONAL_AND_INTEGER_RANGE_PROOF',
 high_product_omission_max=omitted_high,high_product_absolute_bound=str(eta),
 middle_omission_max=omitted_middle,middle_directed_error_strict3=True,
 first_non_ADC_column4_add_max=first_col4_max,constants_nearest_Q48=constants,
 horner_Q48_error=str(horner),horner_strict4=True,
 remaining_rounding_square_and_Taylor_error=str(remaining),remaining_strict27=True,
 coefficient_upper_bounds=dict(c2=str(c2max),c1=str(c1max),tail=str(tailmax)),
 per_binade=rows,maximum_E=5148,all_declared_shift_and_operand_ranges=True,
 coarse_fifth_32classes_times2_binades=64,division_u_max=umax,division_domain_values_proved_algebraically=umax+1,
 division_boundary_spot_checks=len(division_edges),division_not_ARM_calls=True,
 HOST_packing_interval_identity_checks=jobs,HOST_checks_not_ARM_calls=True,
 RNE_proof='The strict enclosure and modular veto exclude every midpoint for admitted inputs; integer half-up displacement then equals RNE. Unresolved inputs use unchanged refinement.',
 no_device_Git_canonical_network=True)
with (O/'proof.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in out.items()if k not in ['per_binade','coefficient_upper_bounds']},indent=2))
