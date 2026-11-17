#!/usr/bin/env python3
"""Check the range, enclosure and work bounds for the pow power products."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]

def certify():
    # For finite nonzero x, abs(log(x)) < 745. The rational series verifies
    # both log(2) cutoffs used by the existing fixed-point pow interval.
    lo = sum((F(2, (2*i+1)*3**(2*i+1)) for i in range(40)), F(0))
    hi = lo+F(9, 4*81*3**81)
    assert 1074*hi < 745 and 1075*hi < 1024
    assert F(745, 1 << 64) < F(1, 1 << 54)
    tiny = F(745, 1 << 64)
    assert tiny/(1-tiny) < F(1, 1 << 53)
    assert F(1, (1 << 52)+1) > F(1,1 << 53)
    assert struct.unpack('<Q',struct.pack('<d',2.**-64))[0] == 0x3BF0000000000000
    assert struct.unpack('<Q',struct.pack('<d',2.**63))[0] == 0x43E0000000000000

    # The exponent field for a binary64 value at or above 2^-64
    # provides at least -116 after removing its 52 fraction bits.
    max_k = 64+52
    max_fraction_p = (1 << 53)-1
    max_integer_p = (1 << 63)-1
    terms = (1 << max_k)+max_fraction_p
    assert terms > max_integer_p+1
    assert 1075*terms+3 < 1 << 127
    assert 65535**2+2*65535 < 1 << 32

    # Truncating one normalized multiplication loses strictly less than
    # delta=2^(1-P) relative. The exact expression, with each square
    # expanded as two subexpressions, has terms leaves and terms-1
    # products. Bernoulli bounds the total loss by z=(terms-1)*delta.
    # Since z<1/2, 1/(1-z) <= 1+2z. For S < 2^P, 2*z*S < 4*(terms-1).
    # The renormalizing ceil can add at most one unit of the old scale.
    addition = 4*(terms-1)
    assert addition+1 < 1 << 119
    for precision in (128,256,4096):
        delta = F(1,1 << (precision-1))
        loss = (terms-1)*delta
        assert 0 < loss < F(1,2)
        assert F(1,1-loss) <= 1+2*loss
        assert addition < 1 << (precision-2)

    words = 4096//16
    largest_work = max(
        (62+1)*words**2+62*4*words,
        (52+max_k+1)*words**2+52*4*words)
    assert largest_work == 11128832
    assert F(addition+1,1 << (16*words-1)) < F(1,1 << 3976)
    source = ROOT/'code/native_eabi_m0_pow_power_bounds.inc'
    assert 'PowerBounds<256>::side' in source.read_text()
    return dict(status='PASS_POWER_PRODUCT_ENCLOSURE',
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        active_domain='positive finite binary64 x, 2^-64 <= |y| < 2^63, one adjacent rounding boundary',
        maximum_denominator_shift=max_k,maximum_product_leaves=terms,
        significand_bits=16*words,minimum_signed_scale_bits=128,
        maximum_full_products=52+max_k+1,
        maximum_limb_multiply_accumulates=largest_work,
        relative_width_bound='2^-3976',
        scope='The result is certified whenever the intervals decide; the bound does not prove they separate for every input.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',type=Path,required=True)
    args = parser.parse_args()
    report = certify()
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'], report['relative_width_bound'])

if __name__=='__main__':
    main()
