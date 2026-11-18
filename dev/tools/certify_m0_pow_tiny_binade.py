#!/usr/bin/env python3
"""Certify the binary64 pow shortcut for 2^-64 <= abs(y) < 2^-63."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research/m0-pow-comparison-20261117'))
from midpoint_grid import FixedInterval, add, ceil_div

HIDDEN = 1 << 52
FIRST = 0x3BF0000000000000
ONE = 0x3FF0000000000000
MAXIMUM = 0x7FEFFFFFFFFFFFFF
GRID = FixedInterval(256)
LN2 = GRID.log(2, 1)
TARGET = GRID.scale(GRID.log(1 << 54, (1 << 54)-1), 1 << 116)


def absolute_log(bits):
    exponent, significand = divmod(bits, HIDDEN)
    if exponent:
        exponent -= 1023
        scale = HIDDEN
        significand += HIDDEN
    else:
        lead = significand.bit_length()-1
        exponent = lead-1074
        scale = 1 << lead
    value = add(GRID.scale(LN2, exponent), GRID.log(significand, scale))
    return GRID.scale(value, -1 if bits < ONE else 1)


def first_past(denominator):
    """Return the first integer that makes n*denominator exceed TARGET."""
    below = TARGET[0]//denominator[1]
    assert below == TARGET[1]//denominator[0]
    assert below*denominator[1] < TARGET[0] <= TARGET[1] < (below+1)*denominator[0]
    return below+1


def base_limits():
    def inside(bits):
        lo, hi = GRID.scale(absolute_log(bits), 2*HIDDEN-1)
        if hi < TARGET[0]:
            return True
        assert lo > TARGET[1]
        return False

    def first_outside(sign, extent):
        low, high = 0, extent
        assert inside(ONE) and not inside(ONE+sign*high)
        while high-low > 1:
            center = (low+high)//2
            if inside(ONE+sign*center):
                low = center
            else:
                high = center
        return ONE+sign*low

    return first_outside(-1, ONE-1), first_outside(1, MAXIMUM-ONE)


def proof():
    assert not FIRST & (HIDDEN-1)
    ln_limit = GRID.scale(LN2, 1074)[1]
    assert absolute_log(MAXIMUM)[1] < ln_limit < 745*GRID.unit
    first_above_one = GRID.log((1 << 53)+1, 1 << 53)[0]
    second_below_one = GRID.log(1 << 54, (1 << 54)-3)[0]
    # The only possible rounding boundary is 1-2^-54. Above one,
    # there is no boundary. Below one, the second midpoint is out of range.
    assert ln_limit < (min(first_above_one, second_below_one) << 63)
    assert ln_limit < (GRID.log(1 << 54, (1 << 54)-1)[0] << 64)

    positive = first_past(absolute_log(1))
    negative = first_past(absolute_log(MAXIMUM))
    assert HIDDEN < positive < negative < 2*HIDDEN
    first_base, last_base = base_limits()
    # The remaining normal bases take the absolute Q94 log path, well
    # outside the separate relative-log path used near one.
    assert first_base < 0x3FEFFFE000000000 < 0x3FF0001000000000 < last_base
    power_of_two = first_past(LN2)
    assert 0 < power_of_two < (1 << 64) and 1074*(2*HIDDEN-1) < (1 << 64)

    # If j <= abs(log2(x)) <= j+1, n*j >= K or n*(j+1) < K decides
    # from the two endpoints, where K is power_of_two. The remaining
    # j is floor((K-1)/n). For fixed signed y there is at most one
    # such base binade in the decreasing direction, with <= HIDDEN
    # encodings. The two universal ranges remove more y before this test.
    pairs = MAXIMUM*2*HIDDEN
    possible_q94_pairs = HIDDEN*(4*HIDDEN-positive-negative)
    assert possible_q94_pairs*10000 < 3*pairs

    # For a subnormal of coefficient M, scale it to the normal integer
    # 2*M. It ranges from 2 to 2^53-2, so its own log is always in Q94.
    assert 2*(HIDDEN-1) < (1 << 53)
    lo, hi = GRID.scale(LN2, 1075)
    offset = lo >> (GRID.precision-94)
    assert hi >> (GRID.precision-94) == offset
    normal_error, subnormal_error = 128+ceil_div(1023,2), 128+ceil_div(52,2)+1
    assert 745*(1 << 94)+max(normal_error, subnormal_error) < (1 << 104)

    # The argument product is shifted by 53, so its integer represents
    # abs(y*ln(x)) in units of 2^-157. Rounding and the log cause less
    # than error+1 unit of loss. The midpoint floor loses <1 more.
    h = Fraction(1,1 << 54)
    threshold = (h+h*h/2)*(1 << 157)
    assert threshold == (1 << 103)+(1 << 48)
    assert h**3*(1 << 157)/(3*(1-h)) < 1

    # If the Q94 comparison declines, then the true log argument is
    # within (E+2) + (E+1) + 1 Q157 units of the midpoint log. Adjacent
    # positive finite x increase by at least x*2^-53, so their log gap
    # is >2^-54. Multiplication by abs(y)>=2^-64 yields >2^39 Q157
    # units. There can be at most one fallback base for each signed y.
    guard_distance = 2*max(normal_error, subnormal_error)+4
    spacing = Fraction(1,1 << 53)
    assert spacing/(1+spacing) > Fraction(1,1 << 54)
    assert 2*guard_distance < 1 << (157-118)
    # The exponent denominator after reduction is >=2^64. The
    # 2-adic valuation of a finite positive x is in [-1074,1023].
    # In an exact tie the denominator must divide this valuation,
    # making it zero, whereas the midpoint has valuation -54.
    minimum_denominator = 1 << (116-52)
    assert minimum_denominator > 1074

    return dict(status='PASS_LOWEST_POW_BINADE',
                exponent_encodings=[f'{FIRST:016x}',f'{FIRST+HIDDEN-1:016x}'],
                number_with_universal_one={'positive':positive-HIDDEN,'negative':negative-HIDDEN},
                first_exponents_that_can_round_below_one={
                    'positive':f'{FIRST+positive-HIDDEN:016x}',
                    'negative_magnitude':f'{FIRST+negative-HIDDEN:016x}'},
                base_range_rounding_to_one=[f'{first_base:016x}', f'{last_base:016x}'],
                power_of_two_threshold=power_of_two, subnormal_log_offset_q94=f'{offset:026x}',
                positive_finite_base_and_signed_exponent_pairs=pairs,
                maximum_pairs_requiring_q94=possible_q94_pairs,
                minimum_pairs_decided_without_log=pairs-possible_q94_pairs,
                maximum_q94_guard_distance_q157=guard_distance,
                maximum_possible_fallback_bases_per_signed_exponent=1,
                ties_at_midpoint_possible=False,
                midpoint_threshold_q157=f'{int(threshold):027x}',
                maximum_log_error_q94={'normal':normal_error,'subnormal':subnormal_error},
                rounding_ambiguity_requires_existing_rescue=True)


def header(info):
    first, last = info['base_range_rounding_to_one']
    offset = int(info['subnormal_log_offset_q94'],16)
    midpoint = int(info['midpoint_threshold_q157'],16)
    cuts = info['first_exponents_that_can_round_below_one']
    return ('// Generated by dev/tools/certify_m0_pow_tiny_binade.py.\n'
            '#pragma once\n\nnamespace m0_pow_tiny_binade {\n'
            f'constexpr uint64_t FirstPositive = UINT64_C(0x{cuts["positive"]});\n'
            f'constexpr uint64_t FirstNegative = UINT64_C(0x{cuts["negative_magnitude"]});\n'
            f'constexpr uint64_t FirstBase = UINT64_C(0x{first});\n'
            f'constexpr uint64_t LastBase = UINT64_C(0x{last});\n'
            f'constexpr uint64_t PowerOfTwo = UINT64_C(0x{info["power_of_two_threshold"]:016x});\n'
            f'constexpr uint64_t LogOffsetHigh = UINT64_C(0x{offset>>64:016x});\n'
            f'constexpr uint64_t LogOffsetLow = UINT64_C(0x{offset&((1<<64)-1):016x});\n'
            f'constexpr uint64_t MidpointHigh = UINT64_C(0x{midpoint>>64:016x});\n'
            f'constexpr uint64_t MidpointLow = UINT64_C(0x{midpoint&((1<<64)-1):016x});\n'
            '}\n')


def main():
    if not __debug__:
        raise RuntimeError('Enable Python assertions to verify the certificate')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--header', type=Path, help='write a copy of the generated header')
    args = parser.parse_args()
    info = proof()
    rendered = header(info)
    if args.header:
        args.header.write_text(rendered)
    sources = ('code/native_eabi_m0_pow_tiny_binade_constants.inc',
               'code/native_eabi_m0_pow_fast.inc', 'dev/tools/certify_m0_pow_fast.py',
               'dev/tools/certify_m0_pow_tiny_binade.py',
               'research/m0-pow-comparison-20261117/midpoint_grid.py')
    assert (ROOT/sources[0]).read_text() == rendered
    info['source_sha256'] = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources}
    args.json.write_text(json.dumps(info,indent=2)+'\n')
    print(info['status'], info['number_with_universal_one'])


if __name__ == '__main__':
    main()
