#!/usr/bin/env python3
"""Test the large-pow saturation, directed power and subnormal packing."""
import argparse
import ctypes
from decimal import Decimal, localcontext
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys

from m0_mpfr_oracle import Oracle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'research/m0-pow-comparison-20261117'))
from large_exponents import END_Y, FIRST_Y, OUTPUT_LIMIT, geometry

SIGN = 1 << 63
MASK = SIGN-1
WORD_MASK = (1 << 64)-1
INF = 0x7ff0000000000000
ONE = 0x3ff0000000000000
BASE = ONE-1
UNHANDLED = WORD_MASK

WRAPPER = """
#include <stdint.h>
#include "native_eabi_m0_pow_large.inc"
#include "native_eabi_m0_pow_large_power.inc"
extern "C" uint64_t saturation(uint64_t x,uint64_t y) {
  return m0_pow_large::saturate(x,y);
}
extern "C" uint64_t power(uint64_t y) {
  return m0_pow_large::subnormal(y);
}
extern "C" uint64_t pack(uint64_t low,uint64_t middle,uint32_t high,int32_t scale) {
  m0_pow_large::LargePower::Number value{};
  for(unsigned i=0;i<4;++i) {
    value.word[i]=uint16_t(low>>(16*i));
    value.word[4+i]=uint16_t(middle>>(16*i));
  }
  value.word[8]=uint16_t(high);
  value.word[9]=uint16_t(high>>16);
  value.scale=mk61_u128(scale);
  return m0_pow_large::round_subnormal(value);
}
"""


def build(output):
    source = output/'large_pow.cpp'
    library = output/'large_pow.so'
    source.write_text(WRAPPER)
    subprocess.run([shutil.which('c++') or 'c++', '-std=c++17', '-O2', '-shared',
                    '-fPIC', '-I', str(ROOT/'code'), str(source), '-o', str(library)],
                   check=True)
    lib = ctypes.CDLL(str(library))
    u64 = ctypes.c_uint64
    for name, arguments in [('saturation', (u64, u64)), ('power', (u64,)),
                            ('pack', (u64, u64, ctypes.c_uint32, ctypes.c_int32))]:
        function = getattr(lib, name)
        function.argtypes = arguments
        function.restype = u64
    return lib


def check_packing(pack, rng):
    count = 0
    for scale in range(-1078,-1022):
        cut = 159-scale-1074
        hidden = 1 << 159
        coefficients = {hidden, 2*hidden-1}
        for _ in range(24):
            value = hidden|rng.getrandbits(159)
            coefficients.add(value)
            halfway = ((value >> cut) << cut)+(1 << (cut-1))
            coefficients.update(num for num in range(halfway-1,halfway+2)
                                if hidden <= num < 2*hidden)
        for value in coefficients:
            lower, remainder = divmod(value, 1 << cut)
            relation = 2*remainder-(1 << cut)
            expected = lower+int(relation > 0 or (relation == 0 and lower&1))
            result = pack(value&WORD_MASK,(value>>64)&WORD_MASK,value>>128,scale)
            assert result == expected, (scale, value, result, expected)
            count += 1
    return count


def check_saturation(saturate, oracle, cuts):
    bases = {0, 1, 0xfffffffffffff, 0x10000000000000, ONE-3, ONE-2, BASE, ONE,
             ONE+1, ONE+2, 0x4000000000000000, INF-1, INF, INF+1, INF+(1<<51)}
    magnitudes = {FIRST_Y, FIRST_Y+1, END_Y-1, END_Y, END_Y+1, INF-1, INF, INF+1}
    for threshold in cuts.values():
        magnitudes.update(range(threshold-2,threshold+3))
    count, exact = 0, 0
    for base in bases:
        for magnitude in magnitudes:
            for xsign, ysign in ((0,0), (0,SIGN), (SIGN,0), (SIGN,SIGN)):
                x,y = base|xsign, magnitude|ysign
                result = saturate(x,y)
                saturates = base < INF and magnitude < INF and (
                    base != BASE or magnitude >= cuts['overflow' if ysign else 'underflow'])
                if saturates:
                    assert result == oracle.reference('pow',x,y), (hex(x), hex(y), hex(result))
                    exact += 1
                else:
                    assert result == UNHANDLED, (hex(x), hex(y), hex(result))
                count += 1
    return count, exact


def near_midpoint(index):
    with localcontext() as ctx:
        ctx.prec = 180
        ln2 = Decimal(2).ln()
        step = -(1-Decimal(2)**-53).ln()*1024
        t = (1075*ln2-Decimal(2*index+1).ln())/step
        return FIRST_Y+int(t)-(1 << 52)


def check_power(power, oracle, cuts, rng, closest):
    first, last = cuts['band'], cuts['underflow']
    ys = set(range(first,first+16))|set(range(last-16,last))
    ys.update(rng.randrange(first,last) for _ in range(12_000))
    for index in (0, 1, 2, 3, 15, 257, 1023, 65535, closest, OUTPUT_LIMIT-1):
        y0 = near_midpoint(index)
        ys.update(y for y in range(y0-2,y0+4) if first <= y < last)
    assert power(first-1) == power(last) == power(last|SIGN) == UNHANDLED
    for y in ys:
        expected = oracle.reference('pow',BASE,y)
        result = power(y)
        assert result == expected, (hex(y),hex(result),hex(expected))
    return len(ys)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--certificate', type=Path, required=True)
    args = parser.parse_args()
    proof = json.loads(args.certificate.read_text())
    assert proof['status']=='PASS_LARGE_EXPONENT_BAND'
    args.output.mkdir(parents=True, exist_ok=True)
    lib,oracle = build(args.output),Oracle()
    rng = random.Random(0xb039160)
    cuts = geometry()
    packing = check_packing(lib.pack,rng)
    classification,saturated = check_saturation(lib.saturation,oracle,cuts)
    powers = check_power(lib.power,oracle,cuts,rng,int(proof['closest_lower_encoding'],16))
    result = dict(status='PASS', packing=packing, classification=classification,
                  saturated_against_mpfr=saturated, direct_powers_against_mpfr=powers,
                  mpfr=oracle.version)
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result,flush=True)


if __name__ == '__main__':
    main()
