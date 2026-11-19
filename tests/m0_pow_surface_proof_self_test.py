#!/usr/bin/env python3
"""Independent replay, arithmetic and coverage tests for the pow surface pilot."""

from copy import deepcopy
from io import StringIO
from itertools import product
import json
from math import factorial, prod
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT/'research/m0-pow-comparison-20261117'
sys.path.insert(0, str(RESEARCH))
sys.path.insert(0, str(ROOT/'dev/tools'))
import midpoint_surface_rotated as surface
import midpoint_entire_surface as entire
import verify_m0_pow_binary64 as full_proof


FIXTURE = dict(
    block=[1, 163999181102444, 2, 104454274707880, 4],
    degree=2, work_bits=128, origin=6651981437187463,
    transform=[[1, -1, 1], [2, -1, 2], [-2, 2, -3]],
    radius_shift=46, terms=6, mode='nonintegral',
    polynomials=[[0, 77963855125861519336, -72818519389621400197, -31210129335725555749,
                  -233510677030735584, 217470827669423545, -202532755626099247,
                  93282411394665296, -86874842173526775, -37264284383867899]],
)
ENTIRE_FIXTURE = dict(
    block=[1, 163999181102444, 2, 104454274707880, 4, 4],
    degree=2, work_bits=116, q_shift=52, shear=4, mesh=8,
    transform=[[-4, -5, 3], [2, 2, -1], [-1, -1, 1]],
    radius_shift=[42, 42], terms=[5, 5],
    polynomials=[[0, -31172865051341687850, -5362806563909542684, -77963855125861519336,
                  37264284383867899, 6407569221138521, 1101777317987741, 93282411394665296,
                  16039849361312039, 233510677030735584]],
)


def bits(value):
    return struct.unpack('>Q', struct.pack('>d', value))[0]


def generalized_binomial(n, k):
    return prod(n-j for j in range(k))//factorial(k)


class SurfaceProofTest(unittest.TestCase):
    def test_exact_replay_and_tampering(self):
        surface.verify_block(FIXTURE)
        for key, value in (('transform', ((2, 0, 0), (0, 1, 0), (0, 0, 1))),
                           ('origin', FIXTURE['origin']+3),
                           ('polynomials', [[1]+[0]*9]),
                           ('terms', 2)):
            corrupted = deepcopy(FIXTURE)
            corrupted[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                surface.verify_block(corrupted)

    def test_ambiguous_logarithms_are_not_accepted(self):
        around_one = [0, 0, 2, 0, 4]
        with self.assertRaises(ValueError):
            surface.Geometry(around_one, 2, 128)

    def test_true_midpoint_is_not_excluded(self):
        n = 210001
        x, m = n*n, n*n*n
        self.assertEqual(m.bit_length(), 54)
        self.assertEqual(m % 2, 1)
        bx, bm = bits(float(x)), bits(float(m-1))
        x_exp, m_exp = (bx >> 52)-1023, (bm >> 52)-1023
        block = [x_exp, (bx & (surface.Q-1)) >> 4, m_exp, (bm & (surface.Q-1)) >> 4, 4]
        geometry = surface.Geometry(block, 2, 128)
        # At this triple x**(3/2) is exactly the odd integer midpoint m.
        # The declared nonintegral polynomial is p-origin.
        poly = [int(p == (0, 0, 1)) for p in surface.exponents(2, 3)]
        radius, terms = geometry.choose_geometry(surface.IDENTITY, 128)
        with self.assertRaisesRegex(ValueError, 'contains an integer'):
            surface.verify_block(dict(block=block, degree=2, work_bits=128, origin=geometry.origin,
                                      transform=surface.IDENTITY, radius_shift=radius, terms=terms,
                                      mode='nonintegral', polynomials=[poly]))

    def test_kronecker_product_and_truncation(self):
        grid = surface.FixedInterval(48)
        for cut in (5, (3, 6), (7, 3)):
            layout = surface.Series(cut, grid)
            left = [a-2*b+3 for a, b in layout.indices]
            right = [3*a+b-3 for a, b in layout.indices]
            seen = {}
            for (i, j), a in zip(layout.indices, left):
                for (k, l), b in zip(layout.indices, right):
                    seen[i+k, j+l] = seen.get((i+k, j+l), 0)+a*b
            obtained = layout.multiply(list(map(grid.rational, left)), list(map(grid.rational, right)))
            self.assertEqual(obtained, [grid.rational(seen[k]) for k in layout.indices])

    def test_tensor_replays_on_the_same_rectangle(self):
        row = dict(FIXTURE, block=FIXTURE['block']+[4], gap_bits=16300,
                   tensor_shifts=[45, 44], terms=[8, 9])
        surface.verify_block(row)
        with self.assertRaisesRegex(ValueError, 'invalid tensor degree'):
            surface.verify_block(dict(row, terms=[1, 9]))

    def test_parity_covers_negative_and_positive_integer_coordinates(self):
        degree, period = 4, 8
        _, masks = surface.parity_masks(degree)
        for coords in product((-9, -8, -7, -4, -1, 0, 1, 3, 7, 8, 9), repeat=3):
            i, j, k = (t % period for t in coords)
            bit = 1 << ((i*period+j)*period+k)
            for powers, mask in zip(surface.exponents(degree, 3), masks):
                expected = prod(generalized_binomial(n, d) for n, d in zip(coords, powers)) & 1
                self.assertEqual(bool(mask & bit), bool(expected))

    def test_incomplete_pilot_is_not_a_pass(self):
        report = dict(schema=surface.SCHEMA, width=4, samples=1, seed=2040, inverse=False,
                      cases=[dict(block=FIXTURE['block'])])
        with TemporaryDirectory() as temp:
            path = Path(temp)/'report.json'
            path.write_text(json.dumps(report))
            cmd = [sys.executable, '-B', '-S', str(RESEARCH/'midpoint_surface_rotated.py'),
                   'verify', str(path)]
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'PILOT_INCOMPLETE')
            report['cases'][0]['proof'] = FIXTURE
            path.write_text(json.dumps(report))
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout)['status'], 'PILOT_VERIFIED')

    def test_entire_certificate_is_checked_inside_full_partition(self):
        x, m = entire.encoding_spans(ENTIRE_FIXTURE['block'])
        box = full_proof.Box(x, (full_proof.Y_MIN, full_proof.Y_MAX), m, False)
        text = ''.join(json.dumps(record)+'\n' for record in
                       ([full_proof.SCHEMA], ['entire', ENTIRE_FIXTURE]))
        counts, opened = full_proof.verify_partition(StringIO(text), (box,))
        self.assertEqual(counts, {'entire': 1})
        self.assertIsNone(opened)
        for outside in (full_proof.Box((x[0]-1,x[1]), box.y, m, False),
                        full_proof.Box(x, box.y, (m[0],m[1]+1), False)):
            with self.assertRaisesRegex(ValueError, 'does not cover'):
                full_proof.check_leaf(outside, ['entire', ENTIRE_FIXTURE])
        with self.assertRaisesRegex(ValueError, 'does not cover its exponent grid'):
            full_proof.check_leaf(box, ['entire', dict(ENTIRE_FIXTURE, q_shift=51)])
        for malformed in (dict(ENTIRE_FIXTURE, polynomials=[[1]+[0]*9]),
                          dict(ENTIRE_FIXTURE, terms=[1,5]), dict(ENTIRE_FIXTURE, mesh=7)):
            with self.assertRaises(ValueError):
                entire.verify(malformed)

    def test_entire_polynomial_bands_allow_more_than_one_integer(self):
        powers = surface.exponents(1,3)
        variable = [int(p == (1,0,0)) for p in powers]
        translated = [2]+variable[1:]
        self.assertEqual(entire.exclude_bands(1, [(variable,-2,1),(translated,4,4)], 7), [0,1])
        self.assertIsNone(entire.exclude_bands(1, [(variable,-2,2),(translated,4,4)], 7))

    def test_entire_certificate_cannot_exclude_a_true_tie(self):
        n = 210001
        x, m = bits(float(n*n)), bits(float(n*n*n-1))
        block = [(x >> 52)-1023, (x & (surface.Q-1)) >> 4,
                 (m >> 52)-1023, (m & (surface.Q-1)) >> 4, 4, 4]
        polynomial = [int(p == (0,1,0)) for p in surface.exponents(2,3)]
        geom = entire.Entire(block,2,116,52,4)
        radii, terms = geom.choose_terms(surface.IDENTITY,True)
        row = dict(ENTIRE_FIXTURE,block=block,transform=surface.IDENTITY,
                   radius_shift=radii,terms=terms,polynomials=[polynomial])
        with self.assertRaisesRegex(ValueError, 'integer solutions not excluded'):
            entire.verify(row)

    def test_entire_record_can_hold_wide_polynomials(self):
        record = ['entire',dict(ENTIRE_FIXTURE, padding=' '*5000)]
        self.assertEqual(full_proof.read_record(StringIO(json.dumps(record)+'\n')),record)
        with self.assertRaisesRegex(ValueError, 'oversized'):
            full_proof.read_record(StringIO(json.dumps(['gap',' '*5000])+'\n'))


if __name__ == '__main__':
    unittest.main()
