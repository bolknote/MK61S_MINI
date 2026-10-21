#!/usr/bin/env python3
"""Check exp's compiled high products against exact integer arithmetic."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import sys

from native_eabi_m0_arm_self_test import Machine, ROOT


def function_source(text, name, result_type='U'):
    prefix='__attribute__((always_inline)) inline '+result_type+' '+name+'('
    assert text.count(prefix)==1, name
    start=text.index(prefix)
    return text[start:text.index('\n}',start)+2]


def edges():
    values={0,(1<<64)-1}
    for n in range(64):
        values.update(v for v in ((1<<n)-1,1<<n,(1<<n)+1) if v<1<<64)
    # Cross-word carries also depend on simultaneous low/high limb edges.
    limbs=(0,1,2,0x7FFF,0x8000,0xFFFF,0x10000,0x7FFFFFFF,0x80000000,0xFFFFFFFE,0xFFFFFFFF)
    values.update((hi<<32)|lo for hi in limbs for lo in limbs)
    return sorted(values)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'code/native_eabi_m0.cpp')
    p.add_argument('--toolchain',type=Path)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--samples',type=int,default=100000)
    p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
    text=a.source.read_text()
    functions=[function_source(text,n) for n in ('wide32','exp_high_product','exp_high_square')]
    source=a.output_dir/'products.cpp'
    source.write_text('#include <stdint.h>\nusing U=uint64_t;\n'+'\n'.join(functions)+
        '\nextern "C" U square(U x) {return exp_high_square(x);}\n'+
        'extern "C" U product(U x,U y) {return exp_high_product(x,y)+1;}\n')
    sys.path.insert(0,str(ROOT/'tools'))
    from build_picocalc import compiler_bin
    elf=a.output_dir/'products.elf'
    subprocess.run([str(compiler_bin(a.toolchain)/'arm-none-eabi-g++'),
        '-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-fno-lto',
        '-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-nostdlib',
        '-Wl,-Ttext=0x08000000','-Wl,-e,square',str(source),'-o',str(elf)],check=True)
    m=Machine(elf);rng=random.Random(0xE640);boundary=edges();scale=1<<64
    largest_square=largest_product=0;digest=hashlib.sha256();squares=products=0
    def square(x):
        nonlocal largest_square,squares
        q=m.call('square',x)[0];error=abs((q<<64)-x*x)
        assert error<=scale,(hex(x),q,error)
        largest_square=max(largest_square,error);squares+=1
        digest.update(struct.pack('<2Q',x,q))
    def product(x,y):
        nonlocal largest_product,products
        q=m.call('product',x,y)[0];error=abs((q<<64)-x*y)
        assert error<2*scale,(hex(x),hex(y),q,error)
        largest_product=max(largest_product,error);products+=1
        digest.update(struct.pack('<3Q',x,y,q))
    for x in boundary:
        square(x)
        for y in boundary:product(x,y)
    for _ in range(a.samples):
        x,y=rng.getrandbits(64),rng.getrandbits(64)
        square(x);product(x,y)
    report=dict(status='PASS',source_sha256=hashlib.sha256(a.source.read_bytes()).hexdigest(),
        extracted_functions_sha256=hashlib.sha256('\n'.join(functions).encode()).hexdigest(),
        elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
        square_calls=squares,product_calls=products,
        maximum_square_error=str(Fraction(largest_square,scale)),
        maximum_product_error=str(Fraction(largest_product,scale)),
        square_error_bound='<=1',product_error_bound='<2',
        instructions={n:m.call(n,(1<<64)-1,(1<<64)-1,count=True)[2] for n in ('square','product')},
        sha256=digest.hexdigest(),
        scope='Exact source functions extracted without editing production, compiled at -Os for Cortex-M0+. Integer oracle covers powers of two, 16/32-bit limb boundaries, carries and random full-width inputs. This is not a hardware cycle measurement.',
        abi='Every call checks R4-R11, SP and bounded stack writes.')
    a.json.parent.mkdir(parents=True,exist_ok=True)
    a.json.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
