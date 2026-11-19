#!/usr/bin/env python3
"""Compare a binary64 power to a midpoint using directed dyadic roots."""

import argparse
from dataclasses import dataclass
import json
from math import isqrt

from modular_log_compare import midpoint_equal, operands, order


@dataclass(frozen=True)
class Dyadic:
    coefficient: int
    scale: int


def compare_dyadics(left, right):
    a, b = left.coefficient, right.coefficient
    at = a.bit_length() + left.scale
    bt = b.bit_length() + right.scale
    if at != bt:
        return order(at - bt)
    # With the same leading exponent, alignment depends on coefficient sizes.
    shift = left.scale - right.scale
    return order((a << max(shift, 0)) - (b << max(-shift, 0)))


class Directed:
    def __init__(self, precision, upper):
        self.precision = precision
        self.upper = upper
        self.one = Dyadic(1 << (precision - 1), 1 - precision)

    def rounded(self, coefficient, scale, inexact=False):
        if self.upper and inexact:
            coefficient += 1
        if coefficient == 1 << self.precision:
            coefficient >>= 1
            scale += 1
        return Dyadic(coefficient, scale)

    def scaled(self, coefficient, scale):
        discard = coefficient.bit_length() - self.precision
        if discard <= 0:
            return Dyadic(coefficient << -discard, scale + discard)
        high = coefficient >> discard
        return self.rounded(high, scale + discard, coefficient != high << discard)

    def ratio(self, numerator, denominator):
        top = numerator.bit_length() - denominator.bit_length()
        if numerator << max(-top, 0) < denominator << max(top, 0):
            top -= 1
        scale = top + 1 - self.precision
        quotient, remainder = divmod(numerator << max(-scale, 0), denominator << max(scale, 0))
        return self.rounded(quotient, scale, remainder != 0)

    def add(self, left, right):
        if left.scale < right.scale:
            left, right = right, left
        shift = left.scale - right.scale
        if shift >= self.precision:
            # The positive low term is strictly smaller than one ulp of left.
            return self.rounded(left.coefficient, left.scale, True)
        return self.scaled((left.coefficient << shift) + right.coefficient, right.scale)

    def multiply(self, left, right):
        return self.scaled(left.coefficient * right.coefficient, left.scale + right.scale)

    def root(self, value, factor=None):
        # Fuse the optional product with the root. There is only one rounding.
        coefficient, scale = value.coefficient, value.scale
        if factor is not None:
            coefficient *= factor.coefficient
            scale += factor.scale
        top = (coefficient.bit_length() - 1 + scale) // 2
        scale_out = top + 1 - self.precision
        shift = scale - 2 * scale_out
        radicand = coefficient << shift if shift >= 0 else coefficient >> -shift
        root = isqrt(radicand)
        square = root * root
        exact = square == radicand and (shift >= 0 or square << -shift == coefficient)
        return self.rounded(root, scale_out, not exact)

    def integer_power(self, numerator, denominator, exponent):
        # Stay in the positive offset z**i - 1 to preserve relative accuracy
        # in the offset when a large exponent acts on a base near one.
        base = self.ratio(numerator - denominator, denominator)
        offset = base
        for bit in range(exponent.bit_length() - 2, -1, -1):
            double_offset = Dyadic(offset.coefficient, offset.scale + 1)
            offset = self.add(self.multiply(offset, offset), double_offset)
            if exponent >> bit & 1:
                offset = self.add(self.add(offset, base), self.multiply(offset, base))
        return self.add(self.one, offset)

    def fractional_power(self, numerator, denominator, fraction, bits):
        base = self.ratio(numerator, denominator)
        value = self.one
        # Horner's rule on exponent bits, from low to high.
        for _ in range(bits):
            value = self.root(value, base if fraction & 1 else None)
            fraction >>= 1
        return value

    def power(self, numerator, denominator, p, q):
        n, fraction = divmod(p, q)
        if not n:
            return self.fractional_power(numerator, denominator, fraction, q.bit_length() - 1)
        whole = self.integer_power(numerator, denominator, n)
        if not fraction:
            return whole
        part = self.fractional_power(numerator, denominator, fraction, q.bit_length() - 1)
        return self.multiply(whole, part)


def threshold_side(value, midpoint, reciprocal):
    if not reciprocal:
        return compare_dyadics(value, midpoint)
    product = Dyadic(value.coefficient * midpoint.coefficient, value.scale + midpoint.scale)
    return compare_dyadics(product, Dyadic(1, 0))


def side(x, y, lower, precision):
    """Return an exact rounded side (-1 or +1), or 0 when the interval overlaps."""
    if precision < 64:
        raise ValueError('at least 64 significand bits required')
    a, ae, b, be, p, q = operands(x, y, lower)
    midpoint = Dyadic(b, be)
    numerator, denominator = a << max(ae, 0), 1 << max(-ae, 0)
    if numerator == denominator:
        return compare_dyadics(Dyadic(1, 0), midpoint)
    if midpoint_equal(a, ae, b, be, p, q):
        return 1 if lower & 1 else -1

    reciprocal = (p < 0) ^ (numerator < denominator)
    orientation = -1 if reciprocal else 1
    if numerator < denominator:
        numerator, denominator = denominator, numerator

    down = Directed(precision, False).power(numerator, denominator, abs(p), q)
    if threshold_side(down, midpoint, reciprocal) >= 0:
        return orientation
    up = Directed(precision, True).power(numerator, denominator, abs(p), q)
    if threshold_side(up, midpoint, reciprocal) <= 0:
        return -orientation
    return 0


def exact_side(x, y, lower):
    """Refine until the sign is proved, using dynamically sized host integers."""
    precision = 64
    while True:
        answer = side(x, y, lower, precision)
        if answer:
            return answer, precision
        precision *= 2


def work(p, q):
    """Count the operations above the integer root and division primitives."""
    n, fraction = divmod(abs(p), q)
    squares = max(0, n.bit_length() - 1)
    integer_multiplications = n.bit_count() - bool(n)
    roots = q.bit_length() - 1 if fraction else 0
    products = squares + integer_multiplications + fraction.bit_count() + roots + bool(n and fraction)
    return dict(roots=roots, products=products,
                sums=squares + 2 * integer_multiplications + bool(n))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('point', metavar='HEX', nargs=3, type=lambda value: int(value, 16),
                        help='binary64 encodings x y lower')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--precision', type=int, default=256)
    mode.add_argument('--exact', action='store_true', help='increase host precision until decided')
    args = parser.parse_args()
    *_, p, q = operands(*args.point)
    if args.exact:
        answer, precision = exact_side(*args.point)
    else:
        answer, precision = side(*args.point, args.precision), args.precision
    print(json.dumps(dict(side=answer, precision=precision,
                          exponent_denominator_bits=q.bit_length() - 1, endpoint_work=work(p, q))))


if __name__ == '__main__':
    main()
