#!/usr/bin/env python3
"""Check the lowest active pow exponent binade in the linked Pico H ELF."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

from m0_mpfr_oracle import Oracle
from native_eabi_m0_arm_self_test import Machine, SP, nan
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dev/tools'))
from certify_m0_pow_tiny_binade import FIRST, HIDDEN, MAXIMUM, ONE, TARGET, absolute_log, proof

PUBLIC = '_ZN12compact_math3powEdd'
SIGN = 1 << 63
INFINITY = MAXIMUM + 1
LIMIT = FIRST + HIDDEN


def around(center, radius=2):
    return range(center - radius, center + radius + 1)


def corpus(cuts, bases):
    rng = random.Random(0x3bf00000)
    first_base, last_base = bases
    endpoints = {0, 1, 2, 3, HIDDEN - 1, HIDDEN, HIDDEN + 1, ONE - 1,
                 ONE, ONE + 1, MAXIMUM - 1, MAXIMUM, INFINITY, INFINITY + 1,
                 INFINITY | (1 << 51)}
    endpoints.update(around(first_base))
    endpoints.update(around(last_base))
    magnitudes = set().union(*(around(bound) for bound in (FIRST, LIMIT, *cuts)))
    pairs = {(x | sx, y | sy) for x in endpoints for y in magnitudes
             for sx in (0, SIGN) for sy in (0, SIGN)}
    # Test the closest y on both sides of the lower midpoint for every
    # relevant power of two and for bases spread across the active tails.
    powers = [1 << (s + 1074) if s < -1022 else (s + 1023) << 52
              for s in range(-1074, 1024)]
    tails = {*endpoints, *powers}
    tails.update(rng.randrange(1, first_base) for _ in range(1024))
    tails.update(rng.randrange(last_base, MAXIMUM + 1) for _ in range(1024))
    for x in tails:
        if not 0 < x < first_base and not last_base < x <= MAXIMUM:
            continue
        log_lower, log_upper = absolute_log(x)
        below = TARGET[0] // log_upper
        assert below == TARGET[1] // log_lower
        middle = FIRST + below - HIDDEN
        sign = SIGN if x > ONE else 0
        pairs.update((x, y | sign) for y in around(middle, 1) if FIRST <= y < LIMIT)
        pairs.add((x, rng.randrange(FIRST, LIMIT) | sign))
    return sorted(pairs)


def symbol_address(arm, name):
    address, = {value & ~1 for symbol, value in arm.elf.symbols.items() if name in symbol}
    return address


def count_routes(arm):
    visits = Counter()

    def entered(_uc, _address, _size, stage):
        visits[stage] += 1

    for stage in ('pow_lowest_binade', 'pow_refined_log', 'mk61_m0_cr_pow'):
        address = symbol_address(arm, stage)
        arm.uc.hook_add(UC_HOOK_CODE, entered, stage, begin=address, end=address)
    arm.uc.ctl_flush_tb()
    return visits


def verify(arm, oracle, cuts, bases, midpoint_units, visits):
    cases = corpus(cuts, bases)
    categories = Counter()
    rounds = Counter()
    for x, y in cases:
        visits.clear()
        expected = oracle.reference('pow', x, y)
        got = arm.call(PUBLIC, x, y)[0]
        same = (nan(got) and bool(got & (1 << 51))) if nan(expected) else got == expected
        assert same, (hex(x), hex(y), hex(got), hex(expected), visits)
        magnitude = y & (SIGN - 1)
        if not (FIRST <= magnitude < LIMIT and 0 < x <= MAXIMUM and x != ONE):
            continue
        assert visits['pow_lowest_binade'] == 1, (hex(x), hex(y), visits)
        negative = bool(y & SIGN)
        universal = magnitude < cuts[int(negative)]
        inside = bases[0] <= x <= bases[1]
        increasing = (x < ONE) == negative
        field, coefficient = divmod(x, HIDDEN)
        exponent = field - 1023 if field else x.bit_length() - 1 - 1074
        if field:
            coefficient |= HIDDEN
        power_of_two = not coefficient & (coefficient - 1)
        n = HIDDEN + magnitude - FIRST
        j = -exponent - 1 if x < ONE else exponent
        if universal or inside or increasing:
            assert got == ONE and not visits['pow_refined_log'] and not visits['mk61_m0_cr_pow']
            categories['early_one'] += 1
        elif n*j >= midpoint_units or n*(j+1) < midpoint_units:
            assert got == ONE - (n*j >= midpoint_units)
            assert not visits['pow_refined_log'] and not visits['mk61_m0_cr_pow']
            categories['integer_bounds'] += 1
        elif power_of_two:
            assert not visits['pow_refined_log'] and not visits['mk61_m0_cr_pow']
            categories['exact_power_of_two'] += 1
        else:
            assert visits['pow_refined_log'] == 1
            category = 'subnormal_q94' if x < HIDDEN else 'normal_q94'
            categories[category] += 1
            categories['q94_fallbacks'] += visits['mk61_m0_cr_pow']
        rounds[f'{got:016x}'] += 1
    assert all(categories[key] for key in
               ('early_one', 'integer_bounds', 'exact_power_of_two', 'subnormal_q94', 'normal_q94'))
    assert set(rounds) == {f'{ONE:016x}', f'{ONE - 1:016x}'}
    return dict(cases=len(cases), categories=dict(categories), results_in_binade=dict(rounds))


def verify_ambiguity_guard(arm, oracle, visits, x, midpoint):
    # No natural fallback is expected in a small corpus. Substitute a
    # log on the wrong side of the midpoint, one Q157 unit away, and
    # verify that the normal CORE-MATH call gets the unmodified inputs.
    log_lower, log_upper = absolute_log(x)
    below = TARGET[0] // log_upper
    assert below == TARGET[1] // log_lower
    address = symbol_address(arm, 'pow_refined_log')
    for n, offset, result in ((below, 1, ONE), (below + 1, -1, ONE - 1)):
        y = FIRST + n - HIDDEN
        assert FIRST <= y < LIMIT and oracle.reference('pow', x, y) == result
        injected = (((midpoint + offset) << 53) + n - 1) // n
        assert injected*n >> 53 == midpoint + offset
        log_result = struct.pack('<QQII?7x', injected >> 64, injected & ((1 << 64) - 1),
                                 94, 128, True)

        def use_injected_log(uc, _address, _size, _data):
            uc.mem_write(uc.reg_read(UC_ARM_REG_R0), log_result)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        hook = arm.uc.hook_add(UC_HOOK_CODE, use_injected_log, begin=address, end=address)
        arm.uc.ctl_flush_tb()
        try:
            visits.clear()
            assert arm.call(PUBLIC, x, y)[0] == result
            assert visits['pow_refined_log'] == visits['mk61_m0_cr_pow'] == 1
        finally:
            arm.uc.hook_del(hook)
            arm.uc.ctl_flush_tb()
    return 2


def counters(control, candidate, oracle, cuts, bases):
    rows = {'minimum_subnormal_returns_one': (1, cuts[0] - 1),
            'minimum_subnormal_crosses_midpoint': (1, cuts[0]),
            'maximum_finite_returns_one': (MAXIMUM, SIGN | (cuts[1] - 1)),
            'maximum_finite_crosses_midpoint': (MAXIMUM, SIGN | cuts[1]),
            'adjacent_subnormal_crosses_midpoint': (3, LIMIT - 1),
            'normal_below_one_crosses_midpoint': (bases[0] - 1, LIMIT - 1),
            'normal_above_one_crosses_midpoint': (bases[1] + 1, SIGN | (LIMIT - 1)),
            'previous_binade': (1, FIRST - 1),
            'next_binade': (1, LIMIT),
            'ordinary': (0x3ff23456789abcde, 0x3fda123456789abc)}
    report = {}
    for name, (x, y) in rows.items():
        expected = oracle.reference('pow', x, y)
        data = dict(x=f'{x:016x}', y=f'{y:016x}', rounded=f'{expected:016x}')
        for label, arm in (('control', control), ('candidate', candidate)):
            arm.stack_lowest = SP
            got, _, instructions = arm.call(PUBLIC, x, y, count=True)
            assert got == expected, (name, label, hex(got), hex(expected))
            data[label] = dict(instructions=instructions, stack_bytes=SP - arm.stack_lowest)
        report[name] = data
    for name in ('minimum_subnormal', 'maximum_finite'):
        assert report[f'{name}_returns_one']['rounded'] == f'{ONE:016x}'
        assert report[f'{name}_crosses_midpoint']['rounded'] == f'{ONE - 1:016x}'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--bootrom', type=Path, required=True)
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()

    info = proof()
    thresholds = info['first_exponents_that_can_round_below_one']
    cuts = [int(thresholds[key], 16) for key in ('positive', 'negative_magnitude')]
    bases = [int(value, 16) for value in info['base_range_rounding_to_one']]
    oracle = Oracle()
    candidate = Machine(args.elf, True, bootrom=args.bootrom)
    control = Machine(args.control, True, bootrom=args.bootrom)
    visits = count_routes(candidate)
    report = dict(status='PASS', mpfr=oracle.version, bootrom_sha256=candidate.bootrom_sha256,
                  elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
                  control_elf_sha256=hashlib.sha256(args.control.read_bytes()).hexdigest(),
                  **verify(candidate, oracle, cuts, bases, info['power_of_two_threshold'], visits),
                  injected_ambiguity_cases=verify_ambiguity_guard(
                      candidate, oracle, visits, bases[0] - 1, int(info['midpoint_threshold_q157'], 16)),
                  samples=counters(control, candidate, oracle, cuts, bases))
    args.json.write_text(json.dumps(report, indent=2) + '\n')
    print(report['cases'], report['categories'], report['results_in_binade'])
    for name, row in report['samples'].items():
        print(name, row['control']['instructions'], row['candidate']['instructions'])


if __name__ == '__main__':
    main()
