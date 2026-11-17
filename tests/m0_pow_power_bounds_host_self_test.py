#!/usr/bin/env python3
"""Check normalized power bounds against exact integers and directed MPFR."""
import argparse
import ctypes
import decimal
import json
import math
from pathlib import Path
import random
import subprocess
import sys

from m0_mpfr_oracle import Oracle, bits, real

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'dev/tools'))
from certify_m0_pow_power_bounds import unresolved_candidate

ONE = bits(1.)
INF = bits(math.inf)
MASK64 = (1 << 64) - 1

def pair(value):
    return value & MASK64, value >> 64

def square_checks(lib, rng):
    tested = {}
    for precision in (128,4096,8192):
        square = getattr(lib,f'square{precision}')
        square.argtypes = (ctypes.POINTER(ctypes.c_uint16),ctypes.c_bool)
        square.restype = ctypes.c_uint
        words = precision//16
        coefficient = ctypes.c_uint16 * words
        minimum = 1 << (precision-1)
        half = 1 << (precision//2)
        binade = math.isqrt(1 << (2*precision-1))
        cases = [minimum, 2*minimum-1, minimum+(half-1),
                 (half-1)*half+1, (half-1)*(half+1), binade-1, binade, binade+1]
        for start in (0,1,words//4,words//2-1,words//2,words//2+1,words-1):
            for _ in range(16):
                cases.append(minimum | (rng.getrandbits(precision-16*start-1) << (16*start)))
        for index, a in enumerate(cases):
            exact = index%3!=0 or index==0
            result = coefficient(*(a>>(16*i)&65535 for i in range(words)))
            status = square(result,exact)
            squared = a*a
            shift = squared.bit_length()-precision
            truncated, remainder = divmod(squared,1<<shift)
            assert sum(word<<(16*i) for i,word in enumerate(result)) == truncated, (precision,index)
            assert status == 2*(shift-precision+1)+int(exact and remainder==0), (precision,index,status)
        tested[precision] = len(cases)
    return tested

def arithmetic_checks(lib, rng):
    out = (ctypes.c_uint64 * 4)()
    counts = dict(products=0, raised_bounds=0, upper_renormalizations=0)
    for f in (lib.product128, lib.upper128):
        f.argtypes = [ctypes.c_uint64] * 4 + [ctypes.POINTER(ctypes.c_uint64)]
        f.restype = None

    for _ in range(3000):
        a = (1 << 127) | rng.getrandbits(127)
        b = (1 << 127) | rng.getrandbits(127)
        value = a*b
        shift = value.bit_length()-128
        truncated, remainder = divmod(value, 1 << shift)
        lib.product128(*pair(a), *pair(b), out)
        assert tuple(out) == (*pair(truncated),shift-127,int(remainder==0))
        counts['products'] += 1

    for i in range(1000):
        a = (1 << 128)-1-rng.getrandbits(17) if i%2 else (1 << 127)|rng.getrandbits(126)
        terms = (1 << 116) | rng.getrandbits(53)
        product = a+4*(terms-1)
        scale = product >= 1 << 128
        if scale:
            product = (product+1)//2
        lib.upper128(*pair(a), *pair(terms), out)
        assert tuple(out)[:3] == (*pair(product),int(scale))
        counts['raised_bounds'] += 1
        counts['upper_renormalizations'] += scale
    assert counts['upper_renormalizations'] == 500
    return counts

def oracle_cases(rng):
    path = ROOT/'research/m0-pow-boundary-20261023/totality/boundary-gap.json'
    for row in json.loads(path.read_bytes())['cases']:
        x, y, want = (int(row[key],16) for key in ('x','y','rounded'))
        for lower in (want-1,want):
            if 0 <= lower < INF:
                yield 'published-near-boundary', x, y, lower

    for x, y, lower in ((3.,34.,bits(float(3**34-1))), (7.,19.,bits(float(7**19-1))), (2.,-1075.,0),
                        (2.**-215,5.,0),(1.,-1.,ONE),(1.25,2.**-85,ONE-1),
                        (real(ONE-1),2.**63,0),(real(ONE+1),2.**63,INF-1)):
        yield 'exact-and-cutoffs', bits(x), bits(y), lower

    # This exact tie has wider coefficient powers than the narrow probes.
    # The final 8192-bit stage must still settle it before the stream.
    yield 'wide-exact-tie', bits(float(3**32)), bits(17/16), bits(float(3**34-1))

    y = 0x3BFFFFFFFFFFFFFF
    for x in (1,0x000FFFFFFFFFFFFF,0x7FEFFFFFFFFFFFFF):
        for sign in (0,1 << 63):
            for lower in (ONE-1,ONE):
                yield 'large-exponent-workload', x, y|sign, lower

    # At the maximum denominator, only the midpoint immediately below
    # one can remain uncertain. Bases in [2^-738,2^738] are excluded.
    for x in (1, 0x000FFFFFFFFFFFFF, bits(2.**-738), ONE-1,
              ONE+1, bits(2.**738), INF-1):
        for sign in (0, 1 << 63):
            for lower in range(ONE-2, ONE+2):
                yield 'maximum-denominator-domain', x, 0x3BFFFFFFFFFFFFFF|sign, lower

    d = decimal.Context(prec=120)
    decimals = decimal.Decimal.from_float
    extreme = (0, 1, 0x000fffffffffffff, 0x0010000000000000, ONE-1, ONE, INF-1)
    overflow_neighbor = d.power(decimal.Decimal(2),1024)
    for i in range(768):
        if i%4 == 0:
            x = ONE+rng.choice((-1,1))*rng.randrange(1,4097)
        elif i%4 == 1:
            x = rng.randrange(1,0x0010000000000000)
        else:
            x = rng.randrange(1,INF)
        lower = extreme[i%len(extreme)] if i%3 else rng.randrange(INF)
        lo = decimals(real(lower))
        hi = overflow_neighbor if lower+1 == INF else decimals(real(lower+1))
        midpoint = d.divide(d.add(lo,hi),decimal.Decimal(2))
        y = float(d.divide(d.ln(midpoint),d.ln(decimals(real(x)))))
        for v in (math.nextafter(y,-math.inf),y,math.nextafter(y,math.inf)):
            yield 'generated-midpoint', x, bits(v), lower

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cxx',default='c++')
    a = p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    library = (a.output/('bounds.dylib' if sys.platform=='darwin' else 'bounds.so')).resolve()
    subprocess.run([a.cxx,'-std=c++17','-O3','-Wall','-Wextra','-Werror','-fPIC',
        '-dynamiclib' if sys.platform=='darwin' else '-shared','-I'+str(ROOT/'code'),
        str(ROOT/'tests/fixtures/m0_pow_power_bounds_host.cpp'),'-o',str(library)],check=True)
    lib = ctypes.CDLL(str(library))
    rng = random.Random(0x47266D)
    arithmetic = arithmetic_checks(lib,rng)
    oracle = Oracle()
    functions = {p:getattr(lib,f'side{p}') for p in (128,256,4096,8192)}
    counts = {p:dict(checked=0,undecided=0,wrong=0,excluded_by_domain=0) for p in functions}
    for f in functions.values():
        f.argtypes = [ctypes.c_uint64]*3
        f.restype = ctypes.c_int
        assert f(0,ONE,ONE)==f(ONE,INF,ONE)==f(ONE,ONE,INF)==0

    for category, x, y, lower in oracle_cases(rng):
        want = oracle.reference('pow',x,y)
        expected = -1 if want<=lower else 1
        for precision,f in functions.items():
            if category=='generated-midpoint' and precision>=4096:
                stride = 8 if precision==4096 else 32
                if counts[128]['checked']%stride:
                    continue
            order = f(x,y,lower)
            assert order in (0,expected),(precision,category,hex(x),hex(y),hex(lower),order,expected)
            if precision == 256 and category != 'wide-exact-tie':
                assert order, ('unexpected undecided 256-bit input', category, hex(x), hex(y))
            possible = unresolved_candidate(x,y,lower,precision)
            assert order or possible, ('domain excluded an undecided input', precision,
                                      category, hex(x), hex(y), hex(lower))
            counts[precision]['checked'] += 1
            counts[precision]['undecided'] += order==0
            counts[precision]['excluded_by_domain'] += not possible
    assert counts[128]['undecided']>0
    assert counts[256]['undecided']==1  # The added exact tie exceeds this precision.
    assert all(counts[p]['undecided']==0 for p in (4096,8192))
    arithmetic['squares'] = square_checks(lib, random.Random(0x8118192))
    result = dict(status='PASS',mpfr=oracle.version,arithmetic=arithmetic,precisions=counts)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
