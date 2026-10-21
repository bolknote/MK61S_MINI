#!/usr/bin/env python3
"""Certify the checked M0 asin/acos geometry using exact rational bounds."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re

from certify_m0_atan_fast import certificate as atan_certificate


def verify_atan_table(path):
    source=path.read_text()
    def bounds(x):
        if x>F(1,2):
            a,b=bounds(F(1,2));c,d=bounds((2*x-1)/(2+x))
            return a+c,b+d
        lo=sum(((-1)**k*x**(2*k+1)/(2*k+1) for k in range(120)),F(0))
        return lo,lo+x**241/241
    def check(words,lo,hi):
        q=sum(v<<(32*j) for j,v in enumerate(words))
        assert F(2*q-1,2)<lo*(1<<70) and hi*(1<<70)<F(2*q+1,2)
    body=re.search(r'refine_atan_table\[65\]\[3\]=\{(.*?)\};',source,re.S)[1]
    rows=[list(map(int,re.findall(r'(\d+)U',row))) for row in re.findall(r'\{(.*?)\}',body)]
    assert len(rows)==65 and all(len(row)==3 for row in rows)
    for j,row in enumerate(rows):check(row,*bounds(F(j,64)))
    half=re.search(r'refine_atan_half_pi\[3\]=\{(.*?)\};',source)[1]
    a,b=bounds(F(1,5));c,d=bounds(F(1,239))
    pi_lo,pi_hi=8*a-2*d,8*b-2*c
    check(list(map(int,re.findall(r'(\d+)U',half))),pi_lo,pi_hi)
    rounded_half_pi=F(0x1921FB54442D18,1<<52)
    tiny=F(1,1<<56)/(1-F(1,1<<112))
    assert rounded_half_pi-F(1,1<<53)<pi_lo-tiny
    assert pi_hi+tiny<rounded_half_pi+F(1,1<<53)
    return dict(status='PASS',entries=66,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                method='Exact alternating rational atan bounds and Machin half-pi identity; every Q70 cell verified strictly.',
                special_results='asin(+/-1)=+/-RNE(pi/2); acos(1)=+0; acos(-1)=RNE(pi); |x|<2^-56 implies acos(x)=RNE(pi/2). Binary64 pi/2=0x3FF921FB54442D18, pi=0x400921FB54442D18.')


def certificate():
    r=1<<63
    u=F(1,1<<53)
    # RNE of N*2^-126, followed by RNE sqrt. The integer seed is exact.
    assert (1+u)**3 < (1+2*u)**2
    assert (1-u)**3 > (1-2*u)**2
    seed_error=4096
    assert 2*u*r < seed_error
    # Normalization makes 2^62<=g<=2^63 and permits a fixed 47-bit shift.
    newton_error=F(seed_error**2,1<<63)
    quotient_error=F(seed_error+1,32768)+newton_error
    assert quotient_error < F(126,1000)
    assert seed_error*2*r//(1<<48) < 1<<29
    # After flooring the one-SIO quotient, q is within two integer steps
    # of floor(sqrt(N)); the third loop iteration checks the postcondition.
    assert 1+quotient_error < 2

    # The index uses floor(n/2^31)/floor(d/2^47), then RNE to a /64 grid.
    index_error=F(1,2)+max(F(64,32768),F(1,1024)+F(1,1024*32768))
    assert index_error < F(503,1000) < 1
    # Thus |64*n-index*d|<d<2^63: its signed low word is exact.
    # Scale (64*residual,denominator) by 2^-7. The numerator loses at most
    # 1/2 and the denominator less than1. With nn<dd/2 and dd>=2^61:
    truncation=F(1<<64,1<<61)*(F(1,2)+F(1,2))
    estimate_bound=1+quotient_error
    assert estimate_bound<F(1126,1000)
    # A subsequent right shift adds less than one unit. With a nonzero
    # shift the estimate's error is halved, so final |deltaY|<2 Q63 units.
    assert max(estimate_bound,1+estimate_bound/2)<2
    assert F(1,4096)+F(r-2,r)**2>1  # Y remains belowr on the first tier
    assert F(1,4)+(F(1,2)+F(2,r))**2<1  # max(X,Y)>=r/2
    # atan2 angle difference has determinant X*deltaY and dot product
    # r^2+Y*deltaY. This bounds its absolute Q70 contribution per X-bin.
    for j in range(64):
        xmax=((j+1)<<57)-1
        assert F(2*xmax*(1<<70),r*r-2*r)<4*(j+1)+1
    root_interval=4*64+1
    atan=atan_certificate()
    # Geometry uses direct high square/product, followed by a six-bit RNE
    # shift. Recompute the atan polynomial enclosure for those tighter
    # square and slightly wider cube errors.
    h=F(1,128);q70=1<<70;half=F(1,2)
    square=half+F(1,64)
    cube=half+F(3,64)+h*square
    fifth=(half+h*h*cube+h**3*square+cube*square/q70+
           ((1<<17)-1)*(q70*h*h+square)/q70+
           ((1<<24)-1)*(q70*h**3+cube)/q70)
    seventh=(half+h*h*fifth+h**5*square+fifth*square/q70+
             7*(q70*h*h+square)/q70+
             ((1<<24)-1)*(q70*h**5+fifth)/q70)
    c5=F(0xCCCCCCCD,1<<31);c7=F(2454267027,1<<34)
    fifth_term=fifth/5+F(7,5)+(c5-F(8,5))*(q70*h**5+fifth)/8+half
    seventh_term=c7*seventh+max(3*c7+(c7-F(1,7))*q70*h**7,1-3*c7)
    polynomial=(F(atan['ratio_error'])+half+1+half+cube/3+
                fifth_term+seventh_term+q70*h**9/(9*(1-h*h)))
    main=polynomial+truncation+root_interval+F(1,2)
    assert polynomial+truncation+F(1,2) < 62
    assert main < 319
    # An undecided geometry cell can replace the floor-root enclosure by
    # its residual correction. In the non-small-angle branch Y>2^63/65.
    assert 4097*(F(1,65)+F(1,r))**2 < 1
    nonlinear=(1<<70)*(F(65,2*r*r)+F(1,r*(r-1))+F(1,3*(r-1)**3))
    assert nonlinear < F(1,1<<40)
    # floor(R/Y*2^15), using top16 denominator bits and one SIO division,
    # differs by <4. Quantizing X/2^63 to Q16 and final RNE add <1 Q70.
    root_correction=(F(1,2)+64*F(4,1<<15)+
                     64*(2+F(65,r)+F(4,1<<15))/(1<<16)+nonlinear)
    assert root_correction < 1
    refined=F(atan['refinement_error'])+truncation+root_correction+F(1,2)
    assert refined < 32

    # Shared small-angle powers in Q62, |x|<1/64. exp_high_product loses
    # <3 before shifting by at least12. Each inline Q62 product loses<=2.5.
    s=1<<62
    z=F(1,4096)
    errors=[F(1,2)+F(3,4096)]
    for power in range(2,5):
        errors.append(F(5,2)+z*errors[-1]+z**(power-1)*errors[0]+errors[-1]*errors[0]/s)
    for power,error in enumerate(errors,1):
        assert s*z**power+error < 1<<(51-12*(power-1))
    coefficients=(F(1,6),F(3,40),F(5,112),F(35,1152))
    words=(768614336404564651,345876451382054093,205878840108365531,140111988407082098)
    for c,word in zip(coefficients,words):
        assert abs(F(word)-s*c) <= F(1,2)
    factor_error=sum(c*error+F(5,2)+(s*z**power+error)/(2*s)
                     for power,(c,error) in enumerate(zip(coefficients,errors),1))
    asin_tail=F(1<<63)*F(63,2816)*z**5/(1-z)
    small_asin=2*factor_error+F(5,2)+asin_tail
    assert small_asin < 32
    assert F(1,6)*F(1,1<<54)/(1-F(1,1<<54)) < F(1,1<<54)

    # If floor(sqrt(N))<X/64 then X>255/256*2^63. The normalized
    # floor-root, dropping one bit and the exact quotient cost <4 Q63.
    assert F(255,256)**2+(F(255,256*64)+F(2,r))**2 < 1
    input_error=1+(1+estimate_bound)*F(256,255)
    assert input_error < 4
    assert s*z**3+errors[2] < 1<<27
    assert s*z**4+errors[3] < 1<<15
    # Reciprocal division gives exact floors, then exact RNE for odd7/9.
    assert F(2454267027,1<<34)-F(1,7) == F(5,7*(1<<34))
    assert F(5*(1<<27),7*(1<<34)) < F(1,7)
    assert F(954437177,1<<33)-F(1,9) == F(1,9*(1<<33))
    assert F(1<<15,9*(1<<33)) < F(1,9)
    atan_factor=(errors[0]/3+F(1,3)+errors[1]/5+F(5,2)+
                 (s*z*z+errors[1])/(2*s)+errors[2]/7+F(3,7)+errors[3]/9+F(4,9))
    small_atan=4+2*atan_factor+F(5,2)+F(1<<63)*z**5/11
    assert small_atan < 24
    # Converting a relative angle to Q70 shifts left by at most one;
    # otherwise RNE costs<=1/2. Include two half-pi table roundings.
    assert max(2*32,2*24)+F(1,2)+1 < 128
    return dict(status='PASS',root_seed_absolute_bound=seed_error,
        root_quotient_error=str(quotient_error),maximum_root_corrections=2,
        index_error=str(index_error),geometry_q70_error=str(main),
        geometry_q70_error_float=float(main),geometry_interval_q70_maximum=319,
        geometry_interval_rule='63+4*(floor(X/2^57)+1); no angle bias; exact floor root retained in refinement',root_estimate_error=str(estimate_bound),final_shifted_root_error_q63=2,
        refined_geometry_error=str(refined),refined_geometry_error_float=float(refined),
        refined_geometry_interval_q70=32,root_residual_correction_error=str(root_correction),
        small_asin_error=str(small_asin),small_asin_error_float=float(small_asin),
        small_asin_interval_q63=32,small_atan_error=str(small_atan),
        small_atan_error_float=float(small_atan),small_atan_interval_q63=24,
        folded_small_interval_q70=128,
        assumptions='RNE owned sqrt/pack; Q62 product enclosures; RNE Q70 atan/half-pi tables checked by their generator. Every returned binary64 cell must contain the complete interval; unresolved cells use CORE-MATH.',
        scope='Exact rational arithmetic bounds for the private checked asin/acos prototype. Finite MPFR tests and compiler/source/layout checks are recorded separately.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--json',type=Path,required=True)
    p.add_argument('--table',type=Path,default=Path(__file__).resolve().parents[1]/'code/native_eabi_m0_refine_table.inc')
    a=p.parse_args();report=certificate()
    report['atan_table']=verify_atan_table(a.table)
    a.json.parent.mkdir(parents=True,exist_ok=True)
    a.json.write_text(json.dumps(report,indent=2)+'\n')
    print({k:report[k] for k in ('status','geometry_q70_error_float','small_asin_error_float','small_atan_error_float')})


if __name__=='__main__':main()
