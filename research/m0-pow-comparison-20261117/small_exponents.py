#!/usr/bin/env python3
"""Certify a 512-bit pow interval for all bases and a grid of small exponents."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from fractions import Fraction
from functools import cache
import hashlib
import json
from math import factorial
from pathlib import Path
import sys
from time import monotonic

from midpoint_grid import FixedInterval, ceil_div

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'dev/tools'))
from certify_m0_pow_power_bounds import near_one_midpoint_counts

MIN_EXPONENT, MAX_EXPONENT = -64, -55
BITS = 144
UNIT = 1 << BITS
MASK = UNIT-1
LOG_BITS = 256
GRID = UNIT >> 52
TABLE_BITS = 12
TABLE_SIZE = 1 << TABLE_BITS
REMAINDER_BITS = BITS-2*TABLE_BITS
TERM_COUNT = 6
COEFFICIENTS = tuple(UNIT//factorial(index) for index in range(TERM_COUNT))
REVERSE_COEFFICIENTS = tuple(reversed(COEFFICIENTS[:-1]))
REQUIRED_GRID_GAP_BITS = 104
CHUNK = 4096


def exp_lower(residual, log2_lower, coefficients):
    """Evaluate the downward-rounded Taylor polynomial in fixed point."""
    z = residual*log2_lower >> BITS
    result = coefficients[-1]
    for coefficient in reversed(coefficients[:-1]):
        result = coefficient+(result*z >> BITS)
    return result


def exp_table(step_bits, log2_lower):
    """Tabulate lower bounds and the maximum width in fixed-point units."""
    terms = 11
    assert 2*UNIT < factorial(terms) << (terms*step_bits)
    coefficients = tuple(UNIT//factorial(index) for index in range(terms))
    step_lower = exp_lower(UNIT >> step_bits, log2_lower, coefficients)
    # Each Horner step loses <2 units and contracts by <1/2. The
    # Taylor tail contributes <1 unit and argument rounding <4.
    step_upper = step_lower+9
    lower = upper = UNIT
    table = []
    maximum_width = 0
    for _ in range(TABLE_SIZE):
        table.append(lower)
        maximum_width = max(maximum_width, upper-lower)
        lower = lower*step_lower >> BITS
        upper = (upper*step_upper+MASK) >> BITS
    if step_bits == TABLE_BITS:
        assert lower <= 2*UNIT <= upper
    else:
        assert upper < 2*UNIT
    return tuple(table), maximum_width


@cache
def constants():
    log_grid = FixedInterval(LOG_BITS)
    log2 = log_grid.log(2, 1)
    log2_floor = log2[0] >> (LOG_BITS-BITS)
    assert log2_floor == log2[1] >> (LOG_BITS-BITS)
    assert UNIT//2 < log2_floor < UNIT-1
    assert 2*UNIT < factorial(TERM_COUNT) << (2*TABLE_BITS*TERM_COUNT)
    coarse, coarse_width = exp_table(TABLE_BITS, log2_floor)
    fine, fine_width = exp_table(2*TABLE_BITS, log2_floor)
    # A product of three factors in [1,2], rounded downward twice.
    # Each factor error is amplified by at most 4. The two products
    # lose less than 3 more units after the last multiplication.
    error = 4*(coarse_width+fine_width+9)+3
    return log_grid, log2, log2_floor, coarse, fine, error


@cache
def breakpoint_logs(exponent):
    """Enclose the logs of floats and midpoints that can be close to pow."""
    grid, log2, _, _, _, _ = constants()
    below, above = near_one_midpoint_counts(exponent, precision=128)
    rows = []
    # The formulas for the number of odd displacements also bound
    # the even displacements when both are counted on the same grid.
    for offset in range(-2*below, 2*above+1):
        if offset == 0:
            continue  # The breakpoint at one is handled analytically.
        shift = 54 if offset < 0 else 53
        denominator = 1 << shift
        smaller, larger = sorted((denominator, denominator+offset))
        low, high = grid.divide(grid.log(larger, smaller), log2)
        rows.append((offset, low, high))
    return rows


def gap_to_grid(low, high):
    offset = low & (GRID-1)
    return min(offset, GRID-offset-(high-low))


def certify_chunk(task):
    exponent, bits, first, stop = task
    _, _, log2_floor, coarse, fine, exp_error = constants()
    logs = breakpoint_logs(exponent)
    denominator_shift = LOG_BITS-BITS-(bits-1-exponent)
    assert denominator_shift >= 0
    threshold = UNIT >> REQUIRED_GRID_GAP_BITS
    inverse_numerator = 2*UNIT*UNIT
    residual_mask = (1 << REMAINDER_BITS)-1
    minimum = [GRID, GRID]
    closest = [None, None]
    for significand in range(first, stop):
        denominator = significand << denominator_shift
        for offset, log_low, log_high in logs:
            # t = abs(log2(m)/y). It must admit a single floor so both
            # signs can be reduced to [1,2] with one exponential.
            low = log_low//denominator
            high = (log_high+denominator-1)//denominator
            if low >> BITS != high >> BITS:
                raise ArithmeticError(('ambiguous exponent reduction', exponent, significand, offset))
            fraction = low & MASK
            j = fraction >> (BITS-TABLE_BITS)
            k = (fraction >> REMAINDER_BITS) & (TABLE_SIZE-1)
            residual = fraction & residual_mask
            z = residual*log2_floor >> BITS
            lower_exp = COEFFICIENTS[-1]
            for coefficient in REVERSE_COEFFICIENTS:
                lower_exp = coefficient+(lower_exp*z >> BITS)
            forward_low = ((coarse[j]*fine[k] >> BITS)*lower_exp) >> BITS
            # On [0,1], d(2^t)/dt <= 2*ln(2) < 2.
            forward_high = forward_low+exp_error+2*(high-low)
            inverse_low = inverse_numerator//forward_high
            inverse_high = (inverse_numerator+forward_low-1)//forward_low
            gap = min(gap_to_grid(forward_low, forward_high),
                      gap_to_grid(inverse_low, inverse_high))
            if gap <= threshold:
                raise ArithmeticError(('unresolved breakpoint', exponent, significand, offset, gap))
            parity = offset & 1
            if gap < minimum[parity]:
                minimum[parity] = gap
                closest[parity] = (exponent, significand, offset)
    return (stop-first)*len(logs), minimum, closest


def interval_work():
    precision = 512
    unit = Fraction(1, 1 << precision)
    q_width = ((12*(precision+16)+4+1074)*(1 << 64)+2)*unit
    endpoint_width = (4*(precision+16)+2)*unit
    relative_width = 4*(q_width+1155*unit)+4*endpoint_width
    assert relative_width/(1-relative_width) < Fraction(1, 1 << 400)
    assert (Fraction(1, 3)+unit)**2+unit < Fraction(1, 8)
    shrink = 44
    assert 745*Fraction(2)**(MAX_EXPONENT+1)+q_width < Fraction(1, 1 << shrink)
    log_steps = ceil_div(precision, 3)
    exp_steps = ceil_div(precision, shrink)
    products = 2+2*log_steps+4*exp_steps
    words = precision//16+4
    return dict(log_series_iterations=log_steps, exp_iterations_per_endpoint=exp_steps,
                maximum_full_fixed_point_products=products,
                maximum_product_limb_multiply_accumulates=products*words**2,
                maximum_limb_divisions=(2*log_steps+4*exp_steps)*words)


def core_rounding_gap(gap_bits):
    # CORE-MATH gives relative error <2^-240. The rejected bit patterns
    # are within 61*2^10 significand units of a 54-bit grid point.
    # In this domain both the result and approximation lie in (1/2,2).
    epsilon = Fraction(1, 1 << 240)
    maximum_abs_log = 745*Fraction(2)**(MAX_EXPONENT+1)
    exact_lower = 1-maximum_abs_log
    exact_upper = 1/(1-maximum_abs_log)
    assert Fraction(1, 2) < exact_lower*(1-epsilon)
    assert exact_upper*(1+epsilon) < 2
    rejected_value_gap = Fraction(61 << 10, 1 << 255)
    rejected_log_gap = epsilon/(1-epsilon)+2*rejected_value_gap
    assert rejected_log_gap < Fraction(1, 1 << 237) < Fraction(1, 1 << gap_bits)
    return dict(relative_approximation_error_strict_upper_bound='2^-240',
                rejected_absolute_log_gap_strict_upper_bound='2^-237',
                rescue_reachable_in_certified_domain=False)


def certify(bits, first, last, workers):
    assert __debug__, 'Keep Python assertions enabled'
    assert 1 <= bits <= 24 and MIN_EXPONENT <= first <= last <= MAX_EXPONENT
    hidden = 1 << (bits-1)
    tasks = [(exponent, bits, low, min(low+CHUNK, 2*hidden))
             for exponent in range(first, last+1)
             for low in range(hidden, 2*hidden, CHUNK)]
    start = monotonic()
    count, minimum, closest = 0, [GRID, GRID], [None, None]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for index, (tested, gaps, witnesses) in enumerate(pool.map(certify_chunk, tasks), 1):
            count += tested
            for parity, gap in enumerate(gaps):
                if gap < minimum[parity]:
                    minimum[parity] = gap
                    closest[parity] = witnesses[parity]
            if index % 64 == 0 or index == len(tasks):
                print(f'{index}/{len(tasks)} slices, {count} breakpoint preimages, '
                      f'{monotonic()-start:.1f}s', flush=True)
    rows = {str(exponent): len(breakpoint_logs(exponent))
            for exponent in range(first, last+1)}
    assert count == hidden*sum(rows.values()) > 0 and all(closest)
    min_grid_gap = min(minimum)
    assert min_grid_gap > UNIT >> REQUIRED_GRID_GAP_BITS
    # |y| >= 2^-64, and ln(u) on [1,2] has derivative at least 1/2.
    gap_bits = 64+1+BITS-(min_grid_gap.bit_length()-1)
    assert gap_bits < 400
    # The 128-bit range computation covers every non-unit breakpoint
    # within its comparison epsilon, which is greater than 2^-125.
    assert Fraction(1, 1 << 125) > Fraction(1, 1 << gap_bits)
    # For x != 1 the nearest possible base below one is 1-2^-53
    # and above one is 1+2^-52. In either case |ln(x)|>2^-53.
    assert Fraction(1, (1 << 52)+1) > Fraction(1, 1 << 53)
    assert 64+53 < gap_bits
    src = Path(__file__).resolve().parent
    files = (Path(__file__), src/'midpoint_grid.py',
             ROOT/'dev/tools/certify_m0_pow_power_bounds.py',
             ROOT/'dev/tools/certify_m0_pow_interval.py',
             ROOT/'third_party/core_math/pow/pow.c',
             ROOT/'code/native_eabi_m0_cr.cpp',
             ROOT/'code/native_eabi_m0_pow_interval.inc',
             ROOT/'code/native_eabi_m0_pow_interval_table.inc')
    witnesses = {}
    for name, (exponent, significand, offset), gap in zip(('float', 'midpoint'), closest, minimum):
        witnesses[name] = dict(exponent_binade=exponent, significand=significand,
                               breakpoint_offset_units=offset,
                               breakpoint_offset_shift=54 if offset < 0 else 53,
                               distance_to_mantissa_grid_units=gap)
    return dict(status='PASS_PREIMAGE_GRID', exponent_binades=[first, last],
                normalized_exponent_significand_bits=bits,
                signed_binary64_exponents=2*hidden*(last-first+1),
                base_domain='all finite positive binary64 bases',
                checked_breakpoint_preimages=count,
                checked_normalized_preimages_both_signs=2*count,
                breakpoint_counts=rows, fixed_point_bits=BITS,
                minimum_distance_to_mantissa_grid_units=min_grid_gap,
                closest=witnesses,
                absolute_log_gap_strict_lower_bound=f'2^-{gap_bits}',
                first_512_bit_stage_decides=True, first_512_bit_work=interval_work(),
                core_math_256_bit_rounding=core_rounding_gap(gap_bits),
                source_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in files},
                practical_uniform_bound_for_all_binary64=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--significand-bits', type=int, default=20)
    parser.add_argument('--first-exponent', type=int, default=MIN_EXPONENT)
    parser.add_argument('--last-exponent', type=int, default=MAX_EXPONENT)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = certify(args.significand_bits, args.first_exponent, args.last_exponent, args.workers)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(report['status'], report['signed_binary64_exponents'], 'signed exponents',
          report['absolute_log_gap_strict_lower_bound'], flush=True)


if __name__ == '__main__':
    main()
