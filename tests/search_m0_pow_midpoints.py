#!/usr/bin/env python3
"""Look for natural late RP2040 pow calls by targeting binary64 midpoints."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import ctypes
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import sys

from m0_mpfr_oracle import Oracle, _Number, bits, real
from native_eabi_m0_arm_self_test import Machine, SP
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'research/m0-pow-boundary-20261023/totality/boundary-gap.json'
RNDN, RNDU, RNDD = 0, 2, 3
ONE, NORMAL, INF = bits(1.), bits(2.**-1022), bits(math.inf)
SIGN = 1 << 63
PRECISION = 320


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Directed:
    """Reusable MPFR operands for constructing and assessing boundary probes."""

    def __init__(self):
        self.oracle = Oracle()
        self.lib = self.oracle.lib
        pointer = ctypes.POINTER(_Number)
        for name, types in (
            ('log', [pointer, pointer, ctypes.c_int]),
            ('exp', [pointer, pointer, ctypes.c_int]),
            ('add', [pointer, pointer, pointer, ctypes.c_int]),
            ('sub', [pointer, pointer, pointer, ctypes.c_int]),
            ('div', [pointer, pointer, pointer, ctypes.c_int]),
            ('neg', [pointer, pointer, ctypes.c_int]),
            ('div_2si', [pointer, pointer, ctypes.c_long, ctypes.c_int]),
            ('set_ui_2exp', [pointer, ctypes.c_ulong, ctypes.c_long, ctypes.c_int]),
            ('cmp', [pointer, pointer]),
            ('number_p', [pointer]),
            ('sgn', [pointer]),
        ):
            function = getattr(self.lib, 'mpfr_' + name)
            function.argtypes = types
            function.restype = ctypes.c_int
        self.numbers = [_Number() for _ in range(11)]
        self.a, self.b, self.mid, self.zlo, self.zhi, self.lo, self.hi, self.mo, self.mu, self.p, self.q = (
            ctypes.pointer(num) for num in self.numbers)
        for num in self.numbers:
            self.lib.mpfr_init2(num, PRECISION)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        for num in self.numbers:
            self.lib.mpfr_clear(num)

    def midpoint(self, cell):
        lib = self.lib
        lib.mpfr_set_d(self.mid, real(cell), RNDN)
        if cell + 1 == INF:
            lib.mpfr_set_ui_2exp(self.q, 1, 1024, RNDN)
        else:
            lib.mpfr_set_d(self.q, real(cell + 1), RNDN)
        lib.mpfr_add(self.mid, self.mid, self.q, RNDN)
        lib.mpfr_div_2si(self.mid, self.mid, 1, RNDN)

    def log_magnitude(self, value, below_one, lower, upper):
        lib = self.lib
        if below_one:
            lib.mpfr_log(lower, value, RNDU)
            lib.mpfr_log(upper, value, RNDD)
            lib.mpfr_neg(lower, lower, RNDN)
            lib.mpfr_neg(upper, upper, RNDN)
        else:
            lib.mpfr_log(lower, value, RNDD)
            lib.mpfr_log(upper, value, RNDU)

    def invert_exponent(self, x, cell):
        lib = self.lib
        self.midpoint(cell)
        lib.mpfr_set_d(self.a, real(x), RNDN)
        self.log_magnitude(self.mid, cell < ONE, self.mo, self.mu)
        self.log_magnitude(self.a, x < ONE, self.lo, self.hi)
        lib.mpfr_div(self.p, self.mo, self.hi, RNDD)
        lib.mpfr_div(self.q, self.mu, self.lo, RNDU)
        sign = SIGN if (cell < ONE) != (x < ONE) else 0
        return (bits(lib.mpfr_get_d(self.p, RNDD)) | sign,
                bits(lib.mpfr_get_d(self.q, RNDU)) | sign)

    def invert_base(self, y, cell):
        lib = self.lib
        self.midpoint(cell)
        lib.mpfr_set_d(self.b, real(y), RNDN)
        lib.mpfr_log(self.lo, self.mid, RNDD)
        lib.mpfr_log(self.hi, self.mid, RNDU)
        if y & SIGN:
            lower, upper = self.hi, self.lo
        else:
            lower, upper = self.lo, self.hi
        lib.mpfr_div(self.p, lower, self.b, RNDD)
        lib.mpfr_div(self.q, upper, self.b, RNDU)
        lib.mpfr_exp(self.p, self.p, RNDD)
        lib.mpfr_exp(self.q, self.q, RNDU)
        return bits(lib.mpfr_get_d(self.p, RNDD)), bits(lib.mpfr_get_d(self.q, RNDU))

    def rounded(self, x, y):
        lib = self.lib
        lib.mpfr_set_d(self.a, real(x), RNDN)
        lib.mpfr_set_d(self.b, real(y), RNDN)
        lib.mpfr_pow(self.zlo, self.a, self.b, RNDD)
        lib.mpfr_pow(self.zhi, self.a, self.b, RNDU)
        lower = bits(lib.mpfr_get_d(self.zlo, RNDN))
        upper = bits(lib.mpfr_get_d(self.zhi, RNDN))
        return lower if lower == upper else self.oracle.reference('pow', x, y)

    def relative_gap(self, cell):
        lib = self.lib
        if not lib.mpfr_number_p(self.zhi) or lib.mpfr_sgn(self.zlo) <= 0:
            return 'out_of_mpfr_range', None
        self.midpoint(cell)
        low = lib.mpfr_cmp(self.zlo, self.mid)
        high = lib.mpfr_cmp(self.zhi, self.mid)
        if low > 0:
            lib.mpfr_sub(self.lo, self.zlo, self.mid, RNDD)
            lib.mpfr_sub(self.hi, self.zhi, self.mid, RNDU)
        elif high < 0:
            lib.mpfr_sub(self.lo, self.mid, self.zhi, RNDD)
            lib.mpfr_sub(self.hi, self.mid, self.zlo, RNDU)
        else:
            return ('exact_midpoint' if low == high == 0 else 'overlap_320_bits'), None
        lib.mpfr_div(self.lo, self.lo, self.zhi, RNDD)
        lib.mpfr_div(self.hi, self.hi, self.zlo, RNDU)
        return 'separated', (lib.mpfr_get_d(self.lo, RNDD), lib.mpfr_get_d(self.hi, RNDU))


def random_cells(rng, total):
    for i in range(total):
        k = i % 6
        if k == 0:
            yield ONE + rng.randrange(-4096, 4096)
        elif k == 1:
            yield rng.randrange(0, 4096)
        elif k == 2:
            yield NORMAL + rng.randrange(-4096, 4096)
        elif k == 3:
            yield INF - 1 - rng.randrange(4096)
        elif k == 4:
            yield (rng.randrange(1, 2047) << 52) + rng.randrange(-16, 16)
        else:
            yield rng.randrange(INF)


def trials(mathlib, seed_count):
    rng = random.Random(0xA5E6B31F)
    simple_y = tuple(bits(x) for x in (.25, .5, .75, 1., 1.5, 2., 3., -1., -.5, -2., -3., 1024., -1075.))

    # Full local grid around unity. Midpoints straddle the unequal ulp on
    # either side, and the exponents may be positive or negative.
    for off in range(-256, 257):
        if not off:
            continue
        x = ONE + off
        for cell in range(ONE-32, ONE+32):
            for y in set(mathlib.invert_exponent(x, cell)):
                yield 'near_one_grid', x, y, cell

    for i, cell in enumerate(random_cells(rng, seed_count)):
        if i % 4 == 0:
            x = ONE + rng.choice((-1, 1))*rng.randrange(1, 1 << 18)
        elif i % 4 == 1:
            x = rng.randrange(1, NORMAL)
        elif i % 4 == 2:
            x = (rng.randrange(1, 2047) << 52) + rng.randrange(-16, 16)
        else:
            x = rng.randrange(1, INF)
        if x != ONE:
            for y in set(mathlib.invert_exponent(x, cell)):
                yield 'invert_exponent', x, y, cell

    for i, cell in enumerate(random_cells(rng, seed_count)):
        if i % 3 == 0:
            y = simple_y[rng.randrange(len(simple_y))] + rng.randrange(-4, 5)
        elif i % 3 == 1:
            y = bits(rng.choice((-1, 1))*rng.randrange(1, 1024)/2**rng.randrange(8))
        else:
            y = ((1023+rng.randrange(-64, 63)) << 52) | rng.getrandbits(52) | (rng.getrandbits(1) << 63)
        for x in set(mathlib.invert_base(y, cell)):
            yield 'invert_base', x, y, cell

    for row in json.loads(ARCHIVE.read_bytes())['cases']:
        x0, y0 = (int(row[name], 16) for name in ('x', 'y'))
        for x in range(x0-4, x0+5):
            for y in range(y0-4, y0+5):
                yield 'archived_neighbours', x, y, None


def discover(seed_count):
    stats = {}
    expected = {}
    best = {}
    unresolved = []
    with Directed() as numeric:
        for family, x, y, cell in trials(numeric, seed_count):
            counts = stats.setdefault(family, Counter())
            counts['proposed'] += 1
            if not 0 < x < INF or not 0 < (y & (SIGN-1)) < INF:
                counts['outside_positive_finite_search'] += 1
                continue
            rounded = numeric.rounded(x, y)
            if (x, y) in expected:
                assert expected[x, y] == rounded
            expected[x, y] = rounded
            counts['checked_targets'] += 1
            # Archives pin input pairs. Reconstruct both nearest boundaries
            # from the current MPFR result instead of assuming their cells.
            cells = {min(rounded, INF-1), max(0, rounded-1)} if cell is None else (cell,)
            for boundary in sorted(cells):
                outcome, gap = numeric.relative_gap(boundary)
                counts[outcome] += 1
                if outcome == 'overlap_320_bits':
                    unresolved.append(dict(family=family, x=f'{x:016x}', y=f'{y:016x}',
                                           lower=f'{boundary:016x}', rounded=f'{rounded:016x}'))
                if not gap:
                    continue
                lo, hi = gap
                if hi <= 0 or (family in best and hi >= best[family][0]):
                    continue
                best[family] = (hi, dict(x=f'{x:016x}', y=f'{y:016x}', lower=f'{boundary:016x}',
                    rounded=f'{rounded:016x}', gap_lower=lo.hex(), gap_upper=hi.hex(),
                    certified_bits=-math.log2(hi)))
        print('MPFR probes', len(expected), 'distinct inputs;', len(unresolved), 'overlaps', flush=True)
        return expected, stats, {fam: row for fam, (_, row) in best.items()}, unresolved, numeric.oracle.version


def replay_shard(elf, bootrom, index, entries):
    machine = Machine(elf, True, stack_bytes=32768, instruction_budget=1_300_000_000, bootrom=bootrom)
    machine.uc.hook_del(machine.write_hook)
    # Keep the same write restrictions, without a Python callback for every
    # ordinary stack store. Writes to SIO still use the real divider model.
    for start, end in ((0, 0x3fff), (0x08000000, 0x081fffff), (0x10000000, 0x101fffff),
                       (0x20000000, SP-machine.stack_bytes-1), (SP, 0x20041fff),
                       (0xd0000000, 0xd0000fff)):
        machine.uc.hook_add(UC_HOOK_MEM_WRITE, machine.write, begin=start, end=end)
    entered = Counter()
    deep = []
    current = None
    stages = ('mk61_m0_cr_pow', 'mk61_m0_pow_rescue', 'mk61_m0_pow_round_final')

    def stage(_uc, _pc, _size, name):
        entered[name] += 1
        if name != stages[0]:
            deep.append((name, *(f'{v:016x}' for v in current)))
            print('Natural late entry', *deep[-1], flush=True)

    for name in stages:
        address = machine.elf.symbols[name] & ~1
        machine.uc.hook_add(UC_HOOK_CODE, stage, name, begin=address, end=address)

    # A progress callback would normally update the hardware watchdog. Give
    # it an inert platform implementation in the emulator only.
    address = machine.elf.symbols['mk61_m0_pow_progress'] & ~1
    def watchdog(uc, _pc, _size, _):
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    machine.uc.hook_add(UC_HOOK_CODE, watchdog, begin=address, end=address)
    machine.uc.ctl_flush_tb()
    for count, ((x, y), want) in enumerate(entries, 1):
        current = x, y
        got = machine.call('_ZN12compact_math3powEdd', x, y)[0]
        assert got == want, tuple(f'{v:016x}' for v in (x, y, want, got))
        if count % 8192 == 0:
            print('ARM shard', index, count, dict(entered), flush=True)
    return len(entries), {name: entered[name] for name in stages}, deep


def replay(args, expected):
    entries = sorted(expected.items())
    entered = Counter()
    deep = []
    checked = 0
    with ProcessPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(replay_shard, args.elf, args.bootrom, index, entries[index::4])
                for index in range(4)]
        for job in jobs:
            count, hits, late = job.result()
            checked += count
            entered.update(hits)
            deep.extend(late)
    assert checked == len(expected)
    digest = hashlib.sha256()
    with args.output.with_suffix('.pairs').open('wb') as compact:
        for (x, y), want in entries:
            packet = struct.pack('<3Q', x, y, want)
            compact.write(packet)
            digest.update(packet)
    return dict(checked=checked, wrong_rounding=0, stage_entries=dict(entered),
                late_inputs=sorted(deep), corpus_sha256=digest.hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('elf', 'bootrom', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--seed-count', default=32768, type=int,
                        help='Number of sampled targets in each log-inversion direction.')
    args = parser.parse_args()
    if args.seed_count < 1 or sys.flags.optimize:
        parser.error('Supply a positive seed count and leave assertions enabled')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    initial_elf, initial_rom = sha(args.elf), sha(args.bootrom)
    expected, counters, closest, unresolved, version = discover(args.seed_count)
    results = replay(args, expected)
    assert sha(args.elf) == initial_elf and sha(args.bootrom) == initial_rom
    report = dict(status='PASS', mpfr=version, precision=PRECISION, seed_count=args.seed_count,
                  elf_sha256=initial_elf, bootrom_sha256=initial_rom,
                  archive_sha256=sha(ARCHIVE), search_families=counters,
                  closest_nonzero_midpoints=closest, unresolved_gap_probes=unresolved, arm=results)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('PASS', results, flush=True)


if __name__ == '__main__':
    main()
