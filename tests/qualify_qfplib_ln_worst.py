#!/usr/bin/env python3
"""Check every saved CORE-MATH log hard case on actual ARM checked-ln code."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from m0_mpfr_oracle import Oracle,bits
from native_eabi_m0_arm_self_test import Machine,nan
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R2


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args()
    elf_sha=hashlib.sha256(args.elf.read_bytes()).hexdigest()
    raw=args.corpus.read_bytes();corpus_sha=hashlib.sha256(raw).hexdigest()
    values=[];headers=[]
    for line in raw.decode('ascii').splitlines():
        line=line.strip()
        if not line:continue
        if line.startswith('#'):headers.append(line);continue
        token=line.split('#',1)[0].strip().lower()
        if token in ('snan','+snan','-snan'):
            values.append(0x7ff0000000000001|((1<<63) if token.startswith('-') else 0))
        else:values.append(bits(float.fromhex(token)))
    assert values
    machine=Machine(args.elf);oracle=Oracle();digest=hashlib.sha256()
    entries={4:0,8:0}
    def entered(uc,*unused):
        w=uc.reg_read(UC_ARM_REG_R2);assert w in entries,w;entries[w]+=1
    address=machine.elf.symbols['refine']&~1
    machine.uc.hook_add(UC_HOOK_CODE,entered,begin=address,end=address)
    for i,x in enumerate(values):
        got=machine.call('qfp_dln_checked',x)[0];expected=oracle.reference('ln',x)
        assert got==expected or nan(expected) and nan(got) and got&(1<<51),(i,hex(x),hex(got),hex(expected))
        digest.update(struct.pack('<3Q',x,got,expected))
        if (i+1)%1000==0:print('PASS',i+1,'hard cases',dict(entries),flush=True)
    assert elf_sha==hashlib.sha256(args.elf.read_bytes()).hexdigest()
    assert corpus_sha==hashlib.sha256(args.corpus.read_bytes()).hexdigest()
    result=dict(status='PASS',complete_corpus=True,cases=len(values),wrong_rounding=0,
        elf_sha256=elf_sha,corpus_sha256=corpus_sha,corpus_headers=headers,
        mpfr=oracle.version,result_sha256=digest.hexdigest(),refinement_entries=entries,
        abi='Every actual ARM call verifies R4-R11, SP and bounded stack writes.',
        scope='Complete saved hard-case file, independently checked against directed MPFR bounds; not by itself a formal proof of all-input corpus completeness or Q245 termination.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: complete',len(values),'log hard cases',flush=True)


if __name__=='__main__':main()
