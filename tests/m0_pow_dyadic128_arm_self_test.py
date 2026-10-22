#!/usr/bin/env python3
"""Check dyadic128 midpoint decisions and untrusted hints with exact powers."""
import argparse
from fractions import Fraction as F
import hashlib,json,random,struct
from pathlib import Path
from native_eabi_m0_arm_self_test import Machine,SP,bits,real
from m0_mpfr_oracle import Oracle

ONE=0x3FF0000000000000
UNDECIDED=0x7FF8000000000000
MASK=(1<<64)-1
MIN_NORMAL=0x0010000000000000
MAX_FINITE=0x7FEFFFFFFFFFFFFF


def enclosure(value,jitter):
    exponent=value.numerator.bit_length()-value.denominator.bit_length()
    if value<F(2)**exponent:exponent-=1
    scaled=value*F(2)**(127-exponent)
    center=scaled.numerator//scaled.denominator
    if not 1<<127<=center+jitter<1<<128:jitter=0
    exact=scaled.denominator==1
    error=abs(jitter)+(0 if exact else 1)
    center+=jitter
    return struct.pack('<QQiI',center>>64,center&MASK,exponent,error)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf',type=Path,required=True)
    parser.add_argument('--bootrom',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=2400)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    m=Machine(args.elf,True,stack_bytes=16384,instruction_budget=200000000,bootrom=args.bootrom)
    oracle=Oracle();rng=random.Random(0x92128);cases=set()
    for p in (1,3,7,15,31,32):
        for denominator in (1,2,4,8,16,32,64,128):
            for x in (ONE-1,ONE+1,bits(.5),bits(1.75),bits((2**18-1)/2**17)):
                for inverse in (False,True):
                    cases.add((x,bits(float(F(-p if inverse else p,denominator)))))
    for _ in range(args.samples):
        x=(rng.randrange(1018,1029)<<52)|rng.getrandbits(52)
        p=rng.randrange(1,33);denominator=1<<rng.randrange(8)
        cases.add((x,bits(float(F(-p if rng.getrandbits(1) else p,denominator)))))
    for _ in range(300):
        k=rng.randrange(1<<17,1<<26)|1
        root=F(k)*F(2)**rng.randrange(-400,401)
        x=bits(float(root*root))
        assert F(real(x))==root*root
        cases.add((x,bits(1.5)))
    root=F((1<<18)-1,1<<17)
    cases.add((bits(float(root*root)),bits(1.5)))
    hard=json.loads((Path(__file__).resolve().parents[1]/'research/m0-pow-checked-20261022/hard-pow-inputs.json').read_text())
    for group in hard['groups']:
        cases.update((int(c['a'],16),int(c['b'],16)) for c in group['cases'])
    power_ptr=SP-15000;accepted=declined=boundary_calls=boundary_decided=public=exact_ties=0
    digest=hashlib.sha256();counts=[]
    for index,(x,y) in enumerate(sorted(cases)):
        expected=oracle.reference('pow',x,y)
        yf=F(real(y));inverse=yf<0;yf=abs(yf)
        supported=yf.numerator<=32 and yf.denominator<=128
        hints={expected,expected-1,expected+1,ONE,0,0x7FF0000000000000}
        for hint in sorted(h for h in hints if 0<=h<1<<64):
            got=m.call('pow_dyadic128',x,y,c=hint)[0]
            if got==UNDECIDED:declined+=1
            else:
                assert supported and got==expected,(hex(x),hex(y),hex(hint),hex(got),hex(expected))
                accepted+=1;digest.update(struct.pack('<4Q',x,y,hint,got))
                if index%83==0:
                    _,_,n=m.call('pow_dyadic128',x,y,c=hint,count=True);counts.append(n)
        if supported and MIN_NORMAL+2<expected<MAX_FINITE-2:
            power=F(real(x))**yf.numerator
            image=enclosure(power,rng.randrange(-1000,1001))
            m.uc.mem_write(power_ptr,image)
            for cell in (expected-1,expected,ONE):
                midpoint=(F(real(cell))+F(real(cell+1)))/2
                other=midpoint**yf.denominator
                exact=1-power*other if inverse else power-other
                relation=(exact>0)-(exact<0)
                got=m.call('pow_dyadic128_boundary',power_ptr|(yf.denominator<<32),int(inverse),c=cell)[0]&0xFFFFFFFF
                got=got-(1<<32) if got>>31 else got
                assert got in (-1,0,1)
                assert not got or got==relation,(hex(x),hex(y),hex(cell),got,relation)
                if not relation:assert not got;exact_ties+=1
                boundary_calls+=1;boundary_decided+=got!=0
        if index%31==0:
            got=m.call('_ZN12compact_math3powEdd',x,y)[0]
            assert got==expected,(hex(x),hex(y),'public',hex(got),hex(expected))
            public+=1
    assert accepted>1000 and declined>1000 and boundary_decided>1000 and public>50
    result=dict(status='PASS',input_pairs=len(cases),accepted_hint_results=accepted,declined_hints=declined,
        exact_power_boundary_calls=boundary_calls,decided_boundaries=boundary_decided,
        exact_ties_correctly_declined=exact_ties,public_mpfr_calls=public,
        instruction_extrema=[min(counts),max(counts)],wrong_rounding=0,result_sha256=digest.hexdigest(),
        elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),bootrom_sha256=m.bootrom_sha256,
        test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Actual production ARM dyadic midpoint decisions checked with independently formed exact rational x^p and midpoint^q, including jittered valid input enclosures. Both exponent signs and denominator powers through128 are covered. Exact, adjacent, distant and invalid hints have no rounding authority; every accepted result matches directed MPFR. Selected full public calls check integration. This is finite coverage, not totality or physical-speed proof.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS:',len(cases),'pairs;',accepted,'accepted hints;',declined,'declines;',boundary_calls,
          'exact-power boundary calls;',public,'public MPFR calls; instructions',result['instruction_extrema'])


if __name__=='__main__':main()
