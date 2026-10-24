"""Exact prospective bounds; this does not implement a new runtime gate."""
from pathlib import Path
from fractions import Fraction as F
import ast,hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-atan-original-goal-20261024'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
parent=json.loads((P/'result.json').read_text());assert sha(P/'certify.py')==parent['files']['certify.py']
S=1<<70;h=F(1,128);ez=F(1,2)+F(13,512);e3=F(1,2)+F(13,512)+h*ez
old5=(F(1,2)+h*h*e3+h**3*ez+e3*ez/S+
      ((1<<17)-1)*(S*h*h+ez)/S+((1<<24)-1)*(S*h**3+e3)/S)
pos5=F(1,2)+h*h*e3+h**3*ez+e3*ez/S
e7=(F(1,2)+h*h*old5+h**5*ez+old5*ez/S+
    7*(S*h*h+ez)/S+((1<<24)-1)*(S*h**5+old5)/S)
ratio=F(1,2)+F(35,1<<20);der=33*(h+F(33,S))**2
omitted=S*h**11/(11*(1-h*h))
upper7=e3/3+F(1,3)+pos5/5+e7/7+F(3,7)+ratio+1+der
upper9=e3/3+pos5/5+e7/7+F(3,7)+F(51,100)+omitted+ratio+1+der
sym9=e3/3+F(1,3)+old5/5+F(2,5)+e7/7+F(3,7)+F(51,100)+omitted+ratio+1+der
assert 5*upper7<14 and 5*(upper7-F(1,2))<11
assert 15*upper9<42 and 15*(upper9-F(1,2))<35
assert sym9<7
ninth_error=F(1,2)+F(13,65536)*F(128,9)
assert ninth_error<F(51,100)
assert 65535**2+(1<<15)<1<<32
assert 0xAAAAAAAB*3-(1<<33)==1
assert 2454267027*7-(1<<34)==5
assert F(((1<<22)+3)*5,7*(1<<34))<F(1,7)
for n in range(133):assert n*7282>>16==n//9
for r5 in range(-4,10):
 q5=((r5+7)*13108)>>16
 delta=q5-1
 assert r5+7-5*q5==r5-5*delta+2
 assert -2<=r5-5*delta<=2
 assert delta==((abs(r5)+2)//5)*(-1 if r5<0 else 1)
tree=ast.parse((P/'certify.py').read_text());f=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='total')
env={'F':F,'half':F(1,2),'scale':S}
exec(compile(ast.Module(body=[f],type_ignores=[]),str(P/'certify.py'),'exec'),env)
regions=[]
for cap,radius in [(F(1,250),6),(F(1,160),9),(F(1,128),23)]:
 bound=env['total'](cap,F(0),F(1),F(0))+ratio+33*(cap+F(33,S))**2
 assert bound<radius
 regions.append(dict(h_cap=str(cap),radius=radius,error=str(bound),error_float=float(bound)))
inverse=env['total'](F(1,180),F(1,2),F(1),F(0));assert inverse<7
assert 33*(1<<54)<1<<63
assert 54+33+16<1024
report=dict(status='PASS_EXACT_FRACTION_DIRECTIONAL_NINTH_ATAN',parent_bound_source_sha256=sha(P/'certify.py'),source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),
            favorable_old_global_base=str(upper7),favorable_old_global_base_float=float(upper7),
            favorable_ninth_global_base=str(upper9),favorable_ninth_global_base_float=float(upper9),
            ninth_symmetric_bound=str(sym9),ninth_symmetric_bound_float=float(sym9),
            Q16_ninth_error_bound=str(ninth_error),Q16_ninth_error_bound_float=float(ninth_error),
            old_gate_thresholds=dict(normal=11,halved_or_inverted=14),
            ninth_gate_thresholds=dict(normal=35,halved_or_inverted=42),
            symmetric_old_regions=regions,inverse_tight_residual_bound=str(inverse),
            inverse_tight_residual_bound_float=float(inverse),normal_geometry_class='unsigned(source_e+5)<5; the exponent0 exact input1 is conservatively assigned the wider class',inverse_predicate='U64(low_product(h,D>>6)+(D>>7)) < D>>6; a sufficient shifted interval, including all returned values within half a Q70 unit',runtime_implemented=True,goal_complete=False)
(W/'certificate.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if not isinstance(v,str) or len(v)<70},indent=2))
