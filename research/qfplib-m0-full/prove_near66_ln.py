#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Relative ln seed with Q66 deviation, |t|<=2^-11, error below1 Q62 unit."""
import argparse
from fractions import Fraction as F
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ONE=0x3ff0000000000000


def model(encoded):
    negative=encoded<ONE
    a=((ONE-encoded)<<13) if negative else ((encoded-ONE)<<14)
    assert 0<a<=1<<55
    bit=a.bit_length()-1;q=a<<(62-bit)
    z=a*a>>66
    ar=(a+(1<<23))>>24
    quarter=z*ar>>44
    zr=(z+(1<<18))>>19
    fourth=zr*zr>>28
    fifth=fourth*ar>>42
    even=z//3+fourth//5
    odd=(a>>1)+quarter+fifth//6
    deviation=odd+even if negative else odd-even
    # Positive magnitude uses RN-half-up; negative magnitude uses3/4 bias,
    # centering the known downward coefficient-floor errors without extra bits.
    high=q*deviation>>64
    correction=(high+2+int(negative))>>2
    result=q+correction if negative else q-correction
    return result,bit,int(negative)


def prove():
    p=1<<66;t=F(1,1<<11);a=t*p;z=a*a/p;delta=F(1<<23)
    cube_lower=t+z*delta/p+delta/p;cube_upper=z*delta/p
    dz=F((1<<18)+1)
    fourth_error=(2*z*dz+dz*dz)/p
    fourth_max=t**4*p
    fifth_error=(1+fourth_error)*t+(fourth_max+1+fourth_error)*delta/p
    tail=t**6/(7*(1-t))*p
    poslo=-2-cube_upper/4-fourth_error/5-fifth_error/6-tail
    poshi=2+cube_lower/4+fourth_error/5+fifth_error/6
    neglo=-4-cube_lower/4-fourth_error/5-fifth_error/6-tail
    neghi=cube_upper/4+fourth_error/5+fifth_error/6
    bounds=dict(positive=[poslo/8-F(1,2),poshi/8+F(1,2)],
                negative=[neglo/8-F(1,4),neghi/8+F(3,4)])
    maximum=max(abs(v) for row in bounds.values() for v in row)
    assert maximum<1
    for rem in range(4099):assert rem*0xaaab>>17==rem//3
    for value in range((1<<22)+1):
        hi=value>>16
        q=hi*13107+((((value&65535)+hi)*52429)>>18)
        assert q==value//5
    for value in range(2049):assert value*0xaaab>>18==value//6
    return dict(status='PASS',maximum_abs_t='2^-11',factor_precision=66,
        relative_precision=62,output_precision_base=128,error=1,
        rational_output_error_upper_bound=str(maximum),
        centered_output_bounds={k:list(map(str,row)) for k,row in bounds.items()},
        cube_perturbation_bound=str(cube_lower),fourth_perturbation_bound=str(fourth_error),
        fifth_perturbation_bound=str(fifth_error),series_tail_bound=str(tail),
        exact_division_cases=dict(third_residual=4099,fifth=(1<<22)+1,sixth=2049),
        product_construction='Input normalized difference has low21 zero bits. Two16-bit products construct each low-limb cross term exactly; high64 plus offset2/3 then shift2 implements the stated biased product rounding. u<2^11 and deviation.high<2^23, so the cross requires34 bits and is explicitly represented in64 bits.',
        source_sha256={'src/ln_checked.c':hashlib.sha256((ROOT/'src/ln_checked.c').read_bytes()).hexdigest()},
        scope='All-input near-domain error certificate. Exact ARM integer seed, interval packing and MPFR are qualified separately; final Q245 all-domain totality remains unproved.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--json',type=Path,required=True)
    args=p.parse_args();r=prove();args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(r,indent=2)+'\n');print('PASS: near66 relative ln error <1 Q62 unit')
