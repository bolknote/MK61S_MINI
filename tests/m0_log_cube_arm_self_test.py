#!/usr/bin/env python3
"""Check the direct Q70 logarithm product against exact integer arithmetic."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine


def edges(width):
    limit=(1<<width)-1;values={0,limit}
    for n in range(width):
        values.update(x for x in ((1<<n)-1,1<<n,(1<<n)+1) if x<=limit)
    return sorted(values)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=100000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();machine=Machine(args.elf,True);rng=random.Random(0x1070)
    inputs=[(x,y) for x in edges(64) for y in edges(48)]
    inputs += [(rng.getrandbits(64),rng.getrandbits(48)) for _ in range(args.samples)]
    largest=Fraction(0);digest=hashlib.sha256()
    for x,y in inputs:
        result=machine.call('mk61_m0_log_cube70',x,y)[0]
        error=Fraction(abs((result<<70)-x*y),1<<70)
        assert error<Fraction(35,64),(hex(x),hex(y),hex(result),str(error))
        largest=max(largest,error);digest.update(struct.pack('<3Q',x,y,result))
    instructions=machine.call('mk61_m0_log_cube70',(1<<59)-1,(1<<48)-1,count=True)[2]
    report=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        checked_products=len(inputs),maximum_observed_error=str(largest),
        certified_error_bound='35/64',instructions=instructions,sha256=digest.hexdigest(),
        arithmetic='Exact Python integer product, powers of two, limb boundaries and random operands across the full stated input ranges.',
        abi='Every call verifies R4-R11, SP and bounded stack writes.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
