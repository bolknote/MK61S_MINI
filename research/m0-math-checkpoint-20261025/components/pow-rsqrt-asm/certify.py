"""Exact rational rsqrt point-error certificate, not a sampled error estimate."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,re
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
table=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code/native_eabi_m0_rsqrt_table.inc'
source=table.read_text();seeds=[int(s) for s in re.findall(r'\b(\d+)[uU]',source)]
assert len(seeds)==512
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(table)=='52c3eae1c6226efab643387d4ab9611ae366363180fd026151cd4558483ffba6'
reciprocals=[];delta_counts={}
for index,b in enumerate(seeds):
 p,i=divmod(index,256);d=513+2*i
 # b is exact RNE of s0 = 2^32/sqrt(d*2^p/512).
 numerator=d<<p;four_A=4*(1<<64)*512
 assert numerator*(2*b-1)**2<four_A<numerator*(2*b+1)**2
 assert 0<b<(1<<32)
 high=(b>>16)**2+(((b&65535)*(b>>16))>>15)
 r=high>>(9-p);floor=(1<<32)//d
 assert r in (floor-1,floor)
 assert d*r<=(1<<32)<d*(r+2)
 delta_counts[str(r-floor)]=delta_counts.get(str(r-floor),0)+1
 reciprocals.append({'parity':p,'index':i,'d':d,'seed':b,'reciprocal':r,'floor':floor})
# For ANY 0<=N<2^32 the quotient floor(N*r/2^32) does not
# overestimate floor(N/d), and differs by less than2 before flooring.
# Therefore its integer underestimate is at most2; q0*d<=N, no overflow.
# Two comparisons/subtractions give the exact quotient for the whole domain.
# t=floor((distance-1)/(d*2^11)), with t=0 at distance=0.
# Since distance is integral, 0<=r_abs-t<=1, where r_abs=distance/(d*2^11).
v=F(1,513);v_complement=1-v
# Taylor order3 of (1+u)^(-1/2), |u|<=v. Its fourth derivative
# is (105/16)*(1+u)^(-9/2); division by4! gives35/128.
# Bounds with integer powers intentionally enlarge the positive factors.
table_error=F(1,2)/v_complement
t_quantization=F(1,2)/(v_complement**2)
taylor=F(35,128)*(1<<32)*v**4/(v_complement**5)
quadratic_round=[F((3*z+4)//8)-F(3*z,8) for z in range(8)]
assert min(quadratic_round)==F(-3,8) and max(quadratic_round)==F(1,2)
# z=floor(t^2/2^32). Q=RNE_half_up(3*z/8), hence error in(-3/4,1/2].
quadratic_error=F(3,4)
cubic_round=[F((5*z+8)//16)-F(5*z,16) for z in range(16)]
assert min(cubic_round)==F(-7,16) and max(cubic_round)==F(1,2)
# w=floor(floor(t^2/2^32)*floor(t/2^16)/2^16).
# 0<=t^3/2^64-w <1+t/2^32+floor(t^2/2^32)/2^16.
cubic_argument_error=1+v+(1<<16)*v*v
cubic_error=F(7,16)+F(5,16)*cubic_argument_error
seed_round=F(1,2)
seed_error=table_error+t_quantization+taylor+quadratic_error+cubic_error+seed_round
assert seed_error<F(25,8)
# Saturation S<=2^32-1 can add at most1 of absolute error because the
# true s=2^63/sqrt(A) is in(2^31,2^32]; it cannot exceed the bound25/8.
# q_exactNewton = s*2^31 -(S-s)^2*(3*s+(S-s))*2^30/s^2.
# Since s>=2^31 and |S-s|<25/8, its error is nonnegative and less than:
newton_error=F(25,8)**2*(F(3,2)+F(25,8)/(1<<32))
point_down_error=newton_error+1
# Old high product omits two fractional cross terms and the low-low term,
# each in[0,1): 0<=A*S^2/2^64-product<3. Multiplication by S/2^32<1
# and final floor make positive point error<3.
point_up_error=F(3)
assert point_down_error<16 and point_up_error<16
# Thus true_q-16<q<true_q+3. Midpoint positions are512 modulo1024.
# At tail<=496 true_q<512; at tail>=515 true_q>512. Only[497,514]
# needs the original exact161-bit boundary. No midpoint tie is accepted
# by the half-up shortcut. This is a whole-normal-domain proof.
def frac(x):return {'numerator':x.numerator,'denominator':x.denominator,'decimal':float(x)}
out={'status':'PASS_EXACT_RATIONAL_RSQRT_COORDINATE_AND_POINT_BOUND','source_seed_table_sha256':sha(table),'all_512_RNE_seed_integer_certificates':True,'all_512_reciprocals_certified':True,'reciprocal_deltas':delta_counts,'whole_uint32_quotient_underestimate_at_most_2':True,'coordinate_quantization_at_most_1':True,'normal_input_domain':'m in[2^52,2^53), parity0/1, all mantissas','bounds':{n:frac(x) for n,x in [('table_error',table_error),('coordinate_error',t_quantization),('Taylor_order4',taylor),('quadratic',quadratic_error),('cubic_argument',cubic_argument_error),('cubic',cubic_error),('seed_round',seed_round),('seed_total',seed_error),('seed_chosen',F(25,8)),('Newton',newton_error),('point_down',point_down_error),('point_up',point_up_error)]},'strict_point_absolute_error_less_than':16,'unsafe_tail_interval_inclusive':[497,514],'unsafe_integer_tails':18,'exact_original_boundary_retained':True,'rows':reciprocals,'new_tables_or_global_RAM':False,'hardware_accessed':False}
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='rows'},indent=2))
