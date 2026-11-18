#!/usr/bin/env python3
"""Compare the bounded residue lift against full integer powers."""
import argparse
from collections import Counter
import ctypes
import json
from pathlib import Path
import random
import subprocess
import sys

from m0_mpfr_oracle import Oracle, bits
from m0_pow_stream_host_self_test import ABS_MASK, INFINITY, ONE, dyadic, midpoint

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = '''#include "native_eabi_m0_pow_residue.inc"
extern "C" unsigned capacity() { return m0_pow_residue::MaximumBits; }
extern "C" int compare(uint64_t x, uint64_t y, uint64_t lower, unsigned gap) {
    return m0_pow_residue::side(x,y,lower,gap,nullptr);
}
'''


def remove_twos(coefficient, exponent):
    trailing = (coefficient & -coefficient).bit_length()-1
    return coefficient >> trailing, exponent+trailing


def aligned_powers(x, y, lower):
    """Return exact positive integers in the order of the rounding comparison."""
    a, ae = remove_twos(*dyadic(x))
    p, ye = remove_twos(*dyadic(y & ABS_MASK))
    m, me = midpoint(lower)
    assert m & 1
    p <<= max(0, ye)
    k = max(0, -ye)
    q = 1 << k
    xe, me = ae*p, me*q
    a_bound = a.bit_length()*p if a != 1 else 0
    m_bound = m.bit_length()*q if m != 1 else 0
    assert max(a_bound, m_bound, abs(xe), abs(me)) < 1_500_000
    ap, mq = a**p, m**q
    if y >> 63:
        scale = xe+me
        bound = -scale
        return 1 << max(0,-scale), ap*mq << max(0,scale), k, bound, None
    first, second = max(0,xe-me), max(0,me-xe)
    bound = min(a_bound+first, m_bound+second)
    return ap << first, mq << second, k, bound, (first, second)


def log_gap_is_below(a, b, k, gap):
    # |log(a/b)| <= |a-b|/min(a,b); the power comparison's form is
    # q times the original form, for either sign of the exponent.
    return abs(a-b) << gap < min(a,b) << k


def benchmark_cases(oracle, capacity):
    # The chosen dyadic scalings make the test modulus exactly capacity
    # or just below it, while keeping both full powers small on the host.
    selected = []
    for label, sign, q, base_shifts in (
        ('positive',1,1,(48,47,49,46,50)),
        ('negative',-1,128,(39,49,48,47,46,50)),
        ('balanced',-1,512,(47,48,49,46,50)),
    ):
        for base_shift in base_shifts:
            x = bits(1-2.**-base_shift)
            shift = q.bit_length()-1
            scale = 53*q if sign < 0 else 0
            minimum = capacity+32-shift-2-scale
            maximum = capacity+64-shift-2-scale
            for p in range(-(-minimum//base_shift),maximum//base_shift+1):
                if q>1 and p%2==0:
                    continue
                y = bits(sign*p/q)
                rounded = oracle.reference('pow',x,y)
                lower = rounded if label=='balanced' else rounded-1
                a,b,k,n,_ = aligned_powers(x,y,lower)
                gap = n+2+k-capacity
                if gap >= max(32,k+3) and log_gap_is_below(a,b,k,gap):
                    selected.append(dict(name=label,x=x,y=y,lower=lower,expected=1 if a>b else -1,
                                         gap=gap,exponent_numerator=p,denominator=q,
                                         modulus_bits=capacity,full_integer_bits=max(a.bit_length(),b.bit_length())))
                    break
            if selected and selected[-1]['name']==label:
                break
    return selected


def virtual_product_case(oracle):
    x, y, gap = 0x7edf123456789abf, bits(-527/512), 35
    lower = oracle.reference('pow',x,y)-1
    a,b,k,n,_ = aligned_powers(x,y,lower)
    assert 0 <= lower < 1<<52 and log_gap_is_below(a,b,k,gap)
    return dict(name='virtual_recomputation',x=x,y=y,lower=lower,expected=1,
                gap=gap,modulus_bits=n+2+k-gap,exponent_numerator=527,denominator=512,
                full_integer_bits=max(a.bit_length(),b.bit_length()))


def run(compiler, output):
    output.mkdir(parents=True,exist_ok=True)
    cpp = output/'residue.cpp'
    cpp.write_text(WRAPPER)
    dylib = output/('residue.dylib' if sys.platform=='darwin' else 'residue.so')
    subprocess.run([compiler,'-std=c++17','-O3','-Wall','-Wextra','-Werror','-Wno-unused-function',
                    '-dynamiclib' if sys.platform=='darwin' else '-shared','-fPIC',
                    '-I'+str(ROOT/'code'),str(cpp),'-o',str(dylib)],check=True)
    lib = ctypes.CDLL(str(dylib.resolve()))
    lib.compare.argtypes = [ctypes.c_uint64]*3+[ctypes.c_uint]
    lib.compare.restype = ctypes.c_int
    lib.capacity.restype = ctypes.c_uint
    capacity = lib.capacity()
    assert capacity == 49152
    oracle = Oracle()
    rng = random.Random(0x49c278)
    counts = Counter()

    def check(x,y,lower,gap,require_fit=True):
        a,b,k,n,shifts = aligned_powers(x,y,lower)
        assert gap >= k+2 and log_gap_is_below(a,b,k,gap)
        fit = (y>>63 and n<=0) or n+2+k-gap<=capacity
        expected = (1 if a>b else -1) if a!=b else (1 if lower&1 else -1)
        got = lib.compare(x,y,lower,gap)
        assert got==(expected if fit else 0),(hex(x),hex(y),hex(lower),gap,a.bit_length(),b.bit_length())
        assert fit or not require_fit
        counts['admitted' if fit else 'rejected'] += 1
        if fit:
            mode = 'inverse' if shifts is None else ('left_shift' if shifts[0] else
                                                    'right_shift' if shifts[1] else 'no_shift')
            counts[mode] += 1
            counts['exact_tie' if a==b else 'non_tie'] += 1

    for _ in range(2500):
        p = rng.randrange(1,220)
        q = 1 << rng.randrange(0,9)
        y = bits((-p if rng.getrandbits(1) else p)/q)
        x = rng.randrange(1,INFINITY) if q>8 else rng.randrange(ONE-(2<<52),ONE+(2<<52))
        want = oracle.reference('pow',x,y)
        for lower in {want-1,want}:
            if not 0 <= lower < INFINITY:
                continue
            a,b,k,n,_ = aligned_powers(x,y,lower)
            gap = 40+rng.randrange(0,10)
            if log_gap_is_below(a,b,k,gap):
                check(x,y,lower,gap)

    for base,y,lower in ((2.,-1075.,0),(.5,1075.,0),
                         (3.,34.,bits(float(3**34-1))),(7.,19.,bits(float(7**19-1)))):
        check(bits(base),bits(y),lower,16300)
    assert counts['exact_tie']==4
    assert lib.compare(0,ONE,0,16300)==0 and lib.compare(ONE,INFINITY,0,16300)==0
    assert lib.compare(ONE,ONE,INFINITY,16300)==0

    rows = benchmark_cases(oracle,capacity)
    assert len(rows)==3,rows
    for row in rows:
        values = (row['x'],row['y'],row['lower'])
        check(*values,row['gap'])
        check(*values,row['gap']-1,require_fit=False)
        assert lib.compare(*values,row['gap']-1)==0
    virtual = virtual_product_case(oracle)
    check(virtual['x'],virtual['y'],virtual['lower'],virtual['gap'])
    assert counts['admitted']>2000 and counts['rejected']==3
    assert all(counts[k]>0 for k in ('left_shift','right_shift','no_shift','inverse'))
    return dict(status='PASS',mpfr=oracle.version,counts=dict(counts),maximum_modulus_bits=capacity,
                benchmark_cases=rows,virtual_product_case=virtual)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx',default='c++')
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    result = run(args.cxx,args.output)
    (args.output/'host.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
