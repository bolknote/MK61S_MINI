#!/usr/bin/env python3
"""Check algebraic bounds for normalized128-bit integer/dyadic pow paths."""
import argparse
from fractions import Fraction as F
import hashlib,json
from pathlib import Path


def error_bound(n):
    error=0;degree=1
    for bit in range(n.bit_length()-2,-1,-1):
        error=0 if degree==1 else 2*(2*error+4)
        degree*=2
        if n&(1<<bit):error=2*(error+2);degree+=1
    assert degree==n
    return error


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--dyadic-source',type=Path)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args()
    text=args.source.read_text()
    for token in ('multiply(ah,bh)', 'multiply(al,bh).high', 'multiply(ah,bl).high',
                  'error+=al&&bl?4:(al||bl?2:(error?1:0))', 'if(n>32)',
                  'q.low<=q.error', 'q.low>=U(0)-U(q.error)'):
        assert token in text,token
    integers={n:error_bound(n) for n in range(1,33)}
    denominators={n:error_bound(n) for n in (1,2,4,8,16,32,64,128)}
    max_integer=max(integers.values());max_denominator=max(denominators.values())
    max_product=2*(max_integer+max_denominator+4)
    max_radius=1<<15
    assert max_integer==3508 and max_denominator==10920 and max_product==28864
    assert max_product<max_radius
    # For aH*bH+high(aL*bH)+high(aH*bL), the omitted positive
    # fractional cross sum plus aL*bL/2^128 is strictly below3.
    assert F(2*((1<<64)-1),1<<64)+F(((1<<64)-1)**2,1<<128)<3
    assert F(max_radius**2,1<<128)<1
    assert max_radius<1<<64
    # A two-binade exponent gap is conclusive even at enclosure endpoints.
    assert F((1<<128)-1+max_radius,4)<(1<<127)-max_radius
    # Right-shift alignment loses <1/2 unit, hence floor(error/2)+1
    # encloses either parity of an integer radius.
    assert all(F(e,2)+F(1,2)<=e//2+1 for e in range(2))
    assert -1022*32>=-(1<<31) and 1023*32+31<(1<<31)
    assert -1022*(32+128)>=-(1<<31) and 1023*(32+128)+159<(1<<31)
    sources=dict(integer=dict(path=str(args.source),sha256=hashlib.sha256(args.source.read_bytes()).hexdigest()))
    sqrt_cube_lemma=None
    if args.dyadic_source:
        text=args.dyadic_source.read_text()
        for token in ('distance>=2','distance<=-2','(a.error>>1)+1','(b.error>>1)+1',
                      'low>U(a.error+b.error)','coefficient>32','shift < -7',
                      'pow_dyadic128_boundary(power,denominator,inverse,hint-1)'):
            assert token in text,token
        sources['dyadic']=dict(path=str(args.dyadic_source),sha256=hashlib.sha256(args.dyadic_source.read_bytes()).hexdigest())
        if 'numerator==3 && denominator==2' in text:
            for token in ('!(yb&D::Sign)', '!square.error && !square.low',
                          'square.exponent==int(xb>>52)-1023', 'return bits(real(xb)*real(root))'):
                assert token in text,token
            sqrt_cube_lemma='A proposed positive binary64 root has an exact106-bit square in the normalized128-bit format. Equal exponent/significand and zero low/error certify root^2=x exactly. Thus x^(3/2)=x*root and one existing IEEE binary64 multiplication supplies RNE, including exact midpoint parity; no rounded-square equality is used.'
    result=dict(status='PASS_EXACT_RATIONAL_CERTIFICATE',sources=sources,
        positive_integer_exponents='1..32',dyadic_exponents='|p|<=32, q in1,2,4,8,16,32,64,128',
        integer_error_bounds=integers,denominator_error_bounds=denominators,
        maximum_composed_radius=max_product,certified_radius_limit_exclusive=max_radius,
        multiplication_identity='AB/2^128=aH*bH+(aL*bH+aH*bL)/2^64+aL*bL/2^128. The retained exact high products omit a positive tail<3. Input radii contribute <Ea+Eb+1; the code uses4, or smaller certified zero-low-word cases. Normalization scales the radius by at most2.',
        reciprocal_and_dyadic_acceptance='For positive x and midpoint m, sign(x^(p/q)-m)=sign(x^p-m^q); for a negative exponent it equals-sign(x^p*m^q-1). Only strict disjoint integer enclosures decide a side. Two adjacent strict midpoint sides certify a unique RNE cell, independently of the seed. Exact ties and overlapping enclosures decline to the existing path.',
        producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Exact rational tail/error inequalities, all discrete exponentiation-chain bounds, shift-alignment and exponent-width bounds. Source hashes bind the inspected algorithms. Independent ARM interval/MPFR tests must check compiled arithmetic and control-flow integration. No universal pow totality or physical-speed proof.')
    if sqrt_cube_lemma:result['exact_sqrt_cube_lemma']=sqrt_cube_lemma
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: normalized128-bit tail/error proof; max integer radius',max_integer,
          'denominator radius',max_denominator,'composed radius',max_product,'<',max_radius)


if __name__=='__main__':main()
