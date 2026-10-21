#!/usr/bin/env python3
"""Check the ARM bounded Q62 product against independent exact integers."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--samples',type=int,default=100000)
    p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();m=Machine(a.elf,True);rng=random.Random(0x62320)
    mask=(1<<64)-1;low=(1<<32)-1
    edges={0,mask,0xFFFF0000FFFF0000,0x0000FFFF0000FFFF,0xFFFFFFFF00000001}
    for k in range(64):edges.update(v for v in ((1<<k)-1,1<<k,(1<<k)+1) if v<=mask)
    inputs=[(x,y) for x in sorted(edges) for y in sorted(edges)]
    inputs += [(rng.getrandbits(64),rng.getrandbits(64)) for _ in range(a.samples)]
    inputs += [(rng.randrange(1<<62,((1<<62)*203)//100),rng.getrandbits(59)) for _ in range(a.samples//4)]
    digest=hashlib.sha256();largest=0
    for x,y in inputs:
        unshortened=(x*y-(x&low)*(y&low)-
                     ((x&0xFFFF)*((y>>32)&0xFFFF)+((x>>32)&0xFFFF)*(y&0xFFFF))*(1<<32))
        q,r=divmod(unshortened,1<<62)
        expected=q+6+(r>=(1<<61))
        error=abs((expected<<62)-x*y)
        assert error<=13*(1<<61),(hex(x),hex(y),'error bound')
        largest=max(largest,error)
        got=m.call('mk61_m0_product62',x,y)[0]
        assert got==(expected&mask),(hex(x),hex(y),hex(got),hex(expected&mask))
        digest.update(struct.pack('<3Q',x,y,got))
    # The upper bound is attained: (2^32 * 2^29) / 2^62 is exactly 1/2,
    # while the bounded product returns 7. Keep <=6.5, not a strict bound.
    assert largest==13*(1<<61)
    samples=[(1,1),(1<<32,1<<29),((1<<63)-1,(1<<63)-1),(0,mask)]
    counts=[dict(a=f'{x:016X}',b=f'{y:016X}',instructions=m.call('mk61_m0_product62',x,y,count=True)[2]) for x,y in samples]
    report=dict(status='PASS',elf_sha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        actual_arm_calls=m.calls,checked_products=len(inputs),maximum_absolute_error_q62=6.5,
        arithmetic='Exact Python integers; omitted low32 product and 16-bit pairs 02/20, compensated Q62 truncation. Comparison includes unsigned result wrap.',
        abi='Every call verifies R4-R11, SP and bounded stack writes.',sample_instructions=counts,sha256=digest.hexdigest())
    a.json.parent.mkdir(parents=True,exist_ok=True);a.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
