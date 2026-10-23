"""Source-bound classification and ARM checks of every constructed dyadic boundary.

The classification argument is universal; the executed cases are finite.
This does not prove a1024-bit gap for non-boundaries or remove any guard.
"""
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import sys
ROOT=Path.cwd();WORK=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tests'))
from native_eabi_m0_arm_self_test import Machine,SP,bits,real
base=ROOT/'.build/m0-pow-horner-final-v138-20261023'
elf=base/'firmware/mk61s-picocalc-pico-h.elf'
source=base/'source/code/native_eabi_m0_pow_interval.inc'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
text=source.read_text()
for anchor in ['if(roots>=6 || (uint32_t(e)&((1U<<roots)-1))) return false;',
    'if(y>>63) return false;', 'if(t[4] || t[5] || t[6] || t[7] || t[3]>=64) return false;',
    'if(word_product(uint32_t(r),uint32_t(r))!=a) return false;',
    'if(b>54) return false;',
    'if(x==one || !ym) {result=one;return true;}']:
    assert anchor in text,anchor
assert 3**34<1<<54<3**35
assert 3**32<1<<53<3**64
assert 1074*((1<<53)-1)<1<<64
assert (1<<27)**2>=(1<<53)-1
rng=random.Random(0x23102454)


def root_floor(n,k):
    lo,hi=0,1<<(math.ceil(n.bit_length()/k))
    while lo+1<hi:
        mid=(lo+hi)//2
        if mid**k<=n:lo=mid
        else:hi=mid
    return lo


def rounded(coefficient,scale):
    if not coefficient:return 0
    discarded=max(0,coefficient.bit_length()-53,-1074-scale)
    if discarded:
        retained=coefficient>>discarded
        rem=coefficient-(retained<<discarded);half=1<<(discarded-1)
        retained+=rem>half or (rem==half and bool(retained&1))
    else:retained=coefficient
    if not retained:return 0
    exponent=retained.bit_length()-1+scale+discarded
    if exponent>1023:return 0x7ff0000000000000
    if exponent< -1022:return retained<<(scale+discarded+1074)
    significand=retained<<(53-retained.bit_length())
    return ((exponent+1023)<<52)+(significand-(1<<52))


def exact_input(coefficient,scale):
    value=F(coefficient)*F(2)**scale
    try:x=float(value)
    except OverflowError:return None
    if not math.isfinite(x) or not x or F(x)!=value:return None
    return bits(x)


cases={};types={}
def add(x,y,want,description):
    if x is None:return
    assert 0<x<0x7ff0000000000000 and (y&0x7fffffffffffffff or description=='early_evaluate')
    assert 0<=y<1<<64 and (y&0x7fffffffffffffff)<0x7ff0000000000000
    key=(x,y)
    if key in cases:assert cases[key]['want']==want
    cases[key]=dict(want=want,kind=description)


# Construct every possible algebraic shape C^(p/q), sampling coefficient
# endpoints/interiors rather than pretending to enumerate all53-bit inputs.
for q in (1,2,4,8,16,32):
    for p in range(1,35):
        if math.gcd(p,q)!=1:continue
        maximum=min(root_floor((1<<53)-1,q),root_floor((1<<54)-1,p))
        if maximum<3:continue
        coefficients={3,5,7,maximum|1,(maximum-1)|1,(maximum-3)|1}
        for _ in range(3):coefficients.add(rng.randrange(1,(maximum+1)//2)*2+1)
        for c in sorted(coefficients):
            if not 3<=c<=maximum or not c&1:continue
            a,b=c**q,c**p
            scales={0,-q,q,-2*q,2*q,-31*q,31*q,
                    ((-1075*q)//p//q)*q,((-1075*q)//p//q+1)*q,
                    ((970*q)//p//q)*q,((970*q)//p//q+1)*q,
                    (-1022//p)*q,(1023//p)*q}
            for e in scales:
                x=exact_input(a,e)
                add(x,bits(p/q),rounded(b,e//q*p),'odd_positive_dyadic')
                if x is not None:
                    # A>1 and y<0 yields an odd denominator: never dyadic.
                    add(x,bits(-p/q),None,'odd_negative_not_boundary')

# Power-of-two bases include normal/subnormal and zero/overflow midpoints,
# large dyadic y, integer/noninteger e*y and negative exponents.
for e in (-1074,-1023,-1022,-537,-215,-43,-1,1,2,5,31,215,512,1023):
    x=exact_input(1,e)
    exponents={F(-1075),F(-1074),F(-1022),F(0),F(1),F(1023),F(1024),F(2048),F(-2048)}
    for target in exponents:
        y=target/e
        if y and y.denominator&(y.denominator-1)==0 and F(float(y))==y:
            add(x,bits(float(y)),rounded(1,int(target)),'power_of_two_boundary')
    for depth in (1,2,5,10,30,63,64,100,1074):
        for sign in (-1,1):
            y=F(sign,1<<depth)
            if not float(y):continue
            product=e*y
            add(x,bits(float(y)),rounded(1,int(product)) if product.denominator==1 else None,
                'power_of_two_fractional' if product.denominator!=1 else 'power_of_two_boundary')
    for y in (2.**60,2.**1023,-2.**60,-2.**1023):
        target_negative=(e<0)^(y<0)
        add(x,bits(y),0 if target_negative else 0x7ff0000000000000,'power_of_two_large_exponent')

# Rational54-bit shape does not by itself make an arbitrary base a perfect
# qth power. Include genuinely irrational roots and unsupported numerators.
for x in (1.1,1.5,3.,5.,7.,15.,math.ldexp(3.,-1023)):
    for y in (.5,.25,.125,1/64,-.5,-.75,35.,65.):
        add(bits(x),bits(y),None,'not_boundary')
for y in (1,0x8000000000000001,1<<52,0x8010000000000000,bits(1.),bits(-1.),bits(2.**100),bits(-2.**100)):
    add(bits(1.),y,bits(1.),'early_evaluate')
for x in (.5,1.5,3.,math.ldexp(1.,-1074)):
    for y in (0,1<<63):add(bits(x),y,bits(1.),'early_evaluate')

m=Machine(elf,True,stack_bytes=16384,instruction_budget=200000000,
          bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
ptr=SP-15000;digest=hashlib.sha256();outcomes={};examples={}
for index,((x,y),row) in enumerate(sorted(cases.items())):
    want=row['want'];kind=row['kind'];expected_accept=want is not None
    # Generated "not_boundary" rows are independently checked by the same
    # prime-power characterization before relying on their expected decline.
    if kind=='not_boundary':
        xn,xd=F(real(x)).as_integer_ratio();e=-(xd.bit_length()-1)
        while not xn&1:xn>>=1;e+=1
        yn,yd=F(real(y)).as_integer_ratio()
        if yn>0 and yd<=32 and e%yd==0:
            c=root_floor(xn,yd)
            if c**yd==xn and (c**yn).bit_length()<=54:
                want=rounded(c**yn,e//yd*yn);expected_accept=True
    results=[]
    for precision in (512,1024):
        operation='8evaluate' if kind=='early_evaluate' else '14exact_boundary'
        name=f'_ZN15m0_pow_interval5FixedILj{precision}EE{operation}EyyRy'
        m.uc.mem_write(ptr,b'\xa5'*8)
        accepted=m.call(name,x,y,c=ptr)[0]&0xffffffff
        actual=struct.unpack('<Q',m.uc.mem_read(ptr,8))[0]
        assert bool(accepted)==expected_accept,(index,precision,hex(x),hex(y),kind,accepted,expected_accept)
        if expected_accept:assert actual==want,(index,precision,hex(actual),hex(want))
        results.append((accepted,actual if accepted else 0))
    assert results[0]==results[1]
    outcomes[kind]=outcomes.get(kind,0)+1
    examples.setdefault(kind,dict(x=f'{x:016X}',y=f'{y:016X}',accepted=expected_accept,
        rounded=f'{want:016X}' if expected_accept else None))
    digest.update(struct.pack('<4Q',x,y,*results[0]))

record=dict(status='PASS_EXACT_DYADIC_BOUNDARY_CLASSIFICATION_AND_FINITE_ARM_CHECKS',
    theorem_obligation='Positive finite nonzero x and finite y: evaluate handles x==1/y==0 first. Direct exact_boundary is then used for x!=1 and y!=0; dyadic results have odd coefficient B<2^54. This includes every binary64 RNE midpoint, zero/subnormal and overflow thresholds.',
    algebraic_classification=['Write x=A*2^e with A odd,1<=A<2^53; write y=s*p/q reduced with q a power of2.',
        'For A>1 and s<0, x^y has a nontrivial odd denominator or is irrational, so it cannot be dyadic.',
        'For A>1 and s>0, dyadic equality forces q|e and A=C^q, by the2-adic and odd-prime valuations. The exact odd result coefficient is C^p.',
        'C>=3 and C^p<2^54 imply p<=34; C^q<2^53 and power-of-two q imply q<=32.',
        'Repeated exact square roots, e divisibility, and the54-bit capped integer product therefore recognize every such shape. No approximate logarithm is used.',
        'For A=1, x^y is dyadic iff e*y is an integer. Its product fits64 bits before the checked shift; large exponents clamp safely outside all rounding thresholds.',
        'Every RNE midpoint has a normalized odd coefficient of at most54 bits, including B*2^-1075 subnormal midpoints and (2^54-1)*2^970 at overflow.'],
    implementation_scope='Source-bound mathematical argument plus finite execution of both exact V138512/1024 recognizer bodies. Not a mechanized full compiler proof or a non-dyadic separation bound.',
    cases=len(cases),ARM_calls=2*len(cases),outcomes=outcomes,examples=examples,result_sha256=digest.hexdigest(),
    elf_sha256=sha(elf),source_sha256=sha(source),producer_sha256=sha(__file__),
    lowest_checked_write_offset_bytes=SP-m.stack_lowest,result_slot_offset_bytes=15000,
    stack_scope='The write low-water includes the intentional result slot atSP-15000; it is not a callee stack-use measurement.',
    conclusion='An exact dyadic rounding tie is handled before the interval refinement in both Fixed stages. The remaining general totality obligation is separation/termination for non-dyadic values, not a missing exact-tie branch.',
    candidate_changed=False,hardware_accessed=False,general_pow_totality_proved=False)
(WORK/'exact-boundary.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(dict(status=record['status'],cases=len(cases),ARM_calls=2*len(cases),outcomes=outcomes,
    result_slot_offset=record['result_slot_offset_bytes']),indent=2))
