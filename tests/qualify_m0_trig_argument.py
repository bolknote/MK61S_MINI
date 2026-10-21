#!/usr/bin/env python3
"""Check the actual M0 Q70 trig argument enclosure with rational pi bounds."""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine,bits,real


def pi_interval():
    def atan(q,n):
        value=sum((F((-1)**i,(2*i+1)*q**(2*i+1)) for i in range(n)),F(0))
        return value,value+F(1,(2*n+1)*q**(2*n+1))
    a,b=atan(5,80);c,d=atan(239,24)
    return 8*a-2*d,8*b-2*c  # pi/2, Machin identity


def corpus(samples):
    rng=random.Random(0x70622191)
    values=[bits(rng.uniform(1/64,2.**20)) for _ in range(samples)]
    values += [bits(rng.uniform(1/64,math.pi/4)) for _ in range(samples//4)]
    for n in (0,1,2,63,1024,65535,524287):
        for j in (16,17,128,512,803,804):
            for sign in (-1,1):
                x=n*math.pi/2+sign*(j+.5)/1024
                if x<1/64:continue
                b=bits(x)
                values += range(b-2,b+3)
    for n in range(1,667545,4093):
        b=bits(n*math.pi/2)
        values += range(b-4,b+5)
    for x in (1/64,math.pi/4,2.**20):
        b=bits(x);values += range(b-8,b+9)
    for n in (0,1,2,3,63,1024,65535,524287,667543):
        for e in range(-31,-5):
            for factor in (1.,1.5,2.-2.**-20):
                for sign in (-1,1):
                    x=n*math.pi/2+sign*math.ldexp(factor,e)
                    if x<=0:continue
                    b=bits(x);values+=range(max(0,b-2),b+3)
    return sorted({b for b in values if bits(2.**-27)<=b<bits(2.**20)})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--samples',type=int,default=10000)
    p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();pointer=0x20008000
    class ArgumentMachine(Machine):
        def write(self,uc,access,address,size,value,user):
            if pointer<=address and address+size<=pointer+24:return
            return super().write(uc,access,address,size,value,user)
    m=ArgumentMachine(a.elf,True);lo,hi=pi_interval()
    assert hi-lo<F(1,1<<350)
    digest=hashlib.sha256();normal=direct=small=negative=0;largest=F(0);tails=set()
    small_checked=0;small_largest=F(0)
    for b in corpus(a.samples):
        m.uc.mem_write(pointer,b'\xA5'*24)
        m.call('checked_trig_argument',b,pointer)
        raw=bytes(m.uc.mem_read(pointer,24));q,e,n,error,sign,tail=struct.unpack('<QiIIBxh',raw)
        if e!=1:
            small+=1
            if -30<=e<=-6:
                assert (1<<62)<=q<=(1<<63) and error in (0,1)
                x=F(real(b));lower,upper=(n*lo-x,n*hi-x) if sign else (x-n*hi,x-n*lo)
                assert lower>=0
                distance=max(abs(q-lower*(1<<(63-e))),abs(q-upper*(1<<(63-e))))
                assert distance<1 if error else distance==0,('relativeQ63 enclosure',hex(b),q,e,n,error,sign,float(distance))
                small_checked+=1;small_largest=max(small_largest,distance)
                digest.update(struct.pack('<Q',b)+raw)
            continue
        assert error in (0,1) and sign in (0,1) and -128<=tail<=128
        x=F(real(b));lower,upper=(n*lo-x,n*hi-x) if sign else (x-n*hi,x-n*lo)
        # The truncated quotient estimate can select the neighbouring
        # quadrant just beyond pi/4; both kernels certify |r| <0.787.
        assert lower>=0 and upper<F(787,1000),(hex(b),'range',n,sign)
        assert (q+(1<<51))>>52<806,(hex(b),'table index')
        value=(q<<8)+tail
        distance=max(abs(value-lower*(1<<70)),abs(value-upper*(1<<70)))
        if error:assert distance<1,(hex(b),'enclosure',float(distance),n,sign,tail)
        else:assert distance==0 and n==0 and tail==0,(hex(b),'direct',n,tail)
        normal+=1;direct+=not error;negative+=sign;tails.add(tail);largest=max(largest,distance)
        digest.update(struct.pack('<Q',b)+raw)
    result=dict(status='PASS',elf_sha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        actual_arm_calls=m.calls,ordinary_q70_cases=normal,direct_exact=direct,
        negative_remainders=negative,small_other_paths=small,tail_values=len(tails),
        eligible_small_q63_cases=small_checked,largest_small_error_q63=float(small_largest),
        small_exponent_range=[-30,-6],
        largest_error_q70=float(largest),bound_q70=1,
        oracle='Exact rational Machin pi/2 enclosure narrower than 2^-350; binary64 inputs are exact fractions.',
        abi='R4-R11/SP preserved; writes restricted to stack, SIO, and 24-byte result object.',
        sha256=digest.hexdigest(),scope='Finite ordinaryQ70 and eligible small-relativeQ63 argument corpus, independent of the firmware pi constants.')
    a.json.parent.mkdir(parents=True,exist_ok=True);a.json.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
