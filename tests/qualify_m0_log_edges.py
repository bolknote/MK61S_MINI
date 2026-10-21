#!/usr/bin/env python3
"""Check ARM ln at every segment, center and near-one dispatch boundary."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from m0_mpfr_oracle import Oracle, bits
from native_eabi_m0_arm_self_test import Machine


def corpus():
    values={0x3FEF800A2C5E00BA}  # A clamped negative cell has a 49-bit distance.
    for exponent in (1,2,1022,1023,1024,2045,2046):
        for j in range(2049):
            b=(exponent<<52)+(j<<41)
            values.update(x for x in (b-1,b,b+1) if 0<x<0x7ff0000000000000)
    for n in range(258):
        for sign in (-1,1):
            b=bits(1+sign*n/16384)
            values.update(range(b-4,b+5))
    for b in (0x3FEF800000000000,0x3FF0400000000000,0x3FF0000000000000):
        values.update(range(b-128,b+129))
    return sorted(values)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();machine=Machine(args.elf,True);oracle=Oracle()
    digest=hashlib.sha256();inputs=corpus()
    for value in inputs:
        expected=oracle.reference('ln',value)
        got=machine.call('_ZN12compact_math2lnEd',value)[0]
        assert got==expected,(hex(value),hex(got),hex(expected))
        digest.update(struct.pack('<3Q',value,got,expected))
    report=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        mpfr=oracle.version,cases=len(inputs),wrong_rounding=0,sha256=digest.hexdigest(),
        scope='All 1024 normalized segment boundaries and centers across exponent limits; near-one table centers, midpoints and dispatch endpoints; clamped-cell regression.',
        abi='Every call verifies R4-R11, SP and bounded stack writes.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
