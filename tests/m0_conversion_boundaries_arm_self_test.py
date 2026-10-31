#!/usr/bin/env python3
"""Exact conversion-policy boundaries and exhaustive RP2040 18-bit integer band."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from native_eabi_m0_arm_self_test import Machine,SP,bits,real,signed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--bootrom',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    parser.add_argument('--band-bits',type=int,nargs='+',choices=[17,18],default=[17,18])
    args=parser.parse_args()
    assert not args.json.exists()
    machine=Machine(args.elf,True,bootrom=args.bootrom)
    assert not machine.rom_initializers and not machine.rom_models
    start=time.monotonic();counts=Counter();fatal=None;digest=hashlib.sha256()
    def check(symbol,a,expected,result_width=64):
        assert machine.calls<1500000 and time.monotonic()-start<=300
        result=machine.call(symbol,a)[0]&((1<<result_width)-1)
        counts[symbol]+=1
        digest.update(a.to_bytes(8,'little')+expected.to_bytes(8,'little')+result.to_bytes(8,'little'))
        assert result==expected,(symbol,f'{a:016X}',f'{result:016X}',f'{expected:016X}')
    try:
        fractions=[0,1,(1<<51)-1,1<<51,(1<<52)-1]
        for e in range(2048):
            for f in fractions:
                for sign in (0,1<<63):
                    a=sign|(e<<52)|f;x=real(a)
                    expected=0 if math.isnan(x) or x<=0 else 0xffffffff if x>=0xffffffff else int(x)
                    check('__aeabi_d2uiz',a,expected,32)
        print('PASS d2uiz all2048 exponents, both signs, fraction/NaN/Inf edges',flush=True)
        for width in sorted(set(args.band_bits)):
            for a in range(1<<(width-1),1<<width):
                expected=bits(float(a))
                for symbol in ['__aeabi_i2d','__aeabi_ui2d','__aeabi_l2d','__aeabi_ul2d']:
                    check(symbol,a,expected)
                check('__aeabi_i2d',(-a)&0xffffffff,bits(float(-a)))
                check('__aeabi_l2d',(-a)&((1<<64)-1),bits(float(-a)))
                if a%(1<<14)==0:print(width,'bit band',a-(1<<(width-1)),'/',1<<(width-1),flush=True)
        rng=random.Random(0x61c0de29)
        integers={0,1,2,3,0xffffffff,1<<32,1<<63,(1<<64)-1}
        integers.update(((1<<e)+d)&((1<<64)-1) for e in range(64) for d in range(-4,5))
        integers.update(rng.getrandbits(64) for _ in range(1000))
        for a in sorted(integers):
            check('__aeabi_i2d',a,bits(float(signed(a&0xffffffff,32))))
            check('__aeabi_ui2d',a,bits(float(a&0xffffffff)))
            check('__aeabi_l2d',a,bits(float(signed(a,64))))
            check('__aeabi_ul2d',a,bits(float(a)))
    except Exception as error:
        fatal=dict(type=type(error).__name__,message=str(error))
    result=dict(status='PASS_FINITE_CONVERSIONS' if fatal is None else 'FAIL',fatal=fatal,
                elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
                operator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                actual_calls=machine.calls,call_counts=dict(counts),result_sha256=digest.hexdigest(),
                maximum_observed_stack_bytes=SP-machine.stack_lowest,elapsed_seconds=time.monotonic()-start,
                gold='Python exact arbitrary-width integers, binary64-to-int truncation/saturation policy and RNE int-to-binary64 conversion',
                ABI='R4-R11/SP and bounded stack writes checked on every call',pow_calls=0,physical_IO=0,
                scope='Exhaustive requested17/18-bit bands plus finite exponent/fraction/width boundary coverage; not exhaustive64-bit input coverage.')
    args.json.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    if fatal is not None:raise SystemExit(1)


if __name__=='__main__':main()
