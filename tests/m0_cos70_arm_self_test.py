#!/usr/bin/env python3
"""Check actual Q70 cosine decisions against MPFR argument enclosures."""
import argparse
from collections import Counter
import ctypes as C
import hashlib
import json
from pathlib import Path
import random
import struct

from m0_mpfr_oracle import Oracle,_Number,bits
from native_eabi_m0_arm_self_test import Machine


class CosOracle:
    def __init__(self):
        self.oracle=Oracle();self.lib=self.oracle.lib;pointer=C.POINTER(_Number)
        self.lib.mpfr_set_str.argtypes=[pointer,C.c_char_p,C.c_int,C.c_int]
        self.lib.mpfr_set_str.restype=C.c_int
        self.lib.mpfr_mul_2si.argtypes=[pointer,pointer,C.c_long,C.c_int]
        self.lib.mpfr_get_ui.argtypes=[pointer,C.c_int];self.lib.mpfr_get_ui.restype=C.c_ulong
        assert C.sizeof(C.c_ulong)==8,'This host oracle requires64bit unsigned long'
        self.numbers=[_Number() for _ in range(6)]
        for number in self.numbers:self.lib.mpfr_init2(C.byref(number),192)

    def exact(self,number,coefficient,shift):
        assert self.lib.mpfr_set_str(C.byref(number),str(coefficient).encode(),10,0)==0
        assert self.lib.mpfr_mul_2si(C.byref(number),C.byref(number),shift,0)==0

    def bounds(self,q,e,error):
        lo,hi,lower,upper,*_=self.numbers
        self.exact(lo,q-error,e-63);self.exact(hi,q+error,e-63)
        self.lib.mpfr_cos(C.byref(lower),C.byref(hi),3)
        self.lib.mpfr_cos(C.byref(upper),C.byref(lo),2)
        return bits(self.lib.mpfr_get_d(C.byref(lower),0)),bits(self.lib.mpfr_get_d(C.byref(upper),0))

    def boundary_q(self,index,e):
        midpoint,angle=self.numbers[4:]
        self.exact(midpoint,(1<<54)-(2*index+1),-54)
        self.lib.mpfr_acos(C.byref(angle),C.byref(midpoint),0)
        self.lib.mpfr_mul_2si(C.byref(angle),C.byref(angle),63-e,0)
        return self.lib.mpfr_get_ui(C.byref(angle),0)

    def close(self):
        for number in self.numbers:self.lib.mpfr_clear(C.byref(number))


def corpus(oracle,samples):
    rng=random.Random(0x636f7337);values=set();midpoints=0
    def add(q,e):
        if (1<<62)<=q<(1<<63):values.add((q,e))
    for e in range(-26,-5):
        for high in (1<<30,(1<<30)+1,0x5AAAAAAA,(1<<31)-2,(1<<31)-1):
            for low in (0,1,2,0x3FFFFFF,0x4000000,0x7FFFFFFF,0xFFFFFFFE,0xFFFFFFFF):
                add((high<<32)|low,e)
        maximum=max(1,1<<(2*e+52));minimum=maximum//4
        for _ in range(24):
            index=rng.randrange(minimum,maximum)
            q=oracle.boundary_q(index,e)
            if not (1<<62)<=q<(1<<63):continue
            midpoints+=1;step=1<<max(0,-2*e-7)
            for multiplier in (-32,-16,-8,-5,-4,-3,-2,-1,0,1,2,3,4,5,8,16,32):
                for delta in (-1,0,1):add(q+multiplier*step+delta,e)
    for _ in range(samples):add((1<<62)|rng.getrandbits(62),rng.randrange(-26,-5))
    return sorted(values),midpoints


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=30000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();assert args.samples>=0
    oracle=CosOracle();m=Machine(args.elf,True);symbol='checked_trig_cos70'
    assert symbol in m.elf.symbols
    for e in (-26,-16,-6):
        reference=oracle.oracle.reference('cos',bits(2.**(e-1)))
        assert oracle.bounds(1<<62,e,0)==(reference,reference)
    values,midpoints=corpus(oracle,args.samples);counts=Counter();digest=hashlib.sha256()
    for q,e in values:
        for error in (0,1):
            lo,hi=oracle.bounds(q,e,error)
            for sign in (0,1<<63):
                result=m.call(symbol,q,(error<<32)|(e&0xFFFFFFFF),c=sign)[0]
                if result:
                    assert lo==hi and result==(lo|sign),('Q70 decision',hex(q),e,error,hex(sign),hex(result),hex(lo),hex(hi))
                    counts['accepted']+=1
                else:counts['guard_rejected']+=1
                digest.update(struct.pack('<QiI3Q',q,e,error,sign,result,lo))
    for q,e,error in [(0,-6,0),((1<<62)-1,-6,0),(1<<63,-6,0),
                      (1<<62,-27,0),(1<<62,-5,0),(1<<62,-6,2),
                      (1<<62,-(1<<31),0),(1<<62,(1<<31)-1,0)]:
        assert m.call(symbol,q,(error<<32)|(e&0xFFFFFFFF),c=0)[0]==0
        counts['domain_rejected']+=1
    pending=struct.pack('<7I',17,3,17,3,5,2,3)
    for q,e in values[::max(1,len(values)//32)]:
        m.uc.mem_write(0xD0000060,pending)
        m.call(symbol,q,(1<<32)|(e&0xFFFFFFFF),c=0)
        assert bytes(m.uc.mem_read(0xD0000060,len(pending)))==pending
        counts['dirty_sio']+=1
    assert counts['accepted'] and counts['guard_rejected']
    sample_counts=[dict(q=f'{q:016X}',e=e,instructions=m.call(symbol,q,e&0xFFFFFFFF,c=0,count=True)[2])
                   for q,e in [(1<<62,-26),(0x6AB74D893E1057C2,-6),((1<<63)-1,-6)]]
    oracle.close()
    report=dict(status='PASS',elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        argument_pairs=len(values),actual_arm_calls=m.calls,counts=dict(counts),wrong_rounding=0,
        midpoint_targets=midpoints,mpfr=oracle.oracle.version,mpfr_precision=192,
        sample_instructions=sample_counts,result_sha256=digest.hexdigest(),
        scope='Exact63bit dyadic inputs with0/1relativeQ63 argument uncertainty, both result signs. Directed MPFR cos at both interval endpoints must round identically for every accepted ARM result. Includes targeted RNE midpoint neighbourhoods, limb/exponent boundaries, invalid domains and random normalized inputs. Finite qualification complements the rational error certificate.')
    args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
