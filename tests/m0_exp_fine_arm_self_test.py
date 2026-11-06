#!/usr/bin/env python3
"""Check the compiled exp nonlinear correction against exact rational exp bounds."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess

from native_eabi_m0_arm_self_test import Machine, ROOT
from m0_exp_product_arm_self_test import function_source


def bounds(a,negative):
    h=F(a,1<<64)
    term=h*h/2
    total=term
    for n in range(3,8):
        term=term*h/n
        total+=-term if negative and n&1 else term
    next_term=term*h/8
    # For -h the remaining alternating series starts with a positive term.
    # For +h every subsequent term ratio is at most h/9.
    return total,total+(next_term if negative else next_term/(1-h/9))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--samples',type=int,default=20000)
    p.add_argument('--toolchain',type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    source=ROOT/'code/native_eabi_m0_exp_fine.inc'
    functions=[function_source((ROOT/'code/native_eabi_m0.cpp').read_text(),'wide32'),
               function_source(source.read_text(),'exp_fine_nonlinear')]
    fixture=a.output/'nonlinear.cpp'
    fixture.write_text('#include <stdint.h>\nusing U=uint64_t;\n'+'\n'.join(functions)+
                       '\nextern "C" U nonlinear(U a,U negative){return exp_fine_nonlinear(a,negative!=0);}\n')
    elf=a.output/'nonlinear.elf'
    subprocess.run([str(a.toolchain/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb',
                    '-mfloat-abi=soft','-Os','-fno-lto','-fno-builtin','-fno-exceptions','-fno-rtti',
                    '-Wall','-Wextra','-Werror','-nostdlib','-Wl,-Ttext=0x08000000',
                    '-Wl,-e,nonlinear',str(fixture),'-o',str(elf)],check=True)
    machine=Machine(elf)
    maximum=12912720851596686
    inputs={0,1,maximum-1,maximum}
    for bit in range(54):
        inputs.update(x for x in ((1<<bit)-1,1<<bit,(1<<bit)+1) if x<=maximum)
    # Carries in all 16/32-bit product words and the Q48/Q31 truncations.
    for shift in (8,16,29,31,32,33,40,48):
        for head in (1,2,3,0x7fff,0x8000,0xffff,0x10000,0x7fffffff,0xffffffff):
            for delta in (-1,0,1):
                value=(head<<shift)+delta
                if 0<=value<=maximum:inputs.add(value)
    rng=random.Random(0xE6800F1)
    inputs.update(rng.randrange(maximum+1) for _ in range(a.samples))
    worst=F(0)
    digest=hashlib.sha256()
    for value in sorted(inputs):
        for negative in (0,1):
            got=machine.call('nonlinear',value,negative)[0]
            lo,hi=bounds(value,bool(negative))
            lo*=1<<70;hi*=1<<70
            assert F(got)-6<lo<=hi<F(got)+6,(hex(value),negative,got,str(lo),str(hi))
            worst=max(worst,abs(F(got)-lo),abs(hi-F(got)))
            digest.update(struct.pack('<3Q',value,negative,got))
    result=dict(status='PASS_EXACT_RATIONAL_EXP_ENCLOSURES',inputs=len(inputs),
                ARM_calls=2*len(inputs),maximum_error_q70=str(worst),
                maximum_error_q70_float=float(worst),accepted_bound_q70=6,
                elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                result_sha256=digest.hexdigest(),hardware_IO=0,
                scope='Actual ARM polynomial versus independent rational bounds for the exponential remainder, both signs, bounded full mantissas, and limb/carry/truncation edges. Every call checks AAPCS and stack. Universal enclosure relies on the separate rational certificate.')
    (a.output/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],result['ARM_calls'],'calls','worst',float(worst),'<6')


if __name__=='__main__':main()
