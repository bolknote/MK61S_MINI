"""Exact rational specialization of the existing atan Q70 certificate."""
from fractions import Fraction as F
from pathlib import Path
import hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
original=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/proof/certify_m0_atan_fast.py'
spec=importlib.util.spec_from_file_location('frozen_atan_certificate',original)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
parent=module.certificate();assert parent['status']=='PASS'
scale=1<<70;half=F(1,2)
first=8+half+F(1,1<<14);second=first*first/(1<<30)+half+F(1,1<<22)
reciprocal=4*(second+1)**2+3
def total(h,ratio,table,halving):
 square=half+F(13,512)
 cube=half+F(13,512)+h*square
 fifth=(half+h*h*cube+h**3*square+cube*square/scale+
        ((1<<17)-1)*(scale*h*h+square)/scale+
        ((1<<24)-1)*(scale*h**3+cube)/scale)
 seventh=(half+h*h*fifth+h**5*square+fifth*square/scale+
          7*(scale*h*h+square)/scale+
          ((1<<24)-1)*(scale*h**5+fifth)/scale)
 c5=F(0xcccccccd,1<<31)
 fifth_term=fifth/5+F(7,5)+(c5-F(8,5))*(scale*h**5+fifth)/8+half
 c7=F(2454267027,1<<34)
 seventh_term=c7*seventh+max(3*c7+(c7-F(1,7))*scale*h**7,1-3*c7)
 third_term=half+cube/3
 omitted=scale*h**9/(9*(1-h*h))
 return ratio+halving+table+third_term+fifth_term+seventh_term+omitted
old=total(F(1,128),F(13,2)+2*reciprocal,F(1),half)
assert old==F(parent['polynomial_error'])
small=total(F(1,256),F(13,2)+2*reciprocal,F(1),half)
narrow_ratio=F(13,2)+F(49,64)*reciprocal
narrow=total(F(47,8192),narrow_ratio,half,F(0))
global_positive=total(F(1,128),F(13,2)+2*3,F(1),half)
small_positive=total(F(1,256),F(13,2)+2*3,F(1),half)
narrow_positive=total(F(47,8192),F(13,2)+F(49,64)*3,half,F(0))
tiny=total(F(1,256),F(13,2)+F(1,8)*reciprocal,half,F(0))
tiny_positive=total(F(1,256),F(13,2)+F(1,8)*3,half,F(0))
assert small<36
assert narrow*8<176
assert global_positive*8<282 and old*8<426
assert small_positive*8<144 and small*8<288
assert narrow_positive*8<121
assert tiny_positive*8<91 and tiny*8<100
assert (1<<60)+33 < (1<<62)  # tiny normalized numerator forces the small h cap
assert second+1<2  # final correction product stays below2^64
# For e=-5..-1, k<=2^(e+7), s<2^53:
# base<=d=base+s*k<base+2^(e+60)<=2*base.
normalization=[]
for e in range(-5,0):
 base=1<<(58-e);extra=1<<(e+60)
 assert extra<=base
 assert (64-(58-e+1))==e+5
 # Lower/upper binade margins for the approximate Q70 angle. The
 # alternating-series lower bound atan(x)>=x-x^3/3>=2*x/3 leaves
 # >=2^e/6 above2^(e-1). Binary64 x is >=1 ULP below2^(e+1),
 # so atan(x)<x is still >=2^(e-52) below that upper binade.
 assert F(1,1<<(-e))*scale/6>narrow
 assert (1<<(e+18))>narrow
 normalization.append(dict(exponent=e,denominator_lower=base,denominator_strict_upper=2*base,normalization_shift=e+5))
# The specialized packer also replaces the global packer. Its center
# exponent comes from the already known input binade, including q.high=0
# at the lower endpoint. All64-unit intervals fit these two binades.
for e in range(-6,1):
 assert F(1,1<<(-e))*scale/6>64
 assert (1<<(e+18))>64
assert F(1,6)*scale>64 and F(1,64)*scale>64
report=dict(status='PASS_EXACT_RATIONAL_ATAN_LOCAL_ENCLOSURES',parent_certificate_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
            unchanged_parent_selection_endpoint_checks=parent['selection_endpoint_checks'],reciprocal_error=str(reciprocal),
            global_error=str(old),small_h_cap='1/256',small_h_error=str(small),small_h_error_float=float(small),small_h_radius_Q70=36,
            narrow_h_cap='47/8192',narrow_normalized_numerator_strict_cap='49*2^56',narrow_ratio_error=str(narrow_ratio),
            narrow_error_Q70=str(narrow),narrow_error_Q70_float=float(narrow),narrow_error_Q73=str(8*narrow),narrow_radius_Q73=176,
            reciprocal_strict_upper_error=3,
            reciprocal_one_sided_reason='The exact Newton step T satisfies T-R=-d*(S-R)^2/2^126<=0. Truncating its correction changes it by <r/2^30+1<=3; subtract/add branches preserve this upper bound.',
            directional_radii_Q73={'global':[282,426],'small_h':[144,288],'narrow_noninverted':[121,176],'tiny_normalized_n':[91,100]},
            directional_error_Q70={'global_positive':str(global_positive),'small_positive':str(small_positive),'narrow_positive':str(narrow_positive),'tiny_positive':str(tiny_positive),'tiny_negative':str(tiny)},
            tiny_normalized_n_strict_cap='2^59; implies h<2^60+33<2^62',
            table_error_noninverted='1/2 Q70 (one rounded atan grid value)',denominator_truncation_noninverted=0,
            normalization=normalization,
            high_word_test='For k=e+5 in0..4, (uint32_t(n>>32)>>(24-k))<49 iff (n<<k)<49*2^56; geometry ensures no wrap.',
            normalized_numerator_identity='n_normalized = 2^69*abs(x-index/64) for this non-inverted domain.',
            packing='Non-inverted base exponent e=-6..0; inverted base exponent0. Center exponent is base or base-1. Use upper/lower radii according to correction sign and invert, then accept8*midpoint_distance>=radius73. All actual errors are strictly below radius.',
            minimum_pack_shift=11,maximum_pack_shift=18,all_centers_exact_halfway_decline=True,
            no_approximation_or_table_changed=True,hardware_accessed=False,canonical_or_frozen_changed=False,goal_complete=False)
(W/'certificate.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('normalization','narrow_error_Q70','narrow_error_Q73','reciprocal_error','global_error','small_h_error')},indent=2))
