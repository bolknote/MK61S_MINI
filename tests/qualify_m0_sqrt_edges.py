#!/usr/bin/env python3
"""Check actual M0 sqrt at table/seed transitions and rounding midpoints."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import struct

from m0_mpfr_oracle import Oracle
from native_eabi_m0_arm_self_test import Machine,bits


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=20000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    rng=random.Random(0x5A7E2026);cases=set()
    def neighbors(value,radius):
        cases.update(range(max(0,value-radius),value+radius+1))
    for exponent in (1,2,1022,1023,1024,2045,2046):
        for cell in range(257):
            neighbors((exponent<<52)+(cell<<44),4)
    # The Q20 seed coordinate changes halfway through a 2^24-bit-pattern
    # block. Include both cells where the root/inverse seed is largest.
    positions=[0,1,2,(1<<19)-1,1<<19,(1<<20)-2,(1<<20)-1]
    positions += [rng.randrange(1<<20) for _ in range(args.samples//8)]
    for exponent,cell in ((1023,0),(1024,255)):
        for position in positions:
            neighbors((exponent<<52)+(cell<<44)+(position<<24)+(1<<23),2)
    # Square an exact binary64 rounding midpoint, then test the nearest
    # input and its neighbors. Neither sqrt nor floating multiplication
    # is used to construct the midpoint square.
    mantissas=[1<<52,(1<<52)+1,(1<<53)-2,(1<<53)-1]
    mantissas += [(1<<52)|rng.getrandbits(52) for _ in range(args.samples)]
    for mantissa in mantissas:
        midpoint=Fraction(2*mantissa+1,1<<53)
        neighbors(bits(float(midpoint*midpoint)),2)
    machine=Machine(args.elf,True);oracle=Oracle();digest=hashlib.sha256()
    elf_sha=hashlib.sha256(args.elf.read_bytes()).hexdigest()
    for value in sorted(cases):
        expected=oracle.reference('sqrt',value)
        actual=machine.call('mk61_m0_sqrt',value)[0]
        assert actual==expected,(hex(value),hex(actual),hex(expected))
        digest.update(struct.pack('<3Q',value,expected,actual))
    assert elf_sha==hashlib.sha256(args.elf.read_bytes()).hexdigest()
    report=dict(status='PASS',elf_sha256=elf_sha,mpfr=oracle.version,cases=len(cases),
        wrong_rounding=0,sha256=digest.hexdigest(),
        scope='Table boundaries, Q20 seed transitions, and exact squared rounding midpoints; every ARM call checks R4-R11/SP and bounded writes.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
