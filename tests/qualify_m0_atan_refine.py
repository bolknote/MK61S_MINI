#!/usr/bin/env python3
"""Force the integer atan refinement and compare its return with MPFR."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from m0_mpfr_oracle import Oracle,bits,real
from native_eabi_m0_arm_self_test import Machine
from qualify_m0_rounding import corpus
from qualify_m0_atan_edges import corpus as edges


def index(m):
    if m>bits(128.):return 0
    if m>bits(64.):return 1
    xb=bits(1./real(m)) if m>bits(1.) else m
    e=(xb>>52)-1023;s=(xb&((1<<52)-1))|(1<<52)
    return ((s>>(45-e))+1)//2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=20000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();machine=Machine(args.elf,True);oracle=Oracle()
    inputs={v[0] for v in corpus('atan',args.samples)}|set(edges())
    inputs.add(0x3FB97996F4E5F9F0)
    inputs=sorted(v for v in inputs if bits(1/64)<=(v&((1<<63)-1))<bits(2.**55))
    digest=hashlib.sha256()
    for value in inputs:
        selected=index(value&((1<<63)-1));assert 0<=selected<=64
        expected=oracle.reference('atan',value)
        got=machine.call('atan_refine',value,selected)[0]
        assert got==expected,(hex(value),selected,hex(got),hex(expected))
        digest.update(struct.pack('<3QI',value,got,expected,selected))
    report=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        mpfr=oracle.version,cases=len(inputs),wrong_rounding=0,sha256=digest.hexdigest(),
        scope='Direct forced refinement over centers, midpoint/dispatch boundaries, random inputs and the former CORE-MATH case.',
        abi='Every call verifies R4-R11, SP and bounded stack writes.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
