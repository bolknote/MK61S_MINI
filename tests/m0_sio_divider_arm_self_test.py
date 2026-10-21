#!/usr/bin/env python3
"""Exercise actual SDK signed/unsigned wrappers and SIO context restoration."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine, signed


def reference(n,d,signed_mode):
    if signed_mode:
        n,d=signed(n,32),signed(d,32)
        if not d:return (0x80000000 if n<0 else 0x7FFFFFFF if n else 0),0
        q=abs(n)//abs(d)
        if (n<0)!=(d<0):q=-q
        return q&0xFFFFFFFF,(n-q*d)&0xFFFFFFFF
    if not d:return (0xFFFFFFFF if n else 0),0
    return n//d,n%d


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=10000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();assert args.samples>=0
    m=Machine(args.elf,True)
    edges=[0,1,2,3,15,16,17,0x3FFFFFFF,0x40000000,0x7FFFFFFE,0x7FFFFFFF,
           0x80000000,0x80000001,0x80000002,0xFFFFFFFD,0xFFFFFFFE,0xFFFFFFFF]
    inputs=[(n,d) for n in edges for d in edges]
    rng=random.Random(0x73646976)
    inputs += [(rng.getrandbits(32),rng.getrandbits(32)) for _ in range(args.samples)]
    states=[None,struct.pack('<7I',17,3,17,3,5,2,3),
            struct.pack('<7I',0xFFFFFFEF,3,0xFFFFFFEF,3,0xFFFFFFFB,0xFFFFFFFE,3)]
    digest=hashlib.sha256()
    for signed_mode,symbol in [(False,'__wrap___aeabi_uidivmod'),(True,'__wrap___aeabi_idivmod')]:
        assert symbol in m.elf.symbols
        for state in states:
            for n,d in inputs:
                if state is None:m.uc.mem_write(0xD0000078,struct.pack('<I',1))
                else:m.uc.mem_write(0xD0000060,state)
                got=m.call(symbol,n,d,width=32)[0]
                q,r=reference(n,d,signed_mode)
                assert got==(q|(r<<32)),(symbol,hex(n),hex(d),hex(got),hex(q|(r<<32)))
                if state is not None:
                    assert bytes(m.uc.mem_read(0xD0000060,len(state)))==state,('SDK pending context changed',symbol)
                else:
                    a,b,sa,sb=struct.unpack('<4I',m.uc.mem_read(0xD0000060,16))
                    assert (a,b)==(sa,sb)==(n,d),('SIO aliases',symbol,n,d)
                digest.update(struct.pack('<4I',n,d,q,r))
    report=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        actual_arm_calls=m.calls,input_pairs=len(inputs),wrappers=2,contexts=len(states),
        wrong_results=0,context_mismatches=0,alias_mismatches=0,result_sha256=digest.hexdigest(),
        coverage='Signed truncation/remainder,INT_MIN/-1 modulo result, AEABI divide-by-zero saturation, U/S alias coherence, and positive/negative dirty contexts restored by actual SDK instructions.',
        scope='Functional SIO peripheral model plus actual SDK wrapper code; not an interrupt-injection or hardware latency test.')
    args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
