#!/usr/bin/env python3
"""Check the exact short-significand pow path against Python integer powers."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine, bits

INF=0x7ff0000000000000
FRACTION=(1<<52)-1
SIGN=1<<63
UNDECIDED=INF|(1<<51)


def rne(integer,shift):
    if shift<=0:return integer<<(-shift)
    q,r=divmod(integer,1<<shift)
    half=1<<(shift-1)
    return q+(r>half or (r==half and bool(q&1)))


def exact(x,n):
    magnitude=x&(SIGN-1)
    sign=(x&SIGN) if n&1 else 0
    if not magnitude:return sign
    field=magnitude>>52
    coefficient=(magnitude&FRACTION)|((1<<52) if field else 0)
    power=coefficient**n
    scale=(int(field)-1075 if field else -1074)*n
    exponent=power.bit_length()-1+scale
    if exponent<-1022:return rne(power,-scale-1074)|sign
    q=rne(power,power.bit_length()-53)
    if q==1<<53:q>>=1;exponent+=1
    if exponent>1023:return INF|sign
    return ((exponent+1023)<<52)|(q&FRACTION)|sign


def encoding(odd,field):
    full=odd<<(53-odd.bit_length())
    return (field<<52)|(full&FRACTION)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--bootrom',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    machine=Machine(args.elf,True,stack_bytes=16384,instruction_budget=200000000,bootrom=args.bootrom)
    symbol=next(name for name in machine.elf.symbols if name=='pow_short_integer' or 'pow_short_integer' in name)
    rng=random.Random(0x810308)
    pairs=set()
    for n in range(3,9):
        maximum=64//n
        for field in range(1,2047):
            for odd in (1,(1<<maximum)-1):pairs.add((encoding(odd,field),n))
        for width in range(1,maximum+1):
            odds={1 if width==1 else (1<<(width-1))+1,(1<<width)-1}
            for odd in odds:
                for field in (1,2,1022,1023,1024,2045,2046):pairs.add((encoding(odd,field),n))
        for _ in range(400):
            width=rng.randrange(1,maximum+1)
            odd=rng.randrange(1<<(width-1),1<<width)|1
            pairs.add((encoding(odd,rng.randrange(1,2047)),n))
        pairs.update((x,n) for x in (0,1,(1<<52)-1,1<<52,bits(2.**-215),bits(52.5),bits(51.5)))
    digest=hashlib.sha256()
    checked=public_calls=0
    for index,(x,n) in enumerate(sorted(pairs)):
        field=x>>52
        full=(x&FRACTION)|((1<<52) if field else 0)
        odd=full//(full&-full) if full else 0
        supported=field==0 or odd.bit_length()*n<=64
        got=machine.call(symbol,x,n)[0]
        if not supported:
            assert got==UNDECIDED,(hex(x),n,'unsupported coefficient accepted')
            continue
        expected=exact(x,n)
        assert got==expected,(hex(x),n,hex(got),hex(expected))
        checked+=1
        if index%16==0:
            for negative in (False,True):
                value=x|(SIGN if negative else 0)
                result=machine.call('_ZN12compact_math3powEdd',value,bits(float(n)))[0]
                wanted=exact(value,n)
                assert result==wanted,(hex(value),n,hex(result),hex(wanted))
                public_calls+=1
        digest.update(struct.pack('<4Q',x,n,expected,got))
    # This static helper is called only with n=3..8. GCC is allowed to
    # specialize it for those callers; test other exponents at the public ABI.
    for n in (0,1,2,9):
        result=machine.call('_ZN12compact_math3powEdd',bits(1.5),bits(float(n)))[0]
        assert result==exact(bits(1.5),n),n
    samples=[]
    for x,n in [(52.5,8),(51.5,8),(float.fromhex('0x1.bb4p-7'),5),(1.5,3),(1.3,7),(2.,5)]:
        value=bits(x)
        result,_,count=machine.call('_ZN12compact_math3powEdd',value,bits(float(n)),count=True)
        assert result==exact(value,n)
        samples.append(dict(x=x,n=n,instructions=count))
    report=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        bootrom_sha256=machine.bootrom_sha256,intrinsic_models=machine.rom_models,
        exact_cases=checked,public_calls=public_calls,wrong_rounding=0,result_sha256=digest.hexdigest(),
        samples=samples,
        argument=['Normal x=A*2^e with odd A has w=bit_length(A). If w*n<=64, every partial positive integer power is below 2^64.',
                  'For n>=3, the accepted odd coefficient has at most 21bits; its factor fits uint32_t and the split multiplication computes the full exact uint64_t product.',
                  'Normalization followed by sticky shifts and the existing binary64 pack performs one final ties-to-even rounding, including subnormal and overflow boundaries.',
                  'A subnormal nonnegative x raised to any n>=3 is below the half-minimum-subnormal threshold and rounds to zero.'],
        scope='All normal exponent fields, coefficient width transitions, deterministic random short coefficients, exact midpoint examples, gradual underflow, overflow and public negative-base parity. Python computes the complete arbitrary-precision significand power and one final integer RNE rounding; no floating pow or libm oracle. Finite implementation qualification complements the exact algebraic bound.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
