#!/usr/bin/env python3
"""Certify rational bounds used by the Q160 cubic binomial pow refinement."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    text=args.source.read_text()
    start=text.index('static bool pow_near_one_binomial(')
    stop=text.index('\n}\n',start)+3
    helper=text[start:stop]
    for fragment in ('unsigned(ey+11)>15', 'xb-one+64>96',
                     'unsigned(108+ey-int(p))', 'unsigned(2*p-55-2*ey)',
                     'numerator_high=d>>32', 'const U carry=U(upper<product.high)',
                     'sy>>unsigned(20-ey)', 'pow_log_third70(raw)>>1',
                     'q.low<=4', 'q.low>=U(0)-4'):
        assert fragment in helper,fragment
    h=F(1,1<<47)
    # For |y|<32, the fourth falling factorial is bounded by
    # 32*33*34*35. Bernoulli bounds the varying derivative factor.
    derivative_factor=1/(1-36*h)
    assert derivative_factor<2
    remainder_Q160=F(32*33*34*35,24)*2*h**4*(1<<160)
    assert remainder_Q160<F(1,1024)
    # For P(y)=y(y-1)(y-2), |P'(y)|<=3266 on [-32,32].
    # Flooring y to Q32 costs <3266 Q32 units. The two coefficient
    # products cost <34+1 Q32 units, for a combined bound of3301.
    coefficient_error_Q32=3*32**2+6*32+2+34+1
    assert coefficient_error_Q32==3301
    cubic_coefficient_error_Q160=F(coefficient_error_Q32,1<<32)*h**3*(1<<160)/6
    assert cubic_coefficient_error_Q160<F(1,8)
    # raw is floored before division by6. Existing exact RNE division
    # by3 followed by a right shift differs from raw/6 by <=2/3.
    division_errors=[abs(F(((v+1)//3)//2)-F(v,6)) for v in range(6)]
    assert max(division_errors)==F(2,3)
    cubic_error_Q160=cubic_coefficient_error_Q160+F(1,6)+F(2,3)
    total_error_Q160=1+cubic_error_Q160+remainder_Q160
    assert total_error_Q160<2<4
    nonlinear_over_linear=F(33,2)*h+F(33*34,6)*h*h+F(33*34*35,12)*h**3
    assert nonlinear_over_linear<F(1,2)
    maximum_displacement=32*h*(1+nonlinear_over_linear)
    assert maximum_displacement*(1<<160)<1<<119
    assert F(1,1<<11)*F(1,1<<53)*(1-nonlinear_over_linear)*(1<<160)>4
    raw_upper=32*33*34*(1<<19)
    assert raw_upper<1<<35<1<<38
    # The existing divide-by3 implementation's complete floor-loss proof.
    c=F(1,4)+F(1,16);loss=F(2)
    for shift in (4,8,16):
        c*=1+F(1,1<<shift);loss=loss*(1+F(1,1<<shift))+1
    assert c==F((1<<32)-1,3*(1<<32))
    assert 3*(loss+F(1,3))<17
    assert all((11*r)>>5==r//3 for r in range(17))
    assert all((171*t)>>9==t//3 for t in range(193))
    ranges=[]
    for p in (52,53):
        delta=1<<(p-47)
        for ey in range(-11,5):
            linear_shift=108+ey-p
            quadratic_shift=2*p-55-2*ey
            assert 0<linear_shift<64 and 0<quadratic_shift<128
            numerator_max=((1<<53)-1)*delta**2
            difference_max=(1<<(52-ey))+(1<<53)-1
            assert numerator_max<1<<65 and difference_max<1<<64
            assert numerator_max*difference_max<1<<129
            assert ((1<<53)-1)*delta<1<<59
            assert (((1<<53)-1)*delta)<<linear_shift<1<<128
            assert numerator_max>>64<=1
            ranges.append(dict(fraction_bits=p,exponent=ey,delta_max=delta,
                               linear_shift=linear_shift,quadratic_shift=quadratic_shift))
    result=dict(status='PASS_EXACT_RATIONAL_CERTIFICATE',
        domain='|x-1|<=2^-47, x!=1, 2^-11<=|y|<32; both signs of y',
        derivative_factor_upper=str(derivative_factor),
        remainder_Q160_upper=str(remainder_Q160),
        cubic_coefficient_error_Q32=coefficient_error_Q32,
        cubic_error_Q160_upper=str(cubic_error_Q160),
        combined_floor_cubic_and_Taylor_error_Q160_upper=str(total_error_Q160),
        sign_and_nonoverflow_displacement_bound=str(maximum_displacement),
        reserved_radius_Q160=4,existing_divide3_input_upper_exclusive=1<<35,
        checked_integer_ranges=ranges,
        source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256(helper.encode()).hexdigest(),
        existing_third_source_sha256=hashlib.sha256(args.source.with_name('native_eabi_m0_pow_third.inc').read_bytes()).hexdigest(),
        producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Exact rational inequalities and all discrete exponent/side range checks. Linear term exact; one quadratic floor; Q32 cubic coefficient with Lipschitz and product-floor bounds; reuse of the existing certified RNE divide-by3 inside its input domain; fourth-order Taylor remainder. Source hashes bind the certificate to the inspected helper and existing division code. Compiled arithmetic, rounding-cell acceptance and public ABI require the independent ARM test. No universal pow-totality or physical-speed claim.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: exact linear term, one quadratic floor, checked Q32 cubic; remainder',remainder_Q160,
          'Q160; total error',total_error_Q160,'<2 Q160, reserve4; 32 integer range cases')


if __name__=='__main__':
    main()
