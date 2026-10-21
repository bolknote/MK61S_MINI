#!/usr/bin/env python3
"""Check actual ARM float widening and its normal-path flash data reads."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import struct

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ
from native_eabi_m0_arm_self_test import Machine


def expected_bits(value):
    """Widen the integer significand exactly, including subnormals and NaNs."""
    sign=(value>>31)<<63
    exponent=(value>>23)&255
    fraction=value&0x7fffff
    if exponent==255:
        return sign|0x7ff0000000000000|(fraction<<29)|(0x8000000000000 if fraction else 0)
    if exponent:
        return sign|((exponent+896)<<52)|(fraction<<29)
    if not fraction:
        return sign
    width=fraction.bit_length()
    return sign|((width+873)<<52)|((fraction<<(53-width))&((1<<52)-1))


def vectors(samples):
    result=set()
    fractions={0,1,2,3,7,8,15,16,0x7ffffe,0x7fffff,0x400000,0x3fffff}
    for bit in range(23):
        for delta in (-1,0,1):
            fractions.add(((1<<bit)+delta)&0x7fffff)
    for sign in (0,1<<31):
        for exponent in range(256):
            for fraction in fractions:
                result.add(sign|(exponent<<23)|fraction)
    rng=random.Random(0xF2D740)
    result.update(rng.getrandbits(32) for _ in range(samples))
    return sorted(result)


def check(path,inputs,require_literal_free):
    machine=Machine(path,True,stack_bytes=4096)
    active=Counter()
    def code(_uc,address,size,_user):
        del address,size
        active['instructions']+=1
    def read(_uc,_access,address,size,_value,_user):
        if 0x10000000<=address<0x10200000:
            active['flash_reads']+=1
            active['flash_bytes']+=size
    hooks=[machine.uc.hook_add(UC_HOOK_CODE,code),machine.uc.hook_add(UC_HOOK_MEM_READ,read)]
    normal_counts=Counter()
    special_counts=Counter()
    digest=hashlib.sha256()
    try:
        for value in inputs:
            active.clear()
            result=machine.call('__aeabi_f2d',value,width=32)[0]
            expected=expected_bits(value)
            assert result==expected,(str(path),hex(value),hex(result),hex(expected))
            normal=0<((value>>23)&255)<255
            counts=normal_counts if normal else special_counts
            counts[(active['instructions'],active['flash_reads'],active['flash_bytes'])]+=1
            if normal and require_literal_free:
                assert active['instructions']==13,(hex(value),active)
                assert active['flash_reads']==0,(hex(value),active)
            digest.update(struct.pack('<IQ',value,result))
    finally:
        for hook in hooks:
            machine.uc.hook_del(hook)
    describe=lambda counts:[dict(instructions=key[0],flash_data_reads=key[1],
        flash_data_bytes=key[2],cases=cases) for key,cases in sorted(counts.items())]
    return dict(elf=str(path),elf_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        calls=machine.calls,normal_cases=sum(normal_counts.values()),
        special_cases=sum(special_counts.values()),normal_paths=describe(normal_counts),
        special_paths=describe(special_counts),result_sha256=digest.hexdigest(),
        wrong_results=0,ABI='R0 binary32 input, R0/R1 binary64 output; R4-R11 and SP preserved')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--baseline-elf',type=Path)
    parser.add_argument('--samples',type=int,default=10000)
    parser.add_argument('--require-literal-free',action='store_true')
    parser.add_argument('--json',type=Path)
    args=parser.parse_args()
    assert args.samples>=0
    inputs=vectors(args.samples)
    current=check(args.elf,inputs,args.require_literal_free)
    report=dict(status='PASS',cases=len(inputs),current=current,
        oracle='Integer IEEE binary32 significand widening; every finite binary32 value is exactly representable as binary64. NaN sign/payload are preserved and signaling NaNs quieted.',
        scope='Both signs, all 256 exponent encodings, significand bit boundaries and deterministic random encodings. This finite ARM test is not exhaustive over all 2^32 inputs, and instruction/read counts are not physical timings.',
        physical_timing_available=False)
    if args.baseline_elf:
        baseline=check(args.baseline_elf,inputs,False)
        assert baseline['result_sha256']==current['result_sha256']
        report['baseline']=baseline
        if args.require_literal_free:
            assert baseline['normal_paths']==[dict(instructions=13,flash_data_reads=1,
                flash_data_bytes=4,cases=current['normal_cases'])]
            assert baseline['special_paths']==[
                {**row,'instructions':row['instructions']+2} for row in current['special_paths']]
    text=json.dumps(report,indent=2)+'\n'
    if args.json:
        args.json.write_text(text)
    print(text,end='')


if __name__=='__main__':
    main()
