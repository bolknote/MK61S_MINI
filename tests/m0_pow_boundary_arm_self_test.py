#!/usr/bin/env python3
"""Audit the actual512/1024bit pow boundary detectors with exact rationals."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine, SP, bits, real

INF=0x7FF0000000000000
SIGN=1<<63
ONE=0x3FF0000000000000


def nth_root(value,degree):
    # Generic monotone integer search, independent of the ARM restoring
    # square-root algorithm and its repeated root extraction.
    lo,hi=1,1<<((value.bit_length()+degree-1)//degree)
    while lo<hi:
        middle=(lo+hi+1)//2
        if middle**degree<=value:lo=middle
        else:hi=middle-1
    return lo


def rounded_dyadic(coefficient,exponent):
    # Fraction.__float__ rounds an exact integer ratio; no floating pow,
    # logarithm, or approximation to the algebraic result is involved.
    if exponent>4096:return INF
    if exponent < -4096:return 0
    exact=Fraction(coefficient<<exponent) if exponent>=0 else Fraction(coefficient,1<<-exponent)
    try:return bits(float(exact))
    except OverflowError:return INF


def reference(x,y):
    a,d=real(x).as_integer_ratio()
    trailing=(a&-a).bit_length()-1
    a>>=trailing
    exponent=trailing-(d.bit_length()-1)
    p,q=real(y).as_integer_ratio()
    if a==1:
        scale,remainder=divmod(exponent*p,q)
        return None if remainder else (rounded_dyadic(1,scale),'power2')
    if p<0 or p>34 or q>32 or exponent%q:return None
    root=nth_root(a,q)
    if root**q!=a:return None
    coefficient=root**p
    if coefficient.bit_length()>54:return None
    return rounded_dyadic(coefficient,(exponent//q)*p),f'root_degree_{q}'


def corpus(samples):
    values=set()
    def add(x,y):
        if 0<x<INF and x!=ONE and 0<(y&~SIGN)<INF:values.add((x,y))
    def dyadic(coefficient,exponent):
        exact=Fraction(coefficient<<exponent) if exponent>=0 else Fraction(coefficient,1<<-exponent)
        try:value=float(exact)
        except OverflowError:return None
        if not value or not math.isfinite(value) or Fraction(value)!=exact:return None
        return bits(value)
    ys=[bits(sign*value) for sign in (-1,1) for value in
        [*(2.**-k for k in range(12)),2.,3.,33.,54.,2048.,4096.,2.**63,real(INF-1)]]
    for exponent in range(-1074,1024):
        if not exponent:continue
        x=bits(math.ldexp(1.,exponent))
        for y in ys:add(x,y)
        for target in (-1075,-1074,-1023,-1022,1023,1024):
            y=bits(float(Fraction(target,exponent)))
            for delta in (-1,0,1):add(x,y+delta)
    # Every root depth and power limit is exercised at both sides of its
    # exact integer threshold. Scaling covers normal/subnormal endpoints.
    for power in range(1,55):
        for depth in range(6):
            degree=1<<depth
            limit=min(nth_root((1<<53)-1,degree),nth_root((1<<54)-1,power))
            roots={3,5,7,9,15,31,63,127,255,*range(max(3,limit-4),limit+5)}
            for root in roots:
                if not root&1 or root**degree >= 1<<53:continue
                coefficient=root**degree
                scales={degree*(e//degree) for e in (-1074,-1022,-512,-64,-1,0,1,64,512,970)}
                for scale in scales:
                    x=dyadic(coefficient,scale)
                    if x is None:continue
                    y=bits(float(Fraction(power,degree)))
                    add(x,y);add(x,y|SIGN)
                    for delta in (-1,1):add(x+delta,y)
    rng=random.Random(0x706f7742)
    for i in range(samples):
        x=rng.randrange(1,INF)
        y=(rng.randrange(1,INF)|(rng.getrandbits(1)<<63)) if i&1 else bits(rng.choice((-1,1))*rng.randrange(1,65)/2.**rng.randrange(0,8))
        add(x,y)
    return sorted(values)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=50000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();assert args.samples>=0
    for c,e,want in [(1,-1075,0),(3,-1075,2),(1,-1074,1),
                     ((1<<53)-1,971,INF-1),((1<<54)-1,970,INF)]:
        assert rounded_dyadic(c,e)==want
    digest_elf=hashlib.sha256(args.elf.read_bytes()).hexdigest()
    machine=Machine(args.elf,True,stack_bytes=16384,instruction_budget=1000000)
    symbols={p:f'_ZN15m0_pow_interval5FixedILj{p}EE14exact_boundaryEyyRy' for p in (512,1024)}
    assert all(n in machine.elf.symbols for n in symbols.values())
    pointer=SP-15000;inputs=corpus(args.samples);counts=Counter();digest=hashlib.sha256();dirty_inputs=[]
    for x,y in inputs:
        expected=reference(x,y)
        for precision,symbol in symbols.items():
            machine.uc.mem_write(pointer,struct.pack('<Q',0xBAD0BAD0BAD0BAD0))
            got=machine.call(symbol,x,y,c=pointer)[0]&255
            assert got==int(expected is not None),('boundary classification',precision,f'{x:016X}',f'{y:016X}',got,expected)
            if got:
                result=struct.unpack('<Q',machine.uc.mem_read(pointer,8))[0]
                assert result==expected[0],('boundary RNE',precision,f'{x:016X}',f'{y:016X}',f'{result:016X}',f'{expected[0]:016X}')
        kind=expected[1] if expected is not None else 'not_precision54'
        counts[kind]+=1
        if kind.startswith('root_degree_') and not kind.endswith('_1') and len(dirty_inputs)<32:dirty_inputs.append((x,y,expected[0]))
        digest.update(struct.pack('<4Q',x,y,expected[0] if expected else 0,int(expected is not None)))
    pending=struct.pack('<7I',17,3,17,3,5,2,3)
    for x,y,expected in dirty_inputs:
        for symbol in symbols.values():
            machine.uc.mem_write(0xD0000060,pending)
            assert machine.call(symbol,x,y,c=pointer)[0]&255==1
            assert struct.unpack('<Q',machine.uc.mem_read(pointer,8))[0]==expected
            assert bytes(machine.uc.mem_read(0xD0000060,len(pending)))==pending
    assert digest_elf==hashlib.sha256(args.elf.read_bytes()).hexdigest()
    report=dict(status='PASS',elf_sha256=digest_elf,cases=len(inputs),actual_arm_calls=machine.calls,
        precisions=[512,1024],classification_mismatches=0,wrong_rounding=0,classes=dict(counts),
        dirty_sio_checks=2*len(dirty_inputs),result_sha256=digest.hexdigest(),
        oracle='Exact rational input decomposition, direct integer nth-root search, arbitrary-size integer powers, and Fraction-to-binary64 RNE. No log/exp/pow approximation.',
        abi='Every actual ARM call checks savedR4-R11,SP and bounded stack writes.',
        scope='Boundary-focused finite corpus across the entire binary64 exponent range, every supported root depth and power threshold, adjacent nonboundaries, and deterministic random pairs. Complements the range/valuation argument; not exhaustive C++ verification or a totality proof for nonboundary pow cases.')
    args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
