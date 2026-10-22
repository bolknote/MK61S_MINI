#!/usr/bin/env python3
"""Check normalized128-bit power enclosures and public RNE independently."""
import argparse
from fractions import Fraction as F
import hashlib,json,random,struct
from pathlib import Path
from native_eabi_m0_arm_self_test import Machine,SP,bits
from m0_mpfr_oracle import Oracle

ONE=0x3FF0000000000000
UNDECIDED=0x7FF8000000000000
SIGN=1<<63
MASK=(1<<64)-1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--bootrom',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=6000)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    m=Machine(args.elf,True,stack_bytes=16384,instruction_budget=200000000,bootrom=args.bootrom)
    assert all(name in m.elf.symbols for name in ('pow_integer128','pow_integer128_multiply','pow_integer128_boundary'))
    rng=random.Random(0x91128);oracle=Oracle();digest=hashlib.sha256()
    pa,pb=SP-15000,SP-14900
    multiplication_count=0
    for i in range(args.samples):
        a=rng.randrange(1<<127,1<<128);b=rng.randrange(1<<127,1<<128)
        if i%5==0:a&=~MASK
        if i%7==0:b&=~MASK
        ea,eb=rng.randrange(10000),rng.randrange(10000)
        if i%11==0:ea=eb=0
        m.uc.mem_write(pa,struct.pack('<QQiI',a>>64,a&MASK,0,ea))
        m.uc.mem_write(pb,struct.pack('<QQiI',b>>64,b&MASK,0,eb))
        # Deliberately alias both operands for every third square.
        if i%3==0:b=a;eb=ea
        m.call('pow_integer128_multiply',pa,pa if i%3==0 else pb,32)
        hi,lo,ex,error=struct.unpack('<QQiI',m.uc.mem_read(pa,24))
        q=(hi<<64)|lo
        scale=F(2)**(ex-127)
        lower=F((a-ea)*(b-eb),1<<254)
        upper=F((a+ea)*(b+eb),1<<254)
        assert F(q-error)*scale<=lower<=upper<=F(q+error)*scale,(i,a,b,ea,eb,ex,error)
        assert 1<<127<=q<1<<128 and ex in (0,1)
        digest.update(struct.pack('<QQiI',hi,lo,ex,error));multiplication_count+=1
    cases=set()
    fractions=(0,1,(1<<31)-1,1<<31,(1<<52)-2,(1<<52)-1)
    for field in (1,2,511,512,1017,1022,1023,1024,1025,1029,1533,2045,2046):
        for fraction in fractions:
            x=(field<<52)|fraction
            for n in range(1,33):
                for inverse in (False,True):cases.add((x,bits(float(-n if inverse else n))))
    for _ in range(args.samples):
        field=rng.choice((rng.randrange(1,2047),rng.randrange(1019,1028)))
        x=(field<<52)|rng.getrandbits(52);n=rng.randrange(1,33)
        cases.add((x,bits(float(n if rng.getrandbits(1) else -n))))
    for x in (0,1,(1<<52)-1,0x7FF0000000000000,0x7FF0000000000001,ONE|SIGN):
        for y in (bits(3.0),bits(-4.0),bits(.5),0,SIGN,0x7FF0000000000000):cases.add((x,y))
    for x in (ONE-1,ONE+1,bits(1.7),bits(.6)):
        for y in (bits(.5),bits(2.5),bits(32.5),bits(33.),bits(64.),bits(-.5)):cases.add((x,y))
    hard=json.loads((Path(__file__).resolve().parents[1]/'research/m0-pow-checked-20261022/hard-pow-inputs.json').read_text())
    for group in hard['groups']:
        cases.update((int(c['a'],16),int(c['b'],16)) for c in group['cases'])
    accepted=declined=public=0;extrema=[None,0]
    for i,(x,y) in enumerate(sorted(cases)):
        got=m.call('pow_integer128',x,y)[0]
        if got==UNDECIDED:declined+=1
        else:
            expected=oracle.reference('pow',x,y)
            assert got==expected,(hex(x),hex(y),hex(got),hex(expected))
            accepted+=1;digest.update(struct.pack('<3Q',x,y,got))
            if i%37==0:
                _,_,count=m.call('pow_integer128',x,y,count=True)
                extrema[0]=count if extrema[0] is None else min(extrema[0],count)
                extrema[1]=max(extrema[1],count)
        if i%29==0:
            expected=oracle.reference('pow',x,y)
            got=m.call('_ZN12compact_math3powEdd',x,y)[0]
            if expected&0x7FFFFFFFFFFFFFFF>0x7FF0000000000000:
                assert got&0x7FFFFFFFFFFFFFFF>0x7FF0000000000000
            else:assert got==expected,(hex(x),hex(y),'public',hex(got),hex(expected))
            public+=1
    assert accepted>1000 and declined>1000 and public>100
    result=dict(status='PASS',multiply_interval_cases=multiplication_count,power_cases=len(cases),
        accepted_power_results=accepted,declined_power_results=declined,public_mpfr_calls=public,
        helper_instruction_extrema=extrema,wrong_rounding=0,result_sha256=digest.hexdigest(),
        elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),bootrom_sha256=m.bootrom_sha256,
        test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Actual ARM normalized128-bit products, including aliasing squares, are checked against independent exact Fraction products of both operand intervals. Every accepted integer/inverse-power result matches directed MPFR; selected full public calls check integration. Base exponents, full mantissas, both exponent signs, exceptional inputs, declined exponent domains and the saved hard pow fixtures are covered. Finite tests supplement the algebraic certificate; no universal totality or physical-speed claim.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS:',multiplication_count,'exact interval products;',len(cases),'powers;',accepted,'accepted;',
          declined,'declined;',public,'public MPFR calls; instructions',extrema)


if __name__=='__main__':main()
