#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exact certificates for the experimental logarithm error intervals."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def greedy_bound(precision,steps):
    one=1<<precision;low=one//2
    for i in range(1,steps+1):
        def f(x):return x+((x+(1<<(i-1)))>>i)
        left,right=low,one
        while left<right:
            mid=(left+right)//2
            if f(mid)>=one:right=mid
            else:left=mid+1
        assert f(left)>=one and f(left-1)<one
        low=min(f(low) if low<left else low,left)
    return one-low


def prove():
    fast_deficit=greedy_bound(62,20)
    assert fast_deficit<1<<42
    # The omitted low23 residual bits vary monotonically inside every bin.
    # Both endpoint inequalities therefore cover all 2^42 possible deficits.
    for a in range(1,(1<<19)+1):
        high,low=divmod(a,1<<16)
        k=(high*high<<15)+high*low+(low*low>>17)+1
        assert k==(a*a>>17)+1
        first=(a-1)*(1<<23)+1;last=a*(1<<23)
        assert (k<<63)-last*last>0
        assert (k<<63)-first*first<9<<63
    d=F(1,1<<20)
    cubic=d**3/(3*(1-d))*(1<<62)
    assert cubic<9
    # Each accepted rounded multiply incurs <=1/(1-2^-P) fixed log units;
    # table entries are RNE (<=1/2 unit), proved by the constant generator.
    fast_base=F(20,1-F(1,1<<62))+10+9
    assert fast_base<64
    refinements=[]
    for w in [4,8]:
        precision=32*w-11
        deficit=greedy_bound(precision,24)
        assert deficit<1<<(precision-24)
        d=F(1,1<<24);count=7 if w==4 else 12
        tail=d**(count+1)/((count+1)*(1-d))*(1<<precision)
        product_error=1/(1-d)
        polynomial_error=sum((product_error/i+1 for i in range(2,count+1)),F(0))+tail
        greedy_error=24/(1-F(1,1<<precision))
        # Floor constants cost <24 units; the separate exponent ln2 floor
        # costs <|e+1| units. Precision-independent base96 covers all others.
        base=greedy_error+24+polynomial_error
        assert base<96
        refinements.append(dict(words=w,precision=precision,max_deficit=deficit,
                                series_terms=count,error_base_upper_bound=str(base),
                                series_tail_upper_bound=str(tail)))
    # Upstream ln2 split products stay signed32, including normalized
    # subnormal exponents. Check the exact signed96 reconstruction.
    pieces=[0x13de6b,0xfefa3,0xb1721]
    two=sum(v<<(21*i) for i,v in enumerate(pieces))
    assert two==0x2c5c85fdf473de6b
    for n in range(-1073,1025):
        assert all(-(1<<31)<=p*n<1<<31 for p in pieces)
        assert sum((p*n)<<(21*i) for i,p in enumerate(pieces))==two*n
    sources=[ROOT/'src/ln_fast96.inc',ROOT/'src/ln_checked.c',ROOT/'src/ln_constants.inc']
    return dict(status='PASS',fast_steps=20,fast_max_deficit=fast_deficit,
                quadratic_bins_checked=1<<19,quadratic_absolute_error_bound=9,
                fast_error_base=64,fast_error_bound='64+ceil(abs(e+1)/2) Q62',
                fast_base_rational_bound=str(fast_base),refinement=refinements,
                refinement_error_bound='96+abs(e+1) in Q117/Q245 units',
                ln2_exponent_products_checked=2098,
                source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                scope='Analytical bounds plus exact integer/rational checks; assembly/C execution is qualified separately. Final undecided Q245 interval remains a totality limitation.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--json',type=Path,required=True)
    args=p.parse_args();report=prove();args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: fast20 and Q117/Q245 rational error bounds')
