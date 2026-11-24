"""Compare the public RP2040 pow with Classic's resident binary64 System API."""
import argparse
import hashlib
import json
from pathlib import Path
import random

from compact_math_arm_self_test import MathMachine
from native_eabi_m0_arm_self_test import Machine, bits

ROOT = Path(__file__).resolve().parents[1]
POW = '_ZN12compact_math3powEdd'
PICO_MATH = '_ZN8picocalc10NativeHost4mathEmdd'
SIGN = 1 << 63
INF = 0x7ff0000000000000
ONE = bits(1.0)


def corpus(count):
    edges = (0, SIGN, 1, SIGN | 1, (1 << 52)-1, 1 << 52, ONE-1, ONE, ONE+1,
             SIGN | ONE, bits(-2.), bits(.5), bits(-.5), bits(2.), bits(3.),
             bits(4.), INF-1, SIGN | (INF-1), INF, SIGN | INF, INF+1,
             SIGN | (INF+2), INF+(1 << 51)+3, SIGN | (INF+(1 << 51)+4))
    for a in edges:
        for b in edges:
            yield 'special', a, b
    for line in (ROOT/'tests/fixtures/compact_math_binary64.tsv').read_text().splitlines():
        if line.startswith('pow\t'):
            _, a, b, _ = line.split()
            yield 'fixture', int(a, 16), int(b, 16)
    for row in json.loads((ROOT/'tests/fixtures/m0_pow_nearpower_r64.json').read_text())['cases']:
        yield 'near-power', int(row['x'], 16), int(row['y'], 16)
    for i in range(1, 41):
        for j in range(-30, 31):
            yield 'decimal', bits(i/10), bits(j/10)
    boundaries = (2**-65,2**-12,.5,1.,2.,3.,4.,8.,32.,1024.,-1075.)
    for base in (2**-4,1.,1.5,2.,16.):
        for exponent in boundaries:
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    yield 'dispatch-edge', bits(base)+dx, bits(exponent)+dy
    for n in (-1075,-1074,-1023,-1022,-3,-1,0,1,3,1022,1023,1024):
        for fraction in (-.5,-.25,.25,.5):
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    yield 'rounding-edge',bits(2.)+dx,bits(n+fraction)+dy
    rng = random.Random(0x61f411)
    for _ in range(count):
        yield 'raw', rng.getrandbits(64), rng.getrandbits(64)
        yield 'ordinary', (rng.randrange(1018,1029)<<52) | rng.getrandbits(52), bits(rng.uniform(-32,32))
        yield 'near-one', ONE+rng.randint(-8192,8192), bits(rng.uniform(-1,1)*2**rng.randrange(1,63))
        yield 'endpoints', bits(rng.uniform(1.5,2.5)), bits(rng.uniform(995,1110)*rng.choice((-1,1)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pico', type=Path, required=True)
    parser.add_argument('--classic', type=Path, required=True)
    parser.add_argument('--bootrom', type=Path, required=True)
    parser.add_argument('--random', type=int, default=2048)
    args = parser.parse_args()
    if args.random < 0:
        parser.error('--random must be nonnegative')
    pico = Machine(args.pico, rp2040=True, bootrom=args.bootrom)
    classic = MathMachine(args.classic)
    if not classic.compact:
        parser.error('Classic must contain the compact binary64 implementation')
    groups, failures = {}, 0
    for name, a, b in corpus(args.random):
        expected, _ = classic.call(10, a, b)
        # The base AAPCS puts the selector in R0, x in R2:R3 and y on the stack.
        actual = pico.call(PICO_MATH, 10, a, c=b)[0]
        if actual != expected:
            if failures < 12:
                print(f'{name}: {a:016x} {b:016x}: {actual:016x} != Classic {expected:016x}', flush=True)
            failures += 1
        groups[name] = groups.get(name, 0)+1
    print(json.dumps(dict(cases=groups, mismatches=failures,
                          elf_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in (args.pico, args.classic)}), indent=2))
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
