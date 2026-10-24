"""Exact Fraction bounds for halved, inverted and ordinary atan repair."""
from pathlib import Path
from fractions import Fraction as F
import ast,hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-atan-original-goal-20261024'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
parent=json.loads((P/'result.json').read_text());assert sha(P/'certify.py')==parent['files']['certify.py']
tree=ast.parse((P/'certify.py').read_text());function=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='total')
env={'F':F,'half':F(1,2),'scale':1<<70}
exec(compile(ast.Module(body=[function],type_ignores=[]),str(P/'certify.py'),'exec'),env)
total=env['total'];S=1<<70;pc=json.loads((P/'certificate.json').read_text())
assert total(F(47,8192),F(pc['narrow_ratio_error']),F(1,2),F(0))==F(pc['narrow_error_Q70'])
ratio=F(13,2)+2*F(pc['reciprocal_error']);assert ratio<33
trunc=1+F(34,1<<20)
caps=[(F(1,256)+F(1,1<<30),6),(F(1,250),7)];regions=[]
for h,radius in caps:
 # Non-inverted rows have .5 table error and at most .5 halving error.
 # Inverted rows have1 table error and no denominator halving. Both
 # geometries therefore have the same worst-case sum, at most1 Q70.
 polynomial=total(h,F(0),F(1),F(0))
 derivative=33*(h+F(33,S))**2
 bound=polynomial+trunc+derivative
 assert bound<radius,(h,bound,radius)
 regions.append(dict(h_cap=str(h),integer_h_cap=(S*h.numerator)//h.denominator,
                     strict_radius_Q70=radius,polynomial_and_table_or_halving_error=str(polynomial),
                     residual_truncation_error=str(trunc),derivative_error=str(derivative),
                     total_error=str(bound),total_error_float=float(bound)))
assert (1<<58)>>38==1<<20
assert 33*((1<<64)-1)<1<<70
assert 33*(1<<26)<1<<32
assert 54+33<1024
report=dict(status='PASS_EXACT_RATIONAL_ALL_GEOMETRY_ATAN_REPAIR',parent_bound_function_sha256=sha(P/'certify.py'),
            parent_table_proof_sha256=sha(P/'table-proof.json'),global_ratio_error=str(ratio),
            global_ratio_error_float=float(ratio),regions=regions,
            minimum_denominator='2^58',minimum_truncated_divisor='2^20',
            geometry_reason='Inverted D=(s<<6)+(index<<(52-e))>=2^58. Ordinary D>=2^58. The exponent-6 branch halves its exceptional65-bit denominator and loses less than .5 Q70; inverted geometry does not halve. Table error is <=.5 ordinary and <=1 inverted.',
            tail_reuse_reason='Accepted parent reaches repair only within54 Q70 of midpoint. abs(delta)<=33; half>=1024. The quantum/binade/retained significand cannot change.',
            helper_signed_modular_bits=71,helper_quotient_bits=6,
            original_fallback_kept=True,new_tables_or_global_RAM=False,
            canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False)
(W/'certificate.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
