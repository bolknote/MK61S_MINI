#!/usr/bin/env python3
"""Validate tiny binomial pow acceptance with exact cells and directed MPFR."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine,SP
from m0_mpfr_oracle import Oracle

ONE=0x3FF0000000000000
SIGN=1<<63


def rational(bits):
    value=struct.unpack('<d',struct.pack('<Q',bits))[0]
    return F(value)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--bootrom',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=6000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    m=Machine(args.elf,True,stack_bytes=16384,instruction_budget=200000000,bootrom=args.bootrom)
    names=[n for n in m.elf.symbols if 'pow_near_one_binomial' in n]
    assert len(names)==1,names
    oracle=Oracle();rng=random.Random(0x880128)
    cases=set()
    for below,maximum in ((False,32),(True,64)):
        for delta in range(maximum+2):
            x=ONE-delta if below else ONE+delta
            for ey in (-12,-11,-10,-1,0,1,4,5):
                for sy in (1<<52,(1<<52)+1,(3<<51)-1,3<<51,(1<<53)-1):
                    for sign in (0,SIGN):
                        y=((ey+1023)<<52)|(sy-(1<<52))|sign
                        cases.add((x,y))
    for _ in range(args.samples):
        x=ONE+rng.randrange(-66,35)
        ey=rng.randrange(-13,7);sy=rng.randrange(1<<52,1<<53)
        y=((ey+1023)<<52)|(sy-(1<<52))|(SIGN if rng.getrandbits(1) else 0)
        cases.add((x,y))
    hard=json.loads((Path(__file__).resolve().parents[1]/'research/m0-pow-checked-20261022/hard-pow-inputs.json').read_text())
    for group in hard['groups']:
        cases.update((int(c['a'],16),int(c['b'],16)) for c in group['cases'])
    # Outputs remain untouched on declined cells and outside the domain.
    output=SP-15000;canary=bytes.fromhex('735AD9C628B40E91')
    counts=dict(accepted=0,ambiguous=0,outside_domain=0,public_mpfr=0)
    digest=hashlib.sha256();instructions=[]
    for index,(x,y) in enumerate(sorted(cases)):
        ey=((y&~SIGN)>>52)-1023
        eligible=(ONE-64<=x<=ONE+32 and x!=ONE and -11<=ey<=4)
        m.uc.mem_write(output,canary)
        ok=m.call(names[0],x,y,c=output,count=False)[0]&255
        assert ok in (0,1)
        got=struct.unpack('<Q',m.uc.mem_read(output,8))[0]
        if not ok:
            assert m.uc.mem_read(output,8)==canary,(hex(x),hex(y),'write on decline')
            counts['ambiguous' if eligible else 'outside_domain']+=1
        else:
            assert eligible,(hex(x),hex(y),'accepted outside domain')
            f=rational(x)-1;exponent=rational(y)
            polynomial=(1+exponent*f+exponent*(exponent-1)*f*f/2+
                        exponent*(exponent-1)*(exponent-2)*f**3/6)
            remainder=104720*abs(f)**4
            lower=(rational(got-1)+rational(got))/2
            upper=(rational(got)+rational(got+1))/2
            assert lower<polynomial-remainder<=polynomial+remainder<upper,(hex(x),hex(y),hex(got))
            expected=oracle.reference('pow',x,y)
            assert got==expected,(hex(x),hex(y),hex(got),hex(expected))
            digest.update(struct.pack('<3Q',x,y,got));counts['accepted']+=1
            if index%41==0:
                _,_,n=m.call(names[0],x,y,c=output,count=True)
                instructions.append(n)
        if eligible and index%17==0:
            got=m.call('_ZN12compact_math3powEdd',x,y)[0]
            assert got==oracle.reference('pow',x,y),(hex(x),hex(y),hex(got))
            counts['public_mpfr']+=1
    assert counts['accepted']>1000 and counts['outside_domain']>1000 and counts['public_mpfr']>100
    result=dict(status='PASS',cases=len(cases),counts=counts,wrong_rounding=0,
        accepted_results_sha256=digest.hexdigest(),helper_instruction_extrema=[min(instructions),max(instructions)],
        elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),bootrom_sha256=m.bootrom_sha256,
        test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Compiled ARM helper: every accepted result encloses an independently formed exact-rational cubic Taylor interval strictly inside its binary64 rounding cell, and matches directed MPFR. Includes all 96 nonzero base displacements, exponent-domain edges, both signs, random full significands, and the saved hard-pow corpus. Selected full public calls validate integration. Finite coverage; see the separate algebraic domain certificate. No hardware-cycle or totality claim.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS:',len(cases),'cases;',counts,'helper instructions',result['helper_instruction_extrema'])


if __name__=='__main__':
    main()
