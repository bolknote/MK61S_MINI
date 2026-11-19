#!/usr/bin/env python3
"""Exact sign of rational logarithm enclosures without storing their numerators."""

import argparse
from dataclasses import dataclass
from fractions import Fraction
import json
from math import gcd, isqrt
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'dev/tools'))
from certify_m0_pow_power_bounds import uniform_precision_bound
from verify_m0_pow_binary64 import INF, Y_MIN, Y_MAX, dyadic, odd_dyadic
from midpoint_grid import FixedInterval, ceil_div


def order(value):
    return (value > 0)-(value < 0)


@dataclass(frozen=True)
class LogForm:
    base: int
    numerators: tuple
    coefficients: tuple

    @property
    def error_factor(self):
        return sum(map(abs, self.coefficients))

    def integer_width(self, terms):
        # Q = base**terms * terms! is the common positive denominator.
        # Both enclosing numerators have magnitude below 2*error_factor*Q.
        return terms*(self.base.bit_length()-1+(terms-1).bit_length())+self.error_factor.bit_length()+1


def operands(x, y, lower):
    ym = y & ((1 << 63)-1)
    if not (0 < x < INF and 0 <= y < 1 << 64 and Y_MIN <= ym < Y_MAX and 0 <= lower < INF):
        raise ValueError('comparison outside the active pow domain')
    a, ae = odd_dyadic(x)
    b, be = dyadic(lower, midpoint=True)
    numerator, exponent = odd_dyadic(ym)
    p, q = numerator << max(0, exponent), 1 << max(0, -exponent)
    if y >> 63:
        p = -p
    return a, ae, b, be, p, q


def log_form(x, y, lower):
    a, ae, b, be, p, q = operands(x, y, lower)

    # Exact ties need bounded odd powers. Coprime p and q force the
    # odd coefficients to be powers of one integer c with c >= 3.
    if ae*p == be*q:
        if a == b == 1:
            return None
        if 0 < p <= 34 and q <= 32 and a > 1 and b > 1:
            left, right, _, _ = common_factors((a, p), (b, q))
            if not left and not right:
                return None

    aj, bj = a.bit_length(), b.bit_length()
    width = max(aj, bj)
    base = 1 << width
    # x = 2**(ae+aj) * (1-u/base); the same formula applies to m.
    u, v = base-(a << (width-aj)), base-(b << (width-bj))
    return LogForm(base, (base//2, u, v), ((ae+aj)*p-(be+bj)*q, -p, q))


def common_factors(left, right):
    """Cancel all common odd factors without prime factorization."""
    left = [left] if left[0] > 1 else []
    right = [right] if right[0] > 1 else []
    splits = removed = 0
    while True:
        for i, (a, p) in enumerate(left):
            for j, (b, q) in enumerate(right):
                common = gcd(a, b)
                if common == 1:
                    continue
                left.pop(i)
                right.pop(j)
                if a != common:
                    left.append((a//common, p))
                if b != common:
                    right.append((b//common, q))
                if p > q:
                    left.append((common, p-q))
                if q > p:
                    right.append((common, q-p))
                splits += 1
                removed += min(p, q)*(common.bit_length()-1)
                break
            else:
                continue
            break
        else:
            return left, right, splits, removed


def power_bounds(factors, scale):
    lower = scale+sum((a.bit_length()-1)*p for a, p in factors)
    upper = scale+sum(a.bit_length()*p for a, p in factors)
    return lower, upper


def cancelled_powers(x, y, lower, capacity):
    """Try an exact comparison after cancelling common integer powers."""
    if capacity < 1:
        raise ValueError('positive integer comparison capacity required')
    a, ae, b, be, p, q = operands(x, y, lower)
    scale = ae*p-be*q
    ashift, bshift = max(0, scale), max(0, -scale)
    if p > 0:
        left, right, splits, removed = common_factors((a, p), (b, q))
        initial_left = power_bounds([(a, p)] if a > 1 else [], ashift)[1]
        initial_right = power_bounds([(b, q)] if b > 1 else [], bshift)[1]
    else:
        left, right = [], [(f, r) for f, r in ((a, -p), (b, q)) if f > 1]
        splits = removed = 0
        initial_left, initial_right = ashift, power_bounds(right, bshift)[1]
    alo, ahi = power_bounds(left, ashift)
    blo, bhi = power_bounds(right, bshift)
    ahi, bhi = min(ahi, initial_left-removed), min(bhi, initial_right-removed)
    width = max(ahi, bhi)+1
    report = dict(original_integer_width=max(initial_left, initial_right)+1,
                  cancelled_integer_width=width, gcd_splits=splits)
    if not left and not right and not scale:
        return (1 if lower & 1 else -1), report
    if alo > bhi or (alo == bhi and left):
        return 1, report
    if blo > ahi or (blo == ahi and right):
        return -1, report
    if width > capacity:
        return 0, report
    av, bv = 1 << ashift, 1 << bshift
    for a, p in left:
        av *= a**p
    for b, q in right:
        bv *= b**q
    return order(av-bv) or (1 if lower & 1 else -1), report


def enclosure_residues(form, terms, modulus):
    """Return residues of both integer endpoints using bounded-size operations."""
    base = form.base % modulus
    u, v, w = (a % modulus for a in form.numerators)
    a, b, c = (weight % modulus for weight in form.coefficients)
    up = vp = wp = factorial = 1
    total = 0
    for j in range(1, terms+1):
        up, vp, wp = up*u % modulus, vp*v % modulus, wp*w % modulus
        weighted = (a*up+b*vp+c*wp) % modulus
        total = (j*base % modulus*total+factorial*weighted) % modulus
        factorial = factorial*j % modulus
    # Each log uses -log(1-z) and 0 <= z <= 1/2. Its omitted tail
    # is strictly smaller than 2**(-terms), before multiplying by c.
    radius = pow(form.base//2, terms, modulus)*factorial % modulus
    radius = radius*(form.error_factor % modulus) % modulus
    return (total-radius) % modulus, (total+radius) % modulus


def modulus_limit(width):
    # M = lcm(1,...,L). For L a power of two, the central binomial
    # divides M, giving log2(M) >= L-log2(L+1). At most L/2+1 maximal
    # prime powers are present, so the sum of floor(log2(m)) suffices.
    limit = 4
    while limit//2-limit.bit_length()-1 < width+1:
        limit *= 2
    return limit


def prime_powers(limit):
    for p in range(2, limit+1):
        if p != 2 and (not p & 1 or any(p % d == 0 for d in range(3, isqrt(p)+1, 2))):
            continue
        m = p
        while m <= limit//p:
            m *= p
        yield p, m


def prefix(width, limit):
    bits = 0
    for p, m in prime_powers(limit):
        yield p, m
        bits += m.bit_length()-1
        if bits > width:
            return
    raise ArithmeticError('insufficient product of moduli')


def inverse_complement(p, m, moduli):
    complement = 1
    for _, other in moduli():
        if other != m:
            complement = complement*other % m
    return pow(complement, m-m//p-1, m)


def crt_sign(fractions, count, limit):
    """Determine if the CRT fraction lies below or above 1/2 modulo one."""
    bits = limit.bit_length()+1
    block_base = 1 << bits
    half = block_base//2
    # The lcm upper bound is below 2**(2*limit). At the last block,
    # truncation by fewer than count units cannot cross a half-integer.
    blocks = ceil_div(2*limit+limit.bit_length()+2, bits)
    distance = 0
    crossing = 0
    for j in range(blocks):
        total = 0
        nonzero = False
        for m, r in fractions():
            if r:
                nonzero = True
                residue = r*pow(block_base, j, m) % m
                total += (residue << bits)//m
        if not j:
            if not nonzero:
                return 0, 1
            half_index, offset = divmod(total, half)
            crossing = (half_index+1) & 1
            distance = offset-half
        else:
            distance = distance*block_base+total
        if distance >= 0:
            return 1-2*crossing, j+1
        if distance <= -count:
            return 2*crossing-1, j+1
    raise ArithmeticError('uncertainty exceeds the proved truncation bound')


def compare(x, y, lower, terms, cache=False):
    """Return the rounded side, or zero if this finite enclosure overlaps."""
    if terms < 1:
        raise ValueError('positive truncation length required')
    form = log_form(x, y, lower)
    if form is None:
        return (1 if lower & 1 else -1), dict(tie=True)
    width = form.integer_width(terms)
    limit = modulus_limit(width)
    cached_moduli = tuple(prefix(width, limit)) if cache else None

    def moduli():
        return iter(cached_moduli) if cache else prefix(width, limit)

    count = sum(1 for _ in moduli())

    def rows():
        for p, m in moduli():
            inv = inverse_complement(p, m, moduli)
            lo, hi = enclosure_residues(form, terms, m)
            yield m, lo*inv % m, hi*inv % m

    # The optional host cache speeds up experiments. The constant-space
    # comparator replays rows on each requested block.
    cached = tuple(rows()) if cache else None

    def fractions(column):
        return ((entry[0], entry[column]) for entry in (cached if cache else rows()))

    hi, hi_blocks = crt_sign(lambda: fractions(2), count, limit)
    lo_blocks = 0
    if hi <= 0:
        side = -1
    else:
        lo, lo_blocks = crt_sign(lambda: fractions(1), count, limit)
        side = 1 if lo >= 0 else 0
    return side, dict(terms=terms, integer_width=width, modulus_limit=limit, moduli=count,
                      blocks=[lo_blocks, hi_blocks], tie=False)


def uniform_work():
    assert __debug__, 'enable assertions for the separation certificate'
    grid = FixedInterval(128)
    ln2 = grid.log(2, 1)
    gap = uniform_precision_bound(*(Fraction(v, grid.unit) for v in ln2), 116)
    separation = int(gap['nonzero_abs_log_gap_strict_lower_bound'].removeprefix('2^-'))
    # The sum of coefficient magnitudes divided by q is below 2**74.
    # At this number of terms the combined tail is below half the gap.
    assert 1075*((1 << 63)+1) < 1 << 74
    assert 1075*((1 << 116)+(1 << 53)-1) < 1 << 127
    terms = separation+75
    width = terms*(54+(terms-1).bit_length())+128
    limit = modulus_limit(width)
    bits = limit.bit_length()+1
    blocks = ceil_div(2*limit+limit.bit_length()+2, bits)
    # Count trial divisions, modular products/divisions and explicit
    # loop steps generously as single bounded integer operations.
    # Moduli are replayed for each complement and each output block.
    enumerate_work = limit*(8*isqrt(limit)+16*limit.bit_length()+32)
    per_modulus = enumerate_work+64*terms+64*limit.bit_length()+64
    work = 2*blocks*limit*per_modulus+4*enumerate_work+(1 << 25)
    assert limit <= 1 << 44 and width < 1 << 43 and bits+limit.bit_length() < 128
    return dict(separation_bits=separation, terms=terms, integer_width=width, modulus_limit=limit,
                block_bits=bits, maximum_blocks=blocks,
                fixed_width_operation_bound_bits=work.bit_length(),
                one_term_per_125mhz_cycle_seconds=terms/125_000_000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--point', nargs=3, metavar=('X', 'Y', 'LOWER'),
                        help='check one triple of hexadecimal binary64 encodings')
    parser.add_argument('--terms', type=int, default=240)
    parser.add_argument('--cache', action='store_true', help='cache residues on the host')
    parser.add_argument('--cancel', type=int, metavar='BITS',
                        help='compare reduced powers within this integer width')
    args = parser.parse_args()
    if args.cancel is not None and not args.point:
        parser.error('--cancel requires --point')
    if args.point:
        point = tuple(int(v, 16) for v in args.point)
        if args.cancel is not None:
            side, report = cancelled_powers(*point, args.cancel)
        else:
            side, report = compare(*point, args.terms, args.cache)
        result = dict(side=side, **report)
    else:
        result = uniform_work()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
