#!/usr/bin/env python3
"""Check bounded atan reciprocal/quotient ARM results with exact integers."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=100000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();machine=Machine(args.elf,True);rng=random.Random(0xA7A620)
    denominators=[]
    for top in range(32768,65536):
        denominators.extend((top<<48,((top+1)<<48)-1))
    denominators += [(1<<63)|rng.getrandbits(63) for _ in range(args.samples)]
    maximum=Fraction(0);qmaximum=Fraction(0);digest=hashlib.sha256()
    for d in denominators:
        got=machine.call('atan_fast_reciprocal',d)[0]
        error=Fraction(abs(got*d-(1<<126)),d)
        assert error<13,(hex(d),hex(got),str(error))
        maximum=max(maximum,error)
        n=rng.randrange(d//2+1)
        quotient=machine.call('atan_fast_ratio',n,d)[0]
        qerror=Fraction(abs(quotient*d-(n<<64)),d)
        assert qerror<33,(hex(d),hex(n),str(qerror))
        qmaximum=max(qmaximum,qerror)
        digest.update(struct.pack('<4Q',d,got,n,quotient))
    for width in range(1,65):
        for d in ((1<<(width-1)),(1<<width)-1):
            for n in (0,d//4,d//2):
                got=machine.call('atan_fast_ratio',n,d)[0]
                assert Fraction(abs(got*d-(n<<64)),d)<33
    counts={name:machine.call(name,*args_,count=True)[2] for name,args_ in
            (('atan_fast_reciprocal',(0xD432123456789ABC,)),
             ('atan_fast_ratio',(0x1432123456789ABC,0xD432123456789ABC)))}
    result=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        normalized_denominators=len(denominators),actual_arm_calls=machine.calls,
        maximum_reciprocal_error=str(maximum),maximum_quotient_error=str(qmaximum),
        sample_instructions=counts,sha256=digest.hexdigest(),
        scope='Exact integer/rational reference, all 16-bit seed bucket endpoints, random denominators, variable normalization widths.',
        abi='Every call verifies R4-R11, SP and bounded stack writes.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
