#!/usr/bin/env python3
"""Check ARM asin/acos around reductions, endpoints and inverse midpoints."""
import argparse
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import random
import struct

from m0_mpfr_oracle import Oracle, _Number, bits, real
from native_eabi_m0_arm_self_test import Machine, SP, nan
from unicorn import UC_HOOK_CODE

SIGN=1<<63
ONE=bits(1.)


def inverse_midpoint(oracle,name,angle):
    lib=oracle.lib;pointer=C.POINTER(_Number)
    lib.mpfr_add.argtypes=[pointer,pointer,pointer,C.c_int]
    lib.mpfr_div_2ui.argtypes=[pointer,pointer,C.c_ulong,C.c_int]
    a,b,mid,result=(_Number() for _ in range(4))
    for number in (a,b,mid,result):lib.mpfr_init2(C.byref(number),256)
    try:
        lib.mpfr_set_d(C.byref(a),real(angle),0)
        lib.mpfr_set_d(C.byref(b),real(angle+1),0)
        lib.mpfr_add(C.byref(mid),C.byref(a),C.byref(b),0)
        lib.mpfr_div_2ui(C.byref(mid),C.byref(mid),1,0)
        function=lib.mpfr_sin if name=='asin' else lib.mpfr_cos
        endpoints=[]
        for direction in (3,2):
            function(C.byref(result),C.byref(mid),direction)
            endpoints.append(bits(lib.mpfr_get_d(C.byref(result),direction)))
        return endpoints
    finally:
        for number in (a,b,mid,result):lib.mpfr_clear(C.byref(number))


def corpus(oracle,name,samples):
    values={0,SIGN,1,SIGN|1,ONE,SIGN|ONE}
    def nearby(center,radius=8):
        values.update(v for v in range(max(0,center-radius),center+radius+1)
                      if (v&~SIGN)<=ONE)
    for x in (2.**-56,2.**-32,2.**-27,1/64,math.sqrt(.5),math.sqrt(.75)):
        nearby(bits(x),64)
    for j in range(1,65):
        nearby(bits(j/math.sqrt(4096+j*j)),16)
        nearby(bits(64/math.sqrt(4096+j*j)),16)
    for k in range(1,54):nearby(ONE-(1<<k),32)
    rng=random.Random(0xA51C0000+len(name))
    limit=math.pi/2 if name=='asin' else math.pi
    angles=[bits(rng.uniform(1/128,limit)) for _ in range(samples)]
    angles += [bits(2.**e) for e in range(-70,1)]
    angles += [bits(limit*j/1024) for j in range(1,1024)]
    for angle in angles:
        for center in inverse_midpoint(oracle,name,angle):nearby(center,2)
    values.update(v^SIGN for v in list(values))
    return sorted(values)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--samples',type=int,default=5000)
    p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();assert a.samples>=0
    sha=hashlib.sha256(a.elf.read_bytes()).hexdigest()
    m=Machine(a.elf,True,stack_bytes=16384);oracle=Oracle();reports={}
    for name in ('asin','acos'):
        fallback=[0]
        def entered(*unused):fallback[0]+=1
        address=m.elf.symbols['mk61_m0_cr_'+name]&~1
        hook=m.uc.hook_add(UC_HOOK_CODE,entered,begin=address,end=address)
        values=corpus(oracle,name,a.samples);digest=hashlib.sha256()
        try:
            for x in values:
                expected=oracle.reference(name,x)
                got=m.call('_ZN12compact_math4'+name+'Ed',x)[0]
                assert got==expected or (nan(got) and nan(expected)),(name,hex(x),hex(got),hex(expected))
                digest.update(struct.pack('<QQQ',x,got,expected))
        finally:m.uc.hook_del(hook)
        reports[name]=dict(status='PASS',cases=len(values),wrong_rounding=0,
            core_fallback_calls=fallback[0],corpus_sha256=digest.hexdigest())
        print(name,reports[name],flush=True)
    # Pending hardware-divider state must survive both new geometry paths.
    state=struct.pack('<7I',17,3,0,0,5,2,3)
    for name in ('asin','acos'):
        for x in (.1,.7,math.nextafter(1.,0.),-.99,1/128):
            m.uc.mem_write(0xD0000060,state)
            m.floating('_ZN12compact_math4'+name+'Ed',bits(x),0,oracle.reference(name,bits(x)))
            assert bytes(m.uc.mem_read(0xD0000060,len(state)))==state
    assert sha==hashlib.sha256(a.elf.read_bytes()).hexdigest()
    report=dict(status='PASS',elf_sha256=sha,mpfr=oracle.version,operations=reports,
        maximum_stack_bytes=SP-m.stack_lowest,pending_divider_state_checks=10,
        oracle='Directed MPFR bounds; inverse output midpoints bracketed by directed MPFR sin/cos. Reduction/normalization/endpoint neighborhoods included.',
        scope='Finite ARM input corpus. Complete rounding intervals are certified separately.')
    a.json.parent.mkdir(parents=True,exist_ok=True)
    a.json.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
