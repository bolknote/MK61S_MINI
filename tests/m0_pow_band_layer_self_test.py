#!/usr/bin/env python3
"""Check exact midpoint-band certificates, true ties and coverage rejection."""

from dataclasses import astuple, replace
from pathlib import Path
import struct
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'research/m0-pow-comparison-20261117'))
import midpoint_band_layer as layer
import midpoint_band_inverse as inverse
import midpoint_rotated_band as band


def bits(value):
    return struct.unpack('>Q', struct.pack('>d', value))[0]


def linear_proof(block):
    geometry = band.Geometry(block, 1, 64)
    transform = [[1, 0], [0, 1]]
    shift, terms = geometry.choose(transform, 64)
    return dict(degree=1, work_bits=64, origin=geometry.origin, transform=transform,
                shift=shift, terms=terms, prime=0, polynomials=[[0, 1, 0]])


class BandProofTest(unittest.TestCase):
    def test_inverse_certificate_and_cover(self):
        block = band.Block(layer.ONE-1,-600,0,24,layer.SHIFT)
        proof = dict(chart='inverse',degree=4,work_bits=112,shift=31,terms=13,prime=0,
                     transform=[[3716,-11],[-87495,259]],
                     polynomials=[[0,102624408032082134173,459995905841152943411,
                                   14346698162893261089,31628233725122333648,-53959220913547984882,
                                   -434668577493808120,-3094912361237427123,3531232667092129035,
                                   -2855731903834975502,700564350209,12069903468116,183066106680705,
                                   2001575612267235,-5532765971179591]])
        self.assertEqual(layer.verify_rows((block,[[list(astuple(block)),'polynomial',proof]])),
                         {'polynomial':1})
        with self.assertRaisesRegex(ValueError, 'integer in the range'):
            inverse.verify_proof(block,dict(proof,polynomials=[[1]+[0]*14]))
        with self.assertRaisesRegex(ValueError, 'q115'):
            inverse.verify_proof(replace(block,shift=114),proof)

    def test_nonintegral_band_and_scratch_values(self):
        block = band.Block(layer.ONE, -900, 0, 4, layer.SHIFT)
        proof = linear_proof(block)
        band.verify_proof(block, proof)
        for key, value in (('transform', [[1, 0], [0, 2]]), ('origin', proof['origin']+4),
                           ('polynomials', [[1, 0, 0]]), ('terms', 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                band.verify_proof(block, dict(proof, **{key: value}))
        with self.assertRaisesRegex(ValueError, 'singleton'):
            band.verify_proof(replace(block, width=0), proof)

    def test_actual_tie_cannot_be_excluded(self):
        integer = 210001
        x, m = bits(float(integer**2)), bits(float(integer**3-1))
        e = (x >> 52)-1023
        first = (x & ((1 << 52)-1)) & ~15
        block = band.Block(m, e, first, 4, 52)
        with self.assertRaisesRegex(ValueError, 'integer in the range'):
            band.verify_proof(block, linear_proof(block))

    def test_layer_plan_includes_both_midpoints_and_unique_bases(self):
        plan = list(layer.spans(38))
        self.assertEqual(len(plan), 1362)
        self.assertEqual(sum((hi-lo) >> width for _,_,width,lo,hi in plan), 21_435_788)
        self.assertEqual(len({(m,e) for m,e,*_ in plan}), len(plan))
        self.assertEqual({m for m,*_ in plan}, set(layer.MIDPOINTS))
        for m,e,width,lo,hi in plan:
            if e != -739:
                continue
            root = band.Block(m, e, 0, 52, layer.SHIFT)
            self.assertTrue(lo == 0 or layer.sides(root, lo-1)[0])
            self.assertTrue(hi == root.base or layer.sides(root, hi)[1])

    def test_partition_checks_gaps_overlap_and_open_leaves(self):
        root = band.Block(layer.ONE, -900, 0, 4, layer.SHIFT)
        left = list(astuple(replace(root, width=3)))
        right = list(astuple(replace(root, first=8, width=3)))
        self.assertEqual(layer.verify_rows((root, [[left, 'direct'], [right, 'direct']])), {'direct': 2})
        self.assertEqual(layer.verify_rows((root, [[left, 'direct'], [right, 'open']])), {'direct': 1, 'open': 1})
        for rows in ([[left, 'direct']], [[right, 'direct']], [[left, 'direct'], [left, 'direct']]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                layer.verify_rows((root, rows))

    def test_bundle_needs_both_midpoints(self):
        plan = list(layer.spans(38))
        selected = [(lo,hi) for lo,hi,_,e,_,_ in layer.indexed_spans(plan) if e == -739]
        self.assertEqual(selected, [(0,12028), (16755108,16759465)])
        self.assertEqual(layer.merged_ranges([(12000,12028), (0,12000), selected[1]]), selected)
        self.assertNotEqual(layer.merged_ranges([selected[0]]), selected)
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            layer.merged_ranges([selected[0], (12000,13000), selected[1]])
        for lo,hi in selected:
            first, = layer.tasks(plan, lo, lo+1)
            last, = layer.tasks(plan, hi-1, hi)
            self.assertEqual(first.binade, -739)
            self.assertEqual(last.first-first.first, (hi-lo-1) << 38)


if __name__ == '__main__':
    unittest.main()
