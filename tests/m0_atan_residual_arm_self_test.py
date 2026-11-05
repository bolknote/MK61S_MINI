#!/usr/bin/env python3
"""Check atan's narrowed ARM residual against independent unbounded integers."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import random
import struct
import time

from native_eabi_m0_arm_self_test import Machine


def cases(samples):
    denominators=set()
    for width in range(59,65):
        for bit in (0,1,8,16,24,31,32,39,40,48,52,56):
            for offset in (-1,0,1):
                for d in ((1<<(width-1))+(1<<bit)+offset,(1<<width)-(1<<bit)+offset):
                    if 1<<58<=d<1<<64:denominators.add(d)
    denominators.update((1<<58,(1<<64)-1))
    rng=random.Random(0xA7A24072)
    denominators.update(rng.randrange(1<<58,1<<64) for _ in range(samples))
    for d in sorted(denominators):
        n=rng.randrange(d//2+1)
        for numerator in (0,1,n,d//2):
            exact=(numerator<<64)//d
            for offset in (-32,-1,0,1,32):
                estimate=exact+offset
                if 0<=estimate<1<<63:yield numerator,d,estimate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--samples',type=int,default=1000)
    p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();assert 0<=a.samples<=10000
    machine=Machine(a.elf,True);oracle_bound=1+F(35,1<<18)
    symbol=next(n for n in machine.elf.symbols if n=='atan_ratio_adjust')
    digest=hashlib.sha256();maximum=F(0);count=contexts=0;start=time.monotonic()
    for n,d,h in cases(a.samples):
        assert time.monotonic()-start<300
        # This uses full-width exact products, not the optimized limb formula.
        residual=(n<<64)-h*d;assert abs(residual)<33*d
        signed_head=-((-residual)//(1<<40))
        expected=abs(signed_head)//(d>>40)
        if signed_head<0:expected=-expected
        got=machine.call(symbol,n,d,c=h)[0]&0xffffffff
        signed=got-(1<<32) if got>>31 else got
        assert signed==expected,(hex(n),hex(d),hex(h),signed,expected)
        distance=abs(F(signed)-F(residual,d));assert distance<oracle_bound
        maximum=max(maximum,distance);count+=1
        digest.update(struct.pack('<3QI',n,d,h,got))
        if count%127==0:
            for words in ((17,3,17,3,5,2,3),(0x80000001,7,0x80000001,7,0x11223344,0x55667788,2)):
                before=struct.pack('<7I',*words);machine.uc.mem_write(0xd0000060,before)
                assert machine.call(symbol,n,d,c=h)[0]&0xffffffff==got
                assert bytes(machine.uc.mem_read(0xd0000060,28))==before
                contexts+=1
            machine.uc.mem_write(0xd0000078,struct.pack('<I',1))
    report=dict(status='PASS_EXACT_INTEGER_ATAN_RESIDUAL',cases=count,DIRTY_PENDING_checks=contexts,
        maximum_error=str(maximum),exclusive_error_bound=str(oracle_bound),
        records_sha256=digest.hexdigest(),elf_sha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        elapsed_seconds=time.monotonic()-start,hardware_IO=0,pow_calls=0,
        scope='Actual ARM helper, full-width independent integer residual and exact Fraction bound; width/carry/sign endpoints and deterministic random cases. Machine checks R4-R11/SP and bounded stack writes every call.')
    a.json.parent.mkdir(parents=True,exist_ok=True);a.json.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS atan residual',count,'cases;',contexts,'interrupted-divider checks',flush=True)


if __name__=='__main__':main()
