#!/usr/bin/env python3
"""Check exact midpoint-band certificates, true ties and coverage rejection."""

from dataclasses import astuple, replace
import gzip
from pathlib import Path
import struct
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'research/m0-pow-comparison-20261117'))
import midpoint_band_layer as layer
import midpoint_band_inverse as inverse
import midpoint_band_run as runner
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
        self.assertEqual(layer.verify_rows((block,[[list(astuple(block)),'polynomial',proof]]),900),
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

    def test_full_plan_grid_and_archive_compatibility(self):
        plan, header, total = runner.plan_data(42,115)
        self.assertEqual(header,[layer.SCHEMA,16300,42,
                        '983e49f4eaf3afe7d349ee09983578f307f72d07de793d927c55dfa31f5d2c6e'])
        self.assertEqual(total,1_339_778)
        self.assertEqual(runner.plan_data(42,115,900),(plan,header,total))
        self.assertEqual(runner.plan_data(42,115,480),(plan,header,total))
        self.assertEqual(layer.verify_early_interval(115),{512:384,1024:766})
        self.assertEqual(layer.verify_early_interval(115,480),{512:384})
        plan, header, total = runner.plan_data(42,114)
        self.assertEqual({m-layer.ONE for m,*_ in plan},{-3,-2,-1,0})
        self.assertEqual(total,2_301_369)
        self.assertEqual(layer.verify_early_interval(114),{512:388,1024:770})
        self.assertEqual(layer.verify_early_interval(114,480),{512:388})
        self.assertNotEqual(header[0],layer.SCHEMA)
        self.assertEqual(next(layer.tasks(plan,0,1,114)).shift,114)
        with self.assertRaises(ValueError):
            layer.verify_reduction(104)

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

    def test_resumable_archive_requires_exact_coverage_and_content(self):
        self.assertEqual(list(runner.missing_ranges([(7,8),(3,4)],0,10,2)),
                         [(0,2),(2,3),(4,6),(6,7),(8,10)])
        for coverage in ([(1,6),(4,8)],[(0,11)]):
            with self.assertRaises(ValueError):
                list(runner.missing_ranges(coverage,0,10,3))
        plan = ((layer.ONE,-900,2,0,8),)
        prefix = [layer.SCHEMA,layer.GAP,2,'test-plan']
        roots = [list(astuple(root)) for root in layer.tasks(plan,0,2)]
        with TemporaryDirectory() as tmp, patch.object(runner,'plan_data',return_value=(plan,prefix,2)):
            directory = Path(tmp)
            paths = [directory/runner.archive_name(i,i+1) for i in range(2)]
            runner.save_archive(paths[0],prefix+[0,1,2],{0:[[roots[0],'direct']]})
            with self.assertRaisesRegex(ValueError,'entire layer'):
                runner.verify_complete(directory,2,115,1,False)
            runner.save_archive(paths[1],prefix+[1,2,2],{0:[[roots[1],'open']]})
            with self.assertRaisesRegex(ValueError,'unresolved'):
                runner.verify_complete(directory,2,115,1,False)
            paths[1].unlink()
            runner.save_archive(paths[1],prefix+[1,2,2],{0:[[roots[1],'direct']]})
            self.assertEqual(runner.verify_complete(directory,2,115,1,False),(2,{'direct':2}))
            with gzip.open(paths[1],'at') as out:
                out.write('[]\n')
            with self.assertRaisesRegex(ValueError,'unexpected rows'):
                runner.verify_complete(directory,2,115,1,False)


if __name__ == '__main__':
    unittest.main()
