#!/usr/bin/env python3
"""Bound actual tiny/Q70 sine center values using directed MPFR arithmetic."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import random
import struct

from m0_mpfr_oracle import Oracle,_Number
from native_eabi_m0_arm_self_test import Machine


class SineOracle:
    def __init__(self):
        self.oracle=Oracle();self.lib=self.oracle.lib;pointer=C.POINTER(_Number)
        assert C.sizeof(C.c_ulong)==8,'This host oracle requires64bit unsigned long'
        self.lib.mpfr_set_str.argtypes=[pointer,C.c_char_p,C.c_int,C.c_int];self.lib.mpfr_set_str.restype=C.c_int
        self.lib.mpfr_mul_2si.argtypes=[pointer,pointer,C.c_long,C.c_int]
        self.lib.mpfr_sub_ui.argtypes=[pointer,pointer,C.c_ulong,C.c_int]
        self.values=[_Number() for _ in range(3)]
        for value in self.values:self.lib.mpfr_init2(C.byref(value),192)

    def error_bound(self,q,e,actual):
        x,lo,hi=self.values
        assert self.lib.mpfr_set_str(C.byref(x),str(q).encode(),10,0)==0
        assert self.lib.mpfr_mul_2si(C.byref(x),C.byref(x),e-63,0)==0
        for output,direction in [(lo,3),(hi,2)]:
            self.lib.mpfr_sin(C.byref(output),C.byref(x),direction)
            self.lib.mpfr_mul_2si(C.byref(output),C.byref(output),63-e,direction)
            self.lib.mpfr_sub_ui(C.byref(output),C.byref(output),actual,direction)
        return max(abs(self.lib.mpfr_get_d(C.byref(lo),3)),abs(self.lib.mpfr_get_d(C.byref(hi),2)))

    def close(self):
        for value in self.values:self.lib.mpfr_clear(C.byref(value))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True);p.add_argument('--samples',type=int,default=30000)
    p.add_argument('--json',type=Path,required=True);a=p.parse_args();assert a.samples>=0
    digest_elf=hashlib.sha256(a.elf.read_bytes()).hexdigest();machine=Machine(a.elf,True)
    oracle=SineOracle();rng=random.Random(0x73696e37);digest=hashlib.sha256();groups={}
    tiny=[((top<<48)|low,e) for e in range(-30,-26) for top in range(1<<14,1<<15) for low in (0,(1<<48)-1)]
    tiny += [(1<<63,e) for e in range(-30,-26)]
    normal=[((1<<62)|rng.getrandbits(62),rng.randrange(-26,-5)) for _ in range(a.samples)]
    for e in range(-26,-5):
        for high in (1<<30,(1<<30)+1,0x5AAAAAAA,(1<<31)-2,(1<<31)-1):
            for low in (0,1,0x3FFFFFF,0x4000000,0x7FFFFFFF,0xFFFFFFFE,0xFFFFFFFF):normal.append(((high<<32)|low,e))
    for label,symbol,values in [('tiny','checked_trig_sin_tiny',tiny),('q70','checked_trig_sin70',normal)]:
        assert symbol in machine.elf.symbols;largest=0.
        for q,e in values:
            actual=machine.call(symbol,q,e&0xFFFFFFFF)[0]
            assert 0<actual<=q,(label,hex(q),e,hex(actual))
            bound=oracle.error_bound(q,e,actual)
            assert bound<1,(label,hex(q),e,hex(actual),bound)
            largest=max(largest,bound);digest.update(struct.pack('<QiQ',q,e,actual))
        pending=struct.pack('<7I',17,3,17,3,5,2,3);dirty=0
        for q,e in values[::max(1,len(values)//32)]:
            machine.uc.mem_write(0xD0000060,pending);machine.call(symbol,q,e&0xFFFFFFFF)
            assert bytes(machine.uc.mem_read(0xD0000060,len(pending)))==pending;dirty+=1
        groups[label]=dict(cases=len(values),maximum_directed_error_Q63=largest,
            dirty_sio_checks=dirty,sample_instructions=machine.call(symbol,values[-1][0],values[-1][1]&0xFFFFFFFF,count=True)[2])
        print(label,groups[label],flush=True)
    oracle.close();assert digest_elf==hashlib.sha256(a.elf.read_bytes()).hexdigest()
    report=dict(status='PASS',elf_sha256=digest_elf,actual_arm_calls=machine.calls,operations=groups,
        mpfr=oracle.oracle.version,mpfr_precision=192,result_sha256=digest.hexdigest(),
        oracle='Exact63bit dyadic input; directed MPFR sine, normalized back to relativeQ63 and subtracting the actual ARM integer before conversion to a small host error bound.',
        tiny_coverage='Every top16bit bucket at both low48bit endpoints, all four supported exponents, plus q=2^63. The source correction depends only on the top16bits; its exact residual is monotone inside each bucket.',
        scope='Actual center-value tests complement the rational error proof. The Q70 kernel corpus is finite; final argument uncertainty and public RNE packing require separate checks.')
    a.json.parent.mkdir(parents=True,exist_ok=True);a.json.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
