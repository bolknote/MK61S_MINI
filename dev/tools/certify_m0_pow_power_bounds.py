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
    for precision in (128,256,4096,8192):
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
    delta = F(1,1 << (16*words-1))
    assert (addition+1)*delta < F(1,1 << 3976)

    # If the lower endpoints agree, or the smaller upper endpoint reaches
    # the larger lower endpoint, the two closed enclosures overlap. For
    # true values A and B this gives both ratios <= (1+eps_a)*(1+eps_b),
    # with eps_i <= (4*(n_i-1)+1)*delta including the renormalizing ceil.
    # ln(1+eps) <= eps, so the absolute log gap divided by q is strictly
    # below 4*(p/q+1)*delta. The inverse case uses one product with p+q
    # leaves and an exact one, giving the same bound.
    last_y_bits = 0x43DFFFFFFFFFFFFF
    last_y = int(struct.unpack('<d', struct.pack('<Q',last_y_bits))[0])
    assert last_y == (1 << 63)-(1 << 10)
    failure_log_gap = F(1,1 << 4030)
    assert 4*(last_y+1)*delta < failure_log_gap
    final_failure_log_gap = F(1,1 << 8126)
    assert 4*(last_y+1)*F(1,1 << 8191) < final_failure_log_gap

    # For dependent dyadic bases, the primitive integer valuation vector
    # represents a dyadic g with odd coefficient below 2^54, up to inversion.
    # If 1/2 <= g <= 2 and g != 1, the numerator and denominator are at most
    # 2^54, so |ln(g)| >= |g-1|/max(1,g) >= 2^-54. Outside that range use ln(2).
    # For x=g^i, m=g^j, a nonzero |(sign(y)*p*i-q*j)/q| is at least 1/q.
    min_primitive_log = F(1,1 << 54)
    assert lo > min_primitive_log
    dependent_log_gap = min_primitive_log/(1 << max_k)
    assert failure_log_gap < dependent_log_gap == F(1,1 << 170)

    # At a positive exact midpoint tie with a nontrivial odd coefficient,
    # the reduced p and q require x's odd coefficient to be C^q and the
    # midpoint's to be C^p, for odd C >= 3. Thus q <= 32 and both exact
    # power products have fewer than 54*q significant bits. An inverse
    # tie requires both coefficients to be one, as does any other tie
    # with a trivial odd coefficient. Normalization preserves powers of two.
    assert 3**64 > (1 << 53) and 3**35 > (1 << 54)
    assert 54*32 < 16*words
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
        undecided_abs_log_gap_strict_upper_bound='2^-4030',
        undecided_8192_abs_log_gap_strict_upper_bound='2^-8126',
        dependent_nonzero_abs_log_gap_lower_bound='2^-170',
        exact_midpoint_products_significand_bits_upper_bound=54*32,
        scope='For a valid adjacent midpoint, only multiplicatively independent bases with a nonzero cancelling log gap can remain undecided.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',type=Path,required=True)
    args = parser.parse_args()
    report = certify()
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'], report['relative_width_bound'])

if __name__=='__main__':
    main()
