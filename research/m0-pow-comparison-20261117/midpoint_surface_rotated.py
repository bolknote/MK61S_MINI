#!/usr/bin/env python3
"""Exact replay of rotated Newton certificates for two variable pow inputs."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from fractions import Fraction
from functools import lru_cache
import gzip
from itertools import product
import json
from math import ceil
from pathlib import Path
from random import Random
import sys
from time import perf_counter, process_time

from midpoint_grid import FixedInterval, add, interval_series_product, use_flint_products
from midpoint_surface import verify_interval_margin

Q = 1 << 52
GAP = 900
STRIP = Fraction(1, 1 << GAP)
IDENTITY = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
SCHEMA = 'pow-rotated-newton-surface-v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


@lru_cache(maxsize=24)
def exponents(degree, dimensions):
    if dimensions == 2:
        return tuple((i, total-i) for total in range(degree+1)
                     for i in range(total+1))
    return tuple((i, j, total-i-j) for total in range(degree+1)
                 for i in range(total+1) for j in range(total-i+1))


def log_center(grid, exponent, coefficient, unit, ln2):
    magnitude = add(grid.scale(ln2, exponent), grid.log(coefficient, unit))
    return grid.scale(magnitude, 1 if exponent >= 0 else -1)


class Geometry:
    # On a block I,J are integers in [-half,half), u=I/half, v=J/half.
    # The exponent grid is p=2**52*abs(y), with no parity restriction.
    def __init__(self, block, degree, work_bits, origin=None):
        require(isinstance(block, (tuple, list)) and len(block) == 5
                and all(type(v) is int for v in block), 'invalid block')
        ex, bx, em, bm, width = block
        require(-1022 <= ex <= 1023 and -1022 <= em <= 1023 and 4 <= width <= 48
                and 0 <= bx < 1 << (52-width) and 0 <= bm < 1 << (52-width),
                'block is outside a normal binade')
        require(type(degree) is int and 1 <= degree <= 9
                and type(work_bits) is int and 32 <= work_bits <= 384,
                'unsupported polynomial degree or precision')
        self.degree = degree
        self.half = h = 1 << (width-1)
        self.max_radius_shift = 50-width
        self.relative = (Fraction(h, Q+(2*bx+1)*h), Fraction(2*h, 2*(Q+(2*bm+1)*h)+1))
        self.signs = (1 if ex >= 0 else -1, 1 if em >= 0 else -1)
        self.grid = grid = FixedInterval(work_bits+72*degree+96)
        ln2 = grid.log(2, 1)
        self.log_x = log_center(grid, ex, Q+(2*bx+1)*h, Q, ln2)
        self.log_m = log_center(grid, em, 2*(Q+(2*bm+1)*h)+1, 2*Q, ln2)
        require(self.log_x[0] > 0 and self.log_m[0] > 0, 'logarithm sign is undecided')
        f0 = grid.divide(grid.scale(self.log_m, Q), self.log_x)
        if origin is None:
            origin = (f0[0]+f0[1])//(2*grid.unit)
        require(type(origin) is int and abs(origin).bit_length() <= 80,
                'invalid exponent origin')
        self.origin = origin
        fu = grid.divide(grid.scale(grid.multiply(f0, self.log_coefficient(0, 1)), -1),
                         self.log_x)
        fv = grid.divide(grid.scale(self.log_coefficient(1, 1), Q), self.log_x)
        self.linear = (add(f0, grid.rational(-origin)), fu, fv)
        require(max(map(abs, self.linear[0])) <= 2*grid.unit,
                'shift is too far from the true centre')
        result = self.circle_error(1)
        require(result is not None and result[0] > STRIP,
                'opposite-sign logarithms or the denominator are not separated')
        self.real_min_log, self.real_remainder = result
        self.vertical = Q*STRIP/self.real_min_log

    def log_coefficient(self, axis, n):
        value = self.signs[axis]*(-1)**(n-1)*self.relative[axis]**n/n
        return self.grid.rational(value.numerator, value.denominator)

    def circle_error(self, radius):
        """Bound F-F(0)-F_u*u-F_v*v on the complex bidisc."""
        a, b = (v*radius for v in self.relative)
        if max(a, b) >= Fraction(1, 2):
            return None
        dx, dm = a/(1-a), b/(1-b)
        x = Fraction(self.log_x[0], self.grid.unit)
        m = Fraction(self.log_m[1], self.grid.unit)
        low = x-dx
        if low <= 0:
            return None
        # Expand (M+dM)/(X+dX) to first order at dM=dX=0, then replace
        # dM,dX with the linear terms of log(1+t). The four positive
        # terms bound the two logarithm tails and the two quotient tails.
        remainder = Q*(b*b/(2*(1-b)*x)+m*a*a/(2*(1-a)*x*x)
                       +m*dx*dx/(x*x*low)+dx*dm/(x*low))
        return low, remainder

    def linear_form_bounds(self, transform, radius, remainder):
        z, du, dv = self.linear
        unit = self.grid.unit
        h = self.half*unit
        result = []
        for a, b, c in transform:
            linear = max(abs(a*h+c*d) for d in du)+max(abs(b*h+c*d) for d in dv)
            center = abs(c)*max(map(abs, z))
            result.append(Fraction(center+radius*linear, unit)+abs(c)*remainder)
        return tuple(result)

    def tail_parameters(self, transform, shift):
        require(type(shift) is int and 1 <= shift <= self.max_radius_shift,
                'invalid radius')
        radius = 1 << shift
        result = self.circle_error(radius)
        require(result is not None, 'complex logarithm denominator may vanish')
        _, remainder = result
        maximum = max(self.linear_form_bounds(transform, radius, remainder))
        cap = ceil(maximum)+self.degree
        # Cauchy on a bidisc: sum_{n>=terms} (n+1) R^-n
        # <= (2*terms+4) R^-terms for R >= 2. Each binomial factor
        # is bounded by cap; dropping its factorial is conservative.
        velocity = max(abs(row[2]) for row in transform)*self.vertical
        real_max = max(self.linear_form_bounds(transform, 1, self.real_remainder))
        # At a candidate, the third original coordinate moves by at most
        # vertical. Bound the derivative of the binomial product along
        # this segment using its individual linear factors.
        real_cap = ceil(real_max+velocity)+self.degree
        return cap**self.degree, self.degree*velocity*real_cap**(self.degree-1)

    @staticmethod
    def tail_bound(parameters, shift, terms):
        require(type(terms) is int and 2 <= terms <= 128, 'invalid truncation degree')
        constant, vertical = parameters
        return Fraction(constant*(2*terms+4), 1 << (shift*terms))+vertical

    def tails(self, transform, shift, terms):
        return self.tail_bound(self.tail_parameters(transform, shift), shift, terms)

    def choose_geometry(self, transform, work_bits):
        target = Fraction(1, 1 << work_bits)
        candidates = []
        for shift in range(1, self.max_radius_shift+1):
            if self.circle_error(1 << shift) is None:
                continue
            parameters = self.tail_parameters(transform, shift)
            low, high = 1, 128
            if self.tail_bound(parameters, shift, high) > target:
                continue
            while low+1 < high:
                trial = (low+high)//2
                if self.tail_bound(parameters, shift, trial) <= target:
                    high = trial
                else:
                    low = trial
            candidates.append((high, -shift))
        require(bool(candidates), 'no usable complex disk and truncation')
        terms, negative_shift = min(candidates)
        return -negative_shift, terms


def determinant(lines):
    (a, b, c), (d, e, f), (g, h, i) = lines
    return a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g)


def checked_transform(transform):
    require(isinstance(transform, (list, tuple)) and len(transform) == 3
            and all(isinstance(row, (list, tuple)) and len(row) == 3
                    and all(type(v) is int and abs(v) <= 1 << 32 for v in row)
                    for row in transform), 'invalid integer coordinate transform')
    require(abs(determinant(transform)) == 1, 'coordinate transform is not unimodular')
    return tuple(tuple(row) for row in transform)


def adapt(geometry):
    from flint import fmpz_mat

    scale = 1 << 20
    h = geometry.half*scale
    _, du, dv = geometry.linear
    denominator = 2*geometry.grid.unit
    base = ((h, 0, 0), (0, h, 0), (sum(du)*scale//denominator, sum(dv)*scale//denominator,
                                  ceil(max(1, geometry.real_remainder)*scale)))
    _, transform = fmpz_mat(base).lll(transform=True)
    return checked_transform(tuple(tuple(int(transform[i, j]) for j in range(3)) for i in range(3)))


class Series:
    def __init__(self, terms, grid):
        self.terms = terms
        self.grid = grid
        self.indices = exponents(terms-1, 2)
        self.locations = {e: i for i, e in enumerate(self.indices)}
        # Two degrees of at most terms-1 add without carrying from j
        # into i in this Kronecker encoding.
        stride = 2*terms-1
        self.flat = tuple(i*stride+j for i, j in self.indices)
        self.length = max(self.flat)+1

    def multiply(self, a, b):
        left, right = [(0, 0)]*self.length, [(0, 0)]*self.length
        for k, v, w in zip(self.flat, a, b):
            left[k], right[k] = v, w
        exact = interval_series_product(left, right, self.grid)
        return [exact[k] for k in self.flat]

    def basis(self, geometry, transform):
        g = self.grid
        x = [geometry.log_x]+[geometry.log_coefficient(0, n) for n in range(1, self.terms)]
        m = [geometry.log_m]+[geometry.log_coefficient(1, n) for n in range(1, self.terms)]
        inverse = [g.divide(g.rational(1), x[0])]
        for n in range(1, self.terms):
            bound = (0, 0)
            for j in range(1, n+1):
                bound = add(bound, g.multiply(x[j], inverse[n-j]))
            inverse.append(g.divide(g.scale(bound, -1), x[0]))
        offset = [g.scale(g.multiply(inverse[i], m[j]), Q) for i, j in self.indices]
        offset[0] = add(offset[0], g.rational(-geometry.origin))
        linear = []
        for a, b, c in transform:
            series = [g.scale(v, c) for v in offset]
            k, l = self.locations[1, 0], self.locations[0, 1]
            series[k] = add(series[k], g.rational(a*geometry.half))
            series[l] = add(series[l], g.rational(b*geometry.half))
            linear.append(series)
        # B_n(L) = B_{n-1}(L)*(L-(n-1))/n. Every product in
        # this basis is integer-valued at integral I,J,p.
        polynomials = {(0, 0, 0): [g.rational(1)]+[(0, 0)]*(len(self.indices)-1)}
        for powers in exponents(geometry.degree, 3)[1:]:
            axis = next(i for i, n in enumerate(powers) if n)
            n = powers[axis]
            previous = list(powers)
            previous[axis] -= 1
            old = polynomials[tuple(previous)]
            factor = linear[axis].copy()
            factor[0] = add(factor[0], g.rational(1-n))
            multiplied = factor if sum(powers) == 1 else self.multiply(old, factor)
            polynomials[powers] = [(lo//n, -(-hi//n)) for lo, hi in multiplied]
        return tuple(polynomials[powers] for powers in exponents(geometry.degree, 3))


@lru_cache(maxsize=8)
def parity_masks(degree):
    # For k<period, binom(n,k) mod 2 depends only on n mod period.
    # This also holds for negative n by the binomial series identity
    # (1+z)**period == 1+z**period in characteristic two.
    period = 1 << degree.bit_length()
    periods = tuple(product(range(period), repeat=3))
    axes = tuple(tuple(sum(1 << index for index, values in enumerate(periods)
                           if values[axis] & k == k) for k in range(degree+1))
                 for axis in range(3))
    masks = tuple(axes[0][i] & axes[1][j] & axes[2][k] for i, j, k in exponents(degree, 3))
    return (1 << (period**3))-1, masks


def excludes_residues(degree, polynomials):
    roots, masks = parity_masks(degree)
    selected = []
    for poly in polynomials:
        parity = 0
        for coefficient, mask in zip(poly, masks):
            if coefficient & 1:
                parity ^= mask
        if parity & roots:
            roots &= ~parity
            selected.append(poly)
        if not roots:
            return selected
    return None


def polynomial_bounds(polynomial, columns, tail_units, maximum_width=None):
    active = [(a, column) for a, column in zip(polynomial, columns) if a]
    # The first basis polynomial is identically 1, with no series tail
    # or displacement error. Subtracting an integer cannot widen a bound.
    radius = tail_units*sum(map(abs, polynomial[1:]))
    center = (0, 0)
    for idx in range(len(columns[0])):
        lo, hi = 0, 0
        for a, column in active:
            x, y = column[idx]
            if a < 0:
                x, y = y, x
            lo, hi = lo+a*x, hi+a*y
        if idx == 0:
            center = lo, hi
        else:
            radius += max(abs(lo), abs(hi))
        if maximum_width is not None and center[1]-center[0]+2*radius >= maximum_width:
            return None
    return center[0]-radius, center[1]+radius


def integer_interval(bounds, unit):
    return -(-bounds[0]//unit), bounds[1]//unit


def verify_block(row):
    geometry = Geometry(row['block'], row['degree'], row['work_bits'], row['origin'])
    transform = checked_transform(row['transform'])
    validate = row['polynomials']
    rank = len(exponents(geometry.degree, 3))
    require(isinstance(validate, list) and 1 <= len(validate) <= rank
            and all(isinstance(poly, list) and len(poly) == rank and any(poly)
                    and all(type(c) is int and abs(c).bit_length() <= 512 for c in poly)
                    for poly in validate), 'invalid integer polynomials')
    mode = row.get('mode', 'zero')
    require(mode in ('zero', 'nonintegral'), 'unknown polynomial proof mode')
    tail = geometry.tails(transform, row['radius_shift'], row['terms'])
    grid = geometry.grid
    columns = Series(row['terms'], grid).basis(geometry, transform)
    tail_units = ceil(tail*grid.unit)
    intervals = [integer_interval(polynomial_bounds(poly, columns, tail_units), grid.unit)
                 for poly in validate]
    if mode == 'nonintegral':
        require(len(intervals) == 1 and intervals[0][0] > intervals[0][1],
                'polynomial interval contains an integer')
    elif all(lo <= hi for lo, hi in intervals):
        require(all(interval == (0, 0) for interval in intervals),
                'a polynomial interval contains an integer other than zero')
        require(excludes_residues(geometry.degree, validate) is not None,
                'polynomials share a modular zero')


def generate_block(block, degree, work_bits, rotated, delta, free_center=False):
    from flint import fmpz_mat

    geometry = Geometry(block, degree, work_bits)
    rank = len(exponents(degree, 3))
    transform = adapt(geometry) if rotated else IDENTITY
    shift, terms = geometry.choose_geometry(transform, work_bits)
    grid = geometry.grid
    start = process_time()
    columns = Series(terms, grid).basis(geometry, transform)
    expansion = process_time()-start
    scale = 1 << work_bits
    start_column = int(free_center)
    basis_rows = columns[start_column:]
    size = len(columns[0])-start_column
    dimension = rank-start_column
    penalty = size+2
    lattice = [[((lo+hi)*scale)//(2*grid.unit) for lo, hi in series[start_column:]]
               + [penalty*(i == j) for j in range(dimension)] for i, series in enumerate(basis_rows)]
    start = process_time()
    reduced = fmpz_mat(lattice).lll(delta=delta)
    lll = process_time()-start
    tail_units = ceil(geometry.tails(transform, shift, terms)*grid.unit)
    small = []
    mode = 'zero'
    selected = None
    row_norms = [sum(abs(int(reduced[i, j])) for j in range(size)) for i in range(dimension)]
    for i, estimate in enumerate(row_norms):
        if estimate >= scale:
            continue
        poly = [0]*start_column+[int(reduced[i, size+j])//penalty for j in range(dimension)]
        bounds = polynomial_bounds(poly, columns, tail_units, 2*grid.unit)
        if bounds is None:
            continue
        first, last = integer_interval(bounds, grid.unit)
        if last < first:
            mode, selected = 'nonintegral', [poly]
            break
        if first == last:
            poly[0] -= first
            small.append(poly)
    if selected is None:
        selected = excludes_residues(degree, small)
    closest = min(row_norms)
    result = dict(terms=terms, radius_shift=shift, rank=rank, transform=transform,
                  expansion_cpu_s=expansion, reduction_cpu_s=lll, small_polynomials=len(small),
                  smallest_row_log2_floor=closest.bit_length()-1-work_bits if closest else None)
    if selected:
        result['proof'] = dict(block=block, degree=degree, work_bits=work_bits,
                               origin=geometry.origin, transform=transform,
                               radius_shift=shift, terms=terms, mode=mode, polynomials=selected)
    return result


def sample_blocks(width, count, seed, inverse):
    # The same physical locations are used across block widths. The
    # positive control rectangle is [3,3.25) x [5,5.5). The inverse
    # case uses midpoints in [5/32,3/16), so log(m)/log(x) is negative.
    rng = Random(seed)
    blocks = set()
    require(4 <= width <= 48 and 1 <= count <= 1 << (2*(49-width)), 'invalid sample size')
    while len(blocks) < count:
        x = ((Q//2)+rng.randrange(Q//8)) >> width
        m = ((Q//4)+rng.randrange(Q//8 if not inverse else Q//4)) >> width
        blocks.add((1, x, -3 if inverse else 2, m, width))
    return sorted(blocks)


def run_block(request):
    block, degree, work_bits, rotated, delta, free_center = request
    start = process_time()
    result = generate_block(block, degree, work_bits, rotated, delta, free_center)
    return dict(block=block, generator_cpu_s=process_time()-start, **result)


def replay_block(row):
    start = process_time()
    verify_block(row)
    return process_time()-start


def batch(function, requests, workers, accelerated):
    context = (ProcessPoolExecutor(max_workers=workers,
                                   initializer=use_flint_products if accelerated else None)
               if workers > 1 else nullcontext())
    with context as pool:
        if pool is None and accelerated:
            use_flint_products()
        values = pool.map(function, requests) if pool else map(function, requests)
        return list(values)


def open_report(path, mode):
    if path.suffix == '.gz':
        return gzip.open(path, mode+'t', encoding='ascii')
    return path.open(mode, encoding='ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    sample = modes.add_parser('sample')
    sample.add_argument('--width', type=int, required=True)
    sample.add_argument('--degree', type=int, required=True)
    sample.add_argument('--work-bits', type=int, default=128)
    sample.add_argument('--samples', type=int, default=4)
    sample.add_argument('--seed', type=int, default=2040)
    sample.add_argument('--delta', type=float, default=0.90)
    sample.add_argument('--plain', action='store_true')
    sample.add_argument('--free-center', action='store_true',
                        help='optimize variation only and then locate the constant term')
    sample.add_argument('--inverse', action='store_true')
    sample.add_argument('--output', type=Path, required=True)
    verify = modes.add_parser('verify')
    verify.add_argument('input', type=Path)
    for mode in (sample, verify):
        mode.add_argument('--workers', type=int, default=1)
        mode.add_argument('--flint-products', action='store_true')
    args = parser.parse_args()
    verify_interval_margin()
    require(__debug__ and args.workers >= 1, 'enable assertions and use positive workers')
    if args.mode == 'verify':
        with open_report(args.input, 'r') as stream:
            report = json.load(stream)
        require(report['schema'] == SCHEMA, 'unrecognized pilot schema')
        cases = report['cases']
        blocks = [tuple(row['block']) for row in cases]
        require(len(set(blocks)) == len(blocks)
                and blocks == sample_blocks(report['width'], report['samples'],
                                            report['seed'], report['inverse']),
                'duplicate, missing or outside pilot blocks')
        proofs = [row['proof'] for row in cases if 'proof' in row]
        require(all(row['proof']['block'] == row['block'] for row in cases if 'proof' in row),
                'a proof has moved to the wrong block')
        start = perf_counter()
        timing = batch(replay_block, proofs, args.workers, args.flint_products)
        complete = len(proofs) == len(cases)
        print(json.dumps(dict(status='PILOT_VERIFIED' if complete else 'PILOT_INCOMPLETE',
                              verified_blocks=len(proofs), requested_blocks=len(cases),
                              base_midpoint_pairs=len(proofs) << (2*report['width']),
                              verification_cpu_s=timing, wall_s=perf_counter()-start)))
        return 0 if complete else 2
    require(0.25 < args.delta < 1.0, 'invalid LLL delta')
    blocks = sample_blocks(args.width, args.samples, args.seed, args.inverse)
    requests = [(block, args.degree, args.work_bits, not args.plain, args.delta, args.free_center)
                for block in blocks]
    start = perf_counter()
    cases = batch(run_block, requests, args.workers, args.flint_products)
    report = dict(schema=SCHEMA, width=args.width, degree=args.degree, work_bits=args.work_bits,
                  samples=args.samples, seed=args.seed, inverse=args.inverse, rotated=not args.plain,
                  delta=args.delta, free_center=args.free_center, wall_s=perf_counter()-start, cases=cases)
    with open_report(args.output, 'x') as stream:
        json.dump(report, stream, separators=(',', ':'))
        stream.write('\n')
    print(json.dumps(dict(width=args.width, degree=args.degree, inverse=args.inverse,
                          rotated=not args.plain, free_center=args.free_center,
                          proved=sum('proof' in row for row in cases),
                          small=[row['small_polynomials'] for row in cases],
                          generator_cpu_s=[row['generator_cpu_s'] for row in cases],
                          wall_s=report['wall_s'])))


if __name__ == '__main__':
    sys.exit(main())
