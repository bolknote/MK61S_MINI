#!/usr/bin/env python3
"""Generate project-owned sqrt/reciprocal coefficients for ARMv6-M binary64."""
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def coefficients():
    with localcontext() as context:
        context.prec = 100
        for index in range(512):
            step = Decimal(2 if index < 256 else 1) / 256
            middle = step * (Decimal(256 + (index & 255)) + Decimal('0.5'))
            root = middle.sqrt()
            scale = Decimal(1 << 31)
            values = (scale * root, scale * step / (2 * root),
                      -scale * step * step / (8 * middle * root),
                      scale / root, -scale * step / (2 * middle * root),
                      3 * scale * step * step / (8 * middle * middle * root))
            rounded = tuple(int(x.to_integral_value(rounding=ROUND_HALF_EVEN)) for x in values)
            s = Fraction(2 if index < 256 else 1, 256)
            m = s * Fraction(2*(256+(index & 255))+1, 2)
            squares = ((1 << 62)*m, (1 << 62)*s*s/(4*m),
                       (1 << 62)*s**4/(64*m**3), Fraction(1 << 62)/m,
                       (1 << 62)*s*s/(4*m**3), 9*(1 << 62)*s**4/(64*m**5))
            for v, exact in zip(rounded, squares):
                n = abs(v)
                assert (2*n-1)**2*exact.denominator <= 4*exact.numerator <= (2*n+1)**2*exact.denominator
                if 4*exact.numerator in ((2*n-1)**2*exact.denominator, (2*n+1)**2*exact.denominator):
                    assert n % 2 == 0
            yield rounded


def rounding_certificate(rows):
    """Bound seed and Newton error before the exact final correction."""
    assert max(abs(row[2]) for row in rows)<=5793
    assert max(abs(row[5]) for row in rows)<=12288
    # Taylor remainder, rounded coefficients, discarded coordinate bits,
    # the Q16 quadratic evaluation, and final fixed-point truncation.
    root=Fraction(3,2)+Fraction(7,8)+Fraction(1,2)+(1+Fraction(5793,65536))/2+1
    inverse=5+Fraction(7,8)+Fraction(1,4)+(1+Fraction(12288,65536))/2+1
    assert root<5 and inverse<8
    residual=2*(1<<32)*5+25
    assert residual<1<<36
    refined=(Fraction(17,32)+Fraction(25,2048)+Fraction(residual*8,1<<42)+
             Fraction(31*((1<<31)+8),1<<42)+Fraction(2,32))
    assert refined<1
    return {'root_seed_error_bound':str(root),'inverse_seed_error_bound':str(inverse),
            'refined_root_error_bound':str(refined),'exact_corrections_at_most':1}


def packed_coefficients(rows):
    def nearest_ratio(value,denominator):
        q,r=divmod(value,denominator)
        return q+int(2*r>denominator or (2*r==denominator and q&1))
    packed=[]
    for index,(a,b,c,d,e,f) in enumerate(rows):
        # Quantize the original independently certified coefficients. The
        # additional half-unit from their first rounding is included below.
        b4,c8=nearest_ratio(b,4),nearest_ratio(c,8)
        e4,f8=nearest_ratio(e,4),nearest_ratio(f,8)
        assert 0<=b4<1<<21 and -(1<<10)<=c8<0
        assert -(1<<20)<=e4<0 and 0<=f8<1<<11
        # Bias the last root cell down by one so the Q20 positive endpoint
        # stays in a word and the leaf needs no saturation branch.
        if index==255:a-=1
        packed.append((a,b4|((c8&0x7FF)<<21),d,(e4&0x1FFFFF)|(f8<<21)))
    # Coefficient error: c0 <=1/2, c1 <=5/2, c2 <=9/2,
    # giving <=1/2+5/4+9/8 = 23/8 at |coordinate|<=1/2.
    # The Q20 coordinate is rounded directly from the truncated Q32 cell
    # coordinate: |coordinate error| < 2^-21+2^-32. Two signed product
    # floors contribute <2 units to each seed.
    coefficient=Fraction(23,8)
    coordinate=Fraction(1,1<<21)+Fraction(1,1<<32)
    root=Fraction(3,2)+coefficient+(6000000+5800)*coordinate+(1+Fraction(5800,65536))/2+2
    inverse=5+coefficient+(4200000+12300)*coordinate+(1+Fraction(12300,65536))/2+2
    assert root<10 and inverse<13
    # For the last cell m>=511/128 and step=1/128. Its Q31 Taylor
    # remainder is <8/m^(5/2)<1/3. This saves more than the one-unit bias.
    assert Fraction(511,128)**5>576
    assert root-Fraction(3,2)+Fraction(1,3)+1<10
    residual=2*(1<<32)*10+100
    assert residual<1<<37
    # The three partial products undershoot the real signed high product
    # by <3 units. floor((product+9)/16) therefore has error <5/8.
    # Drop six residual bits so its signed high product still fits R0.
    refined=(Fraction(5,8)+Fraction(100,2048)+Fraction(residual*13,1<<42)+
             Fraction(63*((1<<31)+13),1<<42))
    assert refined<1
    return packed,{'root_seed_error_bound':str(root),'inverse_seed_error_bound':str(inverse),
                   'refined_root_error_bound':str(refined),'exact_corrections_at_most':1,
                   'root_endpoint_cell':255,'root_endpoint_bias':-1}


def main():
    rows = list(coefficients())
    rounding_certificate(rows)
    # Each Q16 block has a fixed positive root slope / negative inverse
    # slope. Check every block extremum in the two boundary segments.
    a,b,c = rows[255][:3]
    assert max(a+((b+((c*(t>>8))>>16))*t>>24)
               for t in range(-8388353,8388608,256)) < 1 << 32
    a,b,c = rows[256][3:]
    assert max(a+((b+((c*(t>>8))>>16))*t>>24)
               for t in range(-8388608,8388608,256)) <= 1 << 31
    packed,certificate=packed_coefficients(rows)
    def evaluate(index,t,inverse):
        row=packed[index];a,word=row[2:] if inverse else row[:2]
        c=word>>21
        if not inverse and c&1024:c-=2048
        c*=8
        b=word&0x1FFFFF
        if inverse and b&(1<<20):b-=1<<21
        b=b*4+((c*(t>>4))>>16)
        assert -(1<<23)<b<1<<23
        return a+(((b&4095)*t)>>20)+(((b>>12)*t)>>8)
    # The biased last cell stays in a word even at the Q20 RNE endpoint.
    assert max(evaluate(255,t,False) for t in range(-(1<<19),(1<<19)+1))<1<<32
    assert max(evaluate(256,t,True) for t in range(-(1<<19),(1<<19)+1))<=1<<31
    target = ROOT / 'code/native_eabi_m0_sqrt64_table.inc'
    target.write_text('// Generated by tools/generate_m0_sqrt64_table.py; project-owned data.\n'
                      '// Q31 midpoint quadratics packed into four words per row.\n'
                      '// Slopes are multiples of four, curvatures multiples of eight.\n' +
                      ''.join(' .word ' + ','.join(str(x) for x in row) + '\n'
                              for row in packed))


if __name__ == '__main__':
    main()
