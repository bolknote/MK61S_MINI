from pathlib import Path
from fractions import Fraction as F
import sys,json,re,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parent))
from generate_m0_log70_table import certificate as log70
from certify_m0_ln_refine import certificate as log94
from certify_m0_log10_fast import certificate as relative
from certify_m0_exp_fast import certificate as exp62

import argparse
p=argparse.ArgumentParser(description='Exact rational pow fast/refinement error certificates')
p.add_argument('--json',type=Path,required=True)
args=p.parse_args()
w=Path(__file__).resolve().parents[1]
a,b,c,d=log70(),log94(),relative(),exp62()
assert F(a['main_error'])+2<16  # bounded fourth/fifth integer replacement
# RNE(2*t/3) contributes<=1/3 and t rounding adds<=1/3 Q44.
assert F(2,3)<F(0xAAAAAAAB,1<<33)+F(1,2)  # below previous linear bound
h=F(1,1400);S=1<<94
# Generic ARMv6-M retains the merged cross-carry product and four-unit guard.
assert ((1<<32)-1)*((1<<22)-1)+((1<<31)-1)*((1<<32)-1)<1<<64
assert 12912720851596686+(1<<43)+(1<<31)<1<<54
assert ((1<<22)-1)*1023<1<<32  # exact narrow exponent*ln2 limbs
main_generic=F(d['scaled_error'])-1
for error in range(503):
    assert main_generic+F(error,2)/(1-h)<4+(error+1)//2
# The RP2040 product omits columns0/1 (<2^49) and rounds bit63.
limb=(1<<16)-1
assert limb*limb*(1+2*(1<<16))<1<<49
assert 3+4*(limb*limb>>16)+4<1<<18
assert (1<<18)+limb*63<1<<32
assert (limb*63>>16)+(32767*limb>>16)+6<1<<16
product_error=F(1,2)+F(1,1<<15)
# t is rounded to nearest. Both integer divisions by3 are exact, and
# thirds have rounding error at most1/3, with no halfway case.
scale=1<<64;residual=F(12912720851596686,scale)
old_c=F(0xAAAAAAAB,1<<32)
old_linear=old_c/2+abs(old_c-F(2,3))*scale*residual/(1<<22)+F(1,2)
square_error=F(1,2)+F(1,1<<23)
old_q=F(0xAAAAAAAB,1<<33)
old_quadratic=old_q*square_error+max(old_q+abs(old_q-F(1,3))*scale*residual**2/(1<<23),1-old_q)
# square<2^21. The magic multiply still equals floor((square+1)/3).
assert (1<<21)+1<1<<33
new_linear=F(2,3)
new_quadratic=F(1,3)+square_error/3
coefficient_reduction=old_linear+old_quadratic-new_linear-new_quadratic
assert coefficient_reduction>0
main=F(d['scaled_error'])-2+product_error-coefficient_reduction*(scale*residual**2+1)/(1<<45)
assert main<3
for error in range(503):
    base=3 if error<=129 else 4
    assert main+F(error,2)/(1-h)<base+(error+1)//2
assert 4+(503+1)//2>=256  # guard rejects this and all wider cells

# Relative unrounded ln uses the same Q94 coefficients as ln_refine,
# without log10's final 1/ln(10) scaling.
rh=F(1,1<<16)
cube=3+rh;fourth=3+rh*cube
third=3+F(1,3)+(1<<30)*rh*rh
quarter=1+cube/4;fifth=3+fourth/5+(1<<30)*rh**4
relative_rounding=2*(third+quarter+fifth)+1
assert relative_rounding<64
for top in range(10,47):
    limit=min(F(1,1<<16),F(2)**(top+1-62))
    shift=5*(top+1)-216
    allowance=((1<<shift)+2)//3 if shift>0 else 1
    assert S*limit**5/(3*(1-limit))<allowance

# Q96 residual: logarithm-product error E, one product flooring, a
# rounded Q112 step multiplied by n<2^20 and floored to Q96, and the
# final >>2. This is <4+E/4 Q94 units.
assert F(1<<20,1<<17)+1==9
base_argument=1+F(1+9,4)
assert base_argument<4
assert F(3006478,1<<32)+F(1<<28,1<<96)<h

# Rounding h64 introduces <=1/2 Q64 unit into the square. Subsequent
# powers truncate exact high products, each with error <=2 units.
dh=F(1,1<<65)+F(1,S)
square=1+S*(2*h*dh+dh*dh)
powers={3:2+h*square+(S*h*h+square)*dh}
for n in range(4,8):
    powers[n]=2+h*powers[n-1]+(S*h**(n-1)+powers[n-1])*dh
recip={3:3074457345618258603,4:768614336404564651,
       5:153722867280912931,6:25620477880152156,7:3660068268593166}
import math
terms={n:2+F(v,1<<64)*powers[n]+abs(F(v,1<<64)-F(1,math.factorial(n)))*S*h**n
       for n,v in recip.items()}
tail=S*h**8/(math.factorial(8)*(1-h))
poly=square/2+1+sum(terms.values())+tail
after_table=2*poly+1+F(1,2)/(1-h)
assert after_table<1<<21
# The table+polynomial derivative is bounded by 2/(1-h); input E
# therefore contributes <E/(2*(1-h)), which is strictly below E.
base_total=after_table+2*base_argument/(1-h)
assert base_total<1<<24
assert F(1,2)/(1-h)<1
assert (1<<24)+(1<<28)<1<<32

# Verify all Q94 exp table cells by integer inequalities, independently
# of Decimal's exp implementation used by their generator.
text=(w/'code/native_eabi_m0_refine_table.inc').read_text()
rows=re.search(r'refine_exp_table\[512\]\[3\]=\{(.*?)\};',text,re.S)[1]
values=[sum(int(v)<<(32*i) for i,v in enumerate(re.findall(r'(\d+)U',r)))
        for r in re.findall(r'\{([^{}]+)\}',rows)]
assert len(values)==512
for i,q in enumerate(values):assert (2*q-1)**512<1<<(95*512+i)<(2*q+1)**512

# Integer exponent shortcut: |y*f|<=2^-28. For y=-n, Taylor's second
# derivative is bounded using (1-|f|)^(n+2)>=1-3|y*f|>1/2.
t=F(1,1<<28)
assert 1-3*t>F(1,2)
assert 2*t*t<F(1,1<<54)
# Positive n has a still smaller bound. The exact first-order term is
# on the 2^-53 grid; only x<1,y<0 yields a binary64 midpoint above1.
# Its nonlinear remainder is strictly positive by convexity.
assert t*t/(2*(1-t))<2*t*t

# Direct near-one argument: f=delta*2^-p, |f|<=2^-36,
# sy<2^53, delta<=2^17. Both exact limb products fit96 bits.
near_h=F(1,1<<36)
near_tail=700*near_h*near_h*(1<<64)/(3*(1-near_h))
assert near_tail<1
# floor(A) differs by <1 Q64, then floor(floor(A)*|f|/2)
# differs by <1. The total error stays strictly below4 Q64.
assert 1+near_h/2+1+near_tail<4
assert 53+17<96 and 64+10+17<96
assert all(-24<=p-12-e<=21 for p in (52,53) for e in range(20,65))

# The normal unrounded logarithm occupies <16 high bits. ln(2)<0.7
# gives a loose bound for every positive normal binary64 operand.
assert F(1024*7*64,10)+1<1<<16
discarded=(65535**2)+(2*65535**2)*(1<<16)
assert discarded<1<<50<1<<53
assert all(21<=s-32<=38 for s in range(53,71))
# Exact product P and truncated P0 differ by less than one Q64 unit
# before flooring. floor(P/2^s)-floor(P0/2^s) is therefore0 or1;
# the implementation adds one to input_error before the same enclosure.

# ln(2)=2*atanh(1/3), with an exact rational tail bound.
ln2_lo=sum((F(2,(2*i+1)*3**(2*i+1)) for i in range(10)),F(0))
ln2_hi=ln2_lo+F(2,21*3**21)*F(9,8)
assert ln2_hi<F(1733,2500)  # 0.6932
assert F((1<<28)+3,1<<64)<F(1,1024)
assert 710-F(1,1024)>1024*ln2_hi
assert 746-F(1,1024)>1075*ln2_hi
# The residual guard/domain is unchanged. All new segment indices lie
# inside the exp certificate's already bounded n range.
assert F(746*512)/ln2_lo+2<d['maximum_segment_index']
assert 2*(4+(502+1)//2)==510
assert all(11<=-k-1012<=63 for k in range(-1075,-1022))
# Uniform subnormal cells have midpoint2^(shift-1), including the
# transition to the minimum normal. At k=-1076 the zero midpoint is2^63.
assert F((1<<63)+510,1<<65)<F(1,2)
# The overflow midpoint2^1024-2^970 becomes Q62 2^62-256 at k=1024.
assert 970+62-1024==8
assert 2*((1<<62)-510)>1<<62

# If y=s*2^(e-52), e<=52 requires the low52-e bits of s to
# vanish for an integer. The next bit is its parity. e>52 is even.
for exponent in range(53,1024):assert exponent-52>=1
# Safe far endpoints for x^2: e<=-539 gives x^2<2^-1076,
# whereas e>=512 gives x^2>=2^1024. NaN/inf use owned multiplication.
assert 2*(-539+1)<-1075
assert 2*512==1024
# x^1=x is exact after NaN quieting. x^-1 and the remaining x^2
# range use owned RNE division/multiplication on all IEEE inputs. Negative
# integer powers reuse the positive magnitude and apply an exact sign;
# RNE symmetry includes signed zero and signed overflow.
# Direct inverse sqrt: exact center cells and rational propagation.
from generate_m0_rsqrt_table import render as rsqrt_render,values as rsqrt_values
assert (w/'code/native_eabi_m0_rsqrt_table.inc').read_text()==rsqrt_render()
rsqrt_values()  # all512 exact integer midpoint inequalities
rh=F(1,512);t_error=1+F(1,513)
derivative=1/(2*(1-rh)**2)
quadratic_error=F(3,8)+F(1,2)
cube_error=1+rh*rh*(1<<16)+rh
cubic_error=F(5,16)*cube_error+F(1,2)
series_tail=(1<<32)*F(35,128)*rh**4/(1-rh)
seed_error=t_error*derivative+quadratic_error+cubic_error+series_tail+F(1,2)*(1+rh)+F(1,2)
assert seed_error<4  # Q32 units; clamping toUINT32_MAX does not enlarge this bound.
# The rounded Q32 center is multiplied by a factor below1+rh. A
# candidate above1 can be clamped to1-2^-32 with error at most the
# larger of its prior error and one unit; seed_error already exceeds1.
factor_error=t_error*derivative+quadratic_error+cubic_error
assert 1+rh/2+F(3,8)*rh**2+F(5,16)*rh**3+factor_error/(1<<32)<1+rh
assert seed_error>1
initial_delta=seed_error/F(1<<32)
newton_ideal=(3*initial_delta**2+2*initial_delta**3)*(1<<63)
# The seed square is exact. The high product misses <2 Q62 units;
# multiplication by seed/2^32 contributes <2 Q63 units, then one floor.
newton_rounding=2+1
assert seed_error<4
assert newton_ideal+newton_rounding<24
# The normalized53-bit input never reaches4. Its inverse root lies
# more than256 Q63 units above1/2; the24-unit interval stays above it.
assert (4-F(1,1<<51))*(F(1,2)+F(1,1<<55))**2<1
assert 256>24
assert 24*2<512
# Normalizing even a least subnormal input leaves the final inverse
# square root normal: exponents range from-512 through537.
assert -1022 < -512 <=537<1024
result=dict(status='PASS_ARITHMETIC_BOUNDS',log70=a,log94=b,
    relative_q94_rounding=str(relative_rounding),pow_log_tail_extra_error=2,pow_linear_coefficient_error=str(F(2,3)),exp62=d,pow_exp_q62_error=str(main),pow_exp_q62_enclosure='3+ceil(E/2) for E<=129;4+ceil(E/2) otherwise',
    pow_exp_product_error=str(product_error),pow_exp_generic_error=str(main_generic),
    pow_quadratic_coefficient_error=str(new_quadratic),
    exp94_square_error=str(square),exp94_base_error=str(base_total),
    exp94_interval='2^24 + ceil(log_error*2^(53-shift))',
    integer_shortcut_remainder=str(2*t*t),
    exp94_table_cells=len(values),direct_rsqrt_seed_error_q32=str(seed_error),direct_rsqrt_error_q63=str(newton_ideal+newton_rounding),direct_rsqrt_interval_q63=24,
    source_sha256=hashlib.sha256((w/'code/native_eabi_m0_pow_fast.inc').read_bytes()).hexdigest(),
    scope='Exact rational propagation and exp table cell verification; independent ARM execution and source review required. Universal fallback pow totality remains unresolved.')
args.json.write_text(json.dumps(result,indent=2)+'\n')
print('PASS: rational pow first/middle intervals, exact shortcuts and exp94 table cells')
