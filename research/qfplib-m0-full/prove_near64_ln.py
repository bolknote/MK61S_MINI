#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Relative ln seed with a Q64 factor, |t|<=2^-11, error below2 Q62 units."""
import argparse
from fractions import Fraction as F
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ONE=0x3ff0000000000000


def model(encoded):
    negative=encoded<ONE
    a=((ONE-encoded)<<11) if negative else ((encoded-ONE)<<12)
    assert 0<a<=1<<53
    bit=a.bit_length()-1;q=a<<(62-bit)
    z=a*a>>64
    ar=(a+(1<<21))>>22
    cube=z*ar>>42
    zr=(z+(1<<16))>>17
    fourth=zr*zr>>30
    fifth=fourth*ar>>42
    even=z//3+fourth//5
    odd=(a>>1)+(cube>>2)+fifth//6
    deviation=odd+even if negative else odd-even
    correction=(q*deviation+(1<<63))>>64
    result=q+correction+1 if negative else q-correction
    return result,bit,int(negative)


def prove():
    p=1<<64;t=F(1,1<<11);a=t*p;z=a*a/p;delta=F(1<<21)
    cube_lower=t+z*delta/p+delta/p
    cube_upper=z*delta/p
    dz=F((1<<16)+1)
    fourth_error=(2*z*dz+dz*dz)/p
    fourth_max=t**4*p
    fifth_error=(1+fourth_error)*t+(fourth_max+1+fourth_error)*delta/p
    tail=t**6/(7*(1-t))*p
    poslo=-2-cube_upper/4-fourth_error/5-fifth_error/6-tail
    poshi=2+cube_lower/4+fourth_error/5+fifth_error/6
    neglo=-4-cube_lower/4-fourth_error/5-fifth_error/6-tail
    neghi=cube_upper/4+fourth_error/5+fifth_error/6
    bounds=dict(positive=[poslo/2-F(1,2),poshi/2+F(1,2)],
                negative=[neglo/2+F(1,2),neghi/2+F(3,2)])
    maximum=max(abs(v) for row in bounds.values() for v in row)
    assert maximum<2
    for rem in range(1027):assert rem*0xaaab>>17==rem//3
    for value in range((1<<20)+1):
        hi=value>>16
        q=hi*13107+((((value&65535)+hi)*52429)>>18)
        assert q==value//5
    for value in range(513):assert value*0xaaab>>18==value//6
    return dict(status='PASS',maximum_abs_t='2^-11',factor_precision=64,
        relative_precision=62,output_precision_base=126,error=2,
        rational_output_error_upper_bound=str(maximum),
        centered_output_bounds={k:list(map(str,row)) for k,row in bounds.items()},
        cube_perturbation_bound=str(cube_lower),fourth_perturbation_bound=str(fourth_error),
        fifth_perturbation_bound=str(fifth_error),series_tail_bound=str(tail),
        exact_division_cases=dict(third_residual=1027,fifth=(1<<20)+1,sixth=513),
        product_construction='Normalized |x-1| has low21 bits zero throughout1+-2^-11, including the outer power-of-two boundary. With u=a.low>>21<2^11 and deviation.high<2^21, u*high fits32 bits; splitting u*low into two16-bit limbs constructs the exact high64 and rounding bit.',
        source_sha256={'src/ln_checked.c':hashlib.sha256((ROOT/'src/ln_checked.c').read_bytes()).hexdigest()},
        scope='All-input relative error certificate in the stated near-one domain; execution/packing checked separately. Q245 final undecided trap remains an all-domain termination limitation.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--json',type=Path,required=True)
    args=p.parse_args();r=prove();args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(r,indent=2)+'\n');print('PASS: near64 relative ln error <2 Q62 units')
