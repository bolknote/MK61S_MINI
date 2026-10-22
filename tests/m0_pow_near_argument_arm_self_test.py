#!/usr/bin/env python3
"""Check the compiled near-one pow argument against exact rational bounds."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine, SP
from m0_mpfr_oracle import Oracle

ONE=0x3FF0000000000000
SIGN=1<<63


def magnitude_bounds(delta,p,sy,ey,below):
    f=Fraction(delta,1<<p)
    y=Fraction(sy)*Fraction(2)**(ey-52)
    polynomial=sum((f**i/Fraction(i) if below or i&1 else -f**i/Fraction(i))
                   for i in range(1,5))
    # Alternating log(1+f): S4 <= log(1+f) <= S4+f^5/5.
    # Positive -log(1-f): the tail lies in [0,f^5/(5*(1-f))].
    tail=f**5/(5*(1-f)) if below else f**5/5
    scale=y*(1<<80)
    return polynomial*scale,(polynomial+tail)*scale


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--bootrom',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=4000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    machine=Machine(args.elf,True,stack_bytes=16384,instruction_budget=200000000,bootrom=args.bootrom)
    matches=[n for n in machine.elf.symbols if n=='pow_near_one_refined_argument' or
             'pow_near_one_refined_argument' in n]
    assert len(matches)==1,matches
    symbol=matches[0];oracle=Oracle();rng=random.Random(0x850080)
    cases=set()
    for p in (52,53):
        maximum=1<<(p-26)
        for width in range(1,maximum.bit_length()+1):
            for delta in {1<<(width-1),(1<<width)-1,maximum,maximum+1}:
                if delta>maximum+1:continue
                leading=p+2-delta.bit_length()
                for d in (2,3,4,5,6,7):
                    for sy in (1<<52,(1<<53)-1,(1<<52)+1):
                        for sign in (False,True):cases.add((p,delta,leading+d,sy,sign))
        for d in (0,1,2,3,4,5,6,7,8):
            cases.add((p,0,40+d,1<<52,False))
    for _ in range(args.samples):
        p=rng.choice((52,53));width=rng.randrange(1,p-24)
        delta=rng.randrange(1<<(width-1),1<<width)
        ey=p+2-delta.bit_length()+rng.randrange(1,9)
        cases.add((p,delta,ey,rng.randrange(1<<52,1<<53),bool(rng.getrandbits(1))))
    output=SP-15000;negative=output+24
    canary=bytes.fromhex('A55A')*16
    digest=hashlib.sha256();accepted=rejected=public_calls=0
    largest_error=Fraction(0)
    for index,(p,delta,ey,sy,sign) in enumerate(sorted(cases)):
        below=p==53;xb=ONE-delta if below else ONE+delta
        yb=((ey+1023)<<52)|(sy-(1<<52))|(SIGN if sign else 0)
        eligible=bool(delta and delta<=1<<(p-26) and 3<=ey-(p+2-delta.bit_length())<=6)
        machine.uc.mem_write(output,canary)
        got=machine.call(symbol,xb,yb,c=output|(negative<<32))[0]&255
        assert bool(got)==eligible,(p,delta,ey,sy,'domain',got,eligible)
        if not got:
            assert bytes(machine.uc.mem_read(output,len(canary)))==canary
            rejected+=1
            continue
        high,low=struct.unpack('<2Q',machine.uc.mem_read(output,16))
        argument=(high<<64)|low
        assert argument&0xFFFF==0,'Q80 to Q96 conversion lost low bits'
        value=argument>>16
        lower,upper=magnitude_bounds(delta,p,sy,ey,below)
        assert value-8<=lower<=upper<=value+8,(p,delta,ey,sy,value,lower,upper)
        largest_error=max(largest_error,abs(Fraction(value)-lower),abs(Fraction(value)-upper))
        expected_negative=below^sign
        assert machine.uc.mem_read(negative,1)[0]==expected_negative
        digest.update(struct.pack('<4Q',xb,yb,high,low)+bytes([expected_negative]))
        accepted+=1
        if index%13==0:
            expected=oracle.reference('pow',xb,yb)
            actual=machine.call('_ZN12compact_math3powEdd',xb,yb)[0]
            assert actual==expected,(hex(xb),hex(yb),hex(actual),hex(expected))
            public_calls+=1
    assert accepted>1000 and rejected>1000 and public_calls>50
    result=dict(status='PASS',accepted_argument_cases=accepted,rejected_domain_cases=rejected,
                public_pow_mpfr_cases=public_calls,wrong_rounding=0,
                largest_observed_bound_distance_Q80=float(largest_error),
                error_bound_Q80=8,error_bound_Q96=8<<16,
                argument_sha256=digest.hexdigest(),elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
                bootrom_sha256=machine.bootrom_sha256,test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                scope='Actual ARM helper with exact Fraction logarithm-series enclosures and full public pow calls against directed MPFR. Domain edges, both sides of one and both exponent signs are included. Finite corpus; the separate algebraic certificate covers the accepted source domain. Not physical cycles or general pow totality.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS:',accepted,'exact rational enclosures;',rejected,'declines;',public_calls,'public MPFR results')


if __name__=='__main__':
    main()
