"""Prospective one-sided near-ln bounds with exact rounding remainders."""
from pathlib import Path
from fractions import Fraction as F
import ast
import copy
import hashlib
import json

W=Path(__file__).resolve().parent
ROOT=W.parents[1]
p=ROOT/'tools/generate_m0_log70_table.py'
source=p.read_text()
function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='certificate')
f=copy.deepcopy(function)
assert isinstance(f.body[-1],ast.Return)
f.body[-1].value=ast.Call(func=ast.Name(id='locals',ctx=ast.Load()),args=[],keywords=[])
env={'Fraction':F}
exec(compile(ast.fix_missing_locations(ast.Module(body=[f],type_ignores=[])),str(p),'exec'),env)
d=env['certificate']()
upper=d['near_argument']/(1-d['nh'])+F(1,2)+d['nsquare']/2+d['ncube']/3+d['nfourth']/4
lower=upper+d['nremainder']
assert upper<2 and lower<F(9,4)
# Replace the residual's symmetric error by its exact signed r/den;
# its derivative remainder is <=argument*nh/(1-nh).
residual_upper=upper-d['near_argument']
residual_lower=lower-d['near_argument']
assert residual_upper<F(3,2) and residual_lower<F(7,4)
out=dict(status='PROSPECTIVE_NEAR_LN_DIRECTIONAL_GATES_NOT_RUNTIME',
    base_upper=str(upper),base_upper_float=float(upper),base_lower=str(lower),base_lower_float=float(lower),
    bias12='-4*r3-s*(6*r2+3*r4), s=+1 for odd+even, -1 for odd-even',
    exact_remainders=dict(r2=[-1,0],r3=[-1,0,1],r4=[-2,-1,0,1]),
    gate='upper:12*distance-bias12>=24; lower:12*distance+bias12>=27',
    upper_class='(tail>half)==add, where add=(subtract==negative)',
    residual_aware_upper=str(residual_upper),residual_aware_upper_float=float(residual_upper),
    residual_aware_lower=str(residual_lower),residual_aware_lower_float=float(residual_lower),
    exact_residual='r=(delta<<21)-h*(8192+signed_n), recoverable from signed low32',
    residual_aware_gate='upper:den*(12*distance-bias12)+12*r>=18*den; lower:den*(12*distance+bias12)-12*r>=21*den',
    residual_aware_midpoint_needs_explicit_rounding_decision=True,
    certificate_function_sha256=hashlib.sha256(ast.get_source_segment(source,function).encode()).hexdigest(),
    runtime_implemented=False,hardware_accessed=False)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
