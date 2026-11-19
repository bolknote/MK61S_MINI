#!/usr/bin/env python3
"""Check CRT carries and direct comparisons of integer powers for pow."""

from fractions import Fraction
from itertools import product
from math import factorial, gcd, prod
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'research/m0-pow-comparison-20261117'))
import modular_log_compare as proof


def bits(value):
    return struct.unpack('>Q', struct.pack('>d', value))[0]


def real(encoding):
    return Fraction(struct.unpack('>d', struct.pack('>Q', encoding))[0])


def direct(x, y, lower):
    exponent = real(y)
    midpoint = (real(lower)+real(lower+1))/2
    delta = real(x)**exponent.numerator-midpoint**exponent.denominator
    return proof.order(delta) or (1 if lower & 1 else -1)


class ModularLogCompare(unittest.TestCase):
    def test_signed_crt_all_representatives(self):
        mods = (8, 9, 5, 7)
        modulus = prod(mods)
        factors = [(m, pow(modulus//m, -1, m)) for m in mods]
        used_multiple_blocks = False
        for integer in range(1-modulus//2, modulus//2):
            def fractions():
                return ((m, inv*integer % m) for m, inv in factors)

            sign, blocks = proof.crt_sign(fractions, len(mods), 16)
            self.assertEqual(sign, proof.order(integer), integer)
            used_multiple_blocks |= blocks > 1
        self.assertTrue(used_multiple_blocks)

    def test_rational_enclosures_mod_prime_powers(self):
        forms = (proof.LogForm(16, (8, 7, 3), (-22, 11, 7)),
                 proof.LogForm(32, (16, 16, 1), (0, 1 << 100, -(1 << 102))))
        for form, terms in product(forms, (1, 5, 19)):
            scale = form.base**terms * factorial(terms)
            total = sum(c*sum(Fraction(a, form.base)**j/j for j in range(1, terms+1))
                        for a, c in zip(form.numerators, form.coefficients))
            numerator = scale*total
            radius = scale*form.error_factor // (1 << terms)
            self.assertEqual(numerator.denominator, 1)
            for modulus in (2, 3, 7, 9, 121, 1024, 65537):
                self.assertEqual(proof.enclosure_residues(form, terms, modulus),
                                 ((int(numerator)-radius) % modulus, (int(numerator)+radius) % modulus))

    def test_cancellation_with_unequal_multiplicities(self):
        for a, b, p, q in product((1, 3, 9, 15, 25, 63, 75), repeat=4):
            left, right, splits, removed = proof.common_factors((a, p), (b, q))
            common = gcd(a**p, b**q)
            self.assertEqual(prod(f**e for f, e in left), a**p//common)
            self.assertEqual(prod(f**e for f, e in right), b**q//common)
            self.assertLessEqual(splits, 67)
            self.assertGreaterEqual(common, 1 << removed)

    def test_side_on_small_integer_products(self):
        for x, y, lower in product((0.75, 1.0, 1.25, 3.0),
                                   (-2.25, -0.5, 0.5, 2.0), (0.75, 1., 1.25, 3.0)):
            triple = tuple(map(bits, (x,y,lower)))
            want = direct(*triple)
            self.assertEqual(proof.cancelled_powers(*triple, 8192)[0], want)
            self.assertEqual(proof.compare(*triple, 64, cache=True)[0], want)

    def test_uncached_and_exact_ties(self):
        for x, y, lower in ((0.75, -0.5, bits(1.0625)), (1.25, 0.5, bits(1.5)),
                            (2., -1075., 0), (3., 34., bits(float(3**34)))):
            triple = bits(x), bits(y), lower
            self.assertEqual(proof.compare(*triple, 12)[0], direct(*triple))

    def test_large_reduced_powers_and_coprime_control(self):
        a = (1 << 27)-1
        x = bits(a/(1 << 27))
        lower = (1022 << 52) + (a*a-1)//2 - (1 << 52)
        for y, want in ((2-2.**-52, 1), (2., -1), (2+2.**-51, -1)):
            side, stats = proof.cancelled_powers(x, bits(y), lower, 88_415)
            self.assertEqual(side, want)
            if y != 2:
                self.assertGreater(stats['original_integer_width'], 1 << 56)
            self.assertLessEqual(stats['cancelled_integer_width'], 28)
        control = 0x7fd0000000000001, 0x3ff0040201008043, 0x7fe00000000007f5
        side, stats = proof.cancelled_powers(*control, 88_415)
        self.assertEqual(side, 0)
        self.assertEqual(stats['gcd_splits'], 0)

    def test_uniform_small_word_bound(self):
        work = proof.uniform_work()
        self.assertEqual(work['terms'], 80_840_269_504)
        self.assertEqual(work['modulus_limit'], 1 << 44)
        self.assertLessEqual(work['fixed_width_operation_bound_bits'], 154)


if __name__ == '__main__':
    unittest.main()
