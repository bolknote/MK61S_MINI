#!/usr/bin/env python3
"""Rational error bounds for exp with compensated high64 products."""
import argparse
from fractions import Fraction as F
import json
from pathlib import Path
import re


def certificate():
    scale=1<<64;half=F(1,2);h=F(12912720851596686,scale)
    real_h=F(1,1400);r_error=1+F(1,8192)
    assert h+r_error/scale<real_h
    # A 32-bit significand head times the Q31 inverse ln2, rounded to n.
    inverse=0xB8AA3B29
    text=(Path(__file__).resolve().parents[1]/'code/native_eabi_m0_exp_table.inc').read_text()
    words=[int(x) for x in re.findall(r'UINT64_C\((\d+)\)',text)]
    low=int(re.search(r'exp_step_low=(\d+)U',text)[1])
    high,values=words[0],words[1:];assert len(values)==512 and 0<=low<1<<32
    lower=sum((F(2,(2*i+1)*3**(2*i+1)) for i in range(100)),F(0))
    upper=lower+F(2,201*3**201)*F(9,8)
    split=(high<<32)+low
    assert F(2*split-1,2)<lower*(1<<87)<upper*(1<<87)<F(2*split+1,2)
    assert F(2*inverse-1,2)<F(1<<31)/upper<F(1<<31)/lower<F(2*inverse+1,2)
    for i,v in enumerate(values):assert (2*v-1)**512<(1<<(63*512+i))<(2*v+1)**512
    segment_error=half+(F(1<<31)/lower+(1<<31))/(1<<44)
    assert segment_error*upper/512<real_h
    assert F(1,1<<11)<real_h
    nmax=(((1<<32)-1)*inverse+(1<<43))>>44
    assert nmax<1<<20
    # For e in [-10,9], d=21-e lies in [12,31]. The half-up bit
    # of p/2^(32+d) is in high32(p); low32(p) cannot change it.
    # ((high>>(d-1))+1)>>1 avoids both variable 64-bit shifts.
    # e=-11 uses high's top bit directly. Bound the old addition and
    # the new 32-bit addition too, so the algebra has no wraparound.
    assert ((1<<32)-1)*inverse+(1<<62)<1<<64
    for e in range(-11,10):
        high_shift=20-e
        assert 11<=high_shift<=31
        assert (((1<<32)-1)>>high_shift)+1<1<<32
    # The Q96 step is nearest: its error in n*step Q64 is <n/2^33.
    # Input truncation and step-product flooring have opposite signs.
    assert 1+F(nmax,1<<33)<r_error
    z_error=1
    assert scale*h*h+z_error<1<<44
    c=F(0xAAAAAAAB,1<<32)
    linear=c/2+abs(c-F(2,3))*scale*h/(1<<22)+half
    square_error=half+F(z_error,1<<23)
    q=F(0xAAAAAAAB,1<<33)
    quadratic=q*square_error+max(q+abs(q-F(1,3))*scale*h*h/(1<<23),1-q)
    # floor(z/2^32)*floor(t/2^16), rounded after >>17.
    ae=1+F(z_error,1<<32);be=1+F(1,1<<17)
    cubic=half+(ae*scale*h/(1<<38)+be*scale*h*h/(1<<32)+ae*be)/(1<<17)
    f=F(2185,1<<15)
    fifth=f*cubic+max(7*f+abs(f-F(1,15))*scale*h**3/(1<<23),1-7*f)
    coefficient=linear+quadratic+fifth
    assert coefficient<3
    vmax=h/6+h*h/24+h**3/120
    polynomial=(half+F(z_error,2)+
                coefficient*(scale*h*h+z_error)/(1<<44)+z_error*vmax+1+
                scale*h**6/(720*(1-h)))
    delta=polynomial+r_error/(1-real_h)
    total=2+half/(1-real_h)+delta/2
    assert isinstance(total,F)
    assert total<5
    assert scale*h/(1<<22)+half<1<<32
    assert ((scale*h*h+z_error)/(1<<32))*((scale*h/(1<<22)+half)/(1<<16))+(1<<16)<1<<32
    assert scale*(h/6+h*h/24+h**3/120)/(1<<20)+coefficient<1<<31
    return dict(status='PASS',coefficient_error=str(coefficient),coefficient_error_float=float(coefficient),
        scaled_error=str(total),scaled_error_float=float(total),returned_interval_q62=5,
        high64_error=2,square_high64_error=1,split_reduction_error=str(r_error),maximum_segment_index=nmax,
        segment_rounding_high_word_shift_range=[11,31],
        scope='Exact rational bounds for Q96 split reduction, Q44 polynomial quantization, Taylor tail, compensated high products and table rounding.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();d=certificate();a.json.parent.mkdir(parents=True,exist_ok=True)
    a.json.write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))


if __name__=='__main__':main()
