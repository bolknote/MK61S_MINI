"""Source-bound one-sided coefficient proof for the private Q70 ln child."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json
import sys

sys.dont_write_bytecode=True
from propagation import ARGUMENT,S,enclosures,radii40,coefficient_bias20

W=Path(__file__).resolve().parent
ROOT=W.parents[1]
BASE=ROOT/'.build/m0-ln-main-ln2-sign-20261024'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=(W/'native_eabi_m0_log70.inc').read_text()
assert sha(BASE/'native_eabi_m0_log70.inc')=='661ae2b62f0f2e3b9da08b689de0a7876f83fa2f80f57380113b78cbbd74e79b'
assert sha(W/'native_eabi_m0_log70.inc')=='4db4753b23ebaa7a17aed662d2f59d6b351f6c0d8739559ad4235e6c615f1fd2'
assert sha(W/'candidate.elf')=='2c0d376fe0b12c99f694279c2382977b00001875b4777aed504c0e1e309df728'
for token in ('const int32_t r4=int32_t((fourth+2U)&3U)-2;',
 'const int32_t r5=int32_t(fifth)-5*int32_t(((fifth+2U)*52429U)>>18);',
 'int32_t bias20=5*r4+(negative?4*r5:-4*r5);',
 'uint32_t lower=negative?85U:90U;',
 'uint32_t upper=den>=3585U?(negative?85U:80U):',
 'den>=2081U?(negative?180U:170U):(negative?190U:180U);',
 'if(sign) {const uint32_t old=lower;lower=upper;upper=old;bias20=-bias20;}',
 'const uint32_t limit=above?upper:lower+20U*n;',
 'const int32_t adjustment=2*bias20*int32_t(den)-40*oriented;',
 '(int32_t(40U*distance)-int32_t(limit))*int32_t(den)+',
 '(above?-adjustment:adjustment)>=0;',
 'if(!distance) return ln_refine(x);',
 'const int32_t residue=int32_t(delta_low-h_low*den);',
 'const int32_t oriented=(negative!=(sign!=0))?-residue:residue;',
 'safe=distance>=4U || ((bh&0xFFFFFU)<32768U && (bh&1023U)>=1022U);',
 'else safe=distance>=((bh&512U)?7U:6U);',
 'radius=tail>half?6U:(negative?3U:4U);'):
    assert token in source,token

parent_raw=json.loads((ROOT/'.build/m0-ln-main-raw-split-family-20261024/certificate.json').read_text())
assert F(parent_raw['generic_quotient_error'])==ARGUMENT
parent_ln2=json.loads((BASE/'certificate.json').read_text())
assert parent_ln2['ln2_Q70_is_strictly_below_exact_ln2']
assert parent_ln2['rational_100term_log2_lower_and_upper_checked']
assert -F(1,2)<F(parent_ln2['actual_ln2_Q70_error_approx'])<0

bands={}
for minimum in (2049,2081,3585):
    b=enclosures(minimum)
    bands[minimum]={n:dict(exact=str(v),approx=float(v)) for n,v in b.items() if isinstance(v,F)}
    for negative in (False,True):
        lower,upper=radii40(minimum,negative)
        prefix='negative' if negative else 'positive'
        assert b[prefix+'_lower']<F(lower,40)
        assert b[prefix+'_upper']<F(upper,40)

# The old cheap branches do not use coefficient metadata. Reproduce
# their independent one-sided arithmetic bounds by adding the possible
# coefficient remainders back to the new bounds.
b=enclosures(2049);h=b['h'];nonlinear=b['nonlinear']
raw_neg_lo=b['negative_lower']+F(1,2)+F(2,5)
raw_neg_hi=b['negative_upper']+F(1,4)+F(2,5)
raw_pos_lo=b['positive_lower']+F(1,2)+F(2,5)
raw_pos_hi=b['positive_upper']+F(1,4)+F(2,5)
# negative_lower/positive_lower already include square/third rounding;
# only the fourth and fifth coefficient rounding is restored here.
assert raw_neg_lo<3 and raw_neg_hi<6
assert raw_pos_lo<4 and raw_pos_hi<6
assert raw_neg_lo-nonlinear+1/(1-h)<4
assert raw_neg_hi-nonlinear<6
assert raw_pos_lo-nonlinear<4
assert raw_pos_hi-nonlinear+1/(1-h)<7
minimum_argument=F(255,256*2111)
endpoint_remainder=S*minimum_argument**6/(6*(1+h))
assert raw_pos_lo-endpoint_remainder<1
assert raw_pos_lo-nonlinear-endpoint_remainder<1

for value in range(65536):
    assert ((value+2)*52429)>>18==(value+2)//5
    assert (value+2)*52429<1<<32
    assert -2<=value-5*(((value+2)*52429)>>18)<=2
for fourth in range(4):
    assert fourth-4*((fourth+2)//4)==((fourth+2)&3)-2
for den in range(2049,4096,2):
    assert ARGUMENT*den<32768
    for negative in (False,True):
        lo,hi=radii40(den,negative)
        minimum=3585 if den>=3585 else 2081 if den>=2081 else 2049
        bounds=enclosures(minimum)
        prefix='negative' if negative else 'positive'
        assert bounds[prefix+'_lower']<F(lo,40)
        assert bounds[prefix+'_upper']<F(hi,40)
for k in range(-1022,1024):
    extra=(abs(k)+1)//2
    exponent=k+1023
    assert 2*extra-((exponent^1)&1)==abs(k)

max_bias=max(abs(coefficient_bias20(fourth,fifth,negative))
    for fourth in range(4) for fifth in range(5) for negative in (False,True))
assert max_bias==18
max_residual=(ARGUMENT*4095).__ceil__()-1
max_limit=190+20*1023
max_cold_distance=15+512
max_adjustment=2*max_bias*4095+40*max_residual
max_expression=(40*max_cold_distance+max_limit)*4095+max_adjustment
assert max_expression<1<<28
max_error=F(19,4)+F(18,20)+ARGUMENT+F(1023,2)
assert max_error<1024
assert max_error-F(1022,2)<512

out=dict(status='PASS_SOURCE_BOUND_MAIN_LN_ONE_SIDED_COEFFICIENT_ENCLOSURES',
    source_sha256=sha(W/'native_eabi_m0_log70.inc'),candidate_ELF_sha256=sha(W/'candidate.elf'),
    propagation_source_sha256=sha(W/'propagation.py'),bands=bands,
    actual_argument_error=str(ARGUMENT),actual_h_below_one_over_den_minus_one=True,
    coefficient_bias='r4/4 +/-r5/5 =bias20/20; plus on negative offsets, minus on positive',
    fourth_remainder_domain=[-2,1],fifth_remainder_domain=[-2,2],fifth_nearest_division_cases=65536,
    one_sided_square_error='z-h^2*2^70 in(-1-2^-16,1]; ceil(z/2)-z/2 in{0,1/2}',
    known_linear_error='-v*r/den, r=(delta<<29)-h*den; v=-1 iff offset/output signs differ',
    omitted_P5_log_error='positive for either offset sign; at most2^70*hmax^6/(6*(1-hmax))',
    magnitude_ln2_error='n*(L70-2^70*ln2) in(-n/2,0) for either exponent sign',
    exact_n_parity_cases=2046,signed_residue_abs_below=32768,
    integer_gate_abs_below=max_expression,all_gate_intermediates_fit_signed32=True,
    integer_gate_proof='Above: E<U/40+bias/20-oriented/den<=distance. Below: E>-L/40-n/2+bias/20-oriented/den>=-distance. Strict interval bounds make equality safe.',
    old_cheap_exact_radii=dict(below=4,negative_above=6,positive_above=7),
    old_cheap_raw_radii=dict(negative_below=3,positive_below=4,above=6),
    cheap_positive_endpoint_lower_radius=1,endpoint_minimum_positive_P5_error=str(endpoint_remainder),
    endpoint_domain='k=0,index<=31,offset_high10>=1022',exact_midpoints_still_decline=True,
    pack_widths=[64,80],max_absolute_error=str(max_error),no_adjacent_midpoint_skipped=True,
    inherited_argument_helpers_polynomial_tables_and_fallback_retained=True,
    bare_ARM_source_fragment_checks_required=True,hardware_accessed=False,production_GO=False)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='bands'},indent=2))
