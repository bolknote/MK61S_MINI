#!/usr/bin/env python3
"""Check public pow zero/square shortcuts against exact rational rounding."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine, SP, bits, real

SIGN=1<<63
INF=0x7ff0000000000000
QUIET=1<<51
ONE=0x3ff0000000000000
POW='_ZN12compact_math3powEdd'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--bootrom',type=Path)
    p.add_argument('--samples',type=int,default=20000)
    p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();assert a.samples>=0
    m=Machine(a.elf,True,stack_bytes=16384,bootrom=a.bootrom)
    rng=random.Random(0xA700052);digest=hashlib.sha256()
    # Every exponent and both input signs, including all square shortcut
    # thresholds, exact powers of two, short mantissas and full mantissas.
    fractions=(0,1,2,0xffff,0xffffffff,1<<32,(1<<52)-2,(1<<52)-1,
               *(j<<49 for j in range(1,8)))
    values={(e<<52)|f|s for e in range(2047) for f in fractions for s in (0,SIGN)}
    values.update(rng.getrandbits(64) for _ in range(a.samples))
    # Adjacent representations around sqrt(2) exercise both product
    # normalizations throughout the binary64 exponent range.
    for e in range(2047):
        for d in (-1,0,1):
            x=(e<<52)+0x6a09e667f3bcd+d
            values.update((x,x|SIGN))
    for s in (0,SIGN):
        for payload in (0,1,2,1<<31,1<<32,1<<50,QUIET,QUIET+1,(1<<52)-1):
            values.add(s|INF|payload)
    pending=struct.pack('<7I',17,3,0,0,5,2,3)
    counts={'zero':0,'square':0,'reciprocal':0,'dirty_checks':0,
            'inverse_root_enclosures':0,'tight_inverse_root_enclosures':0}
    for x in sorted(values):
        magnitude=x&~SIGN
        zero=x|QUIET if magnitude>INF and not x&QUIET else ONE
        for y in (0,SIGN):
            got=m.call(POW,x,y)[0]
            assert got==zero,('zero',hex(x),hex(y),hex(got),hex(zero))
            digest.update(struct.pack('<4Q',x,y,got,zero));counts['zero']+=1
        if magnitude>INF:
            expected=x|QUIET
        elif magnitude==INF:
            expected=INF
        else:
            exact=Fraction(*real(x).as_integer_ratio())**2
            try:expected=bits(float(exact))
            except OverflowError:expected=INF
        got=m.call(POW,x,bits(2.))[0]
        assert got==expected,('square',hex(x),hex(got),hex(expected))
        digest.update(struct.pack('<4Q',x,bits(2.),got,expected));counts['square']+=1
        if magnitude>INF:expected=x|QUIET
        elif magnitude==INF:expected=x&SIGN
        elif not magnitude:expected=(x&SIGN)|INF
        else:
            exact=1/Fraction(*real(x).as_integer_ratio())
            try:expected=bits(float(exact))
            except OverflowError:expected=(x&SIGN)|INF
        got=m.call(POW,x,bits(-1.))[0]
        assert got==expected,('reciprocal',hex(x),hex(got),hex(expected))
        digest.update(struct.pack('<4Q',x,bits(-1.),got,expected));counts['reciprocal']+=1
    for e in (0,484,485,511,512,1023,1534,1535,2046,2047):
        for s in (0,SIGN):
            x=(e<<52)|s|1
            for y in (0,SIGN,bits(2.),bits(-1.)):
                m.uc.mem_write(0xD0000060,pending)
                m.call(POW,x,y)
                assert bytes(m.uc.mem_read(0xD0000060,len(pending)))==pending
                counts['dirty_checks']+=1
    # The shared rational-seed entry is reached before touching SIO.
    # Exercise every short dyadic seed, signs and both normal-range edges.
    for e in (1,1023,2044,2045):
        for j in range(8):
            for sign in (0,SIGN):
                x=(e<<52)|(j<<49)|sign
                m.uc.mem_write(0xD0000060,pending)
                exact=1/Fraction(*real(x).as_integer_ratio())
                expected=bits(float(exact))
                assert m.call(POW,x,bits(-1.))[0]==expected
                assert bytes(m.uc.mem_read(0xD0000060,len(pending)))==pending
                counts['dirty_checks']+=1
    # An integer inequality checks the mathematical enclosure directly,
    # independently of the seed/Newton implementation and of MPFR. Include
    # every table cell, exact centers and both sides of discarded-bit edges.
    table=[v for k,v in m.elf.symbols.items() if k.endswith('pow_rsqrt_seeds')]
    assert len(table)==1,table
    offsets=(0,1,2047,2048,2049,(1<<43)-2049,(1<<43)-2048,
             (1<<43)-1,1<<43,(1<<43)+1,(1<<43)+2048,(1<<44)-1)
    roots={(1<<52)+(cell<<44)+offset for cell in range(256) for offset in offsets}
    roots.update((1<<52)|rng.getrandbits(52) for _ in range(a.samples))
    m.uc.mem_write(0xD0000060,struct.pack('<7I',0,0,0,0,0,0,1))
    for significand in sorted(roots):
        for parity in (0,1):
            q=m.call('mk61_m0_pow_rsqrt_approx',significand,parity|(table[0]<<32))[0]
            target=1<<(178-parity)
            radius=24 if q&1 else 6
            assert (q-radius)**2*significand<target<(q+radius)**2*significand,(
                'inverse-root enclosure',hex(significand),parity,hex(q))
            digest.update(struct.pack('<4Q',significand,parity,q,target.bit_length()))
            counts['inverse_root_enclosures']+=1
            counts['tight_inverse_root_enclosures']+=int(radius==6)
    r=dict(status='PASS',counts=counts,elf_sha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        result_sha256=digest.hexdigest(),bootrom_sha256=m.bootrom_sha256,
        maximum_stack_bytes=SP-m.stack_lowest,
        oracle='Exact Python rational square/reciprocal rounded once to binary64, explicit NaN identity/quieting policy, and integer (q-radius)^2*M<2^(178-parity)<(q+radius)^2*M inverse-root enclosure, radius6 or24 from the actual tag. Every exponent, both signs, adjacent normalizations, randomized full mantissas, all inverse-root seed cells, AAPCS/SP and pending SIO preservation.',
        scope='Finite ARM qualification of pow shortcuts; not a universal pow totality proof or physical timing.')
    a.json.parent.mkdir(parents=True,exist_ok=True);a.json.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2),flush=True)


if __name__=='__main__':main()
