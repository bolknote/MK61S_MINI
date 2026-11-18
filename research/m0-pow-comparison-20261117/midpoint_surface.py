#!/usr/bin/env python3
"""Certify rectangular base/midpoint blocks for y=p/2**52, p odd."""
import argparse
from itertools import product
import json
from math import comb
from pathlib import Path
from random import Random
from time import perf_counter

from midpoint_grid import FixedInterval, add, ceil_div, interval_series_product

DENOMINATOR = 1 << 52
GAP_BITS = 900


def geometry(x_block, m_block, width, degree, work_bits):
    if not (1 <= width <= 50 and 1 <= degree <= 8 and 16 <= work_bits <= 256):
        raise ValueError('unsupported block or polynomial size')
    if not (0 <= x_block < 1 << (52-width) and 0 <= m_block < 1 << (52-width)):
        raise ValueError('block outside its binade')
    half = 1 << (width-1)
    x_center = DENOMINATOR+(2*x_block+1)*half
    m_center = 2*(DENOMINATOR+(2*m_block+1)*half)+1
    powers = [(i, j, k) for i in range(degree+1) for j in range(degree+1-i)
              for k in range(degree+1-i-j)]
    shrink = 51-width
    terms = max(degree+1, ceil_div(56*degree+work_bits+3, shrink))
    if GAP_BITS < 53+56*degree+degree.bit_length()+work_bits:
        raise ValueError('insufficient precision for the vertical displacement')
    return half, x_center, m_center, powers, terms


def log_series(grid, factor, normalized, center, half, count):
    constant = add(grid.scale(grid.log(2, 1), factor), grid.log(center, normalized))
    return [constant]+[grid.rational((-1)**(n-1)*half**n, n*center**n)
                       for n in range(1, count)]


def surface_series(half, x_center, m_center, terms, degree, work_bits, origin=None):
    grid = FixedInterval(64*degree+work_bits+128)
    log_x = log_series(grid, 1, DENOMINATOR, x_center, half, terms)
    log_m = log_series(grid, 2, 2*DENOMINATOR, m_center, 2*half, terms)
    if origin is None:
        quotient = grid.divide(log_m[0], log_x[0])
        origin = (sum(quotient)*DENOMINATOR)//(2*grid.unit)
    if type(origin) is not int or not DENOMINATOR//2 <= origin <= 4*DENOMINATOR:
        raise ValueError('invalid numerator origin')

    inverse_x = [grid.divide(grid.rational(1), log_x[0])]
    for n in range(1, terms):
        total = (0, 0)
        for j in range(1, n+1):
            total = add(total, grid.multiply(log_x[j], inverse_x[n-j]))
        inverse_x.append(grid.divide(grid.scale(total, -1), log_x[0]))

    one = [grid.rational(1)]+[(0, 0)]*(terms-1)
    left, right = [one], [one]
    for _ in range(degree):
        left.append(interval_series_product(left[-1], inverse_x, grid))
        right.append(interval_series_product(right[-1], log_m, grid))

    # F = q*log(m(v))/log(x(u)). Expand (F-origin)**k as a sum of
    # separable products, with the two Taylor degrees each below terms.
    series = []
    for k in range(degree+1):
        result = [[(0, 0) for _ in range(terms)] for _ in range(terms)]
        for a in range(k+1):
            factor = comb(k, a)*(-origin)**(k-a)*DENOMINATOR**a
            for i, left_entry in enumerate(left[a]):
                for j, right_entry in enumerate(right[a]):
                    value = grid.scale(grid.multiply(left_entry, right_entry), factor)
                    result[i][j] = add(result[i][j], value)
        series.append(result)
    return grid, origin, series


def monomial_coefficients(half, terms, powers, series, grid):
    return [[grid.scale(series[k][u-i][v-j], half**(i+j))
             if u >= i and v >= j else (0, 0)
             for u, v in product(range(terms), repeat=2)]
            for i, j, k in powers]


def modular_certificate(powers, polynomials, modulus, origin):
    """Select relations with no common zero at any allowed residue."""
    residues = range(modulus)
    offsets = range((1-origin) % 2, modulus, 2) if modulus % 2 == 0 else residues
    values = [[pow(i, a, modulus)*pow(j, b, modulus)*pow(t, k, modulus) % modulus
               for a, b, k in powers] for i, j, t in product(residues, residues, offsets)]
    selected = []
    for polynomial in polynomials:
        remaining = [row for row in values if sum(a*b for a, b in zip(row, polynomial)) % modulus == 0]
        if len(remaining) < len(values):
            selected.append(polynomial)
            values = remaining
        if not values:
            return selected
    return None


def verify_block(row):
    x_block, m_block, width, degree, work_bits = (
        row[key] for key in ('x_block', 'm_block', 'width', 'degree', 'work_bits'))
    half, x_center, m_center, powers, terms = geometry(x_block, m_block, width, degree, work_bits)
    grid, origin, series = surface_series(half, x_center, m_center, terms, degree,
                                          work_bits, row['p_origin'])
    coefficients = monomial_coefficients(half, terms, powers, series, grid)
    polynomials = row['polynomials']
    modulus = row['modulus']
    if type(modulus) is not int or not 2 <= modulus <= 13 or not polynomials:
        raise ValueError('invalid modular certificate')

    # On |u|,|v| <= R=2**(51-width) the relative increments of x and m
    # are <=1/4. Each complex log changes by <=1/3. As ln(2)>2/3
    # and ln(8)<3, |F|<10*q and |F-origin|<16*q=2**56.
    # |I|=|half*u| and |J|=|half*v| are <=2**50 on those disks.
    # By Cauchy's estimate the sum omitted by rectangular truncation
    # of each monomial is <=2**(56*degree)*2*R**(-terms)/(1-1/R)**2
    # <=2**(-work_bits). On the real block |p-F| < 2**(53-GAP_BITS).
    # Bounding the monomial derivative in T over the vertical segment
    # makes the induced error <=2**(-work_bits) as well.
    error = 2 << (grid.precision-work_bits)
    for polynomial in polynomials:
        if (len(polynomial) != len(powers) or not any(polynomial)
                or any(type(a) is not int for a in polynomial)):
            raise ValueError('invalid integer polynomial')
        norm = error*sum(map(abs, polynomial))
        active = [(a, c) for a, c in zip(polynomial, coefficients) if a]
        for offset in range(terms**2):
            interval = (0, 0)
            for a, c in active:
                interval = add(interval, grid.scale(c[offset], a))
            norm += max(map(abs, interval))
        if norm >= grid.unit:
            raise ValueError('polynomial is not strictly smaller than one')
    if modular_certificate(powers, polynomials, modulus, origin) is None:
        raise ValueError('polynomials have a common modular zero')


def verify_interval_margin():
    # General width of the existing 1024-bit enclosure, in units of
    # 2**-1024. A logarithmic width bound is w/(1-w).
    precision = 1024
    q_width = (12*(precision+16)+4+1074)*(1 << 64)+2
    exp_width = 4*(precision+16)+2
    width = 4*(q_width+1155)+4*exp_width
    if width << GAP_BITS >= (1 << precision)-width:
        raise ValueError('the enclosure may be wider than the separated midpoint strip')


def generate_block(x_block, m_block, width, degree, work_bits):
    # Only the heuristic polynomial search needs FLINT. The verifier
    # recomputes every interval and modular exclusion with Python integers.
    from flint import fmpz_mat

    half, x_center, m_center, powers, terms = geometry(x_block, m_block, width, degree, work_bits)
    grid, origin, series = surface_series(half, x_center, m_center, terms, degree, work_bits)
    coefficients = monomial_coefficients(half, terms, powers, series, grid)
    scale = 1 << work_bits
    penalty = terms**2+2
    lattice = [[((lo+hi)*scale)//(2*grid.unit) for lo, hi in vector]
               + [penalty*int(i == j) for j in range(len(powers))]
               for i, vector in enumerate(coefficients)]
    reduced = fmpz_mat(lattice).lll(delta=0.99)
    small = []
    for i in range(len(powers)):
        polynomial = [int(reduced[i, terms**2+j])//penalty for j in range(len(powers))]
        estimate = sum(abs(int(reduced[i, j])) for j in range(terms**2))
        if estimate+(2*terms**2+2)*sum(map(abs, polynomial)) < scale:
            small.append(polynomial)
    if not small:
        return None
    for modulus in (2, 3, 5, 7, 11, 13):
        selected = modular_certificate(powers, small, modulus, origin)
        if selected:
            row = dict(x_block=x_block, m_block=m_block, width=width, degree=degree,
                       work_bits=work_bits, p_origin=origin, modulus=modulus, polynomials=selected)
            verify_block(row)
            return row
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    verify = modes.add_parser('verify')
    verify.add_argument('path', type=Path)
    sample = modes.add_parser('sample')
    sample.add_argument('--width', type=int, required=True)
    sample.add_argument('--degree', type=int, required=True)
    sample.add_argument('--work-bits', type=int, default=128)
    sample.add_argument('--samples', type=int, default=32)
    sample.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verify_interval_margin()
    if args.mode == 'verify':
        rows = json.loads(args.path.read_text())['certificates']
        if not rows or len({row['width'] for row in rows}) != 1:
            parser.error('expected a nonempty certificate at one block width')
        seen = set()
        for row in rows:
            verify_block(row)
            block = row['x_block'], row['m_block']
            if block in seen:
                parser.error('duplicate block in certificate')
            seen.add(block)
        print(f'verified {len(rows)} disjoint blocks, {len(rows) << (2*rows[0]["width"])} '
              f'base/midpoint pairs, log gap > 2**-{GAP_BITS}')
        return

    # Uniform fixed-seed sample of disjoint blocks in x=[3,3.25),
    # m=[5,5.5), where 1<log(m)/log(x)<2.
    if not 1 <= args.width <= 49 or not 1 <= args.samples <= 1 << (2*(49-args.width)):
        parser.error('sample size or block size outside the target rectangle')
    rng = Random(2040)
    extent = 1 << (49-args.width)
    blocks = set()
    while len(blocks) < args.samples:
        blocks.add((4*extent+rng.randrange(extent), 2*extent+rng.randrange(extent)))
    start = perf_counter()
    certificates = []
    for x_block, m_block in sorted(blocks):
        row = generate_block(x_block, m_block, args.width, args.degree, args.work_bits)
        if row is not None:
            certificates.append(row)
    elapsed = perf_counter()-start
    result = dict(width=args.width, degree=args.degree, work_bits=args.work_bits,
                  samples=args.samples, seconds=elapsed, certificates=certificates)
    args.output.write_text(json.dumps(result, separators=(',', ':'))+'\n')
    print(f'certified {len(certificates)}/{args.samples} blocks of width 2**{args.width}'
          f' at degree {args.degree} in {elapsed:.3f} s')


if __name__ == '__main__':
    main()
