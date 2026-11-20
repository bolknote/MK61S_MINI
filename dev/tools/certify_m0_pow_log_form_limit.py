#!/usr/bin/env python3
"""Verify numerical limits of logarithmic estimates for binary64 pow."""

import argparse
from fractions import Fraction as F
from hashlib import sha256
import json
from math import gcd
from pathlib import Path
import sys

from certify_m0_pow_laurent_limit import (
    GRID, LN2, MIDPOINT_LOWER, ODD_PART_LOG_LOWER, Q, X,
    certify as certify_laurent, normal_coefficient, require,
)
from certify_m0_pow_log_side import GAP, ROOT


KIT = 'https://arxiv.org/pdf/2205.08899v3'
TORUS = 'https://arxiv.org/html/2610.28079v1#S11'
MIN_K = 3
MIN_L = 5
MIN_SIDE = 4
G = F(25, 108)
LN2_LO = F(LN2[0], GRID.unit)
LN2_HI = F(LN2[1], GRID.unit)


def three_log_limit(height, coefficient):
    """Check the numerical inequalities for Theorem 2.1, as derived in the note."""
    k_factor = 1+F(1, MIN_K)
    require(F(1, 4)-k_factor/72 == G, 'three-log determinant density')
    require(F(MIN_SIDE-1, MIN_SIDE)**4*MIN_SIDE >= 1,
            'lower bound for the numerator of b')

    # exp(t)/t^2 is minimized at t=2 and e>8/3 by its positive series.
    e_lower = sum(F(1, j) for j in (1, 1, 2, 6))
    exp_over_square = e_lower**2/4
    h_limit = 6*(6*G)**3*height**2*MIN_L**2*exp_over_square/k_factor**3
    require(h_limit.denominator == 1 and h_limit > GAP, 'three-log exponent loss')
    limit = int(h_limit)

    # If H=K*L*log2(rho) <= limit, first use b>1/K in (2.8) to
    # bound the heights. The coefficient vector then forces b>1.
    max_k = limit//MIN_L
    max_log_k = max_k.bit_length()*LN2_HI
    denominator = 2*G*MIN_L*MIN_SIDE
    height_cap = (k_factor*limit*LN2_HI/2 + F(2, 3)*max_k*max_log_k)/denominator
    b_lower = F((MIN_SIDE-1)**2, 4)*coefficient/(6*height_cap*max_k**2)
    require(b_lower > 1, 'coefficients do not force b>1')

    # For arbitrary H>=15, height < H^2 follows from the same
    # inequality using ln K < H and K <= H/MIN_L.
    require(k_factor/2+F(2, 3*MIN_L) < denominator,
            'quadratic height bound')
    # 1/A < 32 H^4, and H-5-4 log2(H) is increasing here.
    require(limit*LN2_LO > 4, 'conversion to the pow gap is not monotone')
    excluded = limit-5-4*limit.bit_length()
    require(excluded > GAP, 'three-log gap conversion')
    return dict(formula_loss_bits_strictly_above=limit,
                gap_bits_excluded_through=excluded,
                b_lower_under_loss_cap_thousandths=int(1000*b_lower))


def other_plane_limit(coefficient, raw_exponent, gap_bits):
    """Check the Laurent limits for planes outside span(log(x),log(m))."""
    normal_lower = coefficient//(raw_exponent+1)
    require(normal_lower >= 1 << 42, 'short normal to a different plane')
    # In each row alpha>1, height(alpha) >= max(abs(row))/2.
    # The cross product of two rows has a coefficient <=8*h1*h2.
    small_t_w = F(normal_lower, 2*32)
    # ||n x log||_2 >= ||n||_2 * |Delta|/4. One coordinate is at
    # least half its Euclidean length. The mixed terms of a1*a2
    # are >= (rho-1) times that coordinate in absolute value.
    mixed_lower = F(normal_lower, 8*(1 << gap_bits))
    require(45*LN2_HI < 32, 'exponential lower bound at the split')
    large_t_w = mixed_lower*(1 << 44)/32
    w_lower = min(small_t_w, large_t_w)
    require(w_lower >= 1 << 21 and large_t_w > 32,
            'large- and small-t bounds for Laurent W')
    # (exp(t)-1)/t^2 grows for t>=32, so W>t in that branch.
    # For t<=32 this follows from small_t_w. Thus M <= W*t <= W^2.
    # Theorem 1's loss is > c*W-ln(4*M) with c=64/45. It is
    # > W because ln(4)+2*ln(W) < (c-1)*W for W>=w_lower.
    c = F(64, 45)
    require((c-1)*w_lower > (2+2*int(w_lower).bit_length())*LN2_HI
            and (c-1)*w_lower > 2, 'two-log correction or its monotonicity')
    require(F(8, 3)*w_lower > 1, 'theorem 2 logarithmic factor')
    return int(w_lower//LN2_HI)


def torus_single_slope_limit():
    """Evaluate the necessary exponent derived from (11.14) and (11.16)."""
    # The diagonal jet-space volume gives K*(w0/v)^2*theta <= 1.
    # In (11.14), A > theta and A > 1/(nu*(1-eta)). Use the
    # maximum of eta^3*(1-eta) at eta=3/4, and c2^2=2*ln(2)^2/9.
    max_collision_factor = F(27, 256*6)*F(2, 9)*LN2_HI**2
    minimum_radius = 4  # R = 4*K*(1+abs(ln(x))+abs(ln(m))), K >= 1.
    necessary_nu = minimum_radius**2/max_collision_factor
    require(necessary_nu > 8192, 'single-slope collision cost')

    # At the firmware gap, |xi-p/q| = 2^-GAP/abs(ln(x)). The
    # requested q^-4 estimate has constant 2^-constant_bits.
    require(1074*LN2_HI < 1 << 10, 'binary64 base logarithm bound')
    maximum_gap_nu = F(GAP+10, 2)  # q >= 4, so log2(q) >= 2.
    constant_bits = GAP-53-4*116
    maximum_ratio_nu = 4+F(constant_bits, 2)
    require(max(maximum_gap_nu, maximum_ratio_nu) < 8192,
            'single-slope costs do not exclude the target')
    return dict(source=TORUS, minimum_denominator=4,
                necessary_exponent_strictly_above=int(necessary_nu),
                firmware_gap_exponent_upper=str(maximum_gap_nu),
                requested_ratio_exponent_upper=str(maximum_ratio_nu),
                requested_ratio_constant_bits=constant_bits)


def certify():
    previous = certify_laurent()
    witness = previous['witness']
    a, b = witness['odd_parts']
    p, q = witness['numerator'], witness['denominator']
    x_coefficient, xe = normal_coefficient(X)
    m_coefficient, me = normal_coefficient(MIDPOINT_LOWER)
    scale = p*xe-q*me
    require(x_coefficient == a and 2*m_coefficient+1 == b and q == Q and gcd(p, q) == 1,
            'mismatched witness')
    require(q < p < 2*q and 0 < scale < q and 0 < xe < me < 1024,
            'witness logarithm form or scale')
    height = ODD_PART_LOG_LOWER
    require(gcd(a, b) == gcd(a, 2) == gcd(b, 2) == 1 and height > 0
            and 2*LN2_LO > 1+2*LN2_HI/height and 2*height > 1,
            'height bound for normalized logs')
    require(witness['actual_witness_gap_at_least'] == '2^-57', 'witness cross product bound')

    three = three_log_limit(height, q)
    other_plane = other_plane_limit(q, xe, 57)
    two = min(previous['excluded_gap_bits_through'], other_plane)
    require(two > GAP and three['gap_bits_excluded_through'] > GAP, 'firmware cutoff still attainable')
    source = ROOT/'code/native_eabi_m0_pow_log_side.inc'
    return dict(status='FORMULAS_RULED_OUT_AT_FIRMWARE_GAP', firmware_gap_bits=GAP,
                firmware_source_sha256=sha256(source.read_bytes()).hexdigest(),
                witness=witness, normalized_scale_coefficient=scale,
                laurent_1_and_2_gap_bits_excluded_through=two,
                laurent_other_planes_gap_bits_excluded_through=other_plane,
                kit_theorem_2_1=dict(source=KIT, **three),
                torus_single_slope=torus_single_slope_limit())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    result = json.dumps(certify(), indent=2, sort_keys=True)+'\n'
    if args.json:
        with args.json.open('x') as out:
            out.write(result)
    print(result, end='')
    return 0


if __name__ == '__main__':
    sys.exit(main())
