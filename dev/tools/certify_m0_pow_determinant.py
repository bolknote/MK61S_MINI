#!/usr/bin/env python3
"""Certify larger pow domains that finish before the exact stream on RP2040."""
import argparse
from dataclasses import dataclass
from fractions import Fraction
from functools import cache
import hashlib
import json
from math import ceil
from pathlib import Path

from certify_m0_pow_log_side import GAP, HEADER, ROOT, SOURCE_URL, FixedInterval, arithmetic

LOG_GRID = FixedInterval(160)
LOG_TWO = LOG_GRID.log(2, 1)
EPSILON = Fraction(1, 1 << 128)
POW_BITS = 8192
ORIGIN_RADIUS = 23
ORIGIN_START = ORIGIN_RADIUS-55
ORIGIN_END = 4


@dataclass(frozen=True)
class Determinant:
    rho_shift: int
    mu_numerator: int
    k: int
    l: int
    r1: int
    s1: int
    r2: int
    s2: int


# Each exponent interval is closed. For the first radius, the analytic
# exclusion below ORIGIN_START completes the interval down to zero.
ORIGIN_BANDS = (
    (23, -32, -10, Determinant(27, 137, 116, 9, 3, 3, 28, 37)),
    (23, -10,   4, Determinant(23, 134, 148, 8, 4, 2, 38, 31)),
    (22, -27, -18, Determinant(26, 133, 124, 9, 3, 3, 30, 37)),
    (20, -18, -10, Determinant(24, 149, 135, 8, 2, 4, 29, 37)),
    (20, -10,  -5, Determinant(24, 144, 119, 8, 2, 4, 27, 35)),
    (18,  -5,  -1, Determinant(21, 139, 162, 8, 2, 4, 34, 38)),
)

# If the dyadic exponent is p/q and q divides the scale exponent,
# x and m can be divided by matching powers of two exactly.
SCALED_BANDS = (
    (4,  -1, Determinant(8,  152, 647, 4, 2, 2, 47, 55)),
    (5,   1, Determinant(8,  147, 753, 4, 2, 2, 59, 51)),
    (8,   4, Determinant(9,  133, 652, 5, 3, 2, 74, 44)),
    (14,  8, Determinant(11, 141, 461, 5, 3, 2, 59, 39)),
    (17, 10, Determinant(12, 143, 404, 5, 3, 2, 56, 36)),
)


def power2(shift):
    return Fraction(2)**shift


@cache
def integer_log(value):
    """Outward bounds of the logarithm of a positive integer."""
    assert value > 0
    exponent = value.bit_length()-1
    residual = LOG_GRID.log(value, 1 << exponent)
    return tuple(Fraction(exponent*b+r, LOG_GRID.unit) for b, r in zip(LOG_TWO, residual))


def ceil_log2(value):
    assert value > 0
    n, d = value.numerator, value.denominator
    guess = n.bit_length()-d.bit_length()
    assert power2(guess-1) < value <= power2(guess+1)
    return guess+int(value > power2(guess))


def check_determinant(radius, lower, upper, q_max, parameters):
    """Apply Laurent's Theorem 1 (D=1) with exact rational inequalities."""
    d = power2(-radius)
    x_log = d/(1-d)
    m_log = power2(upper)*x_log+EPSILON
    ln2_lower, ln2_upper = integer_log(2)
    assert max(x_log, m_log) < ln2_lower

    p_max = min((1 << 53)-1, int(q_max*power2(upper)))
    assert 1 <= p_max and upper < 53

    t, k, l = parameters.rho_shift, parameters.k, parameters.l
    r1, s1, r2, s2 = parameters.r1, parameters.s1, parameters.r2, parameters.s2
    n = k*l
    r, s = r1+r2-1, s1+s2-1
    assert t > 0 and k >= 2 and min(l,r1,s1,r2,s2) > 0
    assert r1*s1 >= l and r2*s2 > (k-1)*l
    # Independence gives the first cardinality bound. A collision in
    # r*q+s*p for reduced p/q requires p<r2 and q<s2. In that case
    # even the product for a negative exponent fits the exact 8192-bit pass.
    maximum_collision_product_bits = (r2-1)*53+(s2-1)*54
    assert maximum_collision_product_bits <= POW_BITS
    g = Fraction(1, 4)-Fraction(n, 12*r*s)
    assert g > 0

    # Invert either rational if needed to make its log positive.
    # In (1/2,2) their 53- and 54-bit dyadic significands imply height
    # <=54*ln(2), preserved by inversion. For small delta the two signed
    # terms are of the same sign, so the form after inversion is p*log(u)-q*log(v).
    rho_minus_one = (1 << t)-1
    a1 = rho_minus_one*x_log+108*ln2_upper
    a2 = rho_minus_one*m_log+108*ln2_upper
    numerator_log = integer_log((r-1)*q_max+(s-1)*p_max)[1]
    log_factorials_lower = sum((k-i)*integer_log(i)[0] for i in range(2,k))
    log_b_upper = numerator_log-ln2_lower-2*log_factorials_lower/(k*(k-1))

    mu = Fraction(parameters.mu_numerator, 240)
    assert Fraction(1, 3) <= mu <= 1
    sigma = (1+2*mu-mu*mu)/2
    assert sigma*l > 1
    log_n_hi = integer_log(n)[1]
    # By monotonicity log(N!) <= integral_1^N log(x) dx + log(N).
    # Also e^N+(e-1)^N < 2*e^N. Together they bound Laurent's epsilon.
    epsilon_hi = 2*(2*log_n_hi+1+ln2_upper)/n
    lhs = k*(sigma*l-1)*t*ln2_lower-2*log_n_hi-(k-1)*log_b_upper-g*l*(r*a1+s*a2)
    assert lhs > epsilon_hi, (radius, lower, upper, parameters)

    # Delta = |y*log(u)-log(v)|. Theorem 1's |Lambda'| is at most
    # A*delta*exp(A*delta), where 2*A <= amplification. For delta
    # below the derived bound, A*delta <= 1/2 and exp(A*delta) < 2.
    amplification = l*max(s, r*power2(-lower))
    assert ln2_lower > Fraction(1, 2)
    gap_bits = ceil(mu*n*t)+ceil_log2(amplification)
    assert 128 < gap_bits < GAP, (radius, lower, upper, gap_bits)

    q_shift = q_max.bit_length()-1
    x_squares = p_max.bit_length()-1
    return dict(relative_radius_bits=radius, abs_y_lower_shift=lower, abs_y_upper_shift=upper,
                q_max=q_max, p_max=p_max, rho_shift=t, mu=str(mu), k=k, l=l,
                r1=r1, s1=s1, r2=r2, s2=s2,
                determinant_slack_lower_thousandths=int(1000*(lhs-epsilon_hi)),
                independent_gap_bits=gap_bits,
                maximum_collision_product_bits=maximum_collision_product_bits,
                maximum_full_power_products_each_pass=x_squares+q_shift+1,
                maximum_short_power_products_each_pass=x_squares)


def base_count(radius, exponent):
    """Count positive finite binary64 values in one scale neighborhood."""
    assert radius >= 2 and -1074 <= exponent <= 1023
    upper_step = max(exponent-52, -1074)
    lower_step = max(exponent-53, -1074)
    assert 1+power2(-radius) < 2*(1-power2(-radius))
    return 1+int(power2(exponent-radius-upper_step))+int(power2(exponent-radius-lower_step))


def certify():
    assert arithmetic()['unresolved_gap'] == f'2^-{GAP}' and GAP == 16300
    # A 54-bit dyadic v != 1 in (1/2,2) has |log(v)| > 2^-54.
    # The same bound holds outside (1/2,2). At v=1, u!=1 gives a
    # gap > 2^-117 for all active exponents |y|>=2^-64.
    assert Fraction(1, (1 << 53)+1) > power2(-54)
    assert Fraction(1, (1 << 52)+1) > power2(-53)
    d = power2(-ORIGIN_RADIUS)
    assert power2(ORIGIN_START)*d/(1-d)+EPSILON < power2(-54)
    assert 54+116 < GAP

    origin = [check_determinant(d, lo, hi, 1 << (52-lo), params)
              for d,lo,hi,params in ORIGIN_BANDS]
    assert [(r['abs_y_lower_shift'],r['abs_y_upper_shift']) for r in origin[:2]] == [
        (ORIGIN_START,-10),(-10,ORIGIN_END)]
    further_origin_ranges = []
    for radius, lower in ((22,-27),(20,-18),(18,-5)):
        covered = lower
        for d,lo,hi,_ in sorted(ORIGIN_BANDS, key=lambda row: row[1]):
            if d <= radius and lo <= covered:
                covered = max(covered, hi)
        assert covered >= -1
        further_origin_ranges.append(dict(relative_radius_bits=radius, abs_y_lower_shift=lower,
                                          abs_y_upper_shift=-1, base_encodings=base_count(radius,0)))
    # q divides a nonzero scaling exponent s, and s is in [-1074,1023].
    # Thus the maximum possible power-of-two denominator is 1024.
    maximum_q = 1 << 10
    assert maximum_q <= 1074 < 2*maximum_q
    scaled = []
    for radius, high, params in SCALED_BANDS:
        band = check_determinant(radius, -10, high, maximum_q, params)
        # q=2**k must divide the nonzero exponent s. For a fixed y=p/q,
        # all applicable neighborhoods are pairwise disjoint and can be counted.
        band['base_encodings_by_q_nonzero_scale'] = {
            str(q): sum(base_count(radius,e) for e in range(-1074, 1024) if e and e%q==0)
            for q in (1 << k for k in range(11)) if power2(high)*q >= 1
        }
        assert base_count(radius,0) == 3*(1 << (52-radius))+1
        scaled.append(band)

    sources = (
        Path(__file__),
        HEADER,
        ROOT/'code/native_eabi_m0_cr.cpp',
        ROOT/'code/native_eabi_m0_pow_exact.inc',
        ROOT/'code/native_eabi_m0_pow_log_side.inc',
        ROOT/'code/native_eabi_m0_pow_power_bounds.inc',
        ROOT/'dev/tools/certify_m0_pow_log_side.py',
        ROOT/'dev/tools/certify_m0_pow_power_bounds.py',
        ROOT/'research/m0-pow-comparison-20261117/midpoint_grid.py',
    )
    return dict(status='PASS_POW_DETERMINANT', source=SOURCE_URL, theorem='Theorem 1, page 326',
                practical_uniform_latency_established=False, comparator_gap_bits=GAP,
                origin_all_exponents_up_to=dict(relative_radius_bits=ORIGIN_RADIUS,
                    abs_y_upper_shift=ORIGIN_END, base_encodings=base_count(ORIGIN_RADIUS,0)),
                origin_bands=origin, origin_additional_ranges=further_origin_ranges, scaled_bands=scaled,
                source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sources})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError('Enable Python assertions to verify the certificate')
    report = certify()
    if args.json:
        args.json.write_text(json.dumps(report, indent=2)+'\n')
    print(report['status'], report['origin_all_exponents_up_to'])


if __name__ == '__main__':
    main()
