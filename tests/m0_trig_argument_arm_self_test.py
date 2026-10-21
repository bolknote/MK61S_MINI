#!/usr/bin/env python3
"""Compare actual RP2040 argument reduction with a pinned full-shift baseline."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine, SP, bits


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--baseline-elf',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=50000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    assert args.samples>=0
    lower,upper=0x3E40000000000000,0x4130000000000000
    values=set()

    def around(value,span=4):
        values.update(range(max(lower,value-span),min(upper,value+span+1)))

    for exponent in range(996,1043):
        for fraction in (0,1,(1<<51)-1,1<<51,(1<<52)-2,(1<<52)-1):
            around((exponent<<52)|fraction)
    for multiple in [*range(1,4097),*range(4096,667545,997)]:
        around(bits(multiple*(math.pi/2)),16)
    around(0x3FE921FB54442D18,64)
    rng=random.Random(0x61726761)
    values.update(rng.randrange(lower,upper) for _ in range(args.samples))
    machines={'before':Machine(args.baseline_elf,True,stack_bytes=16384),
              'new':Machine(args.elf,True,stack_bytes=16384)}
    pointer=SP-15000
    digest=hashlib.sha256()
    leading_exponents=set()
    for value in sorted(values):
        results={}
        for label,machine in machines.items():
            machine.uc.mem_write(pointer,b'\0'*24)
            machine.call('checked_trig_argument',value,pointer)
            results[label]=bytes(machine.uc.mem_read(pointer,24))
        assert results['new']==results['before'],(
            'argument fields differ',f'{value:016X}',
            results['new'].hex(),results['before'].hex())
        q,exponent,n,error,negative,tail=struct.unpack('<QiII?xh',results['new'])
        if n and exponent!=1:
            leading_exponents.add(exponent)
        digest.update(struct.pack('<Q',value)+results['new'])
    counts=[]
    for value in (bits(.2),bits(1.0),bits(100.0),bits(math.pi/2),bits(1000*math.pi/2)):
        row={'input':f'{value:016X}'}
        for label,machine in machines.items():
            row[label]=machine.call('checked_trig_argument',value,pointer,count=True)[2]
        counts.append(row)
    report=dict(status='PASS',cases=len(values),field_mismatches=0,
        elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        baseline_elf_sha256=hashlib.sha256(args.baseline_elf.read_bytes()).hexdigest(),
        relative_exponents=sorted(leading_exponents),result_sha256=digest.hexdigest(),
        sample_instructions=counts,
        scope='Actual ARM output fields compared with the previous full-width-shift implementation. Exponent/mantissa boundaries, neighbours of pi/2 multiples, and deterministic random normal inputs throughout the public fast domain. Complements the exact word-decomposition identity; does not replace end-to-end MPFR qualification.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
