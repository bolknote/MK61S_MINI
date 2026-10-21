#!/usr/bin/env python3
"""Certify the integer atan reduction and Q70 polynomial with exact rationals."""
import argparse
from fractions import Fraction as F
import json
from pathlib import Path


def certificate():
    scale=1<<70;half=F(1,2);h=F(1,128)
    first=8+half+F(1,1<<14)
    second=first*first/(1<<30)+half+F(1,1<<22)
    assert first<9 and second<F(500001,1000000)
    # For d.high > 2^31 this also forces the integer Q31 estimate below
    # 2^31. At d.high == 2^31 both Newton steps are exact.
    assert F(1<<62,(1<<31)+1)+second<1<<31
    coarse=second+1
    reciprocal=4*coarse*coarse+3
    ratio=F(13,2)+2*reciprocal
    assert reciprocal<13 and ratio<33
    cap=h-F(1,1<<24)
    assert h/(1+F(1,4096))<cap
    checked=0
    for e in range(7):
        for top in range(32768,65536):
            seed=(1<<30)//top
            index=(seed+(1<<(8+e)))>>(9+e)
            assert 1<=index<=64
            for s in (top<<37,((top+1)<<37)-1):
                numerator=abs((1<<(58-e))-index*s)
                denominator=(s<<6)+(index<<(52-e))
                assert numerator*cap.denominator<denominator*cap.numerator
                checked+=1
    # Halving the exceptional 65-bit denominator loses <1/2 Q70 unit.
    argument=ratio+half
    seeded_cap=cap+argument/scale
    assert seeded_cap<h
    square=half+F(13,512)
    cube=half+F(13,512)+h*square
    fifth=(half+h*h*cube+h**3*square+cube*square/scale+
           ((1<<17)-1)*(scale*h*h+square)/scale+
           ((1<<24)-1)*(scale*h**3+cube)/scale)
    seventh=(half+h*h*fifth+h**5*square+fifth*square/scale+
             7*(scale*h*h+square)/scale+
             ((1<<24)-1)*(scale*h**5+fifth)/scale)
    c5=F(0xCCCCCCCD,1<<31)
    fifth_term=fifth/5+F(7,5)+(c5-F(8,5))*(scale*h**5+fifth)/8+half
    c7=F(2454267027,1<<34)
    seventh_term=c7*seventh+max(3*c7+(c7-F(1,7))*scale*h**7,1-3*c7)
    third_term=half+cube/3
    tail=scale*h**9/(9*(1-h*h))
    total=argument+1+third_term+fifth_term+seventh_term+tail
    assert total<64
    # Every narrowed fixed-point operand fits its stated integer width.
    assert scale*seeded_cap<1<<63
    assert scale*seeded_cap**2+square<1<<56
    assert scale*seeded_cap**3+cube<1<<49
    assert scale*seeded_cap**5+fifth<1<<35
    assert scale*seeded_cap**7+seventh<1<<22
    assert (scale*seeded_cap)**2/(1<<62)+F(13,2)<1<<64
    # The existing exact-ratio refinement uses the <=2.5-unit inline
    # product, keeps terms through r^9/9, and floors the Q70 quotient.
    exact_square=half+F(5,512)
    exact_cube=half+F(5,512)+h*exact_square
    exact_fifth=half+F(5,512)+h*h*exact_cube+h**3*exact_square+exact_cube*exact_square/scale
    exact_seventh=half+F(5,512)+h*h*exact_fifth+h**5*exact_square+exact_fifth*exact_square/scale
    exact_ninth=half+F(5,512)+h*h*exact_seventh+h**7*exact_square+exact_seventh*exact_square/scale
    # exp_high_product omits <3 units from the real scaled product.
    e3=F(6148914691236517206,1<<64)
    e5=F(3689348814741910324,1<<64)
    e7=F(2454267027,1<<34)
    e9=F(7282,1<<16)
    exact_third_term=3+e3*exact_cube+abs(e3-F(1,3))*scale*h**3
    exact_fifth_term=3+e5*exact_fifth+abs(e5-F(1,5))*scale*h**5
    exact_seventh_term=e7*exact_seventh+max(3*e7+(e7-F(1,7))*scale*h**7,1-3*e7)
    exact_ninth_term=e9*exact_ninth+max(4*e9+(e9-F(1,9))*scale*h**9,1-4*e9)
    exact_tail=scale*h**11/(11*(1-h*h))
    exact_total=(1+half+1+exact_third_term+exact_fifth_term+
                 exact_seventh_term+exact_ninth_term+exact_tail)
    assert exact_total<16
    assert F(((1<<63)-8)**2,1<<62)+F(5,2)<1<<64
    return dict(status='PASS',selection_endpoint_checks=checked,
        reciprocal_error=str(reciprocal),ratio_error=str(ratio),
        polynomial_error=str(total),polynomial_error_float=float(total),
        returned_interval_q70=64,reduction_cap=str(cap),
        refinement_error=str(exact_total),refinement_error_float=float(exact_total),
        refinement_interval_q70=16,
        scope='Exact rational Newton, discarded-product, fixed-point rounding, table rounding, optional denominator truncation and atan-series bounds.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();report=certificate()
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
