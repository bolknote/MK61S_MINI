#!/usr/bin/env python3
"""Force the Q94 ARM ln refinement and check its result against MPFR."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from m0_mpfr_oracle import Oracle
from native_eabi_m0_arm_self_test import Machine
from qualify_m0_rounding import corpus
from qualify_m0_log_edges import corpus as edges


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=20000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();machine=Machine(args.elf,True);oracle=Oracle()
    values={row[0] for row in corpus('ln',args.samples)}|set(edges())
    values.add(0x3FF01E2A43FC46C8)
    values=sorted(x for x in values if 0x0010000000000000<=x<0x7ff0000000000000)
    digest=hashlib.sha256()
    for x in values:
        expected=oracle.reference('ln',x)
        got=machine.call('ln_refine',x)[0]
        assert got==expected,(hex(x),hex(got),hex(expected))
        digest.update(struct.pack('<3Q',x,got,expected))
    report=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        mpfr=oracle.version,cases=len(values),wrong_rounding=0,sha256=digest.hexdigest(),
        scope='Direct forced refinement at every log segment/center over exponent limits, near-one boundaries, random values and the former CORE-MATH case.',
        abi='Every call verifies R4-R11, SP and bounded stack writes.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
