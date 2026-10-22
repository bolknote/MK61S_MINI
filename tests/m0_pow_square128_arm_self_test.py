#!/usr/bin/env python3
"""Check the specialized square against the old full product and exact intervals."""
import argparse
from fractions import Fraction as F
import hashlib,json,random,struct
from pathlib import Path
from native_eabi_m0_arm_self_test import Machine,SP


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--baseline-elf',type=Path,required=True)
    p.add_argument('--bootrom',type=Path,required=True)
    p.add_argument('--samples',type=int,default=10000)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args();rng=random.Random(0x980128)
    machines={label:Machine(elf,True,stack_bytes=16384,instruction_budget=200000000,bootrom=args.bootrom)
              for label,elf in dict(baseline=args.baseline_elf,current=args.elf).items()}
    values={1<<127,(1<<128)-1}
    for bit in range(127):
        for tail in ((1<<bit)-1,1<<bit,(1<<bit)+1):values.add((1<<127)|tail)
    values.update(rng.randrange(1<<127,1<<128) for _ in range(args.samples))
    pointer=SP-15000;mask=(1<<64)-1;digest=hashlib.sha256();counts=[]
    for index,value in enumerate(sorted(values)):
        if index%5==0:value&=~mask
        error=0 if index%7==0 else rng.randrange(10000);exponent=rng.randrange(-100,101)
        image=struct.pack('<QQiI',value>>64,value&mask,exponent,error)
        results={}
        for label,m in machines.items():
            m.uc.mem_write(pointer,image)
            if label=='baseline':m.call('pow_integer128_multiply',pointer,pointer,32)
            else:m.call('pow_integer128_square',pointer,0,32)
            results[label]=bytes(m.uc.mem_read(pointer,24))
        assert results['baseline']==results['current'],(index,value,error)
        hi,lo,ex,err=struct.unpack('<QQiI',results['current']);q=(hi<<64)|lo
        scale=F(2)**(ex-127)
        lower=F(value-error)*F(2)**(exponent-127)
        upper=F(value+error)*F(2)**(exponent-127)
        assert F(q-err)*scale<=lower*lower<=upper*upper<=F(q+err)*scale
        digest.update(image+results['current'])
        if index%61==0:
            row={}
            for label,m in machines.items():
                m.uc.mem_write(pointer,image)
                name='pow_integer128_multiply' if label=='baseline' else 'pow_integer128_square'
                row[label]=m.call(name,pointer,pointer if label=='baseline' else 0,32,count=True)[2]
            counts.append(row)
    result=dict(status='PASS',cases=len(values),parent_full_product_bitwise_identical=True,
        exact_rational_interval_checks=len(values),result_sha256=digest.hexdigest(),
        counted_samples=len(counts),mean_instructions={label:sum(row[label] for row in counts)/len(counts) for label in machines},
        elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),baseline_elf_sha256=hashlib.sha256(args.baseline_elf.read_bytes()).hexdigest(),
        bootrom_sha256=machines['current'].bootrom_sha256,test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Every actual ARM square result, radius and exponent equals the qualified generic aliased product byte-for-byte and independently encloses both exact rational input endpoints squared. All-bit carry boundaries, maximal words, zero low words, random full128-bit mantissas and nonzero input radii are included. Every call checks ABI and stack writes. Finite coverage plus the source algebraic identity; not hardware cycles or general pow totality.')
    args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS:',len(values),'parent-identical squares and exact interval checks;',result['mean_instructions'])


if __name__=='__main__':main()
