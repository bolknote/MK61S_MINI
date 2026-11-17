#!/usr/bin/env python3
"""Check the range, enclosure and work bounds for the pow power products."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]

def uniform_precision_bound(ln2_lower, ln2_upper, max_k):
    """Specialize Laurent's real two-logarithm bound using exact rationals.

    This is a sufficient precision for the enclosure argument. It does not
    assert that any binary64 pair needs that precision, or that the firmware
    supports the corresponding allocation.
    """
    # A reduced binary64 base has numerator and denominator at most 2^1074.
    # A rounding midpoint can also be 2^-1075. Inverting a rational leaves
    # its logarithmic height unchanged. Thus log(A_i)=746 is admissible
    # in Laurent's Corollary 2, with D=1, for either inverted base.
    log_height = 746
    assert 1075*ln2_upper < log_height

    # After the exponent cutoffs, p+q <= 2^116+2^53-1. For q=1 the
    # separate p<2^63 bound is smaller. Laurent's b' is (p+q)/746.
    terms = (1 << max_k)+(1 << 53)-1
    assert (1 << 63)+1 < terms
    log_terms_upper = max_k*ln2_upper+F((1 << 53)-1, 1 << max_k)
    # 746=2^9*(373/256); ln(373/256)>2*(117/629).
    log_height_lower = 9*ln2_lower+F(234, 629)
    assert 512*373 == 746*256
    normalized_coefficient_log_upper = log_terms_upper-log_height_lower+F(19, 50)
    h = 75
    assert max(F(30), F(1), normalized_coefficient_log_upper) < h

    # Laurent, Corollary 2, Table 1, m=30 and C2=17.9, gives
    # ln|Lambda| >= -17.9*h^2*746^2 for independent bases. Dividing
    # Lambda by q<=2^116 gives the log gap used by PowerBounds::side.
    loss_nats = F(179, 10)*h*h*log_height*log_height
    gap_bits = int(loss_nats/ln2_lower)+max_k+1
    assert gap_bits*ln2_lower > loss_nats+max_k*ln2_upper

    # An undecided comparison at precision P has gap <2^(66-P).
    # At P>=gap_bits+66 that contradicts the nonzero gap above. Round
    # upward to whole 16-bit limbs. This also covers the dependent
    # gap and exact-tie precision established by the main certificate.
    assert 4*((1 << 63)-(1 << 10)+1) < 1 << 65
    precision = ((gap_bits+66+15)//16)*16
    assert precision-66 >= gap_bits > 170
    significand_bytes = (precision+7)//8
    assert significand_bytes > 264*1024
    return dict(
        source='https://www.impan.pl/shop/en/publication/transaction/download/product/82485',
        theorem='Corollary 2, D=1, m=30, C2=17.9',
        rational_height_log_upper=log_height,
        normalized_coefficient_log_plus_038_upper=str(normalized_coefficient_log_upper),
        rounded_coefficient_log_upper=h,
        logarithmic_form_loss_nats=str(loss_nats),
        nonzero_abs_log_gap_strict_lower_bound=f'2^-{gap_bits}',
        enclosure_error_overhead_bits=66,
        sufficient_enclosure_precision_bits=precision,
        one_significand_bytes_at_sufficient_precision=significand_bytes,
        supported_firmware_precision_bits=8192,
        practical_uniform_latency_established=False,
        scope='A sufficient mathematical precision derived from a cited theorem; '
              'the firmware does not allocate it and no input is proved to need it. '
              'A practical uniform bound still requires a stronger whole-domain '
              'separation proof or another bounded exact comparison algorithm.')


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
    radix = 1 << 16
    assert (radix-1)**2+2*(radix-1) < 1 << 32
    # Doubling each off-diagonal digit, adding a diagonal digit and
    # propagating the carry needs at most two carry units per word.
    assert (3*(radix-1)+2)//radix == 2
    # The biased half-square sum minus the difference square is at most
    # two carry units. The reconstructed cross term needs at most one
    # digit beyond the two half-squares, hence the final carry is 0 or 1.
    assert 2*(radix-1)+radix-1+2 < 3*radix
    assert 2 < radix

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
    leaf_words = 16
    largest_work = {}
    for length in (words,2*words):
        # The dense case splits down to 16-word squares. Each leaf uses
        # one multiply for each diagonal or unordered off-diagonal pair.
        leaf_count = 3**((length//leaf_words).bit_length()-1)
        square_work = leaf_count*leaf_words*(leaf_words+1)//2
        largest_work[16*length] = max(
            62*square_work+length**2+62*4*length,
            (52+max_k)*square_work+length**2+52*4*length)
    assert largest_work == {4096:1969472,8192:5920704}
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
    contents = source.read_text()
    assert 'PowerBounds<256>::side' in contents and f'SquareLeafWords={leaf_words}' in contents
    return dict(status='PASS_POWER_PRODUCT_ENCLOSURE',
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        active_domain='positive finite binary64 x, 2^-64 <= |y| < 2^63, one adjacent rounding boundary',
        maximum_denominator_shift=max_k,maximum_product_leaves=terms,
        significand_bits=16*words,minimum_signed_scale_bits=128,
        maximum_full_products=52+max_k+1,
        maximum_limb_multiply_accumulates=largest_work[4096],
        maximum_8192_limb_multiply_accumulates=largest_work[8192],
        relative_width_bound='2^-3976',
        undecided_abs_log_gap_strict_upper_bound='2^-4030',
        undecided_8192_abs_log_gap_strict_upper_bound='2^-8126',
        dependent_nonzero_abs_log_gap_lower_bound='2^-170',
        exact_midpoint_products_significand_bits_upper_bound=54*32,
        uniform_precision_bound=uniform_precision_bound(lo, hi, max_k),
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
