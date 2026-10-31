#!/usr/bin/env python3
"""Rational certificates for RP2040 exp/atan reuse of first-pass values."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from certify_m0_exp_fast import certificate as exp_certificate
from certify_m0_atan_fast import certificate as atan_certificate
from generate_m0_log70_table import certificate as ln_certificate


def certify(source_root):
    exp=exp_certificate();atan=atan_certificate();ln=ln_certificate()
    real_h=F(1,1400);reduction=F(exp['split_reduction_error'])
    old_exp=F(exp['scaled_error'])
    polynomial=2*(old_exp-2-F(1,2)/(1-real_h))-reduction/(1-real_h)
    discarded_low_product=F(1,1<<15)
    exact_final=F(1,2)+F(1,2)/(1-real_h)+(polynomial+reduction/(1-real_h))/2+discarded_low_product
    tightened=F(1,2)+polynomial/2+F(27,32)/(1-real_h)+discarded_low_product
    assert exact_final<4 and tightened<3
    text=(source_root/'code/native_eabi_m0_refine_table.inc').read_text()
    begin=text.index('refine_exp_table[512][3]={');end=text.index('};',begin)
    rows=[tuple(map(int,row)) for row in re.findall(r'\{(\d+)U,(\d+)U,(\d+)U\}',text[begin:end])]
    assert len(rows)==512
    for index,(lo,mid,hi) in enumerate(rows):
        value=(hi<<64)|(mid<<32)|lo
        target=1<<(95*512+index)
        assert (2*value-1)**512<target<(2*value+1)**512
    assert (1<<20)+3<1<<32
    assert (1<<31)+(1<<31)+(1<<18)+2<1<<33
    assert (1<<31)+(1<<18)+2<1<<32
    assert (27<<27)>(1<<31)
    # A rejected old cell is within10 of512. The exact-product change
    # is at most2, doubled at most once, so the retained integer endpoint
    # and encoded exponent are unchanged while deciding its rounding bit.
    assert 0<512-10-4 and 512+10+4<1024

    h=F(1,128);scale=1<<70;half=F(1,2)
    square=half+F(13,512)
    cube=half+F(13,512)+h*square
    fifth=(half+h*h*cube+h**3*square+cube*square/scale+
           ((1<<17)-1)*(scale*h*h+square)/scale+
           ((1<<24)-1)*(scale*h**3+cube)/scale)
    seventh=(half+h*h*fifth+h**5*square+fifth*square/scale+
             7*(scale*h*h+square)/scale+
             ((1<<24)-1)*(scale*h**5+fifth)/scale)
    ninth=(half+h*h*seventh+h**7*(square+(1<<24)-1)+
           seventh*(square+(1<<24)-1)/scale)
    coefficient=F(7282,1<<16)
    ninth_term=coefficient*ninth+max(4*coefficient+(coefficient-F(1,9))*(scale*h**9+ninth),1-4*coefficient)
    old_tail=scale*h**9/(9*(1-h*h))
    new_tail=scale*h**11/(11*(1-h*h))
    old_argument=F(atan['ratio_error'])+half
    derivative=35*h*h
    quotient_error=1+F(35,1<<18)
    corrected=(F(atan['polynomial_error'])-old_argument-old_tail+
               quotient_error+half+derivative+ninth_term+new_tail)
    assert F(atan['ratio_error'])<33
    assert derivative<F(1,256)
    assert corrected<12
    assert 35*(1<<24)<1<<32
    assert 35*F(1,1<<18)<F(1,7000)
    assert scale*h**7+seventh<1<<22
    seeded_cap=F(atan['reduction_cap'])+(F(atan['ratio_error'])+half)/scale
    assert scale*seeded_cap**2+square<1<<56
    assert (1<<22)*((1<<32)-1)+(1<<45)<1<<64
    assert 260*7282<1<<32
    ln_main=F(ln['main_error'])-(F(ln['product46_error'])+1)/(1-F(1,2048))
    ln_near=F(ln['near_error'])
    assert ln_main<8 and ln_near<4
    files=['native_eabi_m0_exp_round.inc','native_eabi_m0_atan_correct.inc',
           'native_eabi_m0.cpp','native_eabi_m0_atan_fast.inc',
           'native_eabi_m0_exp_table.inc','native_eabi_m0_refine_table.inc','native_eabi_m0_log70.inc']
    hashes={name:hashlib.sha256((source_root/'code'/name).read_bytes()).hexdigest() for name in files}
    return dict(status='PASS_RATIONAL_CORRECTION_BOUNDS',source_sha256=hashes,
                exp=dict(parent=exp,exact_final_absolute_error=str(exact_final),exact_final_absolute_error_float=float(exact_final),
                         tightened_absolute_error=str(tightened),tightened_absolute_error_float=float(tightened),
                         checked_Q94_table_rows=512,strict_error_bounds=[4,3],midpoint_reject_radii=[3,2],
                         input_precondition='Tightened mode uses n!=0, which implies e>=-11 and exact input scaling; known table/reduction fractions bound the uncertainty sum below27/32.',
                         error_argument='One half unit for final-product half-up rounding plus<2^-15 from dropping low16-bit partial products; the existing polynomial bound; Q94-derived table distance and exact reduction low word. The uncertainty sum includes outward integer rounding and n/4 step error.'),
                atan=dict(parent=atan,quotient_estimate_error_exclusive=33,corrected_quotient_error_exclusive=str(quotient_error),
                          ninth_error=str(ninth_term),derivative_correction_error=str(derivative),
                          corrected_error=str(corrected),corrected_error_float=float(corrected),guard=12,
                          error_argument='Correct the approximate ratio using the exact128-bit remainder and a24-bit denominator head. Ratio error is below1+35/2^18; reuse the polynomial, compensate the linear term, add r^9/9. The old table/rounding bounds remain, with a new r^11 tail.'),
                ln=dict(parent=ln,RP_main_error=str(ln_main),RP_main_error_float=float(ln_main),parent_Q70_near_error=str(ln_near),
                        strict_main_error_bound=8,main_midpoint_reject_radius=7,
                        argument='RP2040 exact dyadic residual plus one has error<=1, replacing generic reciprocal/product error. Integer midpoint distances>=8 are safe. n*ln2 adds n/2 to the bound. The final RP2040 near-one implementation has a separate Q77 certificate; parent Q70 near bounds are retained only for provenance.'),
                new_tables=0,new_static_RAM=0,pow_algorithm_changed=False,
                scope='Algebraic rational/width/table certificate, not a machine-checked proof of C++, compiler or all-input implementation. Actual ARM tests remain required.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=ROOT)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();result=certify(args.source_root)
    args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],exp_uniform_error=result['exp']['exact_final_absolute_error_float'],
                         exp_tight_error=result['exp']['tightened_absolute_error_float'],atan_error=result['atan']['corrected_error_float'])))


if __name__=='__main__':main()
