#!/usr/bin/env python3
"""Check the pointer-based first-candidate ABI and poisoned-hint fallback."""
import argparse
from fractions import Fraction
import hashlib,json,random,struct
from pathlib import Path
from native_eabi_m0_arm_self_test import Machine,SP,bits
from m0_mpfr_oracle import Oracle

ONE=0x3FF0000000000000


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--bootrom',type=Path,required=True)
    p.add_argument('--samples',type=int,default=1800)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args();rng=random.Random(0x960055);oracle=Oracle()
    m=Machine(args.elf,True,stack_bytes=16384,instruction_budget=200000000,bootrom=args.bootrom)
    cases={(bits(x),bits(x)) for x in (.5,1.,1.5,2.)}
    for _ in range(args.samples):
        x=(rng.randrange(1021,1026)<<52)|rng.getrandbits(52)
        if rng.randrange(4):
            y=bits(float(Fraction(rng.randrange(1,33),1<<rng.randrange(8))))
        else:y=(rng.randrange(1020,1026)<<52)|rng.getrandbits(52)
        if rng.getrandbits(1):y|=1<<63
        cases.add((x,y))
    hard=json.loads((Path(__file__).resolve().parents[1]/'research/m0-pow-checked-20261022/hard-pow-inputs.json').read_text())
    for group in hard['groups']:
        cases.update((int(c['a'],16),int(c['b'],16)) for c in group['cases'])
    px,py=SP-15000,SP-14904;canary=bytes.fromhex('5A8C1DE3')*4
    calls=public=aliases=0;digest=hashlib.sha256()
    for index,(x,y) in enumerate(sorted(cases)):
        expected=oracle.reference('pow',x,y)
        hints={0,ONE,0x7FF0000000000000,rng.getrandbits(64),expected}
        hints.update(v for v in (expected-1,expected+1) if 0<=v<1<<64)
        a=struct.pack('<Q',x)+canary;b=struct.pack('<Q',y)+canary
        m.uc.mem_write(px,a);m.uc.mem_write(py,b)
        actual_py=px if x==y else py
        for hint in sorted(hints):
            got=m.call('pow_first_candidate',px|(actual_py<<32),hint)[0]
            assert got==expected,(hex(x),hex(y),hex(hint),hex(got),hex(expected))
            assert bytes(m.uc.mem_read(px,len(a)))==a
            assert bytes(m.uc.mem_read(py,len(b)))==b
            digest.update(struct.pack('<4Q',x,y,hint,got));calls+=1;aliases+=x==y
        if index%23==0:
            got=m.call('_ZN12compact_math3powEdd',x,y)[0]
            assert got==expected,(hex(x),hex(y),'public',hex(got),hex(expected))
            public+=1
    assert calls>10000 and aliases>0 and public>50
    result=dict(status='PASS',input_pairs=len(cases),direct_candidate_calls=calls,
        alias_pointer_calls=aliases,public_mpfr_calls=public,input_bytes_and_canaries_preserved=True,
        wrong_rounding=0,result_sha256=digest.hexdigest(),
        elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),bootrom_sha256=m.bootrom_sha256,
        test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Actual ARM pointer+hint entry, with identical, adjacent, distant, random and invalid seeds, including aliased parameter pointers. Every direct return and selected public return matches directed MPFR; parameter bytes and surrounding canaries remain unchanged. Captured ROM executes and every call checks callee-saved registers, SP and stack writes. Finite ABI/fallback coverage, not an all-input precision or physical-speed proof.')
    args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS:',len(cases),'pairs;',calls,'poisoned/valid-seed calls;',aliases,'aliased-pointer calls;',public,'public MPFR calls')


if __name__=='__main__':main()
