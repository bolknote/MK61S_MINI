#!/usr/bin/env python3
"""Check logarithm residual products against independent exact integers."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine


def edges(width):
    limit=(1<<width)-1
    values={0,limit}
    for n in range(width):
        values.update(x for x in ((1<<n)-1,1<<n,(1<<n)+1) if x<=limit)
    return sorted(values)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=100000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    machine=Machine(args.elf,True);rng=random.Random(0x104654)
    digest=hashlib.sha256();groups=[]
    for width,shift,bias in ((41,46,4),(48,54,0)):
        symbol=f'mk61_m0_log_product{shift}'
        xs=edges(width)+[1<<width]
        inputs=[(x,y) for x in xs for y in edges(64)]
        inputs += [(rng.randrange((1<<width)+1),rng.getrandbits(64))
                   for _ in range(args.samples)]
        largest=Fraction(0);count=0
        bound=Fraction(9,2)+Fraction(1,1<<14) if shift==46 else Fraction(17,32)+Fraction(1,1<<22)
        for x,y in inputs:
            omitted=(x&0xffff)*(y&0xffff)+(
                (x&0xffff)*((y>>16)&0xffff)+((x>>16)&0xffff)*(y&0xffff))*(1<<16)
            retained=x*y-omitted
            expected=(retained+(1<<(shift-1)))//(1<<shift)+bias
            assert 0<=expected<1<<64
            error=Fraction(abs((expected<<shift)-x*y),1<<shift)
            assert error<bound,(symbol,hex(x),hex(y),str(error))
            got=machine.call(symbol,x,y)[0]
            assert got==expected,(symbol,hex(x),hex(y),hex(got),hex(expected))
            largest=max(largest,error);count+=1
            digest.update(struct.pack('<3Q',x,y,got))
        instructions=machine.call(symbol,(1<<width)-1,(1<<64)-1,count=True)[2]
        groups.append(dict(symbol=symbol,cases=count,maximum_observed_error=str(largest),
                           certified_error_bound=str(bound),instructions=instructions))
    report=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        actual_arm_calls=machine.calls,groups=groups,sha256=digest.hexdigest(),
        arithmetic='Exact Python integer multiplication and rational error; powers of two, limb boundaries and random residuals.',
        abi='Every call verifies R4-R11, SP and bounded stack writes.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
