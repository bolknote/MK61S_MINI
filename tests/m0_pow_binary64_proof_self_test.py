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
import midpoint_scale_grid as scale_grid


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
    def test_x87_double_rounding_witness(self):
        x, y, lower = 0x3fe1d06cac4007f7, 0x3fb2999bb0510100, 0x3feeaaae1482004e
        precision = 256
        xl, xh = proof.log_point(x, precision, False)
        ml, mh = proof.log_point(lower, precision, True)
        exponent = real(y)
        gap_lo = (exponent*xl-mh)/(1 << precision)
        gap_hi = (exponent*xh-ml)/(1 << precision)
        self.assertGreater(gap_lo, Fraction(1, 1 << 116))
        self.assertLess(gap_hi, Fraction(1, 1 << 115))
        self.assertEqual(lower & 1, 0)
        self.assertEqual(real(lower, True).denominator, 1 << 54)
        # The midpoint is in [1/2,1) and exactly representable at p=64.
        # exp(gap)-1 < 2*gap, so rounding at p=64 lands at that midpoint.
        self.assertLess(2*gap_hi, Fraction(1, 1 << 65))

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

    def test_mixed_width_boundary_uses_actual_alignment(self):
        inside = single(1+2.0**-52, 2000, 363 << 52, inverse=True)
        outside = single(1+2.0**-52, 2000, 362 << 52, inverse=True)
        self.assertGreater(proof.powers_width(inside)[0], 104713)
        self.assertEqual(proof.mixed_width(inside, proof.powers_width(inside)), 88415)
        self.assertEqual(proof.mixed_width(outside, proof.powers_width(outside)), 88416)
        self.assertEqual(proof.check_leaf(inside, ['mixed-residue'], True), 'mixed-residue')
        for box, mixed in ((inside, False), (outside, True)):
            with self.assertRaises(proof.InvalidProof):
                proof.check_leaf(box, ['mixed-residue'], mixed)

    def test_mixed_width_covers_non_singleton_base_and_boundary(self):
        x, y, lower = bits(1+2.0**-52), bits(1975), bits(1.5)
        large = proof.Box((x,x+32), (y,y+1), (lower,lower+32), False)
        self.assertGreater(proof.powers_width(large)[0], proof.RESIDUE_BITS+proof.GAP)
        self.assertEqual(proof.check_leaf(large, ['mixed-residue'], True), 'mixed-residue')
        for i in range(32):
            for j in range(32):
                point = proof.Box((x+i,x+i+1), large.y, (lower+j,lower+j+1), False)
                self.assertLessEqual(proof.mixed_width(point, proof.powers_width(point)),
                                     proof.mixed_width(large, proof.powers_width(large)))

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

    def test_scale_grid_maps_binades_and_subnormals(self):
        x = bits(3.125)
        m = bits(5.25)
        generic = proof.Box((x,x+8), (proof.Y_MIN,proof.Y_MAX), (m,m+8), False)
        expected = ((0x19000000000000,0x19000000000008),
                    (0x2a000000000001,0x2a000000000010))
        for x_delta, m_delta, negative in ((0,0,False), (-1022,1020,True), (790,-700,True)):
            xs, ms = x+(x_delta << 52), m+(m_delta << 52)
            box = proof.Box((xs,xs+8), generic.y, (ms,ms+8), negative)
            self.assertEqual(proof.scale_grid_spans(box, 128), expected)
            self.assertEqual(proof.check_leaf(box, ['scale-grid',512]), 'scale-grid')
        self.assertEqual(proof.significand_span((3,4)), (3 << 51, (3 << 51)+1))
        self.assertEqual(proof.significand_span((2,3), midpoint=True), (5 << 51, (5 << 51)+1))
        self.assertIsNone(proof.significand_span((3,5)))
        self.assertIsNone(proof.significand_span((1,3), midpoint=True))
        tie = single(2, 1075, 0, inverse=True)
        self.assertEqual(proof.check_leaf(tie, ['scale-grid',512]), 'scale-grid')
        self.assertEqual(proof.analyze((generic,False,False,())), ['scale-grid',512])

    def test_scale_grid_floor_count(self):
        rng = Random(97)
        for _ in range(2048):
            modulus = rng.randrange(1,257)
            count = rng.randrange(128)
            step, start = (rng.randrange(-1024,1025) for _ in range(2))
            radius = rng.randrange((modulus+1)//2)
            terms = [start+i*step for i in range(count)]
            self.assertEqual(scale_grid.floor_sum(count,modulus,step,start),
                             sum(z//modulus for z in terms))
            self.assertEqual(scale_grid.near_count(count,modulus,step,start,radius),
                             sum((z+radius) % modulus <= 2*radius for z in terms))

    def test_scale_grid_exact_normalized_equalities_and_incomplete_block(self):
        for a, b, count in ((1,1,2*scale_grid.P_LIMIT-1), (3,1,1), (1,3,0),
                            (81,27,1), (25,625,1), (27,81,0), (3,5,0)):
            a <<= 53-a.bit_length()
            b <<= 54-b.bit_length()
            self.assertEqual(scale_grid.normalized_equalities(a,b), count)
            x_check = scale_grid.BaseCheck(a,512)
            self.assertEqual(x_check.separated(b,scale_grid.log2_approx(b,1<<53,512))[1], 0)
        low_precision = scale_grid.check_block(0x19000000000000,0x19000000000001,
                                              0x2a000000000000,0x2a000000000001,182,1)
        self.assertEqual(low_precision['status'], 'INCOMPLETE_BLOCK')
        self.assertGreater(low_precision['first_open'][2], 0)


class PartitionTest(unittest.TestCase):
    def test_small_layers_scope_and_search_handoff(self):
        root = proof.roots()[0]
        _, above_q116 = root.split('y',proof.Y_NEXT)
        inside, above_q115 = above_q116.split('y',proof.Y_AFTER_Q115)
        self.assertEqual(proof.choose_split(above_q116,('q115',)),('y',proof.Y_AFTER_Q115))
        self.assertEqual(proof.analyze((inside,True,False,('q115',))),['q115'])
        counts, first = proof.verify_partition(stream(['q115']), (inside,))
        self.assertEqual(counts,{'q115':1})
        self.assertIsNone(first)
        for outside in (root,above_q116,above_q115):
            with self.assertRaisesRegex(proof.InvalidProof,'outside'):
                proof.check_leaf(outside,['q115'])
        _, _, after_q114 = proof.BAND_RANGES['q114']
        q114, _ = above_q115.split('y',after_q114)
        self.assertEqual(proof.analyze((q114,True,False,('q115','q114'))),['q114'])
        with self.assertRaisesRegex(proof.InvalidProof,'outside'):
            proof.check_leaf(inside,['q114'])
        with self.assertRaisesRegex(proof.InvalidProof,'original archive directory'):
            proof.verify_band('q115',None,1,False)

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

    def test_close_frontier_keeps_the_original_partition(self):
        box = proof.Box((bits(1.25), bits(1.5)), (bits(1.5), bits(1.75)),
                        (bits(0.5), bits(2)), False)
        split = ['split', 'm', f'{bits(1.25):016x}']
        previous = stream(split, ['open'], ['open'])
        result = StringIO()
        report = proof.close_frontier(previous, result, (box,), False)
        self.assertEqual(report['visited'], 2)
        self.assertEqual(report['newly_closed'], {'gap': 1})
        self.assertEqual(report['open_boxes'], 1)
        result.seek(0)
        self.assertEqual(json.loads(result.readline()), [proof.SCHEMA])
        self.assertEqual(json.loads(result.readline()), split)
        result.seek(0)
        counts, first = proof.verify_partition(result, (box,))
        self.assertEqual(counts, {'gap': 1, 'open': 1})
        self.assertEqual(first['m'][0], split[-1])

    def test_mixed_schema_has_separate_verification(self):
        source, mixed = StringIO(), StringIO()
        proof.search(source, 20, 60, True)
        proof.search(mixed, 20, 60, True, previous=StringIO(source.getvalue()), mixed=True)
        with self.assertRaises(proof.InvalidProof):
            proof.verify_partition(StringIO(mixed.getvalue()), proof.roots())
        counts, first = proof.verify_partition(StringIO(mixed.getvalue()), proof.roots(), True)
        self.assertIsNotNone(first)
        self.assertGreater(counts['open'], 0)
        proof.check_model(mixed=True)

    def test_listed_boundaries_are_not_a_full_partition(self):
        result = proof.verify_listed_boundaries(StringIO('4000000000000000 c090cc0000000000 '
                                                         '0000000000000000\n'), True)
        self.assertEqual(result['status'], 'PASS_LISTED_BOUNDARIES')
        self.assertEqual(result['counts'], {'powers': 1})
        with self.assertRaises(proof.InvalidProof):
            proof.verify_listed_boundaries(StringIO('3ff0000000000000 3ff0000000000000 '
                                                   '0000000000000000\n'), True)

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
