#!/usr/bin/env python3
"""Compare binary64 powers with RNE midpoints by directed AGM iteration."""

import argparse
from fractions import Fraction
from functools import cache, lru_cache
import json
from math import ceil

from midpoint_grid import FixedInterval, ceil_div
from modular_log_compare import midpoint_equal, operands
from radical_compare import Directed, Dyadic


MIN_PRECISION = 64
GAP_OVERHEAD = 78
LOG_BASES = (
    ((1, 0), (0, 1)),
    ((1, 0), (1, 1)),
    ((1, 0), (2, 1)),
    ((1, 1), (0, 1)),
    ((1, 1), (1, 2)),
    ((1, 2), (0, 1)),
    ((2, 1), (1, 1)),
)


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


@cache
def separation_by_exponent():
    """Cover each active binade using Laurent's Corollary 2 and short changes of basis."""
    grid = FixedInterval(96)
    ln2 = grid.log(2, 1)
    ln2_lo, ln2_hi = (Fraction(value, grid.unit) for value in ln2)
    epsilon = Fraction(1, 1 << 192)
    assert 1075*ln2_hi < 746
    assert all(u*z-v*w == 1 and (u+w)*(1 << 116)*epsilon < Fraction(1, 1 << 54)
               for (u, v), (w, z) in LOG_BASES)
    assert 2*(1075*(1 << 63)+1076) < 1 << 75
    assert 2*3*(1 << 75) < 1 << GAP_OVERHEAD

    def loss_bits(height, coefficients, shift):
        # Crossed denominators in Laurent's b'. Account separately for
        # a coefficient vanishing after the integral basis change.
        a, b = height
        u, v = coefficients
        b0 = (u/b+v/a)*(1 << shift)
        b0_exp = b0.numerator.bit_length()-b0.denominator.bit_length()
        if b0 < Fraction(2)**b0_exp:
            b0_exp -= 1
        scaled = b0/Fraction(2)**b0_exp
        assert 1 <= scaled < 2
        unit_log = ln2_hi if b0_exp >= 0 else ln2_lo
        log_b0 = b0_exp*unit_log+Fraction(grid.log(scaled.numerator, scaled.denominator)[1], grid.unit)
        h = max(30, log_b0+Fraction(19, 50))
        loss = max(Fraction(179, 10)*h*h*a*b, a, b)
        return max(192, shift+int(loss/ln2_lo)+1)

    def bound(lo, hi, shift, bases):
        x_log = min(746, (746+epsilon)/lo)
        m_log = min(746, 746*hi+epsilon)
        x_height = min(746, ceil(x_log+53*ln2_hi))
        m_height = min(746, ceil(m_log+54*ln2_hi))
        choices = []
        for basis in bases:
            distance = tuple(max(abs(u-v*lo), abs(u-v*hi)) for u, v in basis)
            height = tuple(min(u*x_height+v*m_height,
                               ceil(d*x_log+v*epsilon+(53*u+54*v)*ln2_hi))
                           for (u, v), d in zip(basis, distance))
            # The second row's slope gives the first coefficient of the form.
            choices.append(loss_bits(height, distance[::-1], shift))
        return min(choices)

    rows = []
    for exponent in range(-64, 63):
        shift = max(0, 52-exponent)
        cells = 32 if -8 <= exponent <= 5 else 1
        step = Fraction(2)**exponent/cells
        bases = LOG_BASES if cells > 1 else LOG_BASES[:1]
        bits = max(bound(i*step, (i+1)*step, shift, bases) for i in range(cells, 2*cells))
        rows.append((exponent, bits))
    assert len(rows) == 127
    return tuple(rows)


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
