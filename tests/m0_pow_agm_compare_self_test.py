#!/usr/bin/env python3
"""Check directed AGM midpoint decisions against exact powers and MPFR."""

import argparse
from collections import Counter
from fractions import Fraction
from hashlib import sha256
from itertools import product
import json
from multiprocessing import Pool
from pathlib import Path
import sys
import unittest

from m0_mpfr_oracle import Oracle, bits, real
from m0_pow_radical_compare_self_test import MIDPOINTS, active_pairs, batches, direct_side

# The shared corpus harness adds the prototype directory to sys.path.
import agm_compare as agm
from midpoint_grid import FixedInterval
from modular_log_compare import INF


def check(oracle, x, y, result, lower, precision):
    expected = 1 if result > lower else -1
    actual = agm.side(x, y, lower, precision)
    if actual and actual != expected:
        raise AssertionError((tuple(map(hex, (x, y, lower))), precision, actual, expected, oracle.version))
    return actual == 0


def verify_batch(batch):
    pairs, precision = batch
    oracle = Oracle()
    count = Counter(pairs=len(pairs))
    for pair in pairs:
        if pair is None:
            continue
        x, y = pair
        result = oracle.reference('pow', x, y)
        count['active'] += 1
        for lower in (result-1, result):
            if 0 <= lower < INF:
                count['comparisons'] += 1
                count['undecided'] += check(oracle, x, y, result, lower, precision)
    return count


class AgmCompare(unittest.TestCase):
    def test_exact_powers_and_midpoints(self):
        bases = (0.75, 1., 1.25, 3., 0.5, 1.5, real(1), real(INF-1))
        powers = (-3., -1.5, -0.5, 0.03125, 0.5, 1., 1.125, 2., 3.25)
        thresholds = (0, bits(0.75), bits(1.)-1, bits(1.), bits(3.), INF-1)
        for x, y, lower in product(map(bits, bases), map(bits, powers), thresholds):
            want = direct_side(x, y, lower) or (1 if lower & 1 else -1)
            self.assertEqual(agm.side(x, y, lower, 192), want, (x, y, lower))

    def test_ties_and_refinement(self):
        for x, y in ((3., 34), (7., 19), (2., -1075)):
            exact = Fraction(x)**y
            lower = bits(float(exact))
            if Fraction(real(lower)) > exact:
                lower -= 1
            self.assertEqual(direct_side(bits(x), bits(float(y)), lower), 0)
            self.assertEqual(agm.side(bits(x), bits(float(y)), lower, 64), 1 if lower & 1 else -1)
        point = MIDPOINTS[5]
        self.assertEqual(agm.side(*point, 64), 0)
        self.assertEqual(agm.exact_side(*point), (-1, 256))

    def test_elliptic_enclosure(self):
        # Machin's identity, with the omitted alternating tails bounded by
        # the first omitted positive term. This oracle never uses AGM.
        def atan(reciprocal, terms):
            lo = sum((Fraction((-1)**k, (2*k+1)*reciprocal**(2*k+1)) for k in range(terms)), Fraction())
            return lo, lo+Fraction(1, (2*terms+1)*reciprocal**(2*terms+1))

        for precision in (64, 65, 192, 511):
            low5, high5 = atan(5, 2*((precision+24)//4+1))
            low239, high239 = atan(239, 2*((precision+24)//16+1))
            pi_lo, pi_hi = 16*low5-4*high239, 16*high5-4*low239
            params = agm.settings(precision)
            grid = FixedInterval(precision+48)
            logarithm_two = grid.log(2, 1)
            for num, den in ((1, 1), (2, 1), (1001, 1000), (1023, 512), ((1 << 54)-1, 1 << 53)):
                lo, hi = agm.scaled_log(num, den, precision, params)
                true_lo, true_hi = (Fraction((params[0]+2)*g+h, grid.unit)
                                    for g, h in zip(logarithm_two, grid.log(num, den)))
                self.assertLessEqual(Fraction(lo, 1 << precision), 2*true_lo/pi_hi)
                self.assertLessEqual(2*true_hi/pi_lo, Fraction(hi, 1 << precision))

    def test_budget_and_mpfr_extremes(self):
        self.assertEqual([exponent for exponent, _ in agm.separation_by_exponent()],
                         list(range(-64, 63)))
        budget = agm.uniform_work()
        self.assertEqual(budget['gap_bits'], 568469355)
        self.assertEqual(budget['worst_y_binade_exponent'], 0)
        self.assertEqual(budget['bytes_per_significand'], 71058685)
        self.assertEqual(budget['maximum_square_roots_per_pass'], 236)
        self.assertEqual(budget['maximum_square_roots_all_passes'], 3692)
        self.assertFalse(budget['practical_rp2040_bound_established'])
        oracle = Oracle()
        for x, y, lower in MIDPOINTS:
            self.assertFalse(check(oracle, x, y, oracle.reference('pow', x, y), lower, 192))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--precision', type=int, default=192)
    args = parser.parse_args()
    if not args.corpus:
        unittest.main(argv=[sys.argv[0]])
        return
    count = Counter()
    with Pool(args.workers) as pool:
        for result in pool.imap_unordered(verify_batch, batches(active_pairs(args.corpus), 8192, args.precision)):
            count.update(result)
    print(json.dumps(dict(corpus_sha256=sha256(args.corpus.read_bytes()).hexdigest(),
                          mpfr=Oracle().version, precision=args.precision, **count), indent=2))


if __name__ == '__main__':
    main()
