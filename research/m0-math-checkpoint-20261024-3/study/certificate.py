"""Exact coefficient, modular-remainder and error checks for the experiment."""
from pathlib import Path
from fractions import Fraction as F
from itertools import product
import hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
BASE=ROOT/'.build/m0-atan-residual-original-goal-20261024'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASE/'result.json')=='e047da61a015906cac349efa0331625bd625c53a7e42de622fb94268225d669c'
S=1<<70;h=F(1,128)
# Bounds cover endpoint equality too; the parent has stricter operand caps.
cross1=F(65536*65536*255+65535*65535*256+65535*255,1<<53)
cross2=F(65535*2*65535+65536*65536+65535,1<<46)
cross3=F(((1<<17)-1)*((1<<24)-1),1<<70)
cross=cross1+cross2+cross3;assert cross<F(1,2048)
assert 65536*65535<1<<32
assert 2*65536*65535+(1<<28)<1<<34
ez=F(1,2)+F(13,512);e3=F(1,2)+F(13,512)+h*ez
old_e5=(F(1,2)+h*h*e3+h**3*ez+e3*ez/S+
        ((1<<17)-1)*(S*h*h+ez)/S+((1<<24)-1)*(S*h**3+e3)/S)
e7=(F(1,2)+h*h*old_e5+h**5*ez+old_e5*ez/S+
    7*(S*h*h+ez)/S+((1<<24)-1)*(S*h**5+old_e5)/S)
e5=1+F(1,2048)+h*h*e3+h**3*ez+e3*ez/S
e9=F(1,2)+F(1,128)+h*h*e7+h**7*ez+e7*ez/S
assert ez<1 and e3<1 and e7<1
# Thus integer C7<=2^21 and Z<=2^56, even if h equals1/128.
assert (1<<15)*(1<<16)+(1<<23)<1<<32
# The old fifth divisor has positive coefficient error <.4 and a .5
# rounding term. Including its discarded three bits gives -4<=R5<=9.
assert F(0xCCCCCCCD,1<<31)-F(8,5)==F(1,5*(1<<31))
assert F((1<<32)-1,5*(1<<31))<F(2,5)
assert F(((1<<22)+3)*5,7*(1<<34))<F(1,7)
for v in range(1279):assert v*21846>>16==v//3
for v in range(8703):assert v*9363>>16==v//7
for v in range(65):assert (v+2)*13108>>16==(v+2)//5
for v in range(130):assert (v+4)*7282>>16==(v+4)//9
bias_checks=0;max_bias_error=F(0)
for r3,r5,r7,r9 in product(range(-1,2),range(-2,3),range(-3,4),range(-4,5)):
 n=-105*r3+63*r5-45*r7+35*r9;assert abs(n)<=506
 correction=(int(abs(n)>=158)+int(abs(n)>=473))*(-1 if n<0 else 1)
 expected=((abs(n)+157)//315)*(-1 if n<0 else 1)
 assert correction==expected
 max_bias_error=max(max_bias_error,abs(F(n,315)-correction));bias_checks+=1
assert bias_checks==945 and max_bias_error==F(157,315)<F(1,2)
omitted=S*h**11/(11*(1-h*h))
poly=F(1,2)+e3/3+e5/5+e7/7+e9/9+omitted
ratio=F(1,2)+F(35,1<<20)
derivative=33*(h+F(33,S))**2
angle=poly+ratio+1+derivative;assert angle<3
assert (2*33+1)*(1<<25)<1<<32
assert 54+33+5+14+2<1024
report=dict(status='PASS_EXACT_RATIONAL_EXPERIMENTAL_NINTH_POLYNOMIAL_CERTIFICATE',
            parent_result_sha256=sha(BASE/'result.json'),discarded_cross_error=str(cross),cross_error_cap='1/2048',
            old_fifth_remainder_range=[-4,9],corrected_fifth_remainder_range=[-2,2],
            modulo3_divisor_cases=1279,modulo7_divisor_cases=8703,small_fifth_divisor_cases=65,small_ninth_divisor_cases=130,
            combined_rounding_remainder_cases=bias_checks,maximum_combined_bias_error=str(max_bias_error),
            polynomial_error_bound=str(poly),polynomial_error_bound_float=float(poly),
            rounded_ratio_error_bound=str(ratio),all_geometry_angle_bound=str(angle),all_geometry_angle_bound_float=float(angle),
            strict_angle_radius_Q70=3,
            quotient_rounding_reason='Top/Den-u=(u*frac(D/2^38)-frac(abs(R)/2^38))/Den lies in(-1/Den,33/Den). floor((Top+floor(Den/2))/Den) differs from u by less than .5+35/2^20. Its magnitude is at most33.',
            combined_rounding_reason='Four exact nearest-division remainders give bias numerator -105*r3+63*r5-45*r7+35*r9 over315. Thresholds158/473 yield its nearest integer without a division.',
            angle_geometry_reason='Table error plus optional denominator-halving error is at most1 Q70 across all parent geometry classes. Reusing the polynomial at h adds at most33*(hcap+33/2^70)^2 beyond the linear quotient correction.',
            typed_operand_precondition='Pinned parent selector proof: h<1/128, Z<2^56,C3<2^49,C5<2^35,C7<2^22.',
            runtime_implemented=False,public_speed_GO=False,hardware_accessed=False,goal_complete=False)
(W/'certificate.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('polynomial_error_bound','all_geometry_angle_bound','discarded_cross_error')},indent=2))
