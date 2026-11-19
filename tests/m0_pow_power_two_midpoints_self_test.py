#!/usr/bin/env python3
"""Check dyadic midpoint domains and reject incomplete proof coverage."""

from fractions import Fraction
import gzip
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'research/m0-pow-comparison-20261117'))
import power_two_midpoints as proof


class PowerTwoMidpoints(unittest.TestCase):
    def test_last_midpoint_of_the_left_half(self):
        limit = proof.midpoint_limit(1, 64)
        self.assertLess(proof.coefficient(1, limit-1)**2, 2*proof.D**2)
        self.assertGreater(proof.coefficient(1, limit)**2, 2*proof.D**2)
        self.assertEqual(list(proof.spans(64, 64)), [(1, 64, proof.midpoint_limit(1,65), limit)])

    def test_nested_midpoints_and_out_of_range_both_signs(self):
        for side in (-1, 1):
            end = 0
            for sign, k, first, stop in proof.spans(65):
                if sign != side:
                    continue
                self.assertEqual(first, end)
                end = stop
                offset = Fraction(2*stop+1, proof.D*(2 if side < 0 else 1))
                cutoff = Fraction(proof.ln2(160)[1]*1074*(proof.D-1),1<<(160+k))+Fraction(1,1<<proof.GAP)
                if side > 0:
                    cutoff /= 1-cutoff
                self.assertGreater(offset, cutoff)
            self.assertEqual(end, proof.midpoint_limit(side, 65))

    def test_direct_proof_leaves(self):
        for side in (-1, 1):
            proof.verify_block(side, 89, 0, 16, None)
            with self.assertRaises(ValueError):
                proof.verify_block(side, 89, 0, 17, None)

    def test_nonintegral_polynomial_and_forged_constant(self):
        record = [2, 5, 320, 0, 378194, [[1, 0], [0, 1]], [[0, 1, 0, 0, 0, 0]]]
        proof.verify_block(1, 70, 0, 2, record)
        record[-1] = [[1, 0, 0, 0, 0, 0]]
        with self.assertRaises(ValueError):
            proof.verify_block(1, 70, 0, 2, record)

    def test_reject_gaps_overlap_repeated_leaves_and_wrong_grid(self):
        row = [1, 81, 0, 4, None]
        tail = [1, 81, 4, 8, None]
        with TemporaryDirectory() as tmp, patch.object(proof, 'spans', return_value=[(1, 81, 0, 8)]):
            path = Path(tmp)/'proof.gz'

            def save(rows):
                with gzip.open(path, 'wt') as stream:
                    print(json.dumps([proof.SCHEMA, 81, 81]), file=stream)
                    for record in rows:
                        print(json.dumps(record), file=stream)

            save([row, tail])
            self.assertEqual(list(proof.read_proof(path)), [row, tail])
            for invalid in ([row], [tail], [row, row], [row, tail, row], [row, [1, 80, 4, 8, None]]):
                save(invalid)
                with self.assertRaises(ValueError):
                    list(proof.read_proof(path))


if __name__ == '__main__':
    unittest.main()
