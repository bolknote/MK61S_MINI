#!/usr/bin/env python3
"""Audit a parameter-independent limit of Laurent's bounds for RP2040 pow."""

import argparse
from fractions import Fraction
from hashlib import sha256
import json
from math import gcd
from pathlib import Path
import sys

from certify_m0_pow_log_side import FixedInterval, GAP, ROOT, SOURCE_URL, arithmetic

Q = 1 << 52
X = 0x7fd0000000000001
Y = 0x3ff0040201008043
MIDPOINT_LOWER = 0x7fe00000000007f5
LOG_X_LOWER = 700
ODD_PART_LOG_LOWER = 36
GRID = FixedInterval(192)
LN2 = GRID.log(2, 1)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def normal_coefficient(bits):
    require(type(bits) is int and 0 < bits < 0x7ff0000000000000 and bits >> 52,
            'not a positive normal binary64')
    return Q+(bits & (Q-1)), (bits >> 52)-1023


def log_enclosure(coefficient, significand_unit, exponent):
    residual = GRID.log(coefficient, significand_unit)
    scale = GRID.scale(LN2, exponent)
    return residual[0]+scale[0], residual[1]+scale[1]


def check_witness(x=X, y=Y, lower=MIDPOINT_LOWER):
    """Give a genuine adjacent rounding midpoint with independent odd parts."""
    a, xe = normal_coefficient(x)
    p, ye = normal_coefficient(y)
    m, me = normal_coefficient(lower)
    require(ye == 0 and p & 1 and me == ((lower-1) >> 52)-1023,
            'wrong exponent grid or midpoint at a binade transition')
    b = 2*m+1
    require(a & 1 and gcd(a, b) == 1, 'odd parts do not prove multiplicative independence')
    require(ODD_PART_LOG_LOWER*GRID.unit < 52*LN2[0], 'odd-part height lower bound')
    xl, xu = log_enclosure(a, Q, xe)
    ml, mu = log_enclosure(b, 2*Q, me)
    _, previous_mu = log_enclosure(b-2, 2*Q, me)
    require(xl > LOG_X_LOWER*GRID.unit and ml > LOG_X_LOWER*GRID.unit,
            'large-logarithm witness is outside the proof domain')
    # Round-to-nearest(x**y) is precisely lower, given these two strict
    # logarithmic inequalities. No libm, MPFR or transcendental point
    # estimate from the heuristic search is trusted by the checker.
    require(Q*previous_mu < p*xl <= p*xu < Q*ml, 'midpoints do not bracket x**y')
    gap_lo, gap_hi = Q*ml-p*xu, Q*mu-p*xl
    upper_bits = GRID.precision+52-gap_hi.bit_length()
    lower_bits = GRID.precision+53-gap_lo.bit_length()
    require(0 < gap_lo <= gap_hi and 0 <= upper_bits < lower_bits < GAP,
            'invalid witness log gap')
    return dict(x=f'{x:016x}', y=f'{y:016x}', upper_midpoint_lower_encoding=f'{lower:016x}',
                rounded_encoding=f'{lower:016x}', odd_parts=[a, b], numerator=p, denominator=Q,
                actual_witness_gap_at_least=f'2^-{lower_bits}',
                actual_witness_gap_below=f'2^-{upper_bits}')


def sigma(mu):
    return (1+2*mu-mu*mu)/2


def check_mu(cells):
    """Outward rational bound on every mu in the continuous allowed range."""
    require(type(cells) is int and 1 <= cells <= 65536, 'invalid interval count')
    minimum = Fraction(1)
    for i in range(cells):
        lo = Fraction(cells+2*i, 3*cells)
        hi = lo+Fraction(2, 3*cells)
        # sigma is positive and increasing on [1/3,1], so this lower
        # bound applies to the entire closed interval, not just a sample.
        minimum = min(minimum, lo/sigma(hi)**4)
    return minimum


def certify(bits=GAP):
    require(__debug__, 'certificate dependencies need assertions enabled')
    require(type(bits) is int and bits >= 1, 'expected a positive target precision')
    require(arithmetic()['unresolved_gap'] == f'2^-{GAP}', 'wrong firmware cutoff')
    source = ROOT/'code/native_eabi_m0_pow_log_side.inc'
    require('constexpr unsigned Precision = 16384;' in source.read_text() and GAP == 16300,
            're-audit the RP2040 logarithmic stage')
    witness = check_witness()
    mu_lower = check_mu(256)
    # This kernel verifies the numeric inequalities. The algebraic
    # reductions from Laurent's Theorems 1 and 2 to these obligations
    # are in doc/measurements/m0-pow-laurent-limit-20261119.md.
    require(mu_lower > Fraction(4, 5), 'the mu interval lower bound is too loose')
    c = Fraction(16, 9)*Fraction(4, 5)
    # L=1 is impossible. The cardinality and weighted AM-GM bounds
    # give b>=1 for K>=5, otherwise b>=1/2 and 2 log K wins.
    require(all(2**(k-1) < k*k for k in (2, 3, 4)), 'small determinant exclusion')
    require(3*(5-1) >= 2*(5+1), 'large determinant exclusion')
    # L>=2 makes b>=1 for every K>=2, since 3(K-1)>=K+1.
    require(3*(2-1) >= 2+1, 'large L determinant exclusion')

    h0, x0 = ODD_PART_LOG_LOWER, LOG_X_LOWER
    w0 = 2*h0*x0
    growth = Fraction(h0*x0, 120)
    require(2*h0*h0 >= growth > 0, 'height-growth inequality')
    # Either t<=sqrt(M), or exp(t)-1>=t**5/120. Both give the
    # log(M) bound used when converting Laurent's Lambda' back to Delta.
    # Since log(3)<2, the transformed theorem-1 exponent loss is
    # > (c-1/growth)*W - 2. The theorem-2 auxiliary logarithm is positive.
    theorems_minimum_loss = (c-1/growth)*w0-2
    require(Fraction(8, 3)*w0 > 1 and c*w0 > theorems_minimum_loss > 0,
            'theorem 2 auxiliary factor or common bound')
    # Upper bound ln(2) to turn the common lower loss into a rigorous
    # floor of the number of bits which these formulae cannot certify.
    ln2_hi = Fraction(LN2[1], GRID.unit)
    excluded = theorems_minimum_loss//ln2_hi
    unchanged_bases_excluded = (8*c*x0*x0)//ln2_hi
    require(excluded >= 100_000 and excluded*ln2_hi <= theorems_minimum_loss,
            'common lower loss did not exclude the intended precision')
    return dict(
        status='RULED_OUT_AT_TARGET' if bits <= excluded else 'INCONCLUSIVE_AT_TARGET',
        source=SOURCE_URL, theorems=[1, 2], requested_gap_bits=bits,
        firmware_gap_bits=GAP, excluded_gap_bits_through=excluded,
        unchanged_bases_excluded_through=unchanged_bases_excluded,
        theorem_loss_nats_strictly_above=str(theorems_minimum_loss),
        mu_partition_cells=256, mu_over_sigma4_lower_millionths=(mu_lower*10**6)//1,
        witness=witness,
        scope='Direct use of the stated Laurent bounds on the two witness rationals or any '
              'independent pair of their integer products, with positive real logarithms '
              'and opposite nonzero integer coefficients. The formula limit is not a claim '
              'about the actual gap and does not '
              'disprove other separation proofs or cover substitutions with extra generators.',
        firmware_source_sha256=sha256(source.read_bytes()).hexdigest(),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bits', type=int, default=GAP)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    report = certify(args.bits)
    result = json.dumps(report, indent=2, sort_keys=True)+'\n'
    if args.json:
        with args.json.open('x') as out:
            out.write(result)
    print(result, end='')
    return 0 if report['status'] == 'RULED_OUT_AT_TARGET' else 2


if __name__ == '__main__':
    sys.exit(main())
