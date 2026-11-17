#!/usr/bin/env python3
"""Certify binary64 base blocks at the first rounding midpoint below one."""
import argparse
from fractions import Fraction
from functools import lru_cache
import json
from pathlib import Path
from time import perf_counter

DENOMINATOR = 1 << 116
MIDPOINT_DENOMINATOR = 1 << 54
GAP_BITS = 900
STRIP_BITS = GAP_BITS-116+8
Y_OFFSET_BITS = 44


def ceil_div(a, b):
    return -(-a//b)


def block_geometry(e, split, index, degree, work_bits):
    assert all(type(value) is int for value in (e, split, index, degree, work_bits))
    assert -1074 <= e <= -739 or 738 <= e <= 1023
    bits = min(52, e+1074)
    assert 3 <= split < bits and 0 <= index < 1 << split
    assert 1 <= degree <= 30 and 1 <= work_bits <= 512
    half = 1 << (bits-split-1)
    center = (1 << bits)+(2*index+1)*half
    encoding_start = ((e+1023) << 52) if e >= -1022 else 1 << bits
    encoding_start += 2*index*half
    powers = [(i, j) for i in range(degree+1) for j in range(degree+1-i)]
    monomial_bits = degree*max(bits-2, Y_OFFSET_BITS)
    terms = ceil_div(monomial_bits+work_bits+2, split-1)
    # Taylor tail per monomial, including the geometric sum, <2^-work_bits.
    assert (split-1)*terms >= monomial_bits+work_bits+2
    assert terms > degree
    # At a candidate point the change in each monomial due to vertical
    # displacement is <2^-work_bits, by bounding its derivative in J.
    assert degree*max(bits-2, Y_OFFSET_BITS+1)+degree.bit_length()+work_bits+2 < STRIP_BITS
    return encoding_start, center, half, bits, powers, terms


class FixedInterval:
    """Closed intervals with endpoints on an exact binary fixed-point grid."""

    def __init__(self, precision):
        self.precision = precision
        self.unit = 1 << precision

    def rational(self, numerator, denominator=1):
        scaled = numerator*self.unit
        return scaled//denominator, ceil_div(scaled, denominator)

    def scale(self, a, factor):
        return (a[0]*factor, a[1]*factor) if factor >= 0 else (a[1]*factor, a[0]*factor)

    def multiply(self, a, b):
        products = [x*y for x in a for y in b]
        return min(products)//self.unit, ceil_div(max(products), self.unit)

    def divide(self, a, b):
        assert b[0] > 0
        bounds = [x*self.unit for x in a]
        return (min(x//y for x in bounds for y in b),
                max(ceil_div(x, y) for x in bounds for y in b))

    def log(self, numerator, denominator):
        assert denominator <= numerator <= 2*denominator
        t = self.rational(numerator-denominator, numerator+denominator)
        square = self.multiply(t, t)
        power, total = t, (0, 0)
        terms = ceil_div(self.precision+1, 3)
        for n in range(terms):
            divisor = 2*n+1
            total = total[0]+power[0]//divisor, total[1]+ceil_div(power[1], divisor)
            power = self.multiply(power, square)
        # t<=1/3. The tail of 2*atanh(t) is <(3/4)*8^-terms.
        return 2*total[0], 2*total[1]+1


def add(a, b):
    return a[0]+b[0], a[1]+b[1]


@lru_cache(maxsize=12)
def constants(precision):
    grid = FixedInterval(precision)
    logarithm = grid.log(2, 1)
    c = grid.scale(grid.log(MIDPOINT_DENOMINATOR, MIDPOINT_DENOMINATOR-1), DENOMINATOR)
    # For a block in the supported binades |L(0)|>511. On the circle
    # |t|=2^(split-1) the added log has magnitude <=1/3 and |L(t)|>510.
    assert 738*logarithm[0] > 511*grid.unit
    assert 1074*logarithm[1] < 745*grid.unit
    assert 0 < c[0] <= c[1] < (1 << 63)*grid.unit
    assert 2+Fraction(1 << 63, 3*510*511) < 1 << Y_OFFSET_BITS
    return logarithm, c


def exact_series(e, center, half, bits, p_origin, count, degree, precision):
    """Enclose the first count Taylor coefficients using only integers."""
    grid = FixedInterval(precision)
    log2, c = constants(precision)
    sign = 1 if e > 0 else -1
    log_center = add(grid.scale(log2, e), grid.log(center, 1 << bits))
    log_coeffs = [grid.scale(log_center, sign)]
    assert log_coeffs[0][0] > 511*grid.unit
    for k in range(1, count):
        coefficient = grid.rational(half**k, k*center**k)
        log_coeffs.append(grid.scale(coefficient, sign*(-1)**(k-1)))
    quotient = [grid.divide(c, log_coeffs[0])]
    constant_term = add(quotient[0], grid.rational(-p_origin))
    assert max(abs(a) for a in constant_term) < 2*grid.unit
    for k in range(1, count):
        total = (0, 0)
        for i in range(1, k+1):
            total = add(total, grid.multiply(log_coeffs[i], quotient[k-i]))
        quotient.append(grid.divide(grid.scale(total, -1), log_coeffs[0]))
    offset = [constant_term, *quotient[1:]]
    powers = [[grid.rational(1), *([(0, 0)]*(count-1))], offset]
    for _ in range(1, degree):
        polynomial = []
        for k in range(count):
            coeff = (0, 0)
            for i in range(k+1):
                coeff = add(coeff, grid.multiply(offset[i], powers[-1][k-i]))
            polynomial.append(coeff)
        powers.append(polynomial)
    return grid, powers


def vanishes_modulo(powers, polynomial, modulus, x, y):
    return sum((coefficient % modulus)*pow(x, i, modulus)*pow(y, j, modulus)
               for (i, j), coefficient in zip(powers, polynomial)) % modulus == 0


def exclude_residues(powers, polynomials, modulus):
    roots = {(x, y) for x in range(modulus) for y in range(modulus)}
    selected = []
    for polynomial in polynomials:
        remaining = {pair for pair in roots if vanishes_modulo(powers, polynomial, modulus, *pair)}
        if remaining != roots:
            selected.append(polynomial)
            roots = remaining
        if not roots:
            return selected
    return None


def verify_block(row):
    e, split, index, degree, work_bits = (row[k] for k in ('e', 'split', 'block', 'degree', 'work_bits'))
    start, center, half, bits, powers, terms = block_geometry(e, split, index, degree, work_bits)
    assert type(row['p_origin']) is int
    precision = degree*max(bits-2, Y_OFFSET_BITS)+work_bits+116+64
    grid, series = exact_series(e, center, half, bits, row['p_origin'], terms, degree, precision)
    # On the circle, |I|<=2^(bits-2) and |J(t)|<2^44 by constants().
    # Cauchy's estimate gives the tail bound used below. For a candidate
    # integer J the vertical strip accounts for the second unit per term.
    per_term_error = 2 << (precision-work_bits)
    modulus = row['modulus']
    assert type(modulus) is int and 2 <= modulus <= 31
    for polynomial in row['polynomials']:
        assert len(polynomial) == len(powers) and any(polynomial)
        assert all(type(coefficient) is int for coefficient in polynomial)
        coeffs = [(i, j, a*half**i) for (i, j), a in zip(powers, polynomial) if a]
        norm = per_term_error*sum(map(abs, polynomial))
        for k in range(terms):
            total = (0, 0)
            for i, j, coeff in coeffs:
                if k >= i:
                    total = add(total, grid.scale(series[j][k-i], coeff))
            norm += max(map(abs, total))
        assert norm < grid.unit, ('polynomial is not strictly below one', e, index)
    assert exclude_residues(powers, row['polynomials'], modulus) is not None, (
        'polynomials have a common modular zero', e, index)
    return start, start+2*half


def generate_block(e, split, index, degree, work_bits, delta=0.99):
    # The search can use Arb and a heuristic lattice reduction. Every
    # accepted polynomial is replayed by verify_block without either one.
    from flint import arb, arb_series, ctx, fmpz_mat

    _, center, half, bits, powers, terms = block_geometry(e, split, index, degree, work_bits)
    ctx.prec = degree*max(bits-2, Y_OFFSET_BITS)+work_bits+64
    ctx.cap = terms
    log_center = e*arb(2).log()+(arb(center)/(1 << bits)).log()
    c = -DENOMINATOR*(1-arb(1)/MIDPOINT_DENOMINATOR).log()
    origin = int((c/abs(log_center)).mid().floor().fmpz())
    t = arb_series([0, 1], prec=terms)
    log_x = log_center+(1+t*(arb(half)/center)).log()
    offset = (c if e > 0 else -c)/log_x-origin
    series = [arb_series([1], prec=terms)]
    for _ in range(degree):
        series.append(series[-1]*offset)
    scale = 1 << work_bits
    penalty = terms+2
    coefficients = []
    for r, (i, j) in enumerate(powers):
        weighted = series[j]*(scale*half**i)
        snapped = [0]*i+[int(weighted[k].mid().floor().fmpz()) for k in range(terms-i)]
        coefficients.append(snapped+[penalty*int(r == k) for k in range(len(powers))])
    start = perf_counter()
    reduced = fmpz_mat(coefficients).lll(delta=delta)
    elapsed = perf_counter()-start
    small = []
    for r in range(len(powers)):
        polynomial = [int(reduced[r, terms+k])//penalty for k in range(len(powers))]
        estimate = sum(abs(int(reduced[r, k])) for k in range(terms))
        if estimate+(2*terms+2)*sum(map(abs, polynomial)) < scale:
            small.append(polynomial)
    for modulus in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31):
        selected = exclude_residues(powers, small, modulus)
        if selected:
            return dict(e=e, split=split, block=index, degree=degree, work_bits=work_bits,
                        p_origin=origin, modulus=modulus, polynomials=selected), elapsed
    return None, elapsed


def verify(rows):
    max_y = Fraction((1 << 53)-1, DENOMINATOR)
    gap = Fraction(1, 1 << GAP_BITS)
    # Other midpoints are farther from one even allowing this log gap.
    assert 745*max_y+gap < min(Fraction(3, MIDPOINT_DENOMINATOR), Fraction(1, (1 << 53)+1))
    product_counts = []
    for p in (512, 1024):
        # Use the existing fixed-point interval certificate's error model.
        u = Fraction(1, 1 << p)
        q_width = ((12*(p+16)+4+1074)*(1 << 64)+2)*u
        endpoint_width = (4*(p+16)+2)*u
        if p == 1024:
            relative_width = 4*(q_width+1155*u)+4*endpoint_width
            assert relative_width/(1-relative_width) < gap
        # The reduction index is zero for these y. Each directed series
        # step contracts the upper term, rounding up in units of 2^-p.
        assert (Fraction(1, 3)+u)**2+u < Fraction(1, 8)
        assert 745*max_y+q_width < Fraction(1, 1 << 53)
        product_counts.append(2+2*ceil_div(p, 3)+4*ceil_div(p, 53))
    assert product_counts == [384, 766]
    intervals = sorted(verify_block(row) for row in rows)
    assert intervals and all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:])), (
        'empty or overlapping block coverage')
    count = sum(end-start for start, end in intervals)
    print(f'PASS {len(intervals)} blocks, {count} base encodings, log gap > 2^-{GAP_BITS}', flush=True)
    print('Full fixed-point product bounds at 512 and 1024 bits:', *product_counts, flush=True)


def main():
    if not __debug__:
        raise RuntimeError('Run the certificate checker with Python assertions enabled')
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--verify', type=Path)
    mode.add_argument('--generate', type=Path)
    parser.add_argument('--delta', type=float, default=0.99,
                        help='LLL reduction parameter for certificate generation')
    parser.add_argument('--run', action='append', nargs=6, type=int,
                        metavar=('BINADE', 'SPLIT', 'FIRST', 'COUNT', 'DEGREE', 'WORK_BITS'))
    args = parser.parse_args()
    if args.verify is not None:
        verify(json.loads(args.verify.read_text()))
        return
    if not args.run:
        parser.error('--generate requires at least one --run')
    if not 0.25 < args.delta < 1:
        parser.error('--delta must be strictly between 0.25 and 1')
    rows = []
    for e, split, first, count, degree, work_bits in args.run:
        assert count > 0
        for index in range(first, first+count):
            row, elapsed = generate_block(e, split, index, degree, work_bits, args.delta)
            if row is None:
                raise RuntimeError(f'No certificate for binade {e}, split {split}, block {index}')
            rows.append(row)
            print(f'binade {e}, split {split}, block {index}, LLL {elapsed:.3f}s', flush=True)
    verify(rows)
    args.generate.write_text('[\n'+',\n'.join('  '+json.dumps(row) for row in rows)+'\n]\n')


if __name__ == '__main__':
    main()
