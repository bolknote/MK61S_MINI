#!/usr/bin/env python3
"""Rational propagation bounds for the M0 log10 Q70 and Q94 passes."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

from generate_m0_log10_constants import bounds, constants, render, ROOT
from generate_m0_log70_table import certificate as log70_certificate
from certify_m0_ln_refine import certificate as log94_certificate


def certificate():
    lo, hi = bounds()
    assert 2 < lo < hi < 3
    c = constants()
    for precision, value in c.items():
        assert F(value, 1 << precision) < 1/hi < 1/lo < F(value+1, 1 << precision)
    raw70 = log70_certificate()
    raw94 = log94_certificate()
    hmain = F(1, 2048)
    # Scaling only the residual avoids quantizing k*ln2 and the center log.
    # The complete ln bound is deliberately retained, including its old
    # table rounding, then the new base10 table contributes another1/2.
    residual_quantization = F(1, 8)/(1-hmain)+F(16, 1 << 62)
    direct = F(16, 2)+F(5, 2)+residual_quantization+F(1, 2)
    assert direct < 12

    # math62_product's missing low product is in [0,4). Bit29 of
    # the cross word selects compensation 2 or3, leaving <=2.5 units.
    product62 = F(5, 2)
    assert 2-F(1, 2)-4 == -product62
    assert 3-F(1, 2) == product62
    square62 = 1+F(1, 1 << 12)
    errors62 = []
    for e, limit in ((35, 4), (20, 8), (14, 32)):
        h = F(1, 1 << e)
        if e == 35:
            error = product62 + 2*(1 << 62)*h*h/(3*(1-h))
        else:
            third = square62/3+F(1, 3)  # nearest integer z/3
            quarter = F(9, 8)+h*square62/4
            error = product62+2*(third+(quarter if e == 14 else 0))
            error += 2*(1 << 62)*h**(4 if e == 14 else 3)/((5 if e == 14 else 4)*(1-h))
        assert error < limit
        errors62.append(dict(maximum_delta=str(h),error=str(error),enclosure=limit))

    # For positive magnitude L=(high*2^64+low), scaling by the floored
    # Q64 constant costs <high+1 units. exp_high_product omits <3 units.
    max_raw_error = 16+(1023+1)//2
    max_high = 710*64
    max_fast_enclosure = (max_raw_error+1)//2+max_high+4
    assert max_fast_enclosure < 1 << 16

    # Relative Q94 refinement keeps |x-1|<=2^-16. Its quadratic term
    # fits a uint64, including the discarded square bits.
    h = F(1, 1 << 16)
    assert (1 << 94)*h*h < 1 << 64
    cube = 3+h
    fourth = 3+h*cube
    third = 3+F(1, 3)+(1 << 30)*h*h
    quarter = 1+cube/4
    fifth = 3+fourth/5+(1 << 30)*h**4
    factor = third+quarter+fifth
    # Normalize by at most2, then multiply by C<1/2. Constant-floor and
    # exact-product floor errors fit in the remaining allowance.
    relative_roundings = (2*factor+1)/2+3+2*h
    assert relative_roundings < 32
    assert 1/(1-h) < 1+F(1, 8192)
    # The per-input omitted-series bound is ceil(2^(5*(top+1)-216)/3),
    # with the above geometric correction. Both normalization and the
    # reciprocal multiply are covered (the latter only shrinks it).

    # General Q94 result is divided by1024 before its Q94 multiply.
    # |ln(x)|<710 on normal positive binary64; normalized magnitude<1.
    max_refine_error = 128+(1023+1)//2
    postscale = (F(max_refine_error, 1024)+1)/2+1+1
    assert postscale < (max_refine_error+2047)//2048+3
    return dict(status='PASS',log70=raw70,log94=raw94,near_one_q62=errors62,
                direct_q70_error=str(direct),direct_q70_enclosure=12,
                direct_q70_exponent_error='abs(k)/2',direct_table_bytes=16384,
                maximum_fast_q70_enclosure=max_fast_enclosure,
                relative_q94_rounding_error=str(relative_roundings),relative_q94_base_enclosure=32,
                general_q94_scaling_error=str(postscale),general_q94_enclosure=4,
                scope='Exact rational constants, reused log enclosures, integer product omissions and series tails. Every fast result still requires an entire enclosure inside one binary64 RNE cell; undecided cases use CORE-MATH. Not a machine-checked proof of the C++ implementation.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--json', type=Path, required=True)
    args = p.parse_args()
    assert (ROOT/'code/native_eabi_m0_log10_constants.inc').read_text() == render()
    from generate_m0_log10_table import render as render_table
    assert (ROOT/'code/native_eabi_m0_log10_table.inc').read_text() == render_table()
    result = certificate()
    result['source_sha256'] = {name: hashlib.sha256((ROOT/'code'/name).read_bytes()).hexdigest()
                               for name in ('native_eabi_m0_log10.inc','native_eabi_m0_log10_constants.inc','native_eabi_m0_log10_table.inc')}
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2)+'\n')
    print('PASS: Q70/Q94 log10 scaling and near-one bounds')


if __name__ == '__main__':
    main()
