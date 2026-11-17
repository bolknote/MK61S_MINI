#!/usr/bin/env python3
"""Check the last RP2040 pow comparison against whole Python integer powers."""
import argparse
import ctypes
import json
from pathlib import Path
import random
import shutil
import subprocess

from m0_mpfr_oracle import Oracle, bits

ROOT = Path(__file__).resolve().parents[1]
INFINITY = 0x7FF0000000000000
ONE = 0x3FF0000000000000
ABS_MASK = (1 << 63)-1
FRACTION_MASK = (1 << 52)-1
WRAPPER = '''#include "native_eabi_m0_pow_stream.inc"
extern "C" int relation(uint64_t x, uint64_t y, uint64_t lower) {
    return m0_pow_stream::side(x,y,lower,nullptr);
}
namespace {
struct WorkLimit {};
unsigned remaining;
void check_work() {
    if (--remaining == 0)
        throw WorkLimit{};
}
}
extern "C" int relation_with_budget(uint64_t x, uint64_t y, uint64_t lower, unsigned budget) {
    remaining = budget;
    try {
        return m0_pow_stream::side(x,y,lower,check_work);
    } catch (const WorkLimit&) {
        return 0;
    }
}
'''


def dyadic(encoding):
    field = encoding >> 52
    fraction = encoding & FRACTION_MASK
    return (fraction+(1 << 52), field-1075) if field else (fraction,-1074)


def midpoint(lower):
    upper = lower+1
    a, e = dyadic(lower)
    if upper == INFINITY:
        return (1 << 54)-1, 970
    b, f = dyadic(upper)
    return a+(b << (f-e)), e-1


def expected_side(x, y, lower):
    base, scale = dyadic(x)
    for _ in range((base & -base).bit_length()-1):
        base >>= 1
        scale += 1
    midpoint_coefficient, midpoint_scale = midpoint(lower)
    p, exponent = dyadic(y & ABS_MASK)
    trailing = (p & -p).bit_length()-1
    p >>= trailing
    exponent += trailing
    q = 1 << -exponent if exponent < 0 else 1
    p <<= max(0, exponent)

    a = pow(base, p)
    b = pow(midpoint_coefficient, q)
    ae = scale*p
    be = midpoint_scale*q
    if y >> 63:
        a, b, ae, be = 1, a*b, 0, ae+be
    common = min(ae, be)
    a <<= ae-common
    b <<= be-common
    if a == b:
        return 1 if lower & 1 else -1
    return 1 if a > b else -1


def build(out, cxx, reduced):
    out.mkdir()
    wrapper = out / 'probe.cpp'
    wrapper.write_text(WRAPPER)
    if reduced:
        # Leave the interpreter and depth limit intact. Keeping only eight
        # words forces recomputation on small enough powers for an oracle.
        header = (ROOT / 'code/native_eabi_m0_pow_stream.inc').read_text()
        needle = 'constexpr unsigned MaterializedWords = 1728;'
        assert header.count(needle) == 1
        (out / 'native_eabi_m0_pow_stream.inc').write_text(
            header.replace(needle, 'constexpr unsigned MaterializedWords = 8;'))
    library = out / 'probe.so'
    subprocess.run([cxx, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                    '-I'+str(ROOT/'code'), str(wrapper), '-o', str(library)], check=True)
    probe = ctypes.CDLL(str(library))
    probe.relation.argtypes = (ctypes.c_uint64,)*3
    probe.relation.restype = ctypes.c_int
    probe.relation_with_budget.argtypes = (ctypes.c_uint64,)*3 + (ctypes.c_uint,)
    probe.relation_with_budget.restype = ctypes.c_int
    return probe


def check(probe, oracle, reduced):
    rng = random.Random(0x6373696e)
    pairs = [(3., 34.), (35., 11.), (9., -13.), (2., -1075.), (2., 1024.),
             (3., 2.), (2.**-1074, 1.5), (81., .75), (3.5, 2.5), (.5, 1075.)]
    if reduced:
        pairs = [(3.5, 2.5), (.5, 1075.), (1.25, 3.75)]
    cases = 0
    for i in range(len(pairs)+(35 if reduced else 450)):
        if i < len(pairs):
            x, y = map(bits, pairs[i])
        else:
            x = bits(rng.randrange(8,256)/128) if reduced else rng.randrange(1,INFINITY)
            p = rng.randrange(1,14 if reduced else 55)
            q = 1 << rng.randrange(0,4 if reduced else 7)
            y = bits((-p if rng.getrandbits(1) else p)/q)
        rounded = oracle.reference('pow', x, y)
        cells = (min(rounded, INFINITY-1), max(0,rounded-1))
        if i >= len(pairs):
            cells += (rng.randrange(0,INFINITY),)
        for lower in cells:
            assert probe(x,y,lower) == expected_side(x,y,lower), (hex(x),hex(y),hex(lower))
            cases += 1

    if not reduced:
        for p, q in ((127,64),(257,32),(383,16),(511,1),(511,128),(1,512),(1024,1)):
            exponents = (p,) if p == 1024 else (p/q, -p/q)
            for exponent in exponents:
                x, y = ONE-1, bits(exponent)
                lower = oracle.reference('pow',x,y)
                assert probe(x,y,lower) == expected_side(x,y,lower), (p,q,exponent)
                cases += 1
    return cases


def check_streaming_work(probe, oracle):
    # The two fractional inverse cases place the virtual factor on opposite
    # sides of the root product. The last one also needs a wide window.
    x = ONE-1
    count = 0
    for exponent in (1023., -1024., -1023., 1023/128, -1/1024, -1023/128):
        y = bits(exponent)
        rounded = oracle.reference('pow',x,y)
        for lower in (rounded-1, rounded):
            want = expected_side(x,y,lower)
            got = probe(x,y,lower,4096)
            assert got == want, (hex(x),hex(y),hex(lower),got,want)
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cxx', default=shutil.which('c++') or 'c++')
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    oracle = Oracle()
    production = build(args.output/'production',args.cxx,False)
    reduced = build(args.output/'recompute',args.cxx,True)
    counts = dict(production=check(production.relation,oracle,False),
                  recompute=check(reduced.relation,oracle,True),
                  streamed=check_streaming_work(production.relation_with_budget,oracle))
    print(json.dumps(dict(status='PASS', cases=counts, mpfr=oracle.version),indent=2))


if __name__ == '__main__':
    main()
