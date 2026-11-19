#!/usr/bin/env python3
"""Tests for the full-domain proof checker, including rejection of coverage holes."""

from fractions import Fraction
from io import StringIO
import json
from pathlib import Path
from random import Random
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT/'dev/tools'
sys.path.insert(0, str(TOOLS))
import verify_m0_pow_binary64 as proof


def bits(value):
    return struct.unpack('>Q', struct.pack('>d', value))[0]


def real(encoding, midpoint=False):
    return proof.dyadic_scale(1, proof.dyadic(encoding, midpoint))


def stream(*rows):
    return StringIO(''.join(json.dumps(row)+'\n' for row in ([proof.SCHEMA], *rows)))


def single(x, magnitude, lower, inverse=False):
    x, magnitude = bits(x), bits(magnitude)
    return proof.Box((x, x+1), (magnitude, magnitude+1), (lower, lower+1), inverse)


class ArithmeticTest(unittest.TestCase):
    def test_exact_midpoints_at_all_transitions(self):
        for field in range(1, 2048):
            lower = (field << 52)-1
            upper = real(lower+1) if lower+1 < proof.INF else Fraction(1 << 1024)
            self.assertEqual(real(lower, True), (real(lower)+upper)/2)
        self.assertEqual(real(0, True), Fraction(1, 1 << 1075))

    def test_directed_binary64_ceil(self):
        rng = Random(2040)
        transitions = {field << 52 for field in range(1, 2047)}
        transitions.update(rng.randrange(1, proof.INF-1) for _ in range(2048))
        transitions.update((0, 1, proof.INF-2, proof.INF-1))
        for lower in transitions:
            self.assertEqual(proof.ceil_binary64(real(lower)), lower)
            self.assertEqual(proof.ceil_binary64(real(lower, True)), lower+1)
        self.assertEqual(proof.ceil_binary64(Fraction(1 << 1024)), proof.INF)

    def test_grid_across_multiple_y_binades(self):
        # 1+log2(1+2^-53) is strictly between 1 and nextabove(1):
        # a continuous interval check on y alone cannot help.
        lower = bits(2.0)
        for x, inverse in ((2.0, False), (0.5, True)):
            x_bits = bits(x)
            box = proof.Box((x_bits, x_bits+1), (bits(0.5), bits(2.0)), (lower, lower+1), inverse)
            logs = proof.enclosures(box, 128)
            self.assertFalse(proof.excludes_gap(box, 128, logs))
            self.assertTrue(proof.excludes_y_grid(box, 128, logs))

    def test_exact_tie_and_wide_residue(self):
        # pow(2,-1075) is the exact tie between zero and minsubnormal.
        tie = single(2, 1075, 0, inverse=True)
        logs = proof.enclosures(tie, 128)
        self.assertFalse(proof.excludes_gap(tie, 128, logs))
        self.assertFalse(proof.excludes_y_grid(tie, 128, logs))
        self.assertEqual(proof.check_leaf(tie, ['powers']), 'powers')
        # Nontrivial odd parts and a sufficiently long, bounded p.
        bounded = single(1.25, 1000, bits(4.0))
        self.assertEqual(proof.check_leaf(bounded, ['residue']), 'residue')
        unbounded = single(1.25, 1.0+2.0**-52, bits(4.0))
        for kind in ('powers', 'residue'):
            with self.assertRaises(proof.InvalidProof):
                proof.check_leaf(unbounded, [kind])

    def test_affine_integer_exclusion_and_rejected_tie(self):
        x, m = bits(3.125), bits(5.25)
        box = proof.Box((x, x+128), (bits(1), bits(2)), (m, m+128), False)
        logs = proof.enclosures(box, 192)
        self.assertFalse(proof.excludes_y_grid(box, 192, logs))
        row = proof.try_affine(box)
        self.assertIsNotNone(row)
        self.assertEqual(proof.check_leaf(box, row), 'affine')
        with self.assertRaises(proof.InvalidProof):
            proof.check_leaf(box, ['affine', 192, 1, 0, 0])
        tie = single(2, 1075, 0, inverse=True)
        for d in range(1, 33):
            self.assertFalse(proof.affine_excludes(proof.affine_geometry(tie, 192), d, 0, 0))

    def test_origin_theorem_edges(self):
        lo, hi = proof.ONE-(1 << 30), proof.ONE+(1 << 29)+1
        box = proof.Box((lo, proof.ONE), (proof.Y_MIN, bits(16)+1), (0, proof.INF), True)
        self.assertEqual(proof.check_leaf(box, ['origin']), 'origin')
        for outside in (proof.Box((lo-1, lo), box.y, box.m, True),
                        proof.Box((hi, hi+1), box.y, box.m, True),
                        proof.Box(box.x, (bits(16)+1, bits(16)+2), box.m, True)):
            with self.assertRaises(proof.InvalidProof):
                proof.check_leaf(outside, ['origin'])


class PartitionTest(unittest.TestCase):
    def test_fixed_roots(self):
        domain = proof.roots()
        self.assertEqual([(b.negative_y, b.x) for b in domain], [
            (False, (1, proof.ONE)), (False, (proof.ONE+1, proof.INF)),
            (True, (1, proof.ONE)), (True, (proof.ONE+1, proof.INF)),
        ])
        self.assertTrue(all(b.y == (proof.Y_MIN, proof.Y_MAX) and b.m == (0, proof.INF) for b in domain))

    def test_split_requires_both_children_and_no_tail(self):
        full = single(2, 1, proof.ONE-1)
        box = proof.Box(full.x, full.y, (proof.ONE-1, proof.ONE+1), full.negative_y)
        split = ['split', 'm', f'{proof.ONE:016x}']
        counts, first = proof.verify_partition(stream(split, ['powers'], ['gap', 128]), (box,))
        self.assertIsNone(first)
        self.assertEqual(counts, {'powers': 1, 'gap': 1})
        for rows in ((split, ['powers']), (['gap', 128], ['powers']),
                     (['split', 'm', f'{proof.ONE-1:016x}'], ['powers'], ['powers'])):
            with self.assertRaises(proof.InvalidProof):
                proof.verify_partition(stream(*rows), (box,))

    def test_full_search_and_resume(self):
        first, continued, fresh = StringIO(), StringIO(), StringIO()
        proof.search(first, 200, 60, True)
        proof.search(continued, 200, 60, True, previous=StringIO(first.getvalue()))
        proof.search(fresh, 400, 60, True)
        # The resume continues the pending breadth-first queue without rewriting
        # or silently discarding any of the previously checked subtrees.
        self.assertEqual(continued.getvalue(), fresh.getvalue())
        counts, missing = proof.verify_partition(StringIO(continued.getvalue()), proof.roots())
        self.assertIsNotNone(missing)
        self.assertGreater(counts['open'], 0)

    def test_cli_distinguishes_incomplete_and_out_of_scope(self):
        def run(path):
            return subprocess.run([sys.executable, '-B', str(TOOLS/'verify_m0_pow_binary64.py'),
                                   'verify', str(path)], capture_output=True, text=True)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'proof.jsonl'
            partial = stream(*([['split', 'y', f'{proof.Y_NEXT:016x}'], ['q116'], ['open']]*4))
            path.write_text(partial.getvalue())
            result = run(path)
            self.assertEqual(result.returncode, 2, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['status'], 'INCOMPLETE')
            self.assertEqual(report['leaf_counts'], {'open': 4, 'q116': 4})
            compressed = path.with_suffix('.jsonl.gz')
            with proof.open_proof(compressed, 'x') as output:
                output.write(partial.getvalue())
            self.assertEqual(run(compressed).stdout, result.stdout)
            path.write_text(stream(*([['q116']]*4)).getvalue())
            result = run(path)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn('outside', result.stderr)
            path.write_text(json.dumps({'verified_blocks': 156610112, 'pilot': False})+'\n')
            result = run(path)
            self.assertEqual(result.returncode, 1, result.stdout)


if __name__ == '__main__':
    unittest.main()
