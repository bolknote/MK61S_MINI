#!/usr/bin/env python3
"""Exact rational error certificate for the Q94 logarithm refinement."""
import argparse
from fractions import Fraction as F
import json
from pathlib import Path


def certificate():
    scale=1<<94;h=F(1,2048);half=F(1,2)
    assert h-F(1,2049)>F(2,scale)
    # r96_product is the exact floor of the 96x96 product >>94: its
    # high-word carries reconstruct all words above discarded bit 93.
    # Rounding the reciprocal costs <1 unit and flooring costs <1.
    argument=2/(1-h)
    # h64=floor(h*2^64); the 30 discarded bits correct its square.
    square=2+F(1,1<<34)
    cube=3+h*square+scale*h*h/(1<<64)
    powers={3:cube}
    for n in range(4,8):
        powers[n]=3+h*powers[n-1]+scale*h**(n-1)/(1<<64)
    c3=F(6148914691236517206,1<<64)
    c5=F(3689348814741910324,1<<64)
    c6=F(3074457345618258603,1<<64)
    c7=F(2635249153387078803,1<<64)
    terms={n:3+c*powers[n]+abs(c-F(1,n))*scale*h**n
           for n,c in ((3,c3),(5,c5),(6,c6),(7,c7))}
    terms[4]=1+powers[4]/4
    remainder=scale*h**8/(8*(1-h))
    total=argument+half+(half+square/2)+sum(terms.values())+remainder
    assert total<128
    assert scale*h**2+square<1<<73
    for n,e in powers.items():assert scale*h**n+e<1<<64
    return dict(status='PASS',base_error=str(total),base_error_float=float(total),
        returned_base_interval_q94=128,exponent_error='abs(k)/2',
        square_error=str(square),cube_error=str(cube),
        scope='Full reciprocal/product quantization, corrected square, truncated h64 in higher powers, approximate high products, Taylor coefficients, table rounding and log series tail.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();report=certificate()
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
