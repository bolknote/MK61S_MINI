#!/usr/bin/env python3
"""Certify a fixed precision for pow boundaries close to one, using Laurent 2."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from math import ceil, isqrt
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
ONE = 0x3FF0000000000000
DISTANCE_BITS = 37
SUFFICIENT_PRECISION = 8032
ROUND_BITS = 192
ROUND_SCALE = 1 << ROUND_BITS
SOURCE_URL = 'https://www.impan.pl/shop/en/publication/transaction/download/product/82485'


def down(value):
    return F(value.numerator*ROUND_SCALE//value.denominator, ROUND_SCALE)


def up(value):
    return F(ceil(value*ROUND_SCALE), ROUND_SCALE)


def sqrt_bounds(value):
    """Outward rational bounds, with the integer square inequalities checked."""
    assert value >= 0
    root = isqrt((value.numerator << (2*ROUND_BITS))//value.denominator)
    lower, upper = F(root, ROUND_SCALE), F(root+1, ROUND_SCALE)
    assert lower*lower <= value < upper*upper
    return lower, upper


def close_one_boundary(x, lower):
    """Whether base and midpoint lie in [1-2^-37,1+2^-37]."""
    below, above = 1 << (53-DISTANCE_BITS), 1 << (52-DISTANCE_BITS)
    return ONE-below <= x <= ONE+above and ONE-below <= lower < ONE+above


def close_one_input(x, y):
    """A sufficient input condition, without knowing the candidate midpoint."""
    return close_one_boundary(x, ONE) and (y & ((1 << 63)-1)) <= 0x3FE0000000000000


def discrete_domain():
    """Check every included encoding's interval and rational height exactly."""
    first, last = ONE-(1 << 16), ONE+(1 << 15)
    d = F(1, 1 << DISTANCE_BITS)

    def decode(encoding):
        return F.from_float(struct.unpack('<d', encoding.to_bytes(8, 'little'))[0])

    for encoding in range(first, last+1):
        base = decode(encoding)
        assert 1-d <= base <= 1+d
        assert max(base.numerator, base.denominator) <= 1 << 54
        assert close_one_boundary(encoding, ONE)
        if encoding < last:
            midpoint = (base+decode(encoding+1))/2
            assert 1-d < midpoint < 1+d
            assert midpoint != 1
            assert max(midpoint.numerator, midpoint.denominator) <= 1 << 54
            assert close_one_boundary(ONE, encoding)
    assert decode(first-1) < 1-d and decode(last+1) > 1+d
    assert (decode(first-1)+decode(first))/2 < 1-d
    assert (decode(last)+decode(last+1))/2 > 1+d
    assert not close_one_boundary(first-1, ONE)
    assert not close_one_boundary(last+1, ONE)
    assert not close_one_boundary(ONE, first-1)
    assert not close_one_boundary(ONE, last)
    return dict(base_encodings_including_one=last-first+1,
                midpoint_encodings=last-first,
                maximum_rational_height_log='54*ln(2)')


def certify():
    # Both dyadic bases (and their inverses) have height <=54*ln(2).
    # |ln(z)| <= d/(1-d) in [1-d,1+d]. Neither a midpoint nor an
    # active binary64 base can have a zero logarithm. The smallest
    # base log exceeds 2^-53; every midpoint log exceeds 2^-54.
    discrete = discrete_domain()
    ln2_lo = sum((F(2, (2*i+1)*3**(2*i+1)) for i in range(80)), F(0))
    ln2_hi = ln2_lo+F(9, 4*161*3**161)
    d = F(1, 1 << DISTANCE_BITS)
    log_limit = d/(1-d)
    assert F(1, (1 << 52)+1) > F(1, 1 << 53)
    assert F(1, (1 << 53)+1) > F(1, 1 << 54)

    # A PowerBounds overlap at P>=128 has a gap <2^-62 even at
    # the largest active y. A failed production 1024-bit interval
    # gives a much smaller gap to its certified midpoint as well.
    # Thus |y*ln(x)|>2^-55. The inequalities
    # below imply 2^(37-56)<|y|<2^(54-37); so q<=2^71 and p<2^53.
    epsilon = F(1, 1 << 62)
    interval_p = 1024
    interval_unit = F(1, 1 << interval_p)
    log_units = 12*(interval_p+16)+4+1074
    q_width = (log_units*(1 << 64)+2)*interval_unit
    endpoint_width = (4*(interval_p+16)+2)*interval_unit
    relative_width = 4*(q_width+1155*interval_unit)+4*endpoint_width
    assert relative_width < F(1, 1 << 400)
    assert relative_width/(1-relative_width) < epsilon
    assert F(1, 1 << 54)-epsilon > F(1, 1 << 55)
    assert log_limit+epsilon < 2*d
    # For |y|<=1/2 the true log has magnitude <=log_limit/2. A
    # midpoint outside [1-d,1+d] has |ln(m)|>=d/(1+d). Such a
    # boundary cannot overlap even the coarse P=128 enclosure.
    outside_log_gap = d/(1+d)-log_limit/2
    assert outside_log_gap > d/4 > epsilon
    maximum_shift = 108-DISTANCE_BITS
    assert maximum_shift == 71 and 54-DISTANCE_BITS < 53
    maximum_sum = (1 << maximum_shift)+(1 << 53)

    # Laurent, Theorem 2, D=1. Invert each base as needed so its
    # logarithm is positive; this preserves its rational height and
    # the absolute value of the cancelling form p*ln(alpha)-q*ln(beta).
    mu, sigma = F(1, 3), F(7, 9)
    rho_shift, a, h = 39, F(79), F(50)
    assert sigma == (1+2*mu-mu*mu)/2 and F(1, 3) <= mu <= 1
    rho = 1 << rho_shift
    assert rho > 1 and rho*log_limit+108*ln2_hi < a
    lambda_lo = down(sigma*rho_shift*ln2_lo)
    lambda_hi = up(sigma*rho_shift*ln2_hi)
    assert 0 < lambda_lo <= lambda_hi < 22 < h
    assert a*a > lambda_hi*lambda_hi and ln2_hi/2 < h

    # ln((p+q)/a)+ln(lambda)+1.81 < h. Bound the product before
    # taking logs: it is < (9/8)*2^69, and ln(9/8)<1/8.
    assert F(maximum_sum, 1)*22/a < F(9, 8)*(1 << 69)
    h_requirement = 69*ln2_hi+F(1, 8)+F(181, 100)
    assert h_requirement < h

    # Every operation is exact rational arithmetic with outward rounding.
    # Upper bounds use lower positive denominators independently, so
    # dependencies between lambda, H, omega and theta cannot narrow them.
    H_lo = down(h/lambda_hi+1/sigma)
    root_hi = sqrt_bounds(1+1/(4*H_lo*H_lo))[1]
    omega_hi = up(2*(1+root_hi))
    theta_hi = up(root_hi+1/(2*H_lo))
    omega_5_4_hi = sqrt_bounds(sqrt_bounds(omega_hi**5)[1])[1]
    theta_1_4_hi = sqrt_bounds(sqrt_bounds(theta_hi)[1])[1]
    root_H_lo = sqrt_bounds(H_lo)[0]
    inner_hi = up(omega_hi*omega_hi/9 +
                  8*lambda_hi*omega_5_4_hi*theta_1_4_hi/(3*a*root_H_lo) +
                  F(8, 3)*lambda_hi*omega_hi/(a*H_lo))
    C_hi = up(mu/(lambda_lo**3*sigma) *
              (omega_hi/6+sqrt_bounds(inner_hi)[1]/2)**2)
    C_prime_hi = sqrt_bounds(C_hi*sigma*omega_hi*theta_hi/(lambda_lo**3*mu))[1]
    z_hi = up(h+rho_shift*ln2_hi)
    assert C_prime_hi*z_hi*z_hi*a*a < 1 << 14
    loss_hi = up(C_hi*z_hi*z_hi*a*a + sqrt_bounds(omega_hi*theta_hi)[1]*z_hi +
                 14*ln2_hi)
    loss_nats = ceil(loss_hi)
    assert loss_nats == 5466
    gap_bits = int(F(loss_nats)/ln2_lo)+maximum_shift+1
    assert gap_bits*ln2_lo > loss_nats+maximum_shift*ln2_hi
    assert gap_bits == 7957

    # Dividing the nonzero form by q gives the gap for the original
    # pow boundary. An undecided P-bit power enclosure instead has
    # gap <2^(66-P). At P>=8032 these inequalities contradict each
    # other. The separately certified dependent nonzero gap is
    # >=2^-170; exact midpoint coefficients need at most 1728 bits.
    needed_precision = ((gap_bits+66+15)//16)*16
    assert needed_precision == SUFFICIENT_PRECISION <= 8192
    assert needed_precision > 1728 and needed_precision-66 > 170

    stages = {}
    for precision in (4096, 8192):
        words = precision//16
        leaf_work = 3**((words//16).bit_length()-1)*16*17//2
        stages[precision] = ((52+maximum_shift)*leaf_work + words*words +
                             52*4*words)

    sources = ('code/native_eabi_m0_pow_power_bounds.inc',
               'code/native_eabi_m0_pow_interval.inc',
               'dev/tools/certify_m0_pow_close_one.py',
               'dev/tools/certify_m0_pow_interval.py',
               'dev/tools/certify_m0_pow_power_bounds.py')
    return dict(
        status='PASS_CLOSE_ONE_SEPARATION', source=SOURCE_URL, theorem='Theorem 2, page 327',
        arithmetic='Exact Fractions, outward 192-bit rational square-root bounds',
        domain=dict(base_and_midpoint_interval='[1-2^-37,1+2^-37]',
                    maximum_denominator_shift=maximum_shift,
                    numerator_strict_upper_bound=1 << 53,
                    coefficient_bound_prerequisite='Gap <2^-62, from a PowerBounds overlap '
                        'at P>=128 or the midpoint hint from a failed production 1024-bit interval'),
        exhaustive_encoding_check=discrete,
        sufficient_input_domain=dict(base_interval='[1-2^-37,1+2^-37]',
                                     exponent_interval='[-1/2,1/2]',
                                     midpoint_outside_interval_log_gap_strict_lower_bound='2^-39'),
        parameters=dict(D=1, mu=str(mu), sigma=str(sigma), rho=f'2^{rho_shift}',
                        a1=str(a), a2=str(a), h=str(h),
                        h_requirement_upper=str(up(h_requirement)),
                        lambda_lower=str(lambda_lo), lambda_upper=str(lambda_hi),
                        H_lower=str(H_lo), omega_upper=str(omega_hi), theta_upper=str(theta_hi),
                        C_upper=str(C_hi), C_prime_upper=str(C_prime_hi),
                        loss_nats_upper=str(loss_hi)),
        logarithmic_form_loss_nats=loss_nats,
        nonzero_abs_log_gap_strict_lower_bound=f'2^-{gap_bits}',
        sufficient_power_product_precision_bits=needed_precision,
        production_8192_stage_decides=True,
        production_stage_work=dict(
            prerequisite='One boundary hint from the failed 1024-bit interval; then p<2^53 and q<=2^71.',
            maximum_full_products=52+maximum_shift+1,
            maximum_limb_multiply_accumulates=stages),
        stream_comparison_reachable_in_domain=False,
        source_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
        practical_uniform_latency_established=False,
        scope='A whole-domain separation certificate for the stated base/midpoint interval, '
              'conditional on the published theorem and existing enclosure/dependent/tie '
              'arguments. It bounds the final arithmetic stage for this domain only. '
              'Other inputs still lack a practical uniform latency proof. No compiler proof.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()
    report = certify()
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2)+'\n')
    print(report['status'], report['nonzero_abs_log_gap_strict_lower_bound'],
          report['sufficient_power_product_precision_bits'])


if __name__ == '__main__':
    main()
