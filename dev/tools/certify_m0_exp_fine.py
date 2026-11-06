#!/usr/bin/env python3
"""Rational enclosure for the RP2040 exp Q70 midpoint correction."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re

from certify_m0_exp_fast import certificate as fast_certificate


def certificate(root):
    h=F(7,10000)
    scale=1<<70
    square=scale*h*h/2
    cube=scale*h**3/2
    fourth=scale*h**4/24
    # square=floor(r^2/2*2^70); the cube uses square>>8 and r in Q50.
    cube_numerator_error=256*h+square/(1<<50)+1
    third_error=max(2*cube/(3*(1<<40)),1+cube_numerator_error/3)
    assert third_error<2
    fourth_error=1+(1+h*h*(1<<18))/6
    fifth_error=1+(1+fourth_error*h+fourth/(1<<31))/5
    omitted=scale*h**6/(720*(1-h))
    # The exact residual differs from its integer Q64 value by <8193/8192
    # units. The linear part is corrected separately; bound its effect on
    # exp(r)-1-r by |eta|*(exp(h)-1).
    actual_h=h+F(8193,8192*(1<<64))
    nonlinear_input_error=64*F(8193,8192)*actual_h/(1-actual_h)
    polynomial_error=1+third_error+fourth_error+fifth_error+omitted+nonlinear_input_error
    assert polynomial_error<6
    fast=fast_certificate()
    # The caller's delta has the sign of its integer residual, so "below"
    # also selects the sign of the cubic/fifth terms here. The old z is
    # within one unit of r^2*2^64. Its nonlinear correction is nonnegative
    # and smaller than |integer residual|. Below 2^32 the old z is1 and
    # the nonlinear correction is exactly zero.
    tail=h/6+h*h/24+h**3/120+F(3,1<<44)
    assert tail<F(1,8192)
    assert (h+F(1,1<<32))*(F(1,2)+F(1,8192))<1
    # Existing Q64 delta error is <5. The new correction differs by <6/64
    # Q64 units, so its Q16 integer magnitude is <6*65536.
    assert F(fast['scaled_error'])<5
    assert 2*(F(fast['scaled_error'])-F(5,2))<5
    assert square<1<<49 and square/256<1<<41
    assert h*(1<<50)<1<<40 and cube<1<<38
    assert square/(1<<18)<1<<31
    assert scale*h**4/4<1<<28
    assert fourth*h<65536
    assert 65535*0xCCCD<1<<32
    assert (1<<9)*(1<<8)<1<<32
    assert 64*0x5555<1<<32 and 64*0x5556<1<<32
    # Reciprocal constants compute exact integer divisions in the bounded
    # fourth/fifth numerators. Their upward error is below one residue step.
    assert F((1<<28)*0xAAAAAAAB,1<<34)-F(1<<28,6)<F(1,6)
    assert F(65535*0xCCCD,1<<18)-F(65535,5)<F(1,5)
    # Table Q94 and Q62 values are independently rounded; the fractional
    # row word is the signed Q32 correction of the Q62 table entry.
    coarse=(root/'code/native_eabi_m0_exp_table.inc').read_text()
    values=[int(x) for x in re.findall(r'UINT64_C\((\d+)\)',coarse)][1:]
    text=(root/'code/native_eabi_m0_refine_table.inc').read_text()
    block=text.split('refine_exp_table[512][3]={',1)[1].split('};',1)[0]
    rows=[tuple(map(int,m)) for m in re.findall(r'\{(\d+)U,(\d+)U,(\d+)U\}',block)]
    assert len(rows)==len(values)==512
    for i,(lo,middle,hi) in enumerate(rows):
        q=lo+(middle<<32)+(hi<<64)
        assert (2*q-1)**512<1<<(95*512+i)<(2*q+1)**512
        assert (q+(1<<31))>>32==values[i]
    # All terms below are in Q62 units. The last product rounds the Q16
    # correction once. The low partial product approximation loses <2^-15.
    residual_uncertainty=F(1,8192)
    table_cross=actual_h/(2*(1-actual_h))
    quantization=F(7,2*(1<<16))
    coefficient_truncation=F(6,1<<32)
    result_error=F(6,128)+residual_uncertainty/2+table_cross+quantization+F(1,1<<15)+F(1,1<<33)+coefficient_truncation
    assert result_error<F(3136,65536)
    sources={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in [
        'code/native_eabi_m0_exp_fine.inc','code/native_eabi_m0.cpp',
        'code/native_eabi_m0_exp_table.inc','code/native_eabi_m0_refine_table.inc']}
    return dict(status='PASS_RATIONAL_Q70_AND_MIDPOINT_ENCLOSURE',sources=sources,
                nonlinear_error_q70=str(polynomial_error),nonlinear_error_q70_float=float(polynomial_error),
                nonlinear_radius_q70=6,midpoint_error_q62=str(result_error),
                midpoint_error_q62_float=float(result_error),accepted_radius_q16=3136,
                table_rows_certified=512,new_tables_bytes=0,new_static_ram_bytes=0,
                domain='Existing exp caller: n!=0, unnormalized normal Q62 cells, |integer residual|<=0.0007*2^64. Other cases retain the old independent refinement.',
                semantics='Accept only when the entire strict enclosure lies on one side of the binary64 midpoint. Midpoints/undecided intervals fall back; no accuracy tolerance.',
                scope='Exact rational range/error argument and exact integer table certificates; source-pinned ARM implementation/oracle and ABI qualification are separate, not implied by these algebra checks.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    report=certificate(Path(__file__).resolve().parents[2])
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'],'nonlinear',report['nonlinear_error_q70_float'],
          'midpoint',report['midpoint_error_q62_float'], '<',3136/65536)


if __name__=='__main__':main()
