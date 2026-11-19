#!/usr/bin/env python3
"""Replay the arithmetic obligations and reject invalid pow witnesses."""

from fractions import Fraction
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'dev/tools'))
import certify_m0_pow_laurent_limit as limit


class LaurentLimitTest(unittest.TestCase):
    def test_current_target_and_edge(self):
        result = limit.certify()
        self.assertEqual(result['firmware_gap_bits'], 16300)
        self.assertEqual(result['status'], 'RULED_OUT_AT_TARGET')
        self.assertEqual(result['theorem_loss_nats_strictly_above'], '71438')
        edge = result['excluded_gap_bits_through']
        self.assertEqual(edge, 103063)
        self.assertEqual(limit.certify(edge)['status'], 'RULED_OUT_AT_TARGET')
        self.assertEqual(limit.certify(edge+1)['status'], 'INCONCLUSIVE_AT_TARGET')
        self.assertGreater(result['unchanged_bases_excluded_through'], 8_000_000)

    def test_mu_partition_is_outward(self):
        bound = limit.check_mu(256)
        self.assertGreater(bound, Fraction(4, 5))
        for mu in (Fraction(1, 3), Fraction(5, 8), Fraction(13, 20), Fraction(1)):
            self.assertLessEqual(bound, mu/limit.sigma(mu)**4)
        with self.assertRaises(ValueError):
            limit.check_mu(0)

    def test_adjacent_midpoint_and_wrong_encodings(self):
        witness = limit.check_witness()
        self.assertEqual(witness['rounded_encoding'], '7fe00000000007f5')
        self.assertEqual(witness['actual_witness_gap_at_least'], '2^-57')
        self.assertEqual(witness['actual_witness_gap_below'], '2^-56')
        for kwargs in (dict(x=limit.X-1), dict(y=limit.Y-1),
                       dict(lower=limit.MIDPOINT_LOWER+1), dict(lower=limit.MIDPOINT_LOWER-1)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                limit.check_witness(**kwargs)


if __name__ == '__main__':
    unittest.main()
