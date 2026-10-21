#!/usr/bin/env python3
"""Check tangent's two-MUL fourth-power kernel against exact integers."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import sys

from m0_exp_product_arm_self_test import function_source
from native_eabi_m0_arm_self_test import Machine, ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'code/native_eabi_m0_trig_tan.inc')
    p.add_argument('--toolchain',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--samples',type=int,default=100000)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    text=function_source(a.source.read_text(),'checked_trig_tan_fourth','uint32_t')
    cpp=a.output/'fourth.cpp';cpp.write_text('#include <stdint.h>\n'+text+
        '\nextern "C" uint32_t fourth(uint32_t q) {return checked_trig_tan_fourth(q);}\n')
    sys.path.insert(0,str(ROOT/'tools'))
    from build_picocalc import compiler_bin
    elf=a.output/'fourth.elf'
    subprocess.run([str(compiler_bin(a.toolchain)/'arm-none-eabi-g++'),
        '-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-fno-lto',
        '-Wall','-Wextra','-Werror','-nostdlib','-Wl,-Ttext=0x08000000',
        '-Wl,-e,fourth',str(cpp),'-o',str(elf)],check=True)
    m=Machine(elf);rng=random.Random(0x704);largest=0;digest=hashlib.sha256()
    boundary={1<<30}
    for hi in (0,1,8192,16383):
        boundary.update((hi<<16)|lo for lo in range(1<<16))
    for bit in range(31):
        boundary.update(x for x in ((1<<bit)-1,1<<bit,(1<<bit)+1) if x<=1<<30)
    inputs=sorted(boundary)+[rng.randrange((1<<30)+1) for _ in range(a.samples)]
    for q in inputs:
        got=m.call('fourth',q,width=32)[0]&0xFFFFFFFF
        error=abs((got<<34)-q*q)
        assert error<=3*(1<<32),(q,got,error)
        largest=max(largest,error);digest.update(struct.pack('<2I',q,got))
    report=dict(status='PASS',cases=len(inputs),
        source_sha256=hashlib.sha256(a.source.read_bytes()).hexdigest(),
        extracted_function_sha256=hashlib.sha256(text.encode()).hexdigest(),
        elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
        maximum_error=str(Fraction(largest,1<<34)),certified_bound='<=3/4',
        instructions=m.call('fourth',1<<30,width=32,count=True)[2],
        sha256=digest.hexdigest(),
        scope='Actual extracted ARM kernel; every low 16-bit limb at four representative high limbs, powers-of-two boundaries, maximum and random q in [0,2^30]. Exact Python integer squares supply the oracle.',
        abi='Every call checks R4-R11, SP and bounded stack writes.')
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
