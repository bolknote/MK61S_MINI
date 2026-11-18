#!/usr/bin/env python3
"""Certify an integer-power path through the largest active exponent binade."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from fractions import Fraction
from functools import cache
import hashlib
import json
from pathlib import Path
from time import monotonic

from midpoint_grid import FixedInterval, ceil_div

ROOT = Path(__file__).resolve().parents[2]
FIRST_Y = 0x43D0000000000000  # 2^62. The binary64 spacing is exactly 1024.
END_Y = 0x43E0000000000000
LOG_BITS = 160
GRID_BITS = 112
GRID = 1 << GRID_BITS
TABLE_BITS = 10
TABLE_SIZE = 1 << TABLE_BITS
OUTPUT_BITS = 27
OUTPUT_LIMIT = 1 << OUTPUT_BITS
POWER_PRECISION = 160
CHUNK = 1 << 16


@cache
def constants():
    grid = FixedInterval(LOG_BITS)
    ln2 = grid.log(2, 1)
    log_base = grid.log(1 << 53, (1 << 53)-1)
    # x=1-2^-53. For y=1024*n the natural log magnitude is n*step.
    step = grid.scale(log_base, 1024)
    assert step[0] >= grid.unit >> 43
    return grid, ln2, step


def cutoff(logarithm, step):
    """First binary64 exponent whose product exceeds the exact target log."""
    prior = logarithm[0]//step[1]
    assert prior == logarithm[1]//step[0] and (1 << 52) <= prior < (1 << 53)-1
    assert prior*step[1] < logarithm[0] <= logarithm[1] < (prior+1)*step[0]
    return FIRST_Y+prior+1-(1 << 52)


def geometry():
    grid, ln2, step = constants()
    # The closest other magnitudes are 1+-2^-52. Elementary bounds
    # on their logarithms make either saturation automatic at 2^62.
    d = Fraction(1, 1 << 52)
    assert (1 << 62)*d/(1+d) > 746 > Fraction(1075*ln2[1], grid.unit)
    overflow = grid.scale(ln2, 1024)
    correction = grid.log(1 << 54, (1 << 54)-1)
    overflow = overflow[0]-correction[1], overflow[1]-correction[0]
    underflow = grid.scale(ln2, 1075)
    upper_output = grid.scale(ln2, 1074-OUTPUT_BITS)
    result = dict(overflow=cutoff(overflow, step), band=cutoff(upper_output, step),
                  underflow=cutoff(underflow, step))
    assert FIRST_Y < result['overflow'] < result['band'] < result['underflow'] < END_Y
    return result


@cache
def log_tables():
    grid, ln2, step = constants()
    mantissa = [grid.log(TABLE_SIZE+i, TABLE_SIZE) for i in range(TABLE_SIZE)]
    # For an odd integer n in binade e the target is
    # (1075-e)*ln(2)-ln(n/2^e).
    scales = [grid.scale(ln2, 1075-e) for e in range(OUTPUT_BITS+1)]
    return grid, step, mantissa, scales


def verify_chunk(bounds):
    first, stop = bounds
    grid, step, anchors, scales = log_tables()
    smallest, closest = GRID, None
    for index in range(first, stop):
        odd = 2*index+1
        exponent = odd.bit_length()-1
        scaled = odd << TABLE_BITS
        anchor = scaled >> exponent
        lo, hi = anchors[anchor-TABLE_SIZE]
        anchor_scaled = anchor << exponent
        if scaled != anchor_scaled:
            tail_lo, tail_hi = grid.log(scaled, anchor_scaled)
            lo += tail_lo
            hi += tail_hi
        target_lo, target_hi = scales[exponent]
        low = ((target_lo-hi) << GRID_BITS)//step[1]
        high = ceil_div((target_hi-lo) << GRID_BITS, step[0])
        residue = low & (GRID-1)
        gap = min(residue, GRID-residue-(high-low))
        # A borderline case would need a finer checker or a different
        # band. No near-integer value is assumed to lie on either side.
        assert gap > GRID >> (88-43), (index, gap)
        if gap < smallest:
            smallest, closest = gap, index
    return stop-first, smallest, closest


def work_and_separation(minimum):
    # The first midpoint above the band is separated by
    # log(1+2^-(OUTPUT_BITS+1)).
    grid_gap_bits = GRID_BITS-(minimum.bit_length()-1)
    log_gap_bits = min(grid_gap_bits+43, 88)
    outside_gap_lower = Fraction(1, (1 << (OUTPUT_BITS+1))+1)
    assert outside_gap_lower > Fraction(1, 1 << log_gap_bits)
    # The normalized lower-bound power has at most p-1 multiplication
    # losses. The upward bound can additionally round after normalization.
    max_p = (1 << 63)-1024
    relative_width = (4*(max_p-1)+1)*Fraction(2)**(1-POWER_PRECISION)
    assert relative_width < Fraction(1, 1 << 94) < Fraction(1, 1 << log_gap_bits)
    words = POWER_PRECISION//16
    squares, base_products = 62, 52
    multiply_accumulates = squares*words*(words+1)//2+base_products*4*words
    return log_gap_bits, dict(squares=squares, multiply_by_base=base_products,
                              limb_multiply_accumulates=multiply_accumulates)


def fast_argument():
    # For y=1024*n and h=2^-53, the first two terms of -y*log(1-h)
    # have Q64 values n*2^21 and n*2^-33. The second cannot carry out
    # of the low limb. Its floor costs <1 unit and the tail <1 more.
    h = Fraction(1, 1 << 53)
    p = (1 << 63)-1024
    assert 1024*h*(1 << 64) == 1 << 21
    assert 1024*h*h*(1 << 64)/2 == Fraction(1, 1 << 33)
    assert ((1 << 64)-(1 << 21))+(((1 << 53)-1) >> 33) < 1 << 64
    assert p*h**3*(1 << 64)/(3*(1-h)) < 1
    return dict(fractional_bits=64, error_strict_upper_bound_units=2)


def certify(workers):
    cuts = geometry()
    tasks = [(i, min(i+CHUNK, OUTPUT_LIMIT)) for i in range(0, OUTPUT_LIMIT, CHUNK)]
    start = monotonic()
    count, minimum, closest = 0, GRID, None
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for part, (checked, gap, index) in enumerate(pool.map(verify_chunk, tasks), 1):
            count += checked
            if gap < minimum:
                minimum, closest = gap, index
            if part % 32 == 0 or part == len(tasks):
                print(f'{part}/{len(tasks)} slices, {count} midpoints, {monotonic()-start:.1f}s', flush=True)
    assert count == OUTPUT_LIMIT and closest is not None
    log_gap_bits, work = work_and_separation(minimum)
    paths = (Path(__file__), Path(__file__).with_name('midpoint_grid.py'),
             ROOT/'code/native_eabi_m0_pow_large_constants.inc',
             ROOT/'code/native_eabi_m0_pow_large.inc', ROOT/'code/native_eabi_m0_pow_large_power.inc',
             ROOT/'code/native_eabi_m0_pow_power_bounds.inc',
             ROOT/'code/native_eabi_m0_pow_fast.inc', ROOT/'code/native_eabi_m0_pow_exp_round.inc',
             ROOT/'code/native_eabi_m0_cr.cpp', ROOT/'dev/tools/certify_m0_pow_fast.py')
    return dict(
        status='PASS_LARGE_EXPONENT_BAND', exceptional_base_encoding='3fefffffffffffff',
        minimum_magnitude_encoding=f'{FIRST_Y:016x}',
        cutoff_encodings={key: f'{value:016x}' for key, value in cuts.items()},
        rounded_subnormal_codes_maximum=OUTPUT_LIMIT,
        checked_midpoints=count, closest_lower_encoding=f'{closest:016x}',
        minimum_exponent_grid_distance_units=minimum, exponent_grid_fractional_bits=GRID_BITS,
        log_gap_strict_lower_bound=f'2^-{log_gap_bits}',
        largest_active_binade_positive_exponents_all_bases=END_Y-cuts['band'],
        largest_active_binade_negative_exponents_all_bases=END_Y-cuts['overflow'],
        positive_exponents_in_subnormal_power_path=cuts['underflow']-cuts['band'],
        fast_exp_argument=fast_argument(),
        integer_power_precision_bits=POWER_PRECISION, power_work_bound=work,
        source_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in paths},
        practical_uniform_bound_for_all_binary64=False)


def header():
    cuts = geometry()
    return ('// Generated by research/m0-pow-comparison-20261117/large_exponents.py.\n'
            '#pragma once\n\n'
            'namespace m0_pow_large {\n'
            f'constexpr uint32_t FirstHighWord = 0x{FIRST_Y >> 32:08x}U;\n'
            'constexpr uint64_t ExceptionalBase = UINT64_C(0x3fefffffffffffff);\n'
            f'constexpr uint64_t Overflow = UINT64_C(0x{cuts["overflow"]:016x});\n'
            f'constexpr uint64_t SubnormalBand = UINT64_C(0x{cuts["band"]:016x});\n'
            f'constexpr uint64_t Underflow = UINT64_C(0x{cuts["underflow"]:016x});\n'
            '}\n')


def main():
    assert __debug__, 'Keep Python assertions enabled'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--header', type=Path, help='write a copy of the checked C++ constants')
    args = parser.parse_args()
    assert (ROOT/'code/native_eabi_m0_pow_large_constants.inc').read_text() == header()
    report = certify(args.workers)
    if args.header is not None:
        args.header.write_text(header())
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(report['status'], report['checked_midpoints'], report['log_gap_strict_lower_bound'])


if __name__ == '__main__':
    main()
