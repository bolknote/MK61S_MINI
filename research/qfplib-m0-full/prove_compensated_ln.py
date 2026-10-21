#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exact analytic bounds and integer model for compensated Q82 logarithms."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

from generate_ln_compensated import generate_compensation
from prove_checked_ln import greedy_bound

ROOT=Path(__file__).resolve().parent


def model(encoded,data=None):
    if data is None:data=generate_compensation()[1]
    fraction=encoded&((1<<52)-1);exponent=(encoded>>52)-1023
    if exponent==-1023:
        exponent=-1022
        while fraction<1<<52:fraction<<=1;exponent-=1
    else:fraction|=1<<52
    x=fraction<<9;y=0;correction=0;one=1<<62
    for i in range(1,19):
        new=x+((x+(1<<(i-1)))>>i)
        if new>=one:continue
        residual=x&((1<<i)-1)
        if residual&(1<<(i-1)):residual-=1<<i
        minus_rounding=residual<<(20-i)
        reciprocal=data['reciprocal_Q10'][(new>>53)-384]
        correction+=(minus_rounding*reciprocal)>>10
        row=data['log_rows'][i]
        y-=int(row['nearest_Q62'],16);correction+=row['delta_Q20']
        x=new
    n=exponent+1
    correction-=n*data['ln2_delta_Q20']
    base=y+x-one+n*int(data['log_rows'][0]['nearest_Q62'],16)
    deficit=one-x
    quadratic=deficit*deficit>>43
    a=(deficit+(1<<31))>>32
    cubic=a*a*a//(3*(1<<8))
    return (base<<20)+correction-quadratic-cubic,65536


def prove():
    _,data=generate_compensation()
    one=1<<62;low=one//2
    # Every accepted step produces x>=3/4. This validates the compact
    # reciprocal-table domain independently of random tests.
    minimum=one
    for i in range(1,19):
        minimum=min(minimum,low+((low+(1<<(i-1)))>>i))
        deficit=greedy_bound(62,i);low=one-deficit
    assert minimum>=3*(one//4)
    assert greedy_bound(62,18)<1<<44
    # The total correction includes -r/x and the table rounding errors.
    # Rounded reciprocals contribute at most |r|*Rerr; r is at most1/2.
    reciprocal=18*F(1,2)*F(data['reciprocal_error_bound'])*(1<<20)
    rounding_products=18
    table_floors=18
    ln2_floor=1073
    quadratic_floor=1
    # A=round(D/2^32), |D-A*2^32|<=2^31, D<2^44.
    # The cubic is floored at Q82 after applying the same approximation.
    d=F(1<<44);delta=F(1<<31)
    cubic=((d+delta)**3-d**3)/(3*(1<<104))+1
    relative=F(1,1<<18)
    quartic=relative**4/(4*(1-relative))*(1<<82)
    # -log(1-r/x) differs from r/x by an utterly smaller quadratic term.
    q=F(1,1<<63)/F(3,4)
    shift_second_order=18*q*q/(2*(1-q))*(1<<82)
    total=reciprocal+rounding_products+table_floors+ln2_floor+quadratic_floor+cubic+quartic+shift_second_order
    assert total<65536
    assert (18*F(2,3)*(1<<20)+18*(1<<19)+1073*abs(data['ln2_delta_Q20']))<1<<31
    # Narrow exact /3 used by the cubic: low/high16 products share0xAAAA.
    # Check every high16 value and both endpoints of each low16 range,
    # plus a full low16 sweep at the largest high value.
    def third(v):
        a=(v&65535)*0xaaaa;b=(v>>16)*0xaaaa
        carry=(a+(v&65535))>>16
        middle=a+b+(v>>16)+carry
        assert middle<1<<32
        return (b+(middle>>16))>>1
    cases=0
    for high in range(4097):
        for low in [0,1,65534,65535]:
            v=(high<<16)|low
            assert third(v)==v//3;cases+=1
    for low in range(65536):
        v=(4096<<16)|low;assert third(v)==v//3;cases+=1
    paths=[ROOT/'src/ln_comp96.inc',ROOT/'src/ln_comp_constants.inc',ROOT/'src/ln_checked.c']
    return dict(status='PASS',precision=82,steps=18,error=65536,
        rational_error_upper_bound=str(total),reciprocal_error_upper_bound=str(reciprocal),
        cubic_error_upper_bound=str(cubic),quartic_tail_upper_bound=str(quartic),
        accepted_minimum_Q62=minimum,third_integer_cases=cases,
        constants=data,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()},
        scope='Analytic all-mantissa error bounds and exact constants; ARM implementation and interval packing require separate execution qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--json',type=Path,required=True)
    args=p.parse_args();r=prove();args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(r,indent=2)+'\n');print('PASS: compensated Q82 ln error <65536 units')
