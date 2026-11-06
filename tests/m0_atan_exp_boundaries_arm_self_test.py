#!/usr/bin/env python3
"""MPFR checks at exp cells and atan dispatch edges, including interrupted SIO."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

from native_eabi_m0_arm_self_test import Machine,nan,bits
from m0_mpfr_oracle import Oracle
from profile_m0_math import qualify_corpus


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--bootrom',type=Path,help='Execute the captured SDK ROM bit/memory helpers')
    p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();machine=Machine(a.elf,True,stack_bytes=16384,instruction_budget=20000000,bootrom=a.bootrom)
    oracle=Oracle();start=time.monotonic();digest=hashlib.sha256();calls=contexts=0
    atan=set()
    for x in (2.**-27,1/64,1.,64.,128.,2.**55):
        for v in range(bits(x)-16,bits(x)+17):atan.update((v,v|(1<<63)))
    exp=set(qualify_corpus(0)['exp'])
    # Every input-scaling shift, including the zero and32-bit crossings.
    # Independent MPFR results catch wrong cross-word bits and rounding.
    fractions=(0,1,(1<<51)-1,1<<51,(1<<52)-2,(1<<52)-1,
               0x5555555555555,0xAAAAAAAAAAAAA)
    for exponent in range(-54,10):
        for fraction in fractions:
            x=((exponent+1023)<<52)|fraction
            exp.update((x,x|(1<<63)))
    for x in (0xC005754B8935C420,0x401E87A0AD6AC178,0x402508BEB1BC03C0,
              0x40687013D4330FC8,0xC07F9FF4814E19C2):
        exp.update(range(x-16,x+17))
    groups=dict(exp=sorted(exp),atan=sorted(atan))
    for op,values in groups.items():
        for i,x in enumerate(values):
            assert time.monotonic()-start<300
            expected=oracle.reference(op,x)
            states=[(0,0,0,0,0,0,1)]
            if i%127==0:states += [(17,3,17,3,5,2,3),(0x80000001,7,0x80000001,7,0x11223344,0x55667788,2)]
            for words in states:
                before=struct.pack('<7I',*words);machine.uc.mem_write(0xd0000060,before)
                got=machine.call('_ZN12compact_math'+str(len(op))+op+'Ed',x)[0]
                assert (nan(got) and bool(got&(1<<51))) if nan(expected) else got==expected,(op,hex(x),hex(got),hex(expected))
                if words[-1]!=1:
                    assert bytes(machine.uc.mem_read(0xd0000060,28))==before
                    contexts+=1
                calls+=1;digest.update(struct.pack('<3QI',x,expected,got,words[-1]))
    report=dict(status='PASS_MPFR_ATAN_EXP_BOUNDARIES_AND_SIO',input_cases={op:len(values) for op,values in groups.items()},
        actual_ARM_calls=calls,DIRTY_PENDING_checks=contexts,wrong_rounding=0,MPFR_version=oracle.version,
        records_sha256=digest.hexdigest(),elf_sha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        elapsed_seconds=time.monotonic()-start,hardware_IO=0,pow_calls=0,
        scope='All512 exp cells at centers/half cells and reduction exponents, all exp input-scaling shifts with mantissa carry edges, five short-path focus points and neighbours, underflow/overflow/tiny boundaries, atan dispatch endpoints and sampled interrupted-divider contexts. Finite actual ARM corpus, not physical timing or universal correctness proof.')
    if a.bootrom:report['actual_bootrom_sha256']=machine.bootrom_sha256
    a.json.parent.mkdir(parents=True,exist_ok=True);a.json.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS boundaries',report['input_cases'],'ARMcalls',calls,'SIOchecks',contexts,flush=True)


if __name__=='__main__':main()
