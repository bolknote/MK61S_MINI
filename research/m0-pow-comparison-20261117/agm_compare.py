#!/usr/bin/env python3
"""Compare binary64 powers with RNE midpoints by directed AGM iteration."""

import argparse
from fractions import Fraction
from functools import cache, lru_cache
from itertools import product
import json
from math import isqrt

from midpoint_grid import FixedInterval, ceil_div
from modular_log_compare import midpoint_equal, operands
from radical_compare import Directed, Dyadic


MIN_PRECISION = 64
GAP_OVERHEAD = 78
IDENTITY = ((1, 0), (0, 1))
BASIS_LIMIT = 16
SEPARATION_GRID = FixedInterval(96)
SEPARATION_LN2 = SEPARATION_GRID.log(2, 1)


def settings(precision):
    if precision < MIN_PRECISION:
        raise ValueError('at least 64 fractional bits required')
    scale = ceil_div(precision, 2)+(precision+8).bit_length()
    reciprocal_limit = 2*(scale+3)
    convergence = (precision+8).bit_length()
    steps = scale.bit_length()+convergence
    work_bits = precision+5+(steps+2).bit_length()+reciprocal_limit.bit_length()
    # Check the scaled inequalities without ever constructing a P-bit integer.
    if not (scale+3 <= precision+8 and 2*scale >= precision+(precision+8).bit_length()+6
            and 3*((1 << convergence)-1) >= precision+reciprocal_limit.bit_length()+4):
        raise ArithmeticError('AGM accuracy budget')
    return scale, steps, work_bits


def scaled_log(numerator, denominator, precision, parameters):
    """Enclose (2/pi)*ln(2**(scale+2)*numerator/denominator) in Qprecision."""
    if not 0 < denominator <= numerator <= 2*denominator:
        raise ValueError('AGM argument outside [1,2]')
    scale, steps, work_bits = parameters
    down = Directed(work_bits, False)
    inverse = down.ratio(denominator, numerator)
    a, b = down.one, Dyadic(inverse.coefficient, inverse.scale-scale)
    for _ in range(steps):
        total = down.add(a, b)
        a, b = Dyadic(total.coefficient, total.scale-1), down.root(a, b)

    # One output ulp covers both the error in the lower a_n and the
    # positive elliptic remainder. The reciprocal of b_n is already upper.
    lo = (1 << (precision-a.scale))//a.coefficient-1
    hi = ceil_div(1 << (precision-b.scale), b.coefficient)
    if not 0 < hi-lo <= 3:
        raise ArithmeticError('AGM enclosure is wider than proved')
    return lo, hi


@lru_cache(maxsize=8)
def fixed_logs(precision):
    parameters = settings(precision)
    return (scaled_log(1, 1, precision, parameters),
            scaled_log(2, 1, precision, parameters))


def log_coefficients(a, ae, b, be, p, q):
    ad, bd = a.bit_length()-1, b.bit_length()-1
    shift = p*(ae+ad)-q*(be+bd)
    # The coefficients sum to zero, so the scaled logs' common constant drops out.
    coefficients = {(1, 1): q-p-shift, (2, 1): shift}
    for key, coeff in (((a, 1 << ad), p), ((b, 1 << bd), -q)):
        coefficients[key] = coefficients.get(key, 0)+coeff
    return coefficients


def side(x, y, lower, precision):
    """Return the correct side including ties, or zero for overlap."""
    parameters = settings(precision)
    a, ae, b, be, p, q = operands(x, y, lower)
    if midpoint_equal(a, ae, b, be, p, q):
        return 1 if lower & 1 else -1

    lo = hi = 0
    for mantissa, coefficient in log_coefficients(a, ae, b, be, p, q).items():
        if not coefficient:
            continue
        if mantissa in ((1, 1), (2, 1)):
            ends = fixed_logs(precision)[mantissa[0]-1]
        else:
            ends = scaled_log(*mantissa, precision, parameters)
        bottom, top = ends if coefficient > 0 else ends[::-1]
        lo += coefficient*bottom
        hi += coefficient*top
    if lo >= 0:
        return 1
    if hi <= 0:
        return -1
    return 0


def separation_log(value):
    """Enclose a positive rational's logarithm on SEPARATION_GRID."""
    exponent = value.numerator.bit_length()-value.denominator.bit_length()
    if value < Fraction(2)**exponent:
        exponent -= 1
    reduced = value/Fraction(2)**exponent
    lo, hi = SEPARATION_GRID.log(reduced.numerator, reduced.denominator)
    ln2_lo, ln2_hi = SEPARATION_GRID.scale(SEPARATION_LN2, exponent)
    return (Fraction(lo+ln2_lo, SEPARATION_GRID.unit),
            Fraction(hi+ln2_hi, SEPARATION_GRID.unit))


def separation_root(value, upper):
    """Directed square root of a positive rational on SEPARATION_GRID."""
    unit = SEPARATION_GRID.unit
    scaled = value.numerator*unit*unit
    root = isqrt(scaled//value.denominator)
    return Fraction(root+int(upper and root*root*value.denominator < scaled), unit)


@cache
def laurent_parameters(rho):
    mu = Fraction(5, 8)
    sigma = (1+2*mu-mu*mu)/2
    log_lo, log_hi = separation_log(Fraction(rho))
    return mu, sigma, log_lo, log_hi, sigma*log_lo, sigma*log_hi


def laurent_gap(a1, a2, b, shift, rho):
    """Upper bound -log2(|Delta|) using Laurent's Theorem 2 for D=1."""
    mu, sigma, log_lo, log_hi, lam_lo, lam_hi = laurent_parameters(rho)
    ln2_lo, ln2_hi = (Fraction(n, SEPARATION_GRID.unit) for n in SEPARATION_LN2)
    a = a1*a2
    assert min(a1, a2) >= 1 and a >= lam_hi**2 and lam_lo > 0
    h = max(separation_log(b*lam_hi)[1]+Fraction(181, 100), lam_hi, ln2_hi/2)
    H = (h+log_lo)/lam_hi
    s = separation_root(1+1/(4*H**2), True)
    omega, theta = 2*(1+s), s+1/(2*H)
    numerator = 8*lam_hi*separation_root(separation_root(omega**5*theta, True), True)
    radical = (omega**2/9+numerator/(3*separation_root(a*H, False))
               +4*(1/a1+1/a2)*lam_hi*omega/(3*H))
    C = mu/(lam_lo**3*sigma)*(omega/6+separation_root(radical, True)/2)**2
    C_prime = separation_root(C*sigma*omega*theta/(lam_lo**3*mu), True)
    t = h+log_hi
    loss = C*t*t*a+separation_root(omega*theta, True)*t+separation_log(C_prime*t*t*a)[1]
    assert loss > 0
    # Divide Lambda by q <= 2**shift. Use a strict integer bound.
    return shift+int(loss/ln2_lo)+1


def separation_cell(lo, hi, denominator, shift, rho, bases, rows):
    unit = SEPARATION_GRID.unit
    limit = 746*unit
    # One grid ulp covers 2**-192 when passing to the near-midpoint case.
    x_log = min(limit, ceil_div((limit+1)*denominator, lo))
    m_log = min(limit, ceil_div(hi*x_log, denominator)+1)
    ln2_hi = SEPARATION_LN2[1]
    x_height = min(limit, x_log+53*ln2_hi)
    m_height = min(limit, m_log+54*ln2_hi)
    parameters = {}
    for u, v in rows:
        distance = max(abs(u*denominator-v*lo), abs(u*denominator-v*hi))
        ell = min(ceil_div(distance*x_log, denominator)+v, u*x_log+v*m_log)
        height = min(u*x_height+v*m_height, ell+(53*u+54*v)*ln2_hi)
        parameters[u, v] = (max(unit, 2*height+(rho-1)*ell), distance)

    # Every candidate is a unimodular basis. Minimize the height product.
    first, second = min(bases, key=lambda basis: parameters[basis[0]][0]*parameters[basis[1]][0])
    A1, d1 = parameters[first]
    A2, d2 = parameters[second]
    a1, a2 = Fraction(A1, unit), Fraction(A2, unit)
    scale = Fraction(1 << shift, denominator)
    # The other row gives each coefficient, and the denominators in b are crossed.
    return laurent_gap(a1, a2, scale*(d2/a2+d1/a1), shift, rho)


@cache
def separation_by_exponent():
    """Cover all active binades with the two-logarithm separation theorem."""
    bases = tuple(((u, v), (w, z)) for u, v, w, z in product(range(BASIS_LIMIT+1), repeat=4)
                  if u*z-v*w == 1)
    rows = sorted({row for basis in bases for row in basis})
    assert IDENTITY in bases and 1075*SEPARATION_LN2[1] < 746*SEPARATION_GRID.unit
    # With two nonzero terms of the same sign, the inverse basis change
    # would force ell_m <= 2*BASIS_LIMIT*q*2**-192.
    assert 2*BASIS_LIMIT < 1 << (192-116-54)
    # A zero coefficient forces a one-log form with height <= 2*BASIS_LIMIT*746.
    assert 2*BASIS_LIMIT*746*SEPARATION_GRID.unit < (35000-116)*SEPARATION_LN2[0]
    assert 2*(1075*(1 << 63)+1076) < 1 << 75
    assert 2*3*(1 << 75) < 1 << GAP_OVERHEAD

    bounds = []
    for exponent in range(-64, 63):
        shift = max(0, 52-exponent)
        cells = 128 if -6 <= exponent <= 5 else 1
        rho = 8 if -10 <= exponent <= 10 else 24
        step = Fraction(2)**exponent/cells
        band_bases, band_rows = (bases, rows) if cells > 1 else ((IDENTITY,), IDENTITY)
        bits = max(separation_cell(i*step.numerator, (i+1)*step.numerator, step.denominator,
                                   shift, rho, band_bases, band_rows) for i in range(cells, 2*cells))
        bounds.append((exponent, max(35000, bits)))
    return tuple(bounds)


def exact_side(x, y, lower):
    """Refine until resolved, with an explicit all-input cap on host precision."""
    operands(x, y, lower)
    exponent = ((y >> 52) & 2047)-1023
    cap = separation_by_exponent()[exponent+64][1]+GAP_OVERHEAD
    precision = MIN_PRECISION
    while True:
        answer = side(x, y, lower, precision)
        if answer:
            return answer, precision
        if precision == cap:
            raise ArithmeticError('comparison exceeded the certified precision')
        precision = min(2*precision, cap)


def uniform_work():
    exponent, gap = max(separation_by_exponent(), key=lambda band: band[1])
    precision = gap+GAP_OVERHEAD
    _, steps, work_bits = settings(precision)
    passes = (ceil_div(precision, MIN_PRECISION)-1).bit_length()+1
    total_steps = steps+sum(settings(MIN_PRECISION << i)[1] for i in range(passes-1))
    return dict(gap_bits=gap, worst_y_binade_exponent=exponent, precision=precision,
                significand_bits=work_bits, bytes_per_significand=ceil_div(work_bits, 8),
                maximum_radicand_bits=2*work_bits, maximum_passes=passes,
                maximum_square_roots_per_pass=4*steps,
                maximum_sums_per_pass=4*steps, maximum_divisions_per_pass=12,
                maximum_square_roots_all_passes=4*total_steps,
                practical_rp2040_bound_established=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('point', metavar='HEX', nargs='*', type=lambda value: int(value, 16),
                        help='binary64 encodings x y lower')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--precision', type=int, default=192)
    mode.add_argument('--exact', action='store_true', help='refine using dynamically sized host integers')
    mode.add_argument('--budget', action='store_true', help='compute the cap without allocating large limbs')
    args = parser.parse_args()
    if args.budget and not args.point:
        result = uniform_work()
    elif not args.budget and len(args.point) == 3:
        answer, precision = (exact_side(*args.point) if args.exact else
                             (side(*args.point, args.precision), args.precision))
        result = dict(side=answer, precision=precision)
    else:
        parser.error('give either three encodings or --budget')
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
