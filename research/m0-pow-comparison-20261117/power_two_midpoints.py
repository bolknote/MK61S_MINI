#!/usr/bin/env python3
"""Certify pow with power-of-two bases and large reduced y denominators."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from fractions import Fraction
from functools import cache
import gzip
from itertools import chain
import json
from math import ceil, isqrt
from pathlib import Path
import sys
from time import perf_counter

from midpoint_grid import FixedInterval, add, ceil_div, exclude_residues, interval_series_product

D = 1 << 53
GAP = 900
MAX_SHIFT = 89  # The separate dyadic pow certificate covers k >= 90.
SCHEMA = 'pow-power-two-midpoints-v1'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


@cache
def powers(degree):
    return tuple((i, t-i) for t in range(degree+1) for i in range(t+1))


@cache
def ln2(precision):
    return FixedInterval(precision).log(2, 1)


def midpoint_limit(side, shift):
    if shift == 64:
        # The published 2^t separation for the 2^-64 grid with t in
        # [1/2,1) covers the rest of the normalized midpoints here.
        return (isqrt(2*D*D)-D+1)//2 if side == 1 else midpoint_limit(-1, 65)
    # If |s*y*ln(2)-ln(m)| <= 2^-GAP, |ln(m)| <= u. Thus
    # 1-m <= u below 1 and m-1 <= u/(1-u) above 1.
    u = Fraction(ln2(160)[1]*1074*(D-1), 1 << (160+shift))+Fraction(1, 1 << GAP)
    require(u < Fraction(1, 2), 'midpoint bound left the adjacent binades')
    radius = u/(1-u) if side == 1 else 2*u
    return (1+radius*D)//2


def spans(min_shift, max_shift=MAX_SHIFT):
    for side in (1, -1):
        start = 0 if max_shift == MAX_SHIFT else midpoint_limit(side, max_shift+1)
        for k in range(max_shift, min_shift-1, -1):
            stop = midpoint_limit(side, k)
            require(stop >= start, 'midpoint layers are not nested')
            if stop > start:
                yield side, k, start, stop
            start = stop


def coefficient(side, index):
    return (D if side == 1 else 2*D)+side*(2*index+1)


def geometry(side, start, stop):
    middle = (start+stop)//2
    half = (stop-start)//2
    center = coefficient(side, middle)
    require(half and D <= center < 2*D, 'invalid block centre')
    relative = Fraction(2*side*half, center)
    radius_shift = (center//(8*half)).bit_length()-1
    require(radius_shift >= 1, 'no complex radius for the block')
    return half, center, relative, radius_shift


def check_points(side, k, start, stop):
    require(stop-start <= 16, 'direct check is too large')
    for index in range(start, stop):
        for precision in (192, 384, 1024):
            grid = FixedInterval(precision)
            log = grid.log(coefficient(side, index), D)
            low, high = grid.divide(grid.scale(log, 1 << k), ln2(precision))
            pad = 1 << max(0, precision+k+1-GAP)
            if ceil_div(low-pad, grid.unit) > (high+pad)//grid.unit:
                break
        else:
            raise ValueError(f'unseparated midpoint {side} {k} {index}')


def norm_parameters(half, relative, k, coord, transform, grid, radius):
    # Inside |z| <= R, |log(1+r*z)-r*z| <= (|r|R)^2/(2*(1-|r|R)).
    # The factor 1/log(2) is below 2. coord encloses the centre and slope
    # of the offset after subtraction of the integer affine function.
    r = abs(relative)*radius
    require(r <= Fraction(1, 4) and 2*ln2(grid.precision)[0] > grid.unit,
            'invalid logarithm tail bound')
    rest = (1 << k)*r*r/(1-r)
    constant, slope = coord[:2]
    return max(abs(b)*Fraction(max(map(abs, constant)), grid.unit)
               + radius*max(Fraction(abs(a*half*grid.unit+b*q), grid.unit) for q in slope)
               + abs(b)*rest for a, b in transform)


def verify_block(side, k, start, stop, proof):
    if proof is None:
        check_points(side, k, start, stop)
        return
    require(isinstance(proof, list) and len(proof) == 7
            and all(type(v) is int for v in proof[:5]), 'invalid proof record')
    degree, terms, precision, origin, slope, transform, polynomials = proof
    require(2 <= degree <= 10 and degree < terms <= 96 and 256 <= precision <= 1024
            and max(abs(origin), abs(slope)).bit_length() <= 128,
            'unsupported proof degree or precision')
    require(isinstance(transform, list) and len(transform) == 2
            and all(isinstance(row, list) and len(row) == 2 and all(type(x) is int for x in row)
                    for row in transform), 'invalid coordinate transform')
    (a, b), (c, d) = transform
    require(abs(a*d-b*c) == 1 and max(abs(a), abs(b), abs(c), abs(d)) <= 1 << 32,
            'coordinate transform is not unimodular')
    pp = powers(degree)
    require(isinstance(polynomials, list) and 0 < len(polynomials) <= len(pp)
            and all(isinstance(p, list) and len(p) == len(pp) and any(p)
                    and all(type(v) is int and abs(v).bit_length() <= 512 for v in p)
                    for p in polynomials), 'invalid polynomial list')
    half, center, relative, radius_shift = geometry(side, start, stop)
    grid = FixedInterval(precision)
    offset = [add(grid.divide(grid.scale(grid.log(center, D), 1 << k), ln2(precision)),
                  grid.rational(-origin))]
    power = Fraction(1)
    for n in range(1, terms):
        power *= -relative
        term = -power/n
        offset.append(grid.divide(grid.rational(term.numerator << k, term.denominator), ln2(precision)))
    offset[1] = add(offset[1], grid.rational(-slope*half))
    radius = 1 << radius_shift
    disc = norm_parameters(half, relative, k, offset, transform, grid, radius)
    size = norm_parameters(half, relative, k, offset, transform, grid, 1)
    velocity = Fraction(max(abs(b), abs(d)), 1 << (GAP-k-1))
    # Bound the Taylor tail by Cauchy on a disc and the vertical error
    # by differentiating each Newton factor along the displacement.
    tail = (disc+degree)**degree/(radius**(terms-1)*(radius-1))
    vertical = degree*velocity*(size+degree+velocity)**(degree-1)
    pad = ceil((tail+vertical)*grid.unit)
    one = [grid.rational(1)]+[(0, 0)]*(terms-1)
    series = []
    for row in transform:
        x, y = row
        linear = [grid.scale(point, y) for point in offset]
        linear[1] = add(linear[1], grid.rational(x*half))
        sequence = [one]
        for j in range(degree):
            shifted = [add(linear[0], grid.rational(-j)), *linear[1:]]
            prod = interval_series_product(sequence[-1], shifted, grid)
            sequence.append([(lo//(j+1), ceil_div(hi, j+1)) for lo, hi in prod])
        series.append(sequence)

    products = {n: interval_series_product(series[0][i], series[1][j], grid)
                for n, (i, j) in enumerate(pp) if any(p[n] for p in polynomials)}
    zeros = []
    for polynomial in polynomials:
        radius = pad*sum(map(abs, polynomial[1:]))
        summed = [[0, 0] for _ in range(terms)]
        for n, coeffs in products.items():
            scalar = polynomial[n]
            if scalar:
                for dst, value in zip(summed, coeffs):
                    lo, hi = grid.scale(value, scalar)
                    dst[0] += lo
                    dst[1] += hi
        radius += sum(max(map(abs, term)) for term in summed[1:])
        low = ceil_div(summed[0][0]-radius, grid.unit)
        high = (summed[0][1]+radius)//grid.unit
        if low > high:
            return
        if low == high:
            zeros.append([polynomial[0]-low, *polynomial[1:]])
    require(exclude_residues(pp, zeros, 2, 'newton') is not None,
            'polynomials leave a common parity residue')


def generate_block(side, k, start, stop, degree, work):
    from flint import arb, arb_series, ctx, fmpz_mat

    half, center, relative, r = geometry(side, start, stop)
    precision = work+60*degree+80
    ctx.prec = precision
    log2 = arb(2).log()
    z = arb(relative.numerator)/relative.denominator
    q = 1 << k
    f0 = q*(arb(center)/D).log()/log2
    df = q*z/log2
    origin = int((f0+arb('0.5')).mid().floor().fmpz())
    slope = int((df/half+arb('0.5')).mid().floor().fmpz())
    frac = df-slope*half
    w = 1 << 20
    nonlinear = 2*q*z*z
    _, matrix = fmpz_mat([[half*w, 0], [int((frac*w).mid().floor().fmpz()),
                                         int((max(arb(1), nonlinear)*w).mid().floor().fmpz())]]).lll(
                                             delta=0.99, transform=True)
    transform = [[int(matrix[i, j]) for j in range(2)] for i in range(2)]
    radius = 1 << r
    sizes = [abs(b*(f0-origin))+radius*abs(a*half+b*frac)+2*q*abs(b)*(radius*z)**2
             for a, b in transform]
    cap = max(int(size.upper().ceil().fmpz())+degree for size in sizes)
    terms = max(degree+1, ceil_div((cap**degree).bit_length()+work+3, r))
    if terms > 96:
        return None
    ctx.cap = terms
    x = arb_series([0, half], prec=terms)
    off = q*(1+arb_series([0, z], prec=terms)).log()/log2+f0-origin-x*slope
    series = []
    for a, b in transform:
        coord = a*x+b*off
        sequence = [arb_series([1], prec=terms)]
        for j in range(degree):
            sequence.append(sequence[-1]*(coord-j)/(j+1))
        series.append(sequence)
    scale, penalty = 1 << work, terms+2
    pp = powers(degree)
    columns = [series[0][a]*series[1][b] for a, b in pp[1:]]
    lattice = []
    for row, basis in enumerate(columns):
        scaled = scale*basis
        lattice.append([int(scaled[j].mid().floor().fmpz()) for j in range(1, terms)]
                       + [penalty*int(row == j) for j in range(len(columns))])
    reduced = fmpz_mat(lattice).lll(delta=0.65)
    small = []
    polynomials = None
    for row in range(len(columns)):
        p = [int(reduced[row, terms-1+j])//penalty for j in range(len(columns))]
        estimated = sum(abs(int(reduced[row, j])) for j in range(terms-1))
        remainder = estimated+(2*terms+2)*sum(map(abs, p))
        if remainder >= scale:
            continue
        error = arb(remainder)/scale
        center_value = sum(c*basis[0] for c, basis in zip(p, columns) if c)
        # The independent checker uses exact interval arithmetic for this test.
        low = int((center_value-error).lower().ceil().fmpz())
        high = int((center_value+error).upper().floor().fmpz())
        if low > high:
            polynomials = [[0, *p]]
            break
        if low == high:
            small.append([-low, *p])
    if polynomials is None:
        polynomials = exclude_residues(pp, small, 2, 'newton')
    if not polynomials:
        return None
    return [degree, terms, precision, origin, slope, transform, polynomials]


def generate(task):
    side, k, start, stop = task
    if stop-start <= 16:
        check_points(*task)
        return [[*task, None]]
    for degree, work in ((4, 92), (5, 106), (6, 120)):
        proof = generate_block(*task, degree, work)
        if proof is not None:
            return [[*task, proof]]
    middle = (start+stop)//2
    return generate((side, k, start, middle))+generate((side, k, middle, stop))


def replay(tasks):
    count = 0
    for side, k, start, stop, certificate in tasks:
        verify_block(side, k, start, stop, certificate)
        count += stop-start
    return len(tasks), count


def read_proof(path):
    with gzip.open(path, 'rt') as stream:
        header = json.loads(next(stream))
        require(isinstance(header, list) and len(header) in (2, 3) and header[0] == SCHEMA
                and all(type(x) is int for x in header[1:]), 'wrong certificate header')
        min_shift = header[1]
        max_shift = header[2] if len(header) == 3 else MAX_SHIFT
        require(64 <= min_shift <= max_shift <= MAX_SHIFT,
                'wrong certificate header')
        rows = iter(stream)
        for side, k, start, stop in spans(min_shift, max_shift):
            first = start
            while first < stop:
                row = json.loads(next(rows, 'null'))
                require(isinstance(row, list) and len(row) == 5
                        and all(type(x) is int for x in row[:4])
                        and row[:3] == [side, k, first] and first < row[3] <= stop,
                        'discontinuous, overlapping or out-of-domain midpoint block')
                first = row[3]
                yield row
        require(next(rows, None) is None, 'extra midpoint blocks')


def chunks(work, batch):
    current = []
    for row in work:
        current.append(row)
        if len(current) == batch:
            yield current
            current = []
    if current:
        yield current


def generate_chunk(work):
    return list(chain.from_iterable(map(generate, work)))


def process(pool, fn, work, workers):
    # ProcessPoolExecutor.map on Python 3.13 eagerly queues its input.
    for batch in chunks(chunks(work, 64), 4*workers):
        yield from pool.map(fn, batch)


def main():
    require(__debug__, 'enable assertions in the interval arithmetic')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('generate', 'verify'))
    parser.add_argument('file', type=Path)
    parser.add_argument('--from-shift', type=int, default=78)
    parser.add_argument('--to-shift', type=int, default=MAX_SHIFT)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--width', type=int, default=23, help='log2 of the initial block size')
    args = parser.parse_args()
    require(64 <= args.from_shift <= args.to_shift <= MAX_SHIFT and 10 <= args.width <= 30
            and args.workers >= 1, 'invalid search parameters')
    start_time = perf_counter()
    blocks = covered = 0

    def progress(count, points):
        if count//262144 > blocks//262144:
            print(args.mode, count, 'blocks', points, 'midpoints', file=sys.stderr, flush=True)

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        if args.mode == 'generate':
            width = 1 << args.width
            tasks = ((side, k, i, min(i+width, stop)) for side, k, start, stop in
                     spans(args.from_shift, args.to_shift)
                     for i in range(start, stop, width))
            with gzip.open(args.file, 'xt', compresslevel=3) as stream:
                print(json.dumps([SCHEMA, args.from_shift, args.to_shift]), file=stream)
                for rows in process(pool, generate_chunk, tasks, args.workers):
                    for row in rows:
                        print(json.dumps(row, separators=(',', ':')), file=stream)
                    count = len(rows)
                    points = sum(row[3]-row[2] for row in rows)
                    progress(blocks+count, covered+points)
                    blocks += count
                    covered += points
        else:
            for block_count, count in process(pool, replay, read_proof(args.file), args.workers):
                progress(blocks+block_count, covered+count)
                blocks += block_count
                covered += count
    print(json.dumps(dict(status='VERIFIED' if args.mode == 'verify' else 'GENERATED',
                          midpoints=covered, blocks=blocks, seconds=round(perf_counter()-start_time, 3))))


if __name__ == '__main__':
    main()
