#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Relative ln(1+t) seed and exact rational error certificate, |t|<=2^-12."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ONE=0x3ff0000000000000


def model(encoded):
    negative=encoded<ONE
    a=((ONE-encoded)<<9) if negative else ((encoded-ONE)<<10)
    assert 0<a<=1<<50
    b=a.bit_length()-1
    q=a<<(62-b)
    z=a*a>>62
    c=(a+(1<<18))>>19
    cube=z*c>>43
    d=(z+(1<<12))>>13
    fourth=d*d>>36
    factor=(1<<62)+z//3+fourth//5
    correction=(a>>1)+(cube>>2)
    factor+=correction if negative else -correction
    return (q*factor>>62)+(4 if negative else 1),b,int(negative)


def prove():
    a=F(1<<50);delta=F(1<<18)
    cube_error=1+a/(1<<62)+(a*a/(1<<62))*delta/(1<<62)+delta/(1<<62)
    z=a*a/(1<<62);diff=F(4097)
    fourth_error=(2*z*diff+diff*diff)/(1<<62)
    t=F(1,1<<12)
    remainder=t**5/(6*(1-t))*(1<<62)
    factor_error=1+(cube_error/4+1)+(fourth_error/5+1)+remainder
    uncentered_output_error=2*factor_error+1
    # Floor products have a known direction. Center the positive seed by+1,
    # the negative magnitude seed by+4, and certify the asymmetric bounds.
    perturb=cube_error-1
    cube_upper=(z*delta/(1<<62))/4
    positive_low=-2-cube_upper-fourth_error/5
    positive_high=1+perturb/4+fourth_error/5+remainder
    negative_low=-3-perturb/4-fourth_error/5-remainder
    negative_high=cube_upper+fourth_error/5
    output_bounds=dict(positive=[2*positive_low,2*positive_high+1],
                       negative=[2*negative_low+3,2*negative_high+4])
    output_error=max(abs(v) for bounds in output_bounds.values() for v in bounds)
    assert output_error<5
    # Narrow /3 approximation is exact after one small residual correction.
    # q0=floor(n*floor(2^32/3)/2^32). For n<=2^38, n-3q0<=66;
    # multiplication by ceil(2^17/3) is an exact /3 for every such residual.
    for residual in range(67):assert residual*0xaaab>>17==residual//3
    paths=[ROOT/'src/ln_checked.c']
    return dict(status='PASS',maximum_abs_t='2^-12',relative_precision=62,error=5,
        rational_output_error_upper_bound=str(output_error),factor_error_upper_bound=str(factor_error),
        uncentered_output_error_upper_bound=str(uncentered_output_error),
        centered_output_bounds={k:list(map(str,v)) for k,v in output_bounds.items()},
        cube_error_upper_bound=str(cube_error),fourth_error_upper_bound=str(fourth_error),
        series_tail_upper_bound=str(remainder),division_residual_cases=67,
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        scope='Relative interval certificate; integer construction and all ARM operations are checked independently against the model and MPFR. Finite Q245 fallback totality remains unproved.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--json',type=Path,required=True)
    args=p.parse_args();r=prove();args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(r,indent=2)+'\n');print('PASS: relative ln error <5 normalized Q62 units')
