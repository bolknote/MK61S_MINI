#!/usr/bin/env python3
"""Rational error bounds for RP2040 tiny and Q70 sine refinements."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True);p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();source=a.source_root/'code/native_eabi_m0_trig_small_refine.inc'
    scale=1<<70;zmax=1<<58;z_error=F(5,4)
    square_error=2+F(1,1<<18)+(2*zmax*z_error+z_error*z_error)/scale
    cube_error=9+square_error*zmax/scale+F((zmax+z_error)**2*z_error,scale**2)
    factor_error=z_error/6+F(2,3)+3+F(1,1<<18)+square_error/120+F(1,2)+cube_error/5040
    relative=F(1,2)+F(3,64)+factor_error/128+F(1<<15,362880)
    tiny=F(1,2)+F(1,128)+F(1,120*(1<<45))
    assert relative<1 and tiny<1
    assert 315*0xD00D00D1-(1<<40)==299
    assert (1<<31)*299<1<<40
    assert ((1<<34)-1+2520)>>4<1<<31
    assert 0x0222222222222222==(1<<64)//120
    assert 3*0xAAAB-(1<<17)==1
    assert 257*0xAAAB<1<<32
    assert 257<1<<17
    max_high=(32768**3)>>32
    assert max((max_high+(3<<s))>>(s+1) for s in (4,6,8,10))<=257
    report=dict(status='PASS',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        q70=dict(domain='2^62<=q<2^63,-26<=e<=-6; physical argument=q*2^(e-63)',
          factor_error_Q70=str(factor_error),center_relative_Q63_error=str(relative),maximum_error_float=float(relative)),
        tiny=dict(domain='2^62<=q<=2^63,-30<=e<=-27',center_relative_Q63_error=str(tiny),maximum_error_float=float(tiny)),
        output_error='Strictly below1 relativeQ63 unit at the center; add the caller argument error using |sin derivative|<=1.',
        argument=[
          'Q70 z/square/cube truncation bounds are shared with the small-cosine certificate. The sine decrement factor is z/6-z^2/120+z^3/5040.',
          'The reciprocal for the rounded cube/5040 quotient is exact on its31bit input range. The truncated1/120 constant and high-product error contribute fewer than3+2^-18Q70 units.',
          'The final high product plus32, shifted by6, costs less than1/2+3/64 relativeQ63 units. Factor error is scaled by q/2^70<1/128.',
          'The omitted sine x^9 term contributes less than2^15/9! relativeQ63 units. The complete center error is below1.',
          'The tiny kernel uses the top16bits of q in its cubic correction. Omitted low words cost at most1/128 relativeQ63 unit at e=-27; the next term is below2^-45/120. Half-up rounding adds at most1/2.',
          'For both kernels, returning q-center_correction with error1+argument_error encloses the exact normalized sine. The existing RNE pack rejects any ambiguous cell.'
        ],scope='Exact rational bounds and integer-width checks; not exhaustive C++ verification. Actual ARM center values and public functions need independent MPFR tests.')
    a.json.parent.mkdir(parents=True,exist_ok=True);a.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status='PASS',q70_relative_error=float(relative),tiny_relative_error=float(tiny)),indent=2))


if __name__=='__main__':main()
