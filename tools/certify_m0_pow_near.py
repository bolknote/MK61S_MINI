#!/usr/bin/env python3
"""Record exact range/error lemmas for the RP2040 near-one Q80 pow argument."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();text=args.source.read_text()
    for fragment in ('static bool pow_near_one_refined_argument(',
                     'if(unsigned(ey-int(leading)-3)>3) return false;',
                     'const U quartic=pow_near_mul_shift(3*cubic,delta,p+2);',
                     'input_error=8U<<16;',
                     'if(unsigned(ey-int(leading)-3)<=3) return {0,0,0,false,0};'):
        assert text.count(fragment)==1,fragment
    ranges=[]
    for p in (52,53):
        for width in range(1,p-24):
            for d in range(3,7):
                leading=p+2-width;ey=leading+d;shift=ey+28-p
                assert 5<=shift<=35 and 0<leading<=54 and -12<=ey<=64
                ranges.append(dict(p=p,delta_width=width,D=d,linear_left_shift=shift))
    f=Fraction(1,1<<26);linear=512*(1<<80)
    quadratic=Fraction(linear)*f/2
    cubic_raw=Fraction(linear)*f*f
    quartic_raw=cubic_raw*f
    assert linear<1<<90 and quadratic<=1<<62 and cubic_raw<=1<<37
    assert 3*(cubic_raw/3+1)*(1<<27)<1<<67
    # Q=floor(Q*) and R=floor(Q*f*2), followed by nearest division by3.
    cubic_error=(1+2*f)/3+Fraction(1,3)
    quartic_error=1+3*cubic_error*f/4
    remainder=Fraction(linear)*f**4/(5*(1-f))
    combined=1+cubic_error+quartic_error+remainder
    assert cubic_error<1 and quartic_error<2 and remainder<1 and combined<5<8
    # The original first-tier near-one interval extends to |f|<=2^-14.
    maximum_argument=Fraction(512)/(1-Fraction(1,1<<14))
    assert maximum_argument<513<700
    minimum_input_error=4*(1<<(4+3))
    assert minimum_input_error==512 and 4+(minimum_input_error+1)//2>=260>256
    shared_fast_exp='const Product fast_argument=' in text
    if shared_fast_exp:
        assert text.count('pow_exp_argument_checked(fast_argument,2,negative_argument,result)')==1
        assert 1+Fraction(8,1<<16)<2
    report=dict(status='PASS_RANGE_AND_ERROR_LEMMAS',
        source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),ranges=ranges,
        certificate_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        checked_fast_exp_argument=shared_fast_exp,
        errors_Q80=dict(cubic=str(cubic_error),quartic=str(quartic_error),
                        logarithm_remainder=str(remainder),combined=str(combined),accepted=8),
        argument=[
            'For x on either side of one, f=delta/2^p, p=52 or53, delta>0, and bit_length(delta)=b. The normalized Q62 argument has leading=p+2-b. Setting D=ey-leading gives 2^(D+1)<=|y*f|<2^(D+3).',
            'For |f|<=2^-26 and D in[3,6], delta<=2^27, |y*f|<512, and L=|y*f|*2^80 is exactly sy*delta*2^(ey+28-p). All left shifts are5..35, and the full integer has fewer than90bits. Each split32 product and carry retains every bit.',
            'Q=floor(L*f/2) is below2^62. R=floor(2*Q*f) is below2^37. The existing short divide-by3 computes nearest(R/3), with error<=1/3. Therefore C differs from L*f^2/3 by less than(1+2*f)/3+1/3<1.',
            'T=floor(3*C*f/4) differs from L*f^3/4 by less than1+3*error(C)*f/4<2. Its full product needs fewer than67bits; pow_near_mul_shift retains its high word.',
            'The magnitude argument is L-Q+C-T above one, and L+Q+C+T below one. Quadratic floor error is<1. The logarithmic tail is at most L*f^4/(5*(1-f))<1. Total absolute error is<5 Q80 units, enclosed by the selected8units.',
            'The exact shift to Q96 multiplies both the argument and its absolute bound by65536. The unchanged exp refinement adds its own conservative error and accepts only an unambiguous binary64 rounding cell.',
            'When the shared fast exp entry is present, flooring the Q80 argument to Q64 adds less than1unit of error and rescales the existing8unit radius to8/65536. The total is less than2 Q64 units. The original checked Q62 exp body accepts only if its own complete binary64 rounding enclosure fits one cell; otherwise the retained Q96 argument enters the unchanged Q94 exp refinement.',
            'For the first-tier shortcut, |f|<=2^-14 and D in[3,6] imply |y*log(x)|<513. Its approximation error cannot reach the far overflow/underflow endpoints. A logarithm error of at least4 implies input_error>=512 and final error>=260, so the existing error>=256 check necessarily rejects that tier. Returning scale0 takes the same caller to refinement without computing a result.'
        ],
        limitations=['Source-pinned exact range/error lemmas; not machine-checked verification of all compiled instructions.',
                     'The separately tested short division, split products, Q94 exp error and final pack contract remain dependencies.',
                     'General pow totality and hardware speed parity remain unproved; the undecided final trap is retained.'])
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: Q80 ranges, four-term logarithm enclosure, and first-tier rejection lemma')


if __name__=='__main__':
    main()
