"""Qualify exact endpoint guards, scaled arguments and targeted pow midpoints."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import sys

root = Path.cwd()
work = Path(__file__).resolve().parent
sys.path.insert(0, str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine, SP, bits, real, nan
from m0_mpfr_oracle import Oracle

rng = random.Random(0x144C01D)
inf = 0x7FF0000000000000
sign = 1 << 63
one = bits(1.)
cases = {}


def add(x, y, group):
    if 0 <= x < 1 << 64 and 0 <= y < 1 << 64:
        cases.setdefault((x, y), group)


for e in range(1, 2047):
    for offset in (0, (1 << 52)-1):
        x = (e << 52) | offset
        ye = -64+(e % 52)
        y = ((ye+1023) << 52) | rng.getrandbits(52)
        add(x, y, 'every_normal_base_exponent')
        add(x, y | sign, 'every_normal_base_exponent')
for _ in range(20000):
    x = (rng.randrange(1, 2047) << 52) | rng.getrandbits(52)
    y = ((rng.randrange(-64, -12)+1023) << 52) | rng.getrandbits(52)
    add(x, y | (sign if rng.getrandbits(1) else 0), 'random_small_y')
for _ in range(3000):
    x = one+rng.choice((-1, 1))*rng.randrange(1, 1 << 38)
    y = ((rng.randrange(-64, -12)+1023) << 52) | rng.getrandbits(52)
    add(x, y | (sign if rng.getrandbits(1) else 0), 'near_one_large_argument_shifts')

bases = [1, (1 << 52)-1, 1 << 52, bits(1e-200), bits(.125), bits(.5),
         one-1, one, one+1, bits(2.), bits(23.), bits(1e200), inf-1]
for x in bases:
    for e in (-64, -63, -43, -42, -13, -12, 63):
        center = bits(2.**e)
        for y in range(center-4, center+5):
            for s in (0, sign):
                add(x, y | s, 'dispatch_threshold_neighbours')
for i in range(3000):
    x = rng.randrange(1, inf)
    y = (rng.randrange(1086, 2047) << 52) | rng.getrandbits(52)
    add(x, y | (sign if i & 1 else 0), 'huge_finite_y')
    if i < 300:
        add(x | sign, y | (sign if i & 1 else 0), 'negative_base_even_huge_y')

# Host log1p is a seed generator only. Independent directed MPFR pow
# determines every expected answer, including nearby representable y.
midpoint_counts = [0, 1, 2, 3, 31, 127, 1023, (1 << 20)-1, 1 << 20,
                   (1 << 20)+1, (1 << 21)-1, 1 << 21, (1 << 21)+1]
mid_bases = bases[2:]+[bits(.75), bits(1.5), bits(1.000001), bits(.999999)]
for x in mid_bases:
    if x == one:
        continue
    logarithm = math.log(real(x))
    for below in (False, True):
        for n in midpoint_counts:
            delta = math.ldexp(n+.5, -53 if below else -52)
            yseed = math.log1p(-delta if below else delta)/logarithm
            if not math.isfinite(yseed) or not 2.**-64 < abs(yseed) < 2.**-12:
                continue
            seed = bits(yseed)
            for d in range(-4, 5):
                add(x, seed+d, 'RNE_midpoint_and_linear_cutoff_seeds')

special = [0, sign, 1, sign | 1, one, one | sign, inf, inf | sign,
           inf | 1, inf | sign | 1, inf | (1 << 51) | 13, inf | sign | (1 << 51) | 17]
ys = [0, sign, bits(2.**-64), bits(2.**-43), bits(2.**-12), bits(2.**63),
      bits(2.**63) | sign, inf-1, (inf-1) | sign, inf, inf | sign,
      inf | 1, inf | (1 << 51) | 7]
for x in special:
    for y in ys:
        add(x, y, 'IEEE_domain_classes')

elf = work/'firmware/mk61s-picocalc-pico-h.elf'
machine = Machine(elf, True, stack_bytes=16384, instruction_budget=200000000,
                  bootrom=root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
oracle = Oracle()
digest = hashlib.sha256()
groups = Counter()
for i, ((x, y), group) in enumerate(cases.items(), 1):
    expected = oracle.reference('pow', x, y)
    got = machine.call('_ZN12compact_math3powEdd', x, y)[0]
    assert (nan(got) and bool(got & (1 << 51))) if nan(expected) else got == expected, (
        group, hex(x), hex(y), hex(got), hex(expected))
    groups[group] += 1
    digest.update(struct.pack('<4Q', x, y, expected, got))
    if i % 2000 == 0:
        (work/'small-qualification.progress.json').write_text(json.dumps(dict(status='RUNNING', cases=i, groups=dict(groups)), indent=2)+'\n')
        print('PASS', i, flush=True)
report = dict(status='PASS_SMALL_Y_MAGNITUDE_AND_MIDPOINT_MPFR', cases=len(cases), groups=dict(groups),
              wrong_rounding=0, mpfr=oracle.version, result_sha256=digest.hexdigest(),
              elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
              producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              maximum_observed_stack_bytes=SP-machine.stack_lowest,
              scope='Finite public-pow coverage of every normal-base exponent, full small-y significands, huge finite exponents, exact dispatch boundaries and targeted RNE midpoint neighbours. Directed MPFR; all ARM calls check ABI and bounded writes. Not general-pow totality or physical cycles.',
              hardware_accessed=False, production_promoted=False, goal_complete=False)
(work/'small-qualification.json').write_text(json.dumps(report, indent=2)+'\n')
(work/'small-qualification.progress.json').write_text(json.dumps(dict(status='PASS', cases=len(cases)), indent=2)+'\n')
print(json.dumps(report, indent=2), flush=True)
