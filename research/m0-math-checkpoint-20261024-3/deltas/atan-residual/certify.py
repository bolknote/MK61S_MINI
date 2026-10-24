"""Prove the residual repair radius with exact rational arithmetic."""
from pathlib import Path
from fractions import Fraction as F
import ast,hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
BASE=ROOT/'.build/m0-atan-original-goal-20261024'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
parent=json.loads((BASE/'result.json').read_text())
assert sha(BASE/'certify.py')==parent['files']['certify.py']
# Load only the pure error-bound function, never the parent's module-level
# producer, which would write to an immutable review target.
tree=ast.parse((BASE/'certify.py').read_text())
function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='total')
environment={'F':F,'half':F(1,2),'scale':1<<70}
exec(compile(ast.Module(body=[function],type_ignores=[]),str(BASE/'certify.py'),'exec'),environment)
total=environment['total'];S=1<<70
parent_cert=json.loads((BASE/'certificate.json').read_text())
assert total(F(47,8192),F(parent_cert['narrow_ratio_error']),F(1,2),F(0))==F(parent_cert['narrow_error_Q70'])
ratio_error_bound=F(13,2)+F(parent_cert['reciprocal_error'])
assert ratio_error_bound<19<33
hcap=F(1,256)+F(1,1<<30)
polynomial_table=total(hcap,F(0),F(1,2),F(0))
quotient_error=1+F(34,1<<20)
derivative_error=33*(hcap+F(33,S))**2
bound=polynomial_table+quotient_error+derivative_error
assert polynomial_table<F(446,100)
assert derivative_error<F(1,1024)
assert bound<6
assert 33*(1<<26)<1<<32
assert (1<<59)>>38>=1<<20
assert 54+33<1024
assert 33*((1<<64)-1)<1<<70
report=dict(status='PASS_EXACT_RATIONAL_SIX_Q70_RESIDUAL_REPAIR',parent_pure_error_function_sha256=sha(BASE/'certify.py'),parent_table_proof_sha256=sha(BASE/'table-proof.json'),
            domain='Non-inverted e=-5..-1; h<=2^62+2^40; quotient error<33 Q70.',
            normalized_numerator_bound='Nearest1/64 grid selection gives abs(x-index/64)<=1/128. N_normalized=2^69*abs(x-index/64)<=2^62.',
            parent_ratio_error_bound=str(ratio_error_bound),parent_ratio_error_bound_float=float(ratio_error_bound),
            h_real_cap=str(hcap),polynomial_and_table_error=str(polynomial_table),polynomial_and_table_error_float=float(polynomial_table),
            residual_quotient_error=str(quotient_error),derivative_error=str(derivative_error),derivative_error_float=float(derivative_error),
            total_error=str(bound),total_error_float=float(bound),strict_radius_Q70=6,
            truncated_quotient_reason='D0=floor(d/2^38)>=2^20,R0=floor(abs(R)/2^38),q0=floor(R0/D0)<=33. Then -33/2^20<abs(R)/d-q0<1+1/2^20.',
            residual_modular_width=71,
            signed_residual_fits_reason='abs(R)<33*d<=33*(2^64-1)<2^70, so R mod2^71 has a unique signed representative equal to R.',
            product_width_reason='With h=al+2^32*ah,d=bl+2^32*bh, p=al*bl,t=ah*bl+(p>>32),v=al*bh+(t mod2^32), product_low=(v<<32)|(p mod2^32), and product_high mod2^32=(ah*bh+(t>>32)+(v>>32)) mod2^32. The low7 bits of n-product_high-borrow determine the signed71-bit residual.',
            tail_reuse_reason='Repair entered only within54 Q70 of a midpoint. abs(delta)<=33,half>=1024, so the quantum index and retained significand stay unchanged.',
            original_fallback_kept=True,new_tables_or_global_RAM=False,canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False)
(W/'certificate.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('polynomial_and_table_error','total_error','derivative_error')},indent=2))
