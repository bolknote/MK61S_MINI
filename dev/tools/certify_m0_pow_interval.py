#!/usr/bin/env python3
"""Check rational invariants for the owned M0 pow interval refinement."""

import argparse
from fractions import Fraction as F
from math import ceil
from pathlib import Path
import json,hashlib,re
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--json',type=Path,required=True);a=p.parse_args()
ROOT=Path(__file__).resolve().parents[2]
lo=sum((F(2,(2*i+1)*3**(2*i+1)) for i in range(500)),F(0));hi=lo+F(2,1001*3**1001)*F(9,8)
text=(ROOT/'code/native_eabi_m0_pow_interval.inc').read_text();table=(ROOT/'code/native_eabi_m0_pow_interval_table.inc').read_text();words=[int(x) for x in re.findall(r'(\d+)U',table)]
v=sum(x<<(16*i) for i,x in enumerate(words));assert F(v,1<<1024)<lo<hi<F(v+1,1<<1024)
assert 65535**2+65535+65535==(1<<32)-1
assert F(1,1<<52)/(1+F(1,1<<52))>F(1,1<<53)
limit=800
assert 1024>limit and limit-1>1075*hi and limit-1>1024*hi
assert 1074*hi < 745
# The nearest binary64 below one is 1-2^-53, so its midpoint
# is 1-2^-54. Above one the corresponding midpoint is 1+2^-53.
# |y|<2^-64 gives -t <= exp(y*ln(x))-1 <= t/(1-t), with t<2^-54.
tiny_y_t=F(745,1<<64)
assert tiny_y_t < F(1,1<<54)
assert tiny_y_t/(1-tiny_y_t)<F(1,1<<53)
assert 3**64>1<<53 and 3**35>1<<54
inv=F(1512775,1<<20);inv_error=max(abs(inv-1/lo),abs(inv-1/hi));assert inv_error<F(1,1<<21)
rows=[]
for p in [512,1024]:
 u=F(1,1<<p);tmax=F(1,3)+u;zmax=tmax*tmax+u
 assert zmax<F(1,8)
 assert (F(2,3)+u)*u+2*u<3*u
 assert 4*u/8+F(1,3)*3*u+2*u<4*u
 assert 2*(p+16)+1<65536
 log_units=12*(p+16)+4+1074
 log_width=log_units*u
 assert log_width<F(1,1<<54)
 assert (745+log_width)*((1<<53)-1)<1<<64
 q_width=(log_units*(1<<64)+2)*u
 assert q_width<F(1,1<<400)
 # The post-shift width is below one. A shift preceding the large-value
 # guard uses at most ten binary places and the corresponding threshold
 # is exactly representable at both precisions.
 assert q_width<1 and p>=62-52
 k_error=F(1,2)+limit*inv_error+inv/F(1<<20)+q_width/lo
 residual=k_error*hi+q_width+1155*u
 assert residual<F(35,100)<F(1,2)
 endpoint_width=(4*(p+16)+2)*u
 exp_width=2*(q_width+1155*u)+2*endpoint_width
 # After reversing the reduction scale, the interval is inside
 # (2^(scale-1), 2^(scale+1)). Consecutive binary64 rounding midpoints
 # are separated there by at least 2^(scale-54), including subnormals
 # and the overflow midpoint. Any remaining failure identifies one cell boundary.
 assert 1-residual-exp_width>F(1,2)
 assert 1/(1-residual)+exp_width<2
 assert exp_width<F(1,1<<54)
 # Track the upper recurrences in integer units of u, through the first
 # term at most one unit. The mantissa starts at t<=tmax and uses z<=zmax.
 log_iterations, power_units = 0, ceil(tmax/u)
 while power_units > 1:
  log_iterations+=1
  power_units=ceil(power_units*zmax)
 # ceil(ceil(v)/n) = ceil(v/n) for integral n>=1, so the
 # two upward roundings in exp_endpoint add less than one ulp per term.
 exp_iterations, term_units = 0, 1<<p
 while term_units > 1:
  exp_iterations+=1
  term_units=ceil(F(7*term_units,20*exp_iterations))
 assert 0<max(log_iterations,exp_iterations)<p+16
 words=p//16+4
 # Two products initialize t^2 and two advance each log power.
 # Each of the two exp endpoints needs two products per term.
 wide_products=2+2*log_iterations+4*exp_iterations
 bits=0
 while exp_width<F(1,1<<bits):bits+=1
 rows.append(dict(bits=p,log_width_units=log_units,q_width=str(q_width),residual_bound=str(residual),residual_bound_float=float(residual),relative_final_width_bound=str(exp_width*2),conservative_relative_bits=bits-2,
                  max_log_series_iterations=log_iterations,
                  max_exp_series_iterations_per_endpoint=exp_iterations,
                  max_wide_products=wide_products,
                  max_limb_products_in_wide_products=words*words*wide_products,
                  max_limb_divisions=words*(wide_products-2)))
r=dict(status='PASS',header_sha256=hashlib.sha256(text.encode()).hexdigest(),rows=rows,
 tiny_exponent_rounds_to_one={'maximum_abs_exponent_exclusive':'2^-64', 'log_abs_bound':745,
    'negative_displacement_bound':str(tiny_y_t), 'positive_displacement_bound':str(tiny_y_t/(1-tiny_y_t))},
 saturation_width_bound='At most one log unit; if the upper bound reaches 800, the true log magnitude exceeds both binary64 cutoffs.',
 max_rne_midpoints_in_undecided_interval=1,
 conditional_rounding='Directed integer endpoints enclose the positive magnitude. A result is returned only when both endpoints round to the same binary64; a false return is preserved when undecided.',
 boundary_argument='For x=a*2^e with a odd and y=b/2^k with b odd, a dyadic result requires a perfect 2^k-th root and e divisible by 2^k. Nontrivial a has k<=5; an exact/midpoint odd significand has <=54 bits. Negative y requires a=1. The prototype tests these conditions with exact integer roots and capped products.',
 scope='Elementary rational bounds for the experimental fixed-point algorithm, not a machine-checked proof of the C++ implementation and not an all-input totality proof. A fixed maximum precision still does not establish all-input totality.')
a.json.parent.mkdir(parents=True,exist_ok=True);a.json.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({"status":r['status'],"rows":[{k:v for k,v in q.items() if k=='bits' or k.startswith('max_') or k in ['residual_bound_float','conservative_relative_bits']} for q in rows]},indent=2))
