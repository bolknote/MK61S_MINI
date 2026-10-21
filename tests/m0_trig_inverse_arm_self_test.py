#!/usr/bin/env python3
"""Check the actual tangent inverse against a full-width integer Newton model."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine


def rounded(value, shift):
    negative=value<0
    q,r=divmod(abs(value),1<<shift)
    q+=r>(1<<(shift-1)) or (r==(1<<(shift-1)) and q&1)
    return -q if negative else q


def model(denominator):
    d=2*denominator
    seed=(1<<63)//(d>>32)
    y=seed<<31
    residual=((d*y)>>64)-(1<<62)
    return y-rounded(y*residual,62)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--baseline-elf',type=Path)
    p.add_argument('--samples',type=int,default=100000)
    p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();assert a.samples>=0
    digest_elf=hashlib.sha256(a.elf.read_bytes()).hexdigest()
    machine=Machine(a.elf,True)
    assert 'checked_trig_inverse' in machine.elf.symbols
    values=[]
    for top in range(32768,65536):
        for h in (top<<16,((top+1)<<16)-1):
            for low in (0,2,0xfffffffe):values.append((h<<31)|(low>>1))
    rng=random.Random(0x74616e58)
    values += [(1<<62)|rng.getrandbits(62) for _ in range(a.samples)]
    maximum_num,maximum_den=0,1;digest=hashlib.sha256()
    for denominator in values:
        got=machine.call('checked_trig_inverse',denominator)[0]
        expected=model(denominator)
        assert got==expected,('Integer Newton mismatch',hex(denominator),hex(got),hex(expected))
        d=2*denominator;error=abs(got*d-(1<<126))
        assert 2*error<5*d,('Reciprocal error',hex(denominator),hex(got))
        if error*maximum_den>maximum_num*d:maximum_num,maximum_den=error,d
        digest.update(struct.pack('<2Q',denominator,got))
    pending=struct.pack('<7I',17,3,0,0,5,2,3)
    dirty=0
    for denominator in [1<<62,(1<<62)+1,(1<<63)-1,*values[::16384]]:
        machine.uc.mem_write(0xd0000060,pending)
        assert machine.call('checked_trig_inverse',denominator)[0]==model(denominator)
        assert bytes(machine.uc.mem_read(0xd0000060,len(pending)))==pending
        dirty+=1
    machine.uc.mem_write(0xd0000078,struct.pack('<I',1))
    samples=[1<<62,0x61ab9347e1056c22,(1<<63)-1]
    counts=[dict(denominator=f'{v:016X}',new=machine.call('checked_trig_inverse',v,count=True)[2]) for v in samples]
    if a.baseline_elf:
        before=Machine(a.baseline_elf,True)
        for row,v in zip(counts,samples):row['before']=before.call('checked_trig_inverse',v,count=True)[2]
    assert digest_elf==hashlib.sha256(a.elf.read_bytes()).hexdigest()
    report=dict(status='PASS',elf_sha256=digest_elf,cases=len(values),integer_model_mismatches=0,
        maximum_Q62_error=str(Fraction(maximum_num,maximum_den)),certified_strict_error_bound='5/2',
        dirty_sio_checks=dirty,actual_arm_calls=machine.calls,sample_instructions=counts,
        result_sha256=digest.hexdigest(),
        abi='Every call verifies R4-R11, SP and bounded stack writes.',
        scope='All16-bit high-word bucket endpoints, low-word endpoints and random denominators. Full-width integer model, not the optimized expression. Finite ARM corpus complements the analytic all-domain error proof; no physical timing claim.')
    a.json.parent.mkdir(parents=True,exist_ok=True);a.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
