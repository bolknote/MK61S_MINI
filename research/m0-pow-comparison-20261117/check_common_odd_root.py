#!/usr/bin/env python3
"""Independently check the common-odd-root minimum and count the normal pairs."""

from fractions import Fraction
from hashlib import sha256
import json
from math import gcd
from pathlib import Path

from midpoint_scale_grid import logarithm_grid, near_count


def floor_root(n, degree):
    lo, hi = 0, 1 << ((n.bit_length()+degree-1)//degree)
    while hi-lo > 1:
        mid = (lo+hi)//2
        if mid**degree <= n:
            lo = mid
        else:
            hi = mid
    return lo


def normal_pairs():
    total = 0
    for degree in range(2, 35):
        first = floor_root((1 << 53)-1, degree)+1
        last = floor_root((1 << 54)-1, degree)
        totient = sum(gcd(i, degree) == 1 for i in range(1, degree))
        total += totient*((last+1)//2-first//2)
    return total


def main():
    root = Path(__file__).resolve().parent
    report = json.loads((root/'common-odd-root-20261119.json').read_text())
    assert report['verifier_source_sha256'] == sha256((root/'certify_common_odd_root.cpp').read_bytes()).hexdigest()
    assert report['status'] == 'PASS_COMMON_ODD_ROOT'
    assert report['first'] == 3 and report['stop'] == (1 << 27)+1
    assert report['roots_checked'] == (report['stop']-report['first'])//2
    assert report['coefficient_bits'] == 122 and report['grid_bits'] == 320
    assert 3**33 < 1 << 53 < 3**34 < 1 << 54 < 3**35
    assert 33*((1 << 63)-1)+34*(1 << 116) < 1 << 122

    base = report['least_root']
    precision = report['grid_bits']
    grid, ln2 = logarithm_grid(precision)
    assert Fraction(ln2[0], grid.unit) > Fraction(1, 2)
    guard = grid.precision-precision
    lo, hi = grid.divide(grid.log(base, 1 << (base.bit_length()-1)), ln2)
    lo, hi = lo >> guard, -(-hi >> guard)
    assert 0 <= hi-lo <= 2
    unit, cap = 1 << precision, (1 << report['coefficient_bits'])-1
    q = int(report['convergent_denominator'])
    assert 1 <= q <= cap
    residue = q*lo % unit
    distance = min(residue, unit-residue)
    assert distance-(hi-lo)*cap == int(report['min_grid_units'])
    # This count uses Euclidean floor sums, not the convergent-denominator search.
    assert near_count(cap, unit, lo, lo, distance-1) == 0
    assert near_count(cap, unit, lo, lo, distance) == 1
    assert report['strict_log_gap_bits'] == precision+118-int(report['min_grid_units']).bit_length()
    assert report['strict_log_gap_bits'] < 433
    print(f"PASS_MINIMUM_REPLAY {normal_pairs()} normal pairs, gap > 2^-{report['strict_log_gap_bits']}")


if __name__ == '__main__':
    if not __debug__:
        raise RuntimeError('enable Python assertions')
    main()
