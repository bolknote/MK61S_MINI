#!/usr/bin/env python3
"""Check pow midpoint separation over all y and scales for significand pairs."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from functools import cache
from itertools import repeat
import json
from math import isqrt
from time import monotonic

from midpoint_grid import FixedInterval


BASE_UNIT = 1 << 52
MIDPOINT_UNIT = 1 << 53
DENOMINATOR_SHIFT = 116
Q = 1 << DENOMINATOR_SHIFT
P_LIMIT = 1 << (63 + DENOMINATOR_SHIFT)
GAP = 16300
RADIUS = 2*(P_LIMIT-1)+2*Q+1
MIN_PRECISION = (2*RADIUS).bit_length()
MAX_PRECISION = GAP-DENOMINATOR_SHIFT-2


def require(condition, message):
    if not condition:
        raise ValueError(message)


@cache
def logarithm_grid(precision):
    grid = FixedInterval(precision + 32)
    ln2 = grid.log(2, 1)
    require(2 * ln2[0] > grid.unit, 'ln(2) lower bound failed')
    return grid, ln2


def log2_approx(coefficient, unit, precision):
    grid, ln2 = logarithm_grid(precision)
    low, high = grid.divide(grid.log(coefficient, unit), ln2)
    lower, upper = low >> 32, -(-high >> 32)
    require(0 <= upper-lower <= 2, 'fixed-point logarithm enclosure is too wide')
    return lower


def dual_witness(modulus, x_log):
    """Suggest t,s with s = t*x_log mod modulus and small weighted length."""
    old_s, s = modulus, x_log
    old_t, t = 0, 1
    best = s, t
    best_cost = s*P_LIMIT+RADIUS
    while abs(t)*RADIUS < best_cost:
        cost = abs(t)*RADIUS+s*P_LIMIT
        if cost < best_cost:
            best = s, t
            best_cost = cost
        if not s:
            break
        quotient, remainder = divmod(old_s, s)
        old_s, s = s, remainder
        old_t, t = t, old_t-quotient*t
    require((best[1]*x_log-best[0]) % modulus == 0, 'invalid dual witness')
    return best


def floor_sum(n, modulus, step, start):
    """Sum floor((start+i*step)/modulus) for 0 <= i < n by Euclidean division."""
    total = 0
    while True:
        quotient, step = divmod(step, modulus)
        total += quotient*n*(n-1)//2
        quotient, start = divmod(start, modulus)
        total += quotient*n
        end = step*n+start
        if end < modulus:
            return total
        n, start = divmod(end, modulus)
        modulus, step = step, modulus


def near_count(n, modulus, step, start, radius):
    require(0 <= 2*radius < modulus, 'modular intervals overlap')
    return (floor_sum(n, modulus, step, start+radius)
            - floor_sum(n, modulus, step, start-radius-1))


def odd_part(coefficient):
    return coefficient//(coefficient & -coefficient)


def normalized_equalities(base, midpoint):
    """Count P in (-P_LIMIT,P_LIMIT) for which the normalized form is an integer."""
    a, b = odd_part(base), odd_part(midpoint)
    if b == 1:
        return 2*P_LIMIT-1 if a == 1 else 1  # P=0 in the relaxed grid.
    if a == 1:
        return 0
    # a^P = b^Q. With P/Q=u/v reduced, a=c^v and b=c^u. Since c is
    # odd and at least 3, v is a power of two at most 32 and u at most 34.
    while True:
        power = a
        while power < b:
            power *= a
        if power == b:
            return 1
        root = isqrt(a)
        if root*root != a:
            return 0
        a = root


class BaseCheck:
    def __init__(self, base, precision):
        self.base = base
        self.modulus = 1 << precision
        self.x_log = log2_approx(base, BASE_UNIT, precision)
        # The original exponent is P/Q, with |P| < P_LIMIT. Since
        # ln(2)>1/2 and precision+117<GAP, the guard fits in one unit.
        s, t = dual_witness(self.modulus, self.x_log)
        self.dual_limit = (s*(P_LIMIT-1)+abs(t)*RADIUS) >> DENOMINATOR_SHIFT
        self.dual_multiplier = t
        self.dual_modulus = self.modulus >> DENOMINATOR_SHIFT

    def separated(self, midpoint, m_log):
        """Return the proof rule or the count of remaining modular candidates."""
        residue = (self.dual_multiplier*m_log) % self.dual_modulus
        if self.dual_limit < min(residue, self.dual_modulus-residue):
            return 'dual', 0
        count = near_count(2*P_LIMIT-1, self.modulus, self.x_log,
                           (1-P_LIMIT)*self.x_log-Q*m_log, RADIUS)
        equalities = normalized_equalities(self.base, midpoint) if count else 0
        require(count >= equalities, 'the directed enclosure lost an exact equality')
        # At a normalized equality, an actual nonzero difference is
        # an integer multiple of ln(2)/Q, which exceeds the guard.
        return ('euclidean', 0) if count == equalities else ('open', count-equalities)


def check_rows(bases, midpoints, precision):
    dual = euclidean = open_pairs = 0
    first_open = None
    for base in bases:
        check = BaseCheck(base, precision)
        for midpoint, m_log in midpoints:
            rule, remaining = check.separated(midpoint, m_log)
            if rule == 'dual':
                dual += 1
            elif rule == 'euclidean':
                euclidean += 1
            else:
                open_pairs += 1
                if first_open is None:
                    first_open = [base, midpoint, remaining]
    return dual, euclidean, open_pairs, first_open


def check_block(x_first, x_stop, m_first, m_stop, precision, workers):
    require(__debug__, 'Python assertions must be enabled')
    require(BASE_UNIT <= x_first < x_stop <= 2*BASE_UNIT, 'invalid base significand span')
    require(MIDPOINT_UNIT <= m_first < m_stop <= 2*MIDPOINT_UNIT,
            'invalid midpoint significand span')
    require(MIN_PRECISION <= precision <= MAX_PRECISION,
            'invalid precision for the scaled guard')
    require(workers > 0, 'expected positive workers')
    # Cache at most one tile of midpoint logarithms at a time.
    started = monotonic()
    row_size = (x_stop-x_first+4*workers-1)//(4*workers)
    rows = [range(x, min(x+row_size, x_stop)) for x in range(x_first, x_stop, row_size)]
    dual = euclidean = opened = 0
    first_open = None
    context = ProcessPoolExecutor(max_workers=workers) if workers > 1 else nullcontext()
    with context as pool:
        evaluate = pool.map if pool else map
        tile = 1 << 14
        for first in range(m_first, m_stop, tile):
            midpoints = [(m, log2_approx(m, MIDPOINT_UNIT, precision))
                         for m in range(first, min(first+tile, m_stop))]
            for by_dual, by_euclidean, unproved, example in evaluate(
                    check_rows, rows, repeat(midpoints), repeat(precision)):
                dual += by_dual
                euclidean += by_euclidean
                opened += unproved
                if first_open is None:
                    first_open = example
    require(dual+euclidean+opened == (x_stop-x_first)*(m_stop-m_first), 'incomplete block')
    return dict(status='VERIFIED_BLOCK' if not opened else 'INCOMPLETE_BLOCK',
                x=[x_first, x_stop], m=[m_first, m_stop], precision=precision,
                gap_bits=GAP, dual=dual, euclidean=euclidean, open=opened,
                first_open=first_open,
                elapsed_s=round(monotonic()-started, 3))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('x_first', 'x_stop', 'm_first', 'm_stop'):
        parser.add_argument(name, type=lambda v: int(v, 0))
    parser.add_argument('--precision', type=int, default=512)
    parser.add_argument('--workers', type=int, default=1)
    args = parser.parse_args()
    if not __debug__:
        parser.error('Python assertions must be enabled')
    try:
        result = check_block(**vars(args))
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True))
    return 2 if result['open'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
