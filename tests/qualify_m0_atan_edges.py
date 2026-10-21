#!/usr/bin/env python3
"""MPFR qualification of ARM atan reduction centers and dispatch boundaries."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from m0_mpfr_oracle import Oracle,bits
from native_eabi_m0_arm_self_test import Machine


def corpus():
    values=set()
    def around(b,n=4):
        for v in range(b-n,b+n+1):
            if 0<=v<0x7ff0000000000000:values.update((v,v|(1<<63)))
    for j in range(1,65):
        for value in (j/64,(2*j+1)/128):
            if value<=1:
                around(bits(value));around(bits(1/value))
    for top in range(32768,65536,8):
        exponent=(top//8)%6
        b=((1023+exponent)<<52)|((top-32768)<<37)
        around(b,2)
    for value in (2.**-27,1/64,1.,64.,128.,2.**55):
        around(bits(value),32)
    return sorted(values)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();machine=Machine(args.elf,True);oracle=Oracle()
    digest=hashlib.sha256();inputs=corpus()
    for value in inputs:
        expected=oracle.reference('atan',value)
        got=machine.call('_ZN12compact_math4atanEd',value)[0]
        assert got==expected,(hex(value),hex(got),hex(expected))
        digest.update(struct.pack('<3Q',value,got,expected))
    report=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        mpfr=oracle.version,cases=len(inputs),wrong_rounding=0,sha256=digest.hexdigest(),
        scope='Table centers and halfway boundaries, reciprocal reductions, sampled seed bucket boundaries, positive/negative dispatch endpoints.',
        abi='Every call verifies R4-R11, SP and bounded stack writes.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
