#!/usr/bin/env python3
"""Independent integer oracle and directed cases for binary64 fused multiply-add.

The oracle forms the exact signed integer sum of two dyadic terms, then
rounds once. It uses neither native floating-point arithmetic nor firmware.
"""
import random

SIGN = 1 << 63
FRAC = (1 << 52) - 1
INF = 0x7ff0000000000000
QUIET = 1 << 51
MASK = (1 << 64) - 1


def is_nan(a):
    return (a & (SIGN - 1)) > INF


def finite(a):
    exponent = (a >> 52) & 2047
    significand = (a & FRAC) | ((1 << 52) if exponent else 0)
    return (-significand if a & SIGN else significand,
            exponent - 1075 if exponent else -1074)


def round_dyadic(integer, exponent, zero_sign=0):
    if not integer:
        return zero_sign
    sign = SIGN if integer < 0 else 0
    integer = abs(integer)
    top = integer.bit_length() - 1 + exponent
    quantum = max(top - 52, -1074)
    shift = quantum - exponent
    if shift > 0:
        quotient, remainder = divmod(integer, 1 << shift)
        half = 1 << (shift - 1)
        quotient += remainder > half or (remainder == half and quotient & 1)
    else:
        quotient = integer << -shift
    if not quotient:
        return sign
    top = quotient.bit_length() - 1 + quantum
    if top > 1023:
        return sign | INF
    if top < -1022:
        assert quantum == -1074 and quotient < 1 << 52
        return sign | quotient
    significand = quotient >> max(0, quotient.bit_length() - 53)
    assert 1 << 52 <= significand < 1 << 53
    return sign | ((top + 1023) << 52) | (significand & FRAC)


def reference(a, b, c):
    assert all(0 <= v <= MASK for v in (a, b, c))
    for v in (a, b, c):
        if is_nan(v):
            return v | QUIET
    ma, mb, mc = (v & (SIGN - 1) for v in (a, b, c))
    product_sign = (a ^ b) & SIGN
    if ma == INF or mb == INF:
        if not ma or not mb or (mc == INF and (product_sign ^ c) & SIGN):
            return INF | QUIET
        return product_sign | INF
    if mc == INF:
        return c
    sa, ea = finite(a)
    sb, eb = finite(b)
    sc, ec = finite(c)
    ep = ea + eb
    exponent = min(ep, ec)
    exact = (sa * sb << (ep - exponent)) + (sc << (ec - exponent))
    zero_sign = product_sign & c & SIGN if not sa or not sb else 0
    return round_dyadic(exact, exponent, zero_sign)


def equivalent(actual, expected):
    return (is_nan(actual) and bool(actual & QUIET)) if is_nan(expected) else actual == expected


def power(exponent, sign=0):
    if exponent < -1074 or exponent > 1023:
        return None
    if exponent < -1022:
        return sign | 1 << (exponent + 1074)
    return sign | ((exponent + 1023) << 52)


def corpus(samples=2000):
    """Fixed special values, alignment transitions, ties, cancellation, random.

    Each case carries its construction class. Deduplication preserves order;
    finite coverage does not constitute an all-input rounding proof.
    """
    special = [0, SIGN, 1, SIGN | 1, FRAC, SIGN | FRAC, 1 << 52,
               SIGN | (1 << 52), 0x3fe0000000000000, 0x3ff0000000000000,
               0xbff0000000000000, INF - 1, SIGN | (INF - 1), INF,
               SIGN | INF, INF | 1, SIGN | INF | 1, INF | QUIET | 13]
    seen = set()

    def emit(label, a, b, c):
        key = a, b, c
        if key not in seen:
            seen.add(key)
            return label, key

    for a in special:
        for b in special:
            for c in special:
                row = emit('special_cartesian', a, b, c)
                if row:
                    yield row
    fractions = [0, 1, (1 << 16) - 1, 1 << 26, (1 << 32) - 1,
                 1 << 51, FRAC - 1, FRAC]
    exponents = [1, 2, 511, 970, 1022, 1023, 1024, 1075, 1535, 2045, 2046]
    gaps = [0, 1, 2, 20, 21, 22, 23, 52, 53, 63, 64, 65, 73, 74,
            75, 76, 125, 126, 127, 128, 129, 2048, 4096]
    rng = random.Random(0x61f0a20261029)
    for i, ea in enumerate(exponents):
        for eb in exponents:
            for j, fa in enumerate(fractions):
                a = (ea << 52) | fa
                b = (eb << 52) | fractions[(i + j) % len(fractions)]
                sa, ax = finite(a)
                sb, bx = finite(b)
                rounded = round_dyadic(sa * sb, ax + bx)
                if rounded < INF:
                    for delta in (-2, -1, 0, 1, 2):
                        magnitude = rounded + delta
                        if 0 <= magnitude < INF:
                            for sign in (0, SIGN):
                                row = emit('product_cancellation_neighbours', a, b, magnitude | sign)
                                if row:
                                    yield row
                product_top = (sa * sb).bit_length() - 1 + ax + bx
                for gap in gaps:
                    # Both directions exercise discarded product and addend
                    # tails. The 21/22 and 74/75 transitions are distinct.
                    for direction in (-1, 1):
                        c = power(product_top + direction * gap)
                        if c is not None:
                            for sign in (0, SIGN):
                                row = emit('alignment_transitions', a, b, c | sign)
                                if row:
                                    yield row
    for _ in range(samples):
        a, b, c = (rng.getrandbits(64) for _ in range(3))
        row = emit('random_encodings', a, b, c)
        if row:
            yield row
    for a in (0x3ff0000000000000, 0x3ff0000000000001, INF - 1):
        for b, c in ((power(0), power(-53)), (power(1), a | SIGN)):
            row = emit('round_once_witness', a, b, c)
            if row:
                yield row


def self_test():
    one = 0x3ff0000000000000
    assert reference(one, one, power(-53)) == one
    assert reference(one + 1, one, power(-53)) == one + 2
    assert reference(INF - 1, power(1), SIGN | (INF - 1)) == INF - 1
    assert reference(1, power(-1), 1) == 2
    assert reference(one, one, one | SIGN) == 0
    assert reference(SIGN, one, SIGN) == SIGN
    assert reference(SIGN, one, 0) == 0
    assert reference(INF, 0, one) == INF | QUIET
    assert reference(INF, one, SIGN | INF) == INF | QUIET
    assert reference(INF | 1, one, one) & QUIET


if __name__ == '__main__':
    self_test()
    from collections import Counter
    cases = list(corpus())
    print('PASS integer FMA oracle witnesses;', len(cases), 'cases;',
          dict(Counter(label for label, _ in cases)))
