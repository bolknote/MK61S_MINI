#!/usr/bin/env python3
"""Check the dyadic root comparator against exact powers and directed MPFR."""

import argparse
from collections import Counter
from fractions import Fraction
from hashlib import sha256
from itertools import product
import json
from math import gcd
from multiprocessing import Pool
from pathlib import Path
from random import Random
import sys
import unittest

from m0_mpfr_oracle import Oracle, bits, real

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'research/m0-pow-comparison-20261117'))
import radical_compare as candidate
from modular_log_compare import INF, Y_MIN, Y_MAX, operands


MAX_Q = 1 << 116
REVERSE_WITNESS = 0x000ffffffffffffd, 0x3bf720d7d1140d05, 0x3fefffffffffffff
MIDPOINTS = (
    (0x000fffffffffffff, 0x3bffffffffffffff, 0x3ff0000000000000),
    (0x000fffffffffffff, 0xbbffffffffffffff, 0x3ff0000000000000),
    (0x7fd0000000000001, 0x3ff0040201008043, 0x7fe00000000007f5),
    (0x3fefffffffffffff, 0x43d6ffffffffffff, 0x0000000000001215),
    (0x3fefffffffffffff, 0xc3dfffffffffffff, 0x7fefffffffffffff),
    (0x0f1234687b59d4f7, 0x3c3101a6c819d38d, 0x3feffffffffffffb),
    (bits(2.), bits(-1075.), 0),
    (bits(2.), bits(1024.), INF-1),
    REVERSE_WITNESS,
)


def as_fraction(value):
    return Fraction(value.coefficient) * Fraction(2)**value.scale


def direct_side(x, y, lower):
    exponent = Fraction(real(y))
    upper = Fraction(1 << 1024) if lower == INF-1 else Fraction(real(lower+1))
    midpoint = (Fraction(real(lower)) + upper) / 2
    return candidate.order(Fraction(real(x))**exponent.numerator-midpoint**exponent.denominator)


class RadicalCompare(unittest.TestCase):
    def test_exact_products_and_midpoints(self):
        bases = (0.75, 1., 1.25, 3., 0.5, 1.5, real(1), real(INF-1))
        exponents = (-3., -1.5, -0.5, 0.03125, 0.5, 1., 1.125, 2., 3.25)
        boundaries = (0, bits(0.75), bits(1.)-1, bits(1.), bits(3.), INF-1)
        for x, y, lower in product(map(bits, bases), map(bits, exponents), boundaries):
            want = direct_side(x, y, lower)
            if want == 0:
                want = 1 if lower & 1 else -1
            self.assertEqual(candidate.side(x, y, lower, 192), want, (x,y,lower))

    def test_exact_ties_both_parities(self):
        for x, y in ((3., 34.), (7., 19.), (2., -1075.)):
            power = Fraction(x)**int(y)
            lower = bits(float(power))
            if Fraction(real(lower)) > power:
                lower -= 1
            self.assertEqual(direct_side(bits(x), bits(y), lower), 0)
            self.assertEqual(candidate.side(bits(x), bits(y), lower, 64), 1 if lower & 1 else -1)

    def test_root_with_product_and_dropped_bit(self):
        for precision in (64, 67, 128):
            rng = Random(precision)
            grid = 1 << (precision-1)
            for _ in range(256):
                a, b = (candidate.Dyadic(rng.randrange(grid, 2*grid), rng.randrange(-200, 200))
                        for _ in range(2))
                for factor in (None, b):
                    exact = as_fraction(a) * (as_fraction(factor) if factor else 1)
                    low, high = tuple(as_fraction(candidate.Directed(precision, upper).root(a, factor))
                                      for upper in (False, True))
                    self.assertLessEqual(low**2, exact)
                    self.assertLessEqual(exact, high**2)
                    if low != high:
                        self.assertLessEqual(high-low, low/grid)

    def test_sum_across_exponent_gaps(self):
        for offset in (0, 1, 63, 64, 65, 500):
            a = candidate.Dyadic((1 << 64)-1, 72)
            b = candidate.Dyadic((1 << 64)-1, 72-offset)
            total = as_fraction(a)+as_fraction(b)
            lo = as_fraction(candidate.Directed(64, False).add(a, b))
            hi = as_fraction(candidate.Directed(64, True).add(a, b))
            self.assertLessEqual(lo, total)
            self.assertLessEqual(total, hi)

    def test_constant_margin_and_work_limits(self):
        rho = Fraction(1, 1 << 63)
        # Elementary upper bound for ln(2) from 2*atanh(1/3).
        ln2_hi = sum(Fraction(2, (2*i+1)*3**(2*i+1)) for i in range(8)) + Fraction(9, 4*3**17)
        self.assertLess(1075*ln2_hi, 746)
        self.assertLess((1+rho)**229, 1+230*rho)
        self.assertGreater(747*(1-230*rho)-10*rho, 746)
        self.assertLess(230*747+10, 1 << 18)
        self.assertEqual(candidate.work((1 << 63)-1024, 1), dict(roots=0, products=114, sums=167))
        self.assertEqual(candidate.work((1 << 53)-1, MAX_Q), dict(roots=116, products=169, sums=0))
        for k in range(1, 117):
            counts = candidate.work((1 << 53)-1, 1 << k)
            self.assertLessEqual(counts['roots'], 116)
            self.assertLessEqual(counts['products'], 169)
            self.assertLessEqual(counts['sums'], 167)

    def test_refusal_is_distinct_from_a_tie(self):
        difficult = MIDPOINTS[5]
        self.assertEqual(candidate.side(*difficult, 64), 0)
        self.assertEqual(candidate.exact_side(*difficult), (-1, 256))

    def test_reverse_width_witness(self):
        a, ae, b, be, p, q = operands(*REVERSE_WITNESS)
        self.assertEqual((a, ae, b, be, q), ((1 << 52)-3, -1074, (1 << 54)-1, -54, MAX_Q))
        self.assertEqual(gcd(a, b), 1)
        self.assertLess(p, q >> 16)
        # The first 16 inverse steps only square the midpoint. Neither the
        # coarsest bounds [x, 1] nor removal of powers of two can prune it.
        self.assertGreater(Fraction(1)-Fraction(1 << 16, 1 << 54), Fraction(1, 2))
        self.assertLess(Fraction(a)*Fraction(2)**ae, Fraction(1, 2))
        self.assertGreater((b.bit_length()-1)*(1 << 16), 264*1024*8)
        self.assertEqual(candidate.side(*REVERSE_WITNESS, 256), -1)


def verify_target(oracle, x, y, result, lower, precision):
    want = 1 if result > lower else -1
    got = candidate.side(x, y, lower, precision)
    if got and got != want:
        raise AssertionError(tuple(map(hex,(x,y,lower))) + (precision,got,want,oracle.version))
    return got == 0


def parse_power_token(token):
    token = token.strip().lower()
    if token in ('snan', '+snan', '-snan'):
        return INF+1
    return bits(float.fromhex(token) if '0x' in token else float(token))


def active_pairs(corpus):
    with corpus.open() as source:
        for raw_line in source:
            line = raw_line.split('#', 1)[0].strip()
            if not line:
                continue
            x, y = map(parse_power_token,line.split(','))
            sign = x >> 63
            x &= (1 << 63)-1
            ym = y & ((1 << 63)-1)
            if not (0 < x < INF and Y_MIN <= ym < Y_MAX):
                yield None
                continue
            if sign and not real(y).is_integer():
                yield None
                continue
            yield x, y


def batches(pairs, size, precision):
    batch = []
    for pair in pairs:
        batch.append(pair)
        if len(batch) == size:
            yield batch, precision
            batch = []
    if batch:
        yield batch, precision


def verify_batch(argument):
    pairs, precision = argument
    oracle = Oracle()
    count = Counter(pairs=len(pairs))
    for pair in pairs:
        if pair is None:
            continue
        x, y = pair
        answer = oracle.reference('pow', x, y)
        count['active'] += 1
        for lower in (answer - 1, answer):
            if 0 <= lower < INF:
                count['comparisons'] += 1
                count['undecided'] += verify_target(oracle, x, y, answer, lower, precision)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--precision', type=int, default=256)
    args = parser.parse_args()
    if not args.corpus:
        unittest.main(argv=[sys.argv[0]])
        return

    oracle = Oracle()
    targeted = []
    for x, y, lower in MIDPOINTS:
        result = oracle.reference('pow', x, y)
        undecided = verify_target(oracle, x, y, result, lower, args.precision)
        *_, p, q = operands(x, y, lower)
        targeted.append(dict(point=[f'{value:016x}' for value in (x,y,lower)],
                             undecided=undecided, work=candidate.work(p, q)))
    count = Counter()
    with Pool(args.workers) as pool:
        for run in pool.imap_unordered(verify_batch, batches(active_pairs(args.corpus), 8192, args.precision)):
            count.update(run)
    print(json.dumps(dict(corpus_sha256=sha256(args.corpus.read_bytes()).hexdigest(),
                          mpfr=oracle.version, precision=args.precision,
                          **count, targeted=targeted), indent=2))


if __name__ == '__main__':
    main()
