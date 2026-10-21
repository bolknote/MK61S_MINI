#!/usr/bin/env python3
"""Check rational invariants for the owned M0 pow interval refinement."""
import argparse
from fractions import Fraction as F
from pathlib import Path
import json,hashlib,re
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--json',type=Path,required=True);a=p.parse_args()
ROOT=Path(__file__).resolve().parents[1]
lo=sum((F(2,(2*i+1)*3**(2*i+1)) for i in range(500)),F(0));hi=lo+F(2,1001*3**1001)*F(9,8)
text=(ROOT/'code/native_eabi_m0_pow_interval.inc').read_text();table=(ROOT/'code/native_eabi_m0_pow_interval_table.inc').read_text();words=[int(x) for x in re.findall(r'(\d+)U',table)]
v=sum(x<<(16*i) for i,x in enumerate(words));assert F(v,1<<1024)<lo<hi<F(v+1,1<<1024)
assert 65535**2+65535+65535==(1<<32)-1
assert F(1,1<<52)/(1+F(1,1<<52))>F(1,1<<53)
assert 1024>800>1075*hi and 800>1024*hi
assert 3**64>1<<53
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
 k_error=F(1,2)+800*inv_error+inv/F(1<<20)+q_width/lo
 residual=k_error*hi+q_width+1155*u
 assert residual<F(35,100)<F(1,2)
 endpoint_width=(4*(p+16)+2)*u
 exp_width=2*(q_width+1155*u)+2*endpoint_width
 bits=0
 while exp_width<F(1,1<<bits):bits+=1
 rows.append(dict(bits=p,log_width_units=log_units,q_width=str(q_width),residual_bound=str(residual),residual_bound_float=float(residual),relative_final_width_bound=str(exp_width*2),conservative_relative_bits=bits-2))
r=dict(status='PASS',header_sha256=hashlib.sha256(text.encode()).hexdigest(),rows=rows,
 conditional_rounding='Directed integer endpoints enclose the positive magnitude. A result is returned only when both endpoints round to the same binary64; a false return is preserved when undecided.',
 boundary_argument='For x=a*2^e with a odd and y=b/2^k with b odd, a dyadic result requires a perfect 2^k-th root and e divisible by 2^k. Nontrivial a has k<=5; an exact/midpoint odd significand has <=54 bits. Negative y requires a=1. The prototype tests these conditions with exact integer roots and capped products.',
 scope='Elementary rational bounds for the experimental fixed-point algorithm, not a machine-checked proof of the C++ implementation and not an all-input totality proof. A fixed maximum precision still does not establish all-input totality.')
a.json.parent.mkdir(parents=True,exist_ok=True);a.json.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({"status":r['status'],"rows":[{k:v for k,v in q.items() if k in ['bits','residual_bound_float','conservative_relative_bits']} for q in rows]},indent=2))
