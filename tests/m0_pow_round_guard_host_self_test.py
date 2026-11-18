#!/usr/bin/env python3
"""Check the compiled pow guards at each edge of the uncertainty band."""
import ctypes
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'third_party/core_math/pow/pow.c'
MASK = (1 << 64)-1


def compile_guards(directory):
    source = SOURCE.read_text()
    limit2, normal = re.search(r'#define ERR_BND_2 (\d+)\b.*?rd = ([^;]+);', source, re.S).groups()
    limit3, wide = re.search(r'#define ERR_BND_3 (\d+)\b.*?rd = ([^;]+);', source, re.S).groups()
    subnormal = re.search(r'uint64_t m = R\.lo >> .*?rd = ([^;]+);', source, re.S)[1]
    underflow = re.search(r'if \((R\.ex < -1076 \|\|.*?)\) \{', source, re.S)[1]
    unit = directory/'guards.cpp'
    unit.write_text(f'''#include <stdint.h>
#define ERR_BND_2 {limit2}
#define ERR_BND_3 {limit3}
extern "C" int normal(uint64_t lo) {{ return {normal}; }}
extern "C" int subnormal(uint64_t m) {{ return {subnormal}; }}
extern "C" int wide(uint64_t r1, uint64_t r2, uint64_t r3) {{ return {wide}; }}
extern "C" int underflow(int64_t ex, uint64_t hi, uint64_t lo) {{
    const struct {{ int64_t ex; uint64_t hi, lo; }} R = {{ex, hi, lo}};
    return {underflow};
}}
''')
    library = directory/'guards.so'
    compiler = shutil.which('c++')
    assert compiler is not None, 'A host C++ compiler is required'
    subprocess.run([compiler, '-O2', '-shared', '-fPIC', str(unit), '-o', str(library)], check=True)
    guards = ctypes.CDLL(str(library))
    for name, types in (
        ('normal', [ctypes.c_uint64]),
        ('subnormal', [ctypes.c_uint64]),
        ('wide', [ctypes.c_uint64]*3),
        ('underflow', [ctypes.c_int64, ctypes.c_uint64, ctypes.c_uint64]),
    ):
        guard = getattr(guards, name)
        guard.argtypes = types
        guard.restype = ctypes.c_int
    return guards


def truncated_units(tail, width, dropped):
    """Minimum distance to either boundary across the omitted low bits."""
    return min(tail << dropped, ((1 << width)-tail-1)*(1 << dropped)+1)


def check(guards):
    fringe = range(129)
    count = 0
    for tail in [*fringe, *(MASK-i for i in fringe), 1 << 63]:
        assert bool(guards.normal(tail)) == (truncated_units(tail, 64, 10) > 29126)
        assert bool(guards.subnormal(tail)) == (truncated_units(tail, 64, 11) > 29126)
        count += 2

    mask192 = (1 << 192)-1
    for tail in [*fringe, *(mask192-i for i in fringe),
                 1 << 64, 1 << 128, mask192-MASK, mask192-(MASK << 64)]:
        args = (tail >> 128, (tail >> 64)&MASK, tail&MASK)
        assert bool(guards.wide(*args)) == (truncated_units(tail, 192, 10) > 62433)
        count += 1

    # The 128-bit normalized significand approaches 2^128 from below.
    # Check both lips of the band and the adjacent upper-limb/exponent cases.
    margin = 29 << 10
    for distance in (1, 29126, margin-1, margin, margin+1, 1 << 64, (1 << 64)+1):
        significand = (1 << 128)-distance
        assert bool(guards.underflow(-1076, significand >> 64, significand&MASK)) == (distance > margin)
        assert guards.underflow(-1077, significand >> 64, significand&MASK)
        count += 2
    return count


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as path:
        checked = check(compile_guards(Path(path)))
    print(f'PASS {checked} compiled pow rounding-guard checks')
