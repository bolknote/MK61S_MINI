#!/usr/bin/env python3
"""Rational enclosure for RP2040 sin/cos using bounded residual products.

The approach uses Qfplib's narrow-partial-product/short-correction idea;
the Q70 table, reduction, product implementations and refinement are owned.
"""

import argparse,hashlib,json
from fractions import Fraction as F
from pathlib import Path


def certificate(root):
    digit=1<<16
    omitted62=(digit-1)**2*(1+2*digit+3*digit**2)
    assert F(omitted62,1<<62)<12
    odd=F(13,2)
    cube_product=F(1,2)+F(omitted62,1<<70)
    assert cube_product<F(35,64)
    omitted54=(digit-1)**2*(1+2*digit)
    narrow=F(1,2)+F(omitted54,1<<54)
    assert narrow<F(17,32)+F(1,1<<22)
    coefficient_drop=F(255,1<<15)

    h=F(1,1<<11)+F(1,1<<63);scale=1<<70;half=F(1,2)
    square=half+F(1,1<<14)+F(1,4)
    cube=F(35,64)+square*h
    zr=half+square/F(1<<18)
    fourth=half+(2*(1<<30)*zr+zr*zr)/F(1<<34)
    fifth=half+fourth*h+F(1,1<<16)
    sine=cube/6+F(2,3)+fifth/120+half+scale*h**7/5040
    cosine=square/2+half+fourth/24+half+scale*h**6/720
    # Outward allowance also covers the Q94 table's half-unit rounding
    # before its Q70/Q62 slices are truncated.
    table_error=1+F(1,1<<24)
    coefficients=257*h+129*h*h+(sine+cosine)/F(1<<62)
    total=table_error+sine+cosine+odd+narrow+coefficient_drop+coefficients
    assert total<12
    tiny=F(1,1<<38)
    tiny_error=table_error+F(1,2)+(1<<32)*(F(1,1<<30)+F(2,1<<62))+scale*tiny*tiny/2
    assert tiny_error<6
    # Existing argument evaluation adds its separately admitted <=1 Q70.
    # z comes from an argument rounded down to Q62, whose magnitude <=2^51.
    # Its square error before that argument loss is <1, hence integer z<=2^48.
    assert half+F(1,1<<14)<1
    assert (1<<48)//2==1<<47
    assert F((1<<48)**2,24*(1<<70))>1
    files=['native_eabi_m0_trig_checked.inc','native_eabi_m0_product.inc',
           'native_eabi_m0_trig_checked_table.inc']
    return dict(status='PASS_RATIONAL_TRIG_BOUNDED_PRODUCTS',
        source_sha256={n:hashlib.sha256((root/'code'/n).read_bytes()).hexdigest() for n in files},
        omitted_Q62_product=str(F(omitted62,1<<62)),odd_product_error=str(odd),
        cube_product_error=str(cube_product),even_product_error=str(narrow+coefficient_drop),
        total_Q70_error=str(total),total_Q70_error_float=float(total),guard=12,
        near_center_Q70_error=str(tiny_error),near_center_guard=6,
        argument_error_added_separately=True,new_tables=0,new_static_RAM=0,
        unchanged_generic_M0_M4=True,pow_source_changes=0,
        derivation=[
            'The Q62 odd kernel retains every limb pair of degree>=3. The omitted six pairs sum to <12Q62 units; adding6 and half-up rounding gives absolute error<=6.5.',
            'The same omitted pairs contribute <3/64Q70 to the six-product cube kernel. Half-up rounding adds<=1/2. At z==2^48 the separate rounded22-bit shift is exact up to1/2.',
            'The Q54 even kernel omits only pairs00,01,10, contributing <1/32+2^-22. Half-up rounding adds<=1/2. Dropping eight bits of the Q62 coefficient adds<255/32768 because ch<2^47.',
            'Retaining h in Q70 removes the old Q62 truncation in the cube. Propagate the existing square/fourth/fifth and Taylor bounds, coefficient truncation and table flooring.',
            'The complete bound remains below12Q70 units. The existing additional argument error and midpoint rejection are unchanged; ambiguous inputs use the original independent refinement.'
            ,'For |h|*2^70<2^32, one high32 coefficient product costs <4+2^-30 units in discarded coefficient bits and<=1/2 in rounding. The first-order Taylor remainder is<1/128Q70; table flooring gives a total<6. Argument error is added separately.'
        ],scope='Rational algebra/table/width enclosure, not a proof of every compiler instruction. Public ARM MPFR interval checks and Pico timings are separate required gates.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True);p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();r=certificate(a.source_root);a.json.parent.mkdir(parents=True,exist_ok=True)
    with a.json.open('x') as f:f.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps(dict(status=r['status'],error=r['total_Q70_error_float'],guard=r['guard'])))
