#!/usr/bin/env python3
"""Qualify actual ARM pow shortcuts and forced Q94 refinement against MPFR."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct

from m0_mpfr_oracle import Oracle, bits, real
from native_eabi_m0_arm_self_test import Machine, SP, nan
from unicorn import UC_HOOK_CODE


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=10000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();assert args.samples>=0
    elf_sha=hashlib.sha256(args.elf.read_bytes()).hexdigest()
    machine=Machine(args.elf,True,stack_bytes=16384)
    oracle=Oracle();rng=random.Random(0xC0128323);fallback=[0];reports={}
    address=machine.elf.symbols['mk61_m0_cr_pow']&~1
    def entered(*unused):fallback[0]+=1
    machine.uc.hook_add(UC_HOOK_CODE,entered,begin=address,end=address)

    def qualify(name,symbol,values):
        before=fallback[0];digest=hashlib.sha256()
        for a,b in values:
            expected=oracle.reference('pow',a,b)
            got=machine.call(symbol,a,b)[0]
            correct=(nan(got) and bool(got&(1<<51))) if nan(expected) else got==expected
            assert correct,(name,f'{a:016X}',f'{b:016X}',f'{got:016X}',f'{expected:016X}')
            digest.update(struct.pack('<4Q',a,b,got,expected))
        reports[name]=dict(cases=len(values),wrong_rounding=0,
            core_fallbacks=fallback[0]-before,sha256=digest.hexdigest())
        print(name,reports[name],flush=True)

    inverse_roots=[((rng.randrange(1,2047)<<52)|rng.getrandbits(52),bits(-.5))
                   for _ in range(args.samples)]
    for exponent in (1,2,3,1021,1022,1023,1024,1025,2045,2046):
        for fraction in (0,1,2,(1<<52)-2,(1<<52)-1):
            inverse_roots.append(((exponent<<52)|fraction,bits(-.5)))
    qualify('inverse_square_root','pow_rsqrt',inverse_roots)

    subnormal_roots=[(rng.randrange(1,1<<52),bits(-.5)) for _ in range(args.samples)]
    for leading in range(52):
        center=1<<leading
        for delta in (-2,-1,0,1,2):
            if 0<center+delta<1<<52:
                subnormal_roots.append((center+delta,bits(-.5)))
    qualify('inverse_square_root_subnormal','pow_rsqrt',subnormal_roots)

    # Adjacent inputs around inverse-root rounding midpoints exercise the
    # exact 161-bit comparison independently of the approximation table.
    root_midpoints=[]
    for _ in range(args.samples//16):
        significand=(1<<52)+rng.getrandbits(52)
        denominator=(2*significand+1)**2
        exponent=int((1<<108)>=2*denominator)
        m=(1<<(160-exponent))//denominator
        a=((1023+exponent)<<52)+m-(1<<52)
        for delta in (-1,0,1,2):
            for scale in (-511,0,511):
                root_midpoints.append((a+delta+((2*scale)<<52),bits(-.5)))
    qualify('inverse_square_root_midpoints','pow_rsqrt',root_midpoints)

    root_cells=[]
    for parity in (0,1):
        for cell in range(256):
            for offset in (0,1<<43):
                a=((1023+parity)<<52)+(cell<<44)+offset
                root_cells.extend((a+delta,bits(-.5)) for delta in (-1,0,1))
    qualify('inverse_square_root_cells','pow_rsqrt',root_cells)

    middle=[(bits(math.ldexp(rng.uniform(1,2),rng.randrange(-900,900))),
             bits(rng.uniform(-1,1))) for _ in range(args.samples)]
    for _ in range(args.samples):
        a=bits(1.)+rng.choice((-1,1))*rng.randrange(1,1<<36)
        y=math.ldexp(rng.uniform(1,2),rng.randrange(-12,65))
        y=min(y,650/abs(math.log(real(a))))*rng.choice((-1,1))
        middle.append((a,bits(y)))
    qualify('forced_q94','pow_refine_checked',middle)

    # Keep outputs finite while sweeping the complete normal input range.
    bounded=[]
    for _ in range(args.samples):
        a=(rng.randrange(1,2047)<<52)|rng.getrandbits(52)
        logarithm=math.log(real(a))
        y=rng.uniform(-680,680)/logarithm if logarithm else 1.
        bounded.append((a,bits(y)))
    qualify('positive_bounded','_ZN12compact_math3powEdd',bounded)

    # One-ULP neighbours of a dense dyadic grid also cover cancellation
    # at1 and mantissa/exponent transitions, with independently rounded y.
    logarithm_edges=[]
    for i in range(257):
        for delta in (-1,0,1):
            for scale in (0,900):
                a=bits(1.)+(i<<44)+delta+(scale<<52)
                logarithm=math.log(real(a))
                for target in (-620.,-.75,.75,620.):
                    y=target/logarithm if logarithm else 1.
                    logarithm_edges.append((a,bits(y)))
    qualify('normal_logarithm_edges','_ZN12compact_math3powEdd',logarithm_edges)

    exp_range=[]
    for _ in range(args.samples):
        a=(rng.randrange(1,2047)<<52)|rng.getrandbits(52)
        logarithm=math.log(real(a))
        lower,upper=rng.choice(((-746.,-700.),(700.,710.)))
        y=rng.uniform(lower,upper)/logarithm if logarithm else 1.
        exp_range.append((a,bits(y)))
    for power in (-1076,-1075,-1074,-1023,-1022,1023,1024,1025):
        for exponent in (1,2,4,8,16,32,64,128,256,512,900):
            a=bits(math.ldexp(1.,exponent));b=bits(power/exponent)
            for delta in (-1,0,1):
                exp_range.extend(((a,b+delta),(a|(1<<63),b+delta)))
    qualify('underflow_overflow_range','_ZN12compact_math3powEdd',exp_range)

    tiny=[]
    for _ in range(args.samples):
        below=rng.randrange(2);n=rng.randrange(1,65537)*rng.choice((-1,1))
        fraction=53 if below else 52
        maximum=min(1<<(fraction-32),(1<<(fraction-28))//abs(n))
        delta=rng.randrange(1,maximum+1)
        tiny.append((bits(1.)+(-delta if below else delta),bits(float(n))))
    for n in (-65536,-1024,-17,-3,-1,1,3,17,1024,65536):
        for below in (False,True):
            fraction=53 if below else 52
            boundary=min(1<<(fraction-32),(1<<(fraction-28))//abs(n))
            for delta in (1,2,3,boundary-1,boundary,boundary+1):
                tiny.append((bits(1.)+(-delta if below else delta),bits(float(n))))
    qualify('tiny_integer','_ZN12compact_math3powEdd',tiny)

    near_large=[]
    for _ in range(args.samples):
        below=rng.randrange(2);p=53 if below else 52
        delta=rng.randrange(1,(1<<(p-36))+2)
        a=bits(1.)+(-delta if below else delta)
        y=math.ldexp(rng.uniform(1,2),rng.randrange(19,66))
        near_large.append((a,bits(y*rng.choice((-1,1)))))
        near_large.append((a|(1<<63),bits(float(round(y))*rng.choice((-1,1)))))
    for below in (False,True):
        p=53 if below else 52
        for delta in (1,2,17,128,(1<<(p-36))-1,1<<(p-36),(1<<(p-36))+1):
            a=bits(1.)+(-delta if below else delta)
            for ey in (19,20,31,32,40,41,52,53,63,64,65):
                for sign in (-1,1):
                    y=bits(math.ldexp(float(sign),ey))
                    near_large.extend(((a,y),(a|(1<<63),y)))
    qualify('near_one_large_exponent','_ZN12compact_math3powEdd',near_large)

    signed=[(bits(-math.ldexp(rng.uniform(1,2),rng.randrange(-900,900))),
             bits(float(rng.randrange(-32,33)))) for _ in range(args.samples)]
    for _ in range(args.samples):
        a=bits(1.)+rng.choice((-1,1))*rng.randrange(1,1<<36)
        signed.append((a|(1<<63),bits(float(rng.randrange(-65536,65537)))))
    qualify('negative_integer','_ZN12compact_math3powEdd',signed)

    bases=[bits(x) for x in (-0.,-.5,-1.,-2.,-2.**-1022,-float.fromhex('0x1.fffffffffffffp+1023'))]
    bases += [(1<<63)|a for a in (1,2,(1<<52)-1,bits(1.)-1,bits(1.)+1)]
    bases += [0xFFF0000000000000,0xFFF0000000000001,0xFFF8000000000013]
    exponents=[bits(0.),bits(-0.),bits(.5),bits(-.5),0x7FF0000000000000,
               0xFFF0000000000000,0x7FF0000000000001,0x7FF8000000000013]
    for value in (1.,2.,3.,17.,2.**31-1,2.**52-1,2.**52,2.**52+1,2.**53,2.**53+2):
        for sign in (1.,-1.):
            center=bits(value*sign)
            exponents.extend((center-1,center,center+1))
    qualify('signed_boundaries','_ZN12compact_math3powEdd',
            [(a,b) for a in bases for b in dict.fromkeys(exponents)])

    exact=[((rng.randrange(1,2047)<<52)|rng.getrandbits(52)|(rng.randrange(2)<<63),
            bits(rng.choice((1.,-1.,2.)))) for _ in range(args.samples)]
    # Squaring crosses both the subnormal rounding boundary and overflow.
    for exponent in (1,483,484,485,486,1533,1534,1535,1536,2046,2047):
        for fraction in (0,1,(1<<51),(1<<52)-1):
            for sign in (0,1<<63):
                exact.append(((exponent<<52)|fraction|sign,bits(2.)))
    qualify('exact_exponents','_ZN12compact_math3powEdd',exact)

    # Identities may bypass ordinary arithmetic only after handling sNaNs.
    for a,b in ((bits(1.),0x7FF0000000000001),(bits(1.),0xFFF0000000000001),
                (0x7FF0000000000001,bits(0.)),(0xFFF0000000000001,bits(-0.))):
        got=machine.call('_ZN12compact_math3powEdd',a,b)[0]
        assert nan(got) and got&(1<<51),(hex(a),hex(b),hex(got))
    for a,b in ((bits(1.),0x7FF8000000000013),
                (0x7FF8000000000013,bits(0.))):
        assert machine.call('_ZN12compact_math3powEdd',a,b)[0]==bits(1.)

    pending=struct.pack('<7I',17,3,0,0,5,2,3)
    for symbol,a,b in (('pow_rsqrt',bits(.7),bits(-.5)),
                       ('pow_refine_checked',bits(.123),bits(3.1)),
                       ('pow_refine_checked',bits(1.)-1,bits(2.**48)),
                       ('_ZN12compact_math3powEdd',bits(1.)-17,bits(-17.)),
                       ('_ZN12compact_math3powEdd',bits(-1.1),bits(-1.)),
                       ('_ZN12compact_math3powEdd',bits(-.9999999999999),bits(-17.)),
                       ('_ZN12compact_math3powEdd',bits(-3.14),bits(2.))):
        machine.uc.mem_write(0xD0000060,pending)
        assert machine.call(symbol,a,b)[0]==oracle.reference('pow',a,b)
        assert bytes(machine.uc.mem_read(0xD0000060,len(pending)))==pending
    assert elf_sha==hashlib.sha256(args.elf.read_bytes()).hexdigest()
    result=dict(status='PASS',operations=reports,elf_sha256=elf_sha,mpfr=oracle.version,
        maximum_stack_bytes=SP-machine.stack_lowest,pending_divider_checks=7,nan_identity_checks=6,
        oracle='Directed MPFR bounds, rounded to binary64 RNE; every ARM call verifies R4-R11, SP and bounded stack writes.',
        scope='Finite targeted corpus. Full interval bounds are certified separately; universal fallback pow totality remains unproved.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
