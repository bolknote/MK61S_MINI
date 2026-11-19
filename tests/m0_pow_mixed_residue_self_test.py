#!/usr/bin/env python3
"""Select and check bounded mixed-radix pow comparators against exact integers."""

import argparse
from collections import Counter
import ctypes as C
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from random import Random
from statistics import median
import subprocess
import sys
from time import perf_counter_ns

from m0_mpfr_oracle import Oracle, bits
from m0_pow_residue_self_test import aligned_powers, log_gap_is_below
from m0_pow_stream_host_self_test import INFINITY, ONE

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT/'research/m0-pow-comparison-20261117'
CPP = ROOT/'tests/fixtures/m0_pow_mixed_residue.cpp'
BUDGET = 9216
MODES = {1: 'binary', 2: 'binary_minus', 3: 'binary_plus', 4: 'odd_pair', 5: 'triple'}
GAP = 16300


class Plan(C.Structure):
    _fields_ = [(k, C.c_uint) for k in ('mode', 'words', 'scratch')]+[('products', C.c_uint64)]


class Work(C.Structure):
    _fields_ = [(k, C.c_uint64) for k in ('products', 'columns')]


def ring_moduli(mode, base):
    return {
        1: (base,), 2: (base, base-1), 3: (base, base+1),
        4: (base-1, base+1), 5: (base, base-1, base+1),
    }[mode]


@lru_cache(maxsize=None)
def capacity(mode, budget):
    count = len(ring_moduli(mode, 16))
    words = budget//(count+2)-(mode >= 3)
    if not words > 0:
        return 0
    modulus = 1
    for v in ring_moduli(mode, 1 << (16*words)):
        modulus *= v
    return modulus.bit_length()-1


class Native:
    def __init__(self, compiler, output):
        path = output/('mixed.dylib' if sys.platform == 'darwin' else 'mixed.so')
        subprocess.run([compiler, '-std=c++17', '-O3', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-function', '-dynamiclib' if sys.platform == 'darwin' else '-shared',
                        '-fPIC', '-I'+str(ROOT/'code'), '-I'+str(RESEARCH), str(CPP), '-o', str(path)],
                       check=True)
        self.lib = C.CDLL(str(path.resolve()))
        u, U, w = C.c_uint, C.c_uint64, C.POINTER(C.c_uint16)
        self.lib.mixed_capacity.argtypes, self.lib.mixed_capacity.restype = [u,u], u
        self.lib.mixed_compare.argtypes = [U,U,U,u,u,w,u,C.POINTER(Plan),C.POINTER(Work)]
        self.lib.mixed_compare.restype = C.c_int
        self.lib.single_compare.argtypes, self.lib.single_compare.restype = [U,U,U,u], C.c_int
        self.lib.mixed_raw.argtypes, self.lib.mixed_raw.restype = [U,U,u,u,w], C.c_int
        self.lib.mixed_pairs.argtypes = [u,u,u,C.c_bool,C.c_bool]
        self.lib.mixed_pairs.restype = U
        self.lib.mixed_ring.argtypes = [u,u,u,w,u,w,u,w,U,U]
        self.lib.mixed_ring.restype = u
        self.storage = (C.c_uint16*(BUDGET+2))()
        self.ptr = C.cast(C.byref(self.storage,2),w)

    def compare(self, x, y, lower, gap, mode, budget=BUDGET):
        plan, work = Plan(), Work()
        self.storage[0] = 0xb478
        self.storage[budget+1] = 0xf39a
        sign = self.lib.mixed_compare(x,y,lower,gap,mode,self.ptr,budget,C.byref(plan),C.byref(work))
        assert self.storage[0] == 0xb478 and self.storage[budget+1] == 0xf39a
        assert plan.scratch <= budget and work.products <= plan.products
        return sign, plan, work


def pair_and_capacity_checks(native):
    checks = 0
    for budget in (*range(28), BUDGET, BUDGET-1):
        for mode in MODES:
            assert native.lib.mixed_capacity(mode,budget) == capacity(mode,budget)
            checks += 1
    for n in range(1,15):
        for a in range(1,n+1):
            for b in range(1,n+1):
                for square in (False, True) if a == b else (False,):
                    for trunc in (False, True):
                        expected = sum((not square or i <= j) and (not trunc or i+j<n)
                                       for i in range(a) for j in range(b))
                        assert native.lib.mixed_pairs(n,a,b,square,trunc) == expected
                        checks += 1
    return checks


def ring_checks(native):
    rng = Random(0x394fd8)
    checks = 0
    for n in (1,2,3,4,8,16):
        base = 1 << (16*n)
        array = C.c_uint16*(n+1)

        def pack(value):
            return array(*(value >> (16*i) & 65535 for i in range(n+1)))

        def size(value):
            return (value.bit_length()+15)//16

        for mode, modulus in enumerate((base,base-1,base+1)):
            edge = (0,1,2,base//2,modulus-2,modulus-1)
            pairs = [(a,b) for a in edge for b in edge]
            pairs.extend((rng.randrange(modulus),rng.randrange(modulus)) for _ in range(90))
            for i, (a,b) in enumerate(pairs):
                shift = ([0,1,15,16,16*n-1,16*n,16*n+1,32*n,1<<127][i%9]
                         if i<len(edge)**2 else rng.getrandbits(127))
                for op, exact in enumerate((a*b, a*a, a*pow(2,shift,modulus), a-b)):
                    lhs, rhs, scratch = pack(a), pack(b), array()
                    used = native.lib.mixed_ring(mode,n,op,lhs,size(a),rhs,size(b),scratch,
                                                 shift&((1<<64)-1),shift>>64)
                    got = sum(int(lhs[j])<<(16*j) for j in range(used))
                    assert got == exact%modulus,(n,mode,op,a,b,shift,got,exact%modulus)
                    checks += 1
    return checks


def signed_windows(native):
    rng = Random(0xbee021)
    checks = 0
    for n in (1,2,3,4):
        base = 1 << (16*n)
        for mode in MODES:
            modulus = 1
            for value in ring_moduli(mode,base):
                modulus *= value
            stop = min((modulus-1)//2,(1<<64)-2)
            values = {0,1,2,stop,stop-1,stop//2,base//2-1,base//2,base//2+1}
            values.update(rng.randrange(stop) for _ in range(100))
            # Some wider modes don't fit their full boundary in a uint64
            # fixture. A signed exhaustive reconstruction proof is separate.
            for d in sorted({s*d for s in (-1,1) for d in values if d<=stop}):
                got = native.lib.mixed_raw(max(d,0)+1,max(-d,0)+1,mode,n,native.ptr)
                assert got == (int(d>0)-int(d<0)),(mode,n,d,got)
                checks += 1
    return checks


def width_for(a, b, k, n, gap):
    return 0 if n is None else max(1,n+2+k-gap)


def forced_case(width, sign, q, oracle):
    shift = q.bit_length()-1
    for step in (48,49,47,46,50,45,44,43,42,41,40):
        x = bits(1-2.**-step)
        center = (width+41-shift-2-(53*q if sign<0 else 0))//step
        for p in range(max(1,center-2),max(1,center+4)):
            if q>1 and not (p&1):
                continue
            y = bits(sign*p/q)
            result = oracle.reference('pow',x,y)
            for lower in (result-1,result):
                a,b,k,n,_ = aligned_powers(x,y,lower)
                gap = n+2+k-width
                if gap >= max(32,k+2) and log_gap_is_below(a,b,k,gap):
                    return (x,y,lower,gap), (a>b)-(a<b)
    raise AssertionError(('no forced fixture',width,sign,q))


def measured(fn):
    elapsed = []
    for _ in range(3):
        start = perf_counter_ns()
        result = fn()
        elapsed.append(perf_counter_ns()-start)
    return result, round(median(elapsed)/1e6,4)


def run(native):
    counts = Counter(pair_and_capacity_checks=pair_and_capacity_checks(native),
                     ring_operations=ring_checks(native), signed_residue_reconstructions=signed_windows(native))
    oracle = Oracle()
    rng = Random(0x27fa02)

    def check(args, exact, width, measure=False):
        expected = exact or (1 if args[2]&1 else -1)
        rows, accepted = {}, []
        for mode in (*MODES,0):
            fn = lambda: native.compare(*args,mode)
            (got,plan,work), time = measured(fn) if measure else (fn(),None)
            fits = width <= capacity(mode,BUDGET) if mode else width<=capacity(5,BUDGET)
            assert got == (expected if fits else 0),(args,mode,width,got,expected)
            counts['accepted_modes' if fits else 'declined_modes'] += 1
            if plan.mode and mode:
                accepted.append((plan.products,plan.scratch,mode))
                assert plan.mode == mode
            if plan.mode and not mode:
                assert (plan.products,plan.scratch,plan.mode) == min(accepted)
            if measure:
                rows[MODES.get(mode,'automatic')] = dict(
                    result=got, selected=MODES.get(plan.mode), window_words=plan.words,
                    scratch_bytes=2*plan.scratch, product_bound=plan.products,
                    observed_products=work.products, observed_columns=work.columns, host_ms=time)
        return rows

    for _ in range(320):
        x = rng.randrange(ONE-(2<<52),ONE+(2<<52))
        y = bits(rng.choice((-1,1))*rng.randrange(1,220)/(1<<rng.randrange(7)))
        result = oracle.reference('pow',x,y)
        for lower in (result-1,result):
            if not 0<=lower<INFINITY:
                continue
            a,b,k,n,_ = aligned_powers(x,y,lower)
            gap = 38
            if log_gap_is_below(a,b,k,gap):
                check((x,y,lower,gap),(a>b)-(a<b),width_for(a,b,k,n,gap))
                assert (1 if result>lower else -1) == ((a>b)-(a<b) or (1 if lower&1 else -1))
                counts['pow_boundaries'] += 1
    for x,y,lower in ((2.,-1075.,0),(.5,1075.,0),(3.,34.,bits(float(3**34-1))),
                      (7.,19.,bits(float(7**19-1)))):
        case = bits(x),bits(y),lower,GAP
        a,b,k,n,_ = aligned_powers(*case[:3])
        assert a == b
        check(case,0,width_for(a,b,k,n,GAP))
        counts['ties'] += 1
    rows = []
    for width, sign, q in ((16000,1,1),(49152,1,1),(49152,-1,512),(49153,1,1),
                            (65536,-1,512),(73696,1,1),(73727,-1,128),
                            (73728,1,1),(80000,-1,512),(88415,1,1),(88416,-1,128)):
        case, expected = forced_case(width,sign,q,oracle)
        x,y,lower,gap = case
        methods = check(case,expected,width,measure=True)
        old, time = measured(lambda: native.lib.single_compare(*case))
        assert old == (expected if width<=49152 else 0)
        assert expected == (1 if oracle.reference('pow',x,y)>lower else -1)
        rows.append(dict(required_width=width,gap=gap,x=f'{x:016x}',y=f'{y:016x}',
                         midpoint_lower=f'{lower:016x}',expected=expected,methods=methods,
                         existing=dict(result=old,host_ms=time)))
    assert counts['pow_boundaries']>400
    return dict(status='PASS_CANDIDATE_NOT_FULL_DOMAIN', mpfr=oracle.version,
                counts=counts, scratch_budget_bytes=2*BUDGET, cases=rows,
                capacities={MODES[m]:capacity(m,BUDGET) for m in MODES},
                coverage_at_production_gap={MODES[m]:GAP+capacity(m,BUDGET)-2 for m in MODES},
                practical_all_input_bound_established=False,
                fixture_sha256=sha256(CPP.read_bytes()).hexdigest(),
                source_sha256=sha256((RESEARCH/'mixed_residue.hpp').read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx',default='c++')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    if not __debug__:
        parser.error('enable Python assertions')
    args.output.mkdir(parents=True,exist_ok=True)
    result = run(Native(args.cxx,args.output))
    with (args.report or args.output/'mixed-host.json').open('x') as stream:
        json.dump(result,stream,indent=2)
        stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},indent=2))
    for row in result['cases']:
        a = row['methods']['automatic']
        print(row['required_width'],a['selected'],a['observed_products'],
              a['product_bound'],a['host_ms'],row['existing']['host_ms'])


if __name__ == '__main__':
    main()
