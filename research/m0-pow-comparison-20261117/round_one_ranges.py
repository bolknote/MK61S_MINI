#!/usr/bin/env python3
"""Certify ranges rounding to one for every exponent significand."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from small_exponents import (FixedInterval, MAX_EXPONENT, MIN_EXPONENT, ROOT,
                             core_rounding_gap)

ONE = 0x3FF0000000000000
MAXIMUM = 0x7FEFFFFFFFFFFFFF


def absolute_log_upper(encoding, grid, log_two):
    field, mantissa = divmod(encoding, 1 << 52)
    if field:
        exponent, scale = field-1023, 1 << 52
        mantissa += scale
    else:
        bits = mantissa.bit_length()-1
        exponent, scale = bits-1074, 1 << bits
    low, high = grid.log(mantissa, scale)
    units = -exponent*log_two[1]-low if exponent < 0 else exponent*log_two[1]+high
    return Fraction(units, grid.unit)


def endpoints(limit, grid, log_two):
    # Move out from one until the bound exceeds the allowed log magnitude.
    # Checking the endpoints suffices by monotonicity of the exact abs(log).
    result = []
    for direction, extent in [(-1, ONE-1), (1, MAXIMUM-ONE)]:
        low, high = 0, extent+1
        while high-low > 1:
            middle = (low+high)//2
            if absolute_log_upper(ONE+direction*middle, grid, log_two) < limit:
                low = middle
            else:
                high = middle
        encoding = ONE+direction*low
        assert absolute_log_upper(encoding, grid, log_two) < limit
        result.append(encoding)
    return tuple(result)


def certify():
    grid = FixedInterval(256)
    log_two = grid.log(2, 1)
    below, above = ((1 << 54, (1 << 54)-1), ((1 << 53)+1, 1 << 53))
    gap = Fraction(1, 1 << 117)
    assert Fraction(1, (1 << 52)+1) > Fraction(1, 1 << 53)
    core = core_rounding_gap(117)
    covered = 0
    rows = {}
    for exponent in range(MIN_EXPONENT, MAX_EXPONENT+1):
        maximum_magnitude = ((1 << 53)-1)*Fraction(2)**(exponent-52)
        pair_count_per_magnitude = 2  # x=1 for both signs of y.
        signs = {}
        for label, numerator_denominator in [('decreases', below), ('increases', above)]:
            target = Fraction(grid.log(*numerator_denominator)[0], grid.unit)
            first, last = endpoints((target-gap)/maximum_magnitude, grid, log_two)
            signs[label] = dict(first=f'{first:016x}', last=f'{last:016x}')
            pair_count_per_magnitude += last-first
        covered += pair_count_per_magnitude*(1 << 52)
        rows[str(exponent)] = signs
    total = MAXIMUM*(MAX_EXPONENT-MIN_EXPONENT+1)*(1 << 53)
    assert 0 < covered <= total
    paths = (
        Path(__file__), Path(__file__).with_name('small_exponents.py'),
        Path(__file__).with_name('midpoint_grid.py'), ROOT/'third_party/core_math/pow/pow.c',
    )
    return dict(status='PASS_ROUND_TO_ONE_RANGES', exponent_binades=[MIN_EXPONENT, MAX_EXPONENT],
                exponent_significand_bits=53, paired_inputs_covered=covered,
                paired_inputs_in_ten_exponent_binades=total, certified_base_ranges=rows,
                applies_with_sign='Use decreases when y*log(x)<0 and increases when y*log(x)>0. '
                                  'Both ranges include x=1, which returns 1 directly.',
                absolute_log_gap_strict_lower_bound_for_x_other_than_one='2^-117',
                core_math_256_bit_rounding=core,
                source_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in paths})


def main():
    assert __debug__, 'Keep Python assertions enabled'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = certify()
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(report['status'], report['paired_inputs_covered'], 'pairs', flush=True)


if __name__ == '__main__':
    main()
