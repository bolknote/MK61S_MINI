"""Explore exact Euclidean power comparison without logarithms."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
from m0_mpfr_oracle import Oracle, bits
from m0_pow_stream_host_self_test import dyadic, midpoint, expected_side

ONE = 0x3ff0000000000000
INFINITY = 0x7ff0000000000000
ABS = (1 << 63)-1


class SizeLimit(Exception):
    pass


def parameters(encoding):
    p, shift = dyadic(encoding & ABS)
    trailing = (p & -p).bit_length()-1
    p >>= trailing
    shift += trailing
    return p << max(shift, 0), 1 << max(-shift, 0)


def compact_euclid(p, q):
    """Track exact powers as pairs of exponents of the original bases."""
    original = (p, -q)
    a, b = (1, 0), (0, 1)
    direction, rounds = 1, 0
    while True:
        rounds += 1
        t, r = divmod(p, q)
        residual = tuple(t*u-v for u, v in zip(a, b))
        if r == 0:
            remaining = tuple(direction*q*u for u in residual)
            assert remaining == original
            return dict(divisions=rounds, remaining_original_exponents=list(remaining))
        a, b, p, q = tuple(-u for u in residual), a, q, r
        direction = -direction


def rational(encoding):
    coefficient, shift = dyadic(encoding)
    if shift >= 0:
        return Fraction(coefficient << shift)
    return Fraction(coefficient, 1 << -shift)


def compare(a, p, b, q, cap, stats):
    sign = 1
    if a == 1 or b == 1 or (a < 1) != (b < 1):
        return (a > b)-(a < b)
    if a < 1:
        a, b = 1/a, 1/b
        sign = -1
    while True:
        stats['rounds'] += 1
        if p < q:
            a, b, p, q = b, a, q, p
            sign = -sign
        t, r = divmod(p, q)
        # This is a lower bound on the exact numerator or denominator
        # width, before reduction by b in the next division.
        minimum = max(a.numerator.bit_length()-1, a.denominator.bit_length()-1)*t+1
        stats['maximum_power_width_lower_bound'] = max(
            stats['maximum_power_width_lower_bound'], minimum)
        odd_numerator = a.numerator // (a.numerator & -a.numerator)
        odd_denominator = a.denominator // (a.denominator & -a.denominator)
        odd_minimum = max(odd_numerator.bit_length()-1, odd_denominator.bit_length()-1)*t+1
        stats['maximum_odd_power_width_lower_bound'] = max(
            stats.get('maximum_odd_power_width_lower_bound', 0), odd_minimum)
        maximum = max(a.numerator.bit_length(), a.denominator.bit_length())*t
        if maximum > cap:
            stats['stopped_quotient'] = t
            raise SizeLimit
        powered = a ** t
        stats['largest_materialized_width'] = max(
            stats['largest_materialized_width'],
            powered.numerator.bit_length(), powered.denominator.bit_length())
        ratio = powered/b
        if ratio >= 1:
            order = 0 if ratio == 1 and r == 0 else 1
            return sign*order
        if r == 0:
            return -sign
        a, b, p, q = 1/ratio, a, q, r
        sign = -sign


def side(x, y, lower, cap, stats):
    a = rational(x)
    if y >> 63:
        a = 1/a
    p, q = parameters(y)
    m, scale = midpoint(lower)
    b = Fraction(m << scale) if scale >= 0 else Fraction(m, 1 << -scale)
    order = compare(a, p, b, q, cap, stats)
    return order or (1 if lower & 1 else -1)


def check_small_exact(cap):
    cases = 0
    values = [Fraction(n, d) for n, d in ((1, 4), (1, 2), (3, 4), (1, 1),
                                         (5, 4), (3, 2), (2, 1), (3, 1))]
    for a in values:
        for b in values:
            for p in range(1, 34):
                for q in (1, 2, 4, 8, 16, 32):
                    stats = dict(rounds=0, maximum_power_width_lower_bound=0, largest_materialized_width=0)
                    actual = compare(a, p, b, q, cap, stats)
                    left, right = a**p, b**q
                    assert actual == (left > right)-(left < right)
                    compact_euclid(p, q)
                    cases += 1
    return cases


def crt_ambiguity():
    # The inverse comparison uses a product and an aligned power of two.
    # Both signs have representatives in the same a-priori integer bound
    # and in the same residue class for this small modulus.
    x, y, lower = ONE-1, bits(-1023/128), ONE+3
    a, ae = dyadic(x)
    m, me = midpoint(lower)
    p, q = parameters(y)
    assert ae == me == -53
    difference = (1 << (53*(p+q))) - a**p*m**q
    bound = 1 << difference.bit_length()
    modulus = 1_000_000_007*1_000_000_009
    residue = difference % modulus
    positive, negative = residue, residue-modulus
    assert -bound < negative < 0 < positive < bound
    assert positive % modulus == negative % modulus == residue
    return dict(x=f'{x:016x}', y=f'{y:016x}', lower=f'{lower:016x}',
                exact_difference_bits=difference.bit_length(), modulus_bits=modulus.bit_length(),
                same_residue_positive=positive, same_residue_negative=negative,
                residue_alone_determines_sign=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cap', type=int, default=1 << 20,
                        help='Cap the predicted width of each numerator or denominator power')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.cap < 256:
        parser.error('--cap must be at least 256 for the small exact checks')
    oracle = Oracle()
    small = check_small_exact(args.cap)
    rng = random.Random(0x2370aa)
    checks, limited, examples = 0, 0, []
    largest = dict(rounds=0, maximum_power_width_lower_bound=0, largest_materialized_width=0)
    pairs = [(bits(3.), bits(34.)), (bits(2.), bits(-1075.)),
             (ONE-1, bits(-1023/128)), (ONE-1, bits(1023.))]
    for _ in range(400):
        x = rng.randrange(1, INFINITY)
        exponent = rng.choice((-1, 1))*rng.randrange(1, 1024)/(1 << rng.randrange(11))
        pairs.append((x, bits(exponent)))
    for x, y in pairs:
        rounded = oracle.reference('pow', x, y)
        for lower in (max(0, min(INFINITY-1, rounded-1)), min(INFINITY-1, rounded)):
            stats = dict(rounds=0, maximum_power_width_lower_bound=0, largest_materialized_width=0)
            try:
                actual = side(x, y, lower, args.cap, stats)
            except SizeLimit:
                limited += 1
            else:
                expected = expected_side(x, y, lower)
                assert actual == expected, (hex(x), hex(y), hex(lower), actual, expected)
                checks += 1
            for key in largest:
                largest[key] = max(largest[key], stats[key])
    # A valid binary64 pair targeting the midpoint immediately below one.
    # It exposes the first exact power in Euclidean descent, even though
    # the production interval stages already resolve the public pow call.
    for x, y, lower in ((1, 0x3bf6000000000001, ONE-1),
                         (0x000fffffffffffff, 0xbbffffffffffffff, ONE),
                         (ONE-1, bits(-1023/128), ONE+3)):
        stats = dict(rounds=0, maximum_power_width_lower_bound=0, largest_materialized_width=0)
        try:
            actual = side(x, y, lower, args.cap, stats)
        except SizeLimit:
            status = 'requires wider exact power'
        else:
            assert actual == (1 if oracle.reference('pow', x, y) > lower else -1)
            status = 'decided'
        p, q = parameters(y)
        examples.append(dict(x=f'{x:016x}', y=f'{y:016x}', lower=f'{lower:016x}', status=status,
                             compact=compact_euclid(p, q), **stats))
    report = dict(status='PASS_FINITE_EXACT_CHECKS', mpfr=oracle.version, bit_cap=args.cap,
                  small_exhaustive_comparisons=small,
                  exact_midpoint_comparisons=checks, stopped_before_materialization=limited,
                  maximum_work=largest, examples=examples,
                  signed_crt_ambiguity=crt_ambiguity(),
                  prototype_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  reference_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                      ('tests/m0_mpfr_oracle.py', 'tests/m0_pow_stream_host_self_test.py')},
                  scope='Finite exact checks, compact exponent identities and a residue-class ambiguity example. '
                        'The large-power examples are direct comparator calls. They do not establish that '
                        'the public firmware reaches its late fallback on those inputs.',
                  practical_all_input_bound_established=False)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
