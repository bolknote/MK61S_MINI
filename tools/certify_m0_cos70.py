#!/usr/bin/env python3
"""Bound the RP2040 small-cosine refinement with exact rational arithmetic."""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    source=args.source_root/'code/native_eabi_m0_trig_cos70.inc'
    scale=1<<70;zmax=1<<58
    # exp_high_square differs from the real Q64 high square by <=1.
    # Its monotone maximum on q<2^63 is exactly2^62-1.
    h,l=(1<<31)-1,(1<<32)-1
    maximum=h*h+((h*l)>>31)+1
    assert maximum==(1<<62)-1
    assert maximum>>4 < zmax
    delta=F(1,1<<69);radius=F(1,64)+delta
    argument_square_error=(2*F(1,64)*delta+delta*delta)*scale
    z_error=F(5,4)
    assert 1+F(1,16)+argument_square_error<z_error
    # Two retained products form z^2; the discarded low square is <2^-18.
    square_error=2+F(1,1<<18)+(2*zmax*z_error+z_error*z_error)/scale
    cube_error=9+square_error*zmax/scale+F((zmax+z_error)**2*z_error,scale**2)
    fourth_error=1+F(1,1<<9)+F(1,1<<42)+square_error*(2*F((zmax+z_error)**2,scale)+square_error)/scale
    tail=radius**10*scale/math.factorial(10)
    error=F(1,2)+z_error/2+F(13,24)+square_error/24+F(1,2)+cube_error/720+F(1,2)+fourth_error/40320+tail
    assert error<3<4
    quotient_rows=[]
    for divisor,shift,constant,width in [(45,37,0xB60B60B7,31),(40320,46,0x68068069,23)]:
        excess=divisor*constant-(1<<shift)
        assert constant==((1<<shift)+divisor-1)//divisor
        assert 0<=excess<divisor and (1<<width)*excess<(1<<shift)
        quotient_rows.append(dict(divisor=divisor,shift=shift,multiplier=hex(constant),input_bits=width,excess=excess,
            conclusion='Multiplying by ceil(2^shift/divisor) and shifting gives the exact floor quotient throughout this input domain.'))
    assert ((1<<34)-1+360)>>4 <1<<31
    assert (1<<22)-1+20160 <1<<23
    assert F(1<<16,2)-F(1<<16,24*4096)-1-105>0
    assert (radius**2)/2<F(1,2)
    report=dict(status='PASS',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        domain=dict(normalized_q='2^62<=q<2^63',exponent='-26<=e<=-6',argument_error='<=1 relativeQ63 unit'),
        square_error_Q70=str(square_error),cube_error_Q70=str(cube_error),fourth_error_Q70=str(fourth_error),
        taylor_tail_Q70=str(tail),total_error_Q70=str(error),total_error_float=float(error),
        strict_error_bound_Q70=3,retained_guard_Q70=4,reciprocal_quotients=quotient_rows,
        derivation=[
            'The approximate argument is q*2^(e-63); its largest physical error is2^-69. Quantizing exp_high_square>>(-2e-8) and propagating that argument error costs less than5/4Q70 units.',
            'For z=t*2^26+l, z^2/2^70=t^2/2^18+t*l/2^43+l^2/2^70. The first two terms are retained separately; the last is below2^-18.',
            'Truncating z^2 to its high32bits and z to its high32bits bounds the cube loss below9Q70 units; the analogous fourth-power loss is below1+2^-9+2^-42 units. Input-error propagation is included in the exact fractions.',
            'The decrement uses z/2-z^2/24+z^3/720-z^4/40320. Rounded coefficient divisions and the alternating cosine remainder contribute less than the recorded bound.',
            'cos(r) lies in(1/2,1]. Its binary64 spacing below1 is2^-53, hence2^17Q70 units. A decrement more than four units from any half-cell boundary has a unique RNE result for the complete enclosure.'
        ],
        limitations=['The certificate checks rational inequalities and algebraic error propagation, not every C++ instruction.',
            'The normalized argument enclosure is an input precondition; actual argument reduction and final public functions require separate independent tests.',
            'The implementation returns0 and uses the existing refinement whenever its guard is undecided.'])
    args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status='PASS',total_error_float=float(error),strict_error_bound_Q70=3,retained_guard_Q70=4),indent=2))


if __name__=='__main__':
    main()
