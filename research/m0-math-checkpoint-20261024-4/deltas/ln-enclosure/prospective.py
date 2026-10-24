"""Pure exact bounds for the existing ln kernels with the RP exact quotient."""
from pathlib import Path
from fractions import Fraction
import ast
import copy
import hashlib
import json

W = Path(__file__).resolve().parent
ROOT = W.parents[1]
path = ROOT/'tools/generate_m0_log70_table.py'
text = path.read_text()
function = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == 'certificate')
original = {'Fraction': Fraction}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), original)
old = original['certificate']()
changed = copy.deepcopy(function)
assignments = [n for n in ast.walk(changed) if isinstance(n, ast.Assign) and
               any(isinstance(t, ast.Name) and t.id == 'argument' for t in n.targets)]
assert len(assignments) == 1
assignments[0].value = ast.parse('Fraction(1)', mode='eval').body
env = {'Fraction': Fraction}
exec(compile(ast.fix_missing_locations(ast.Module(body=[changed], type_ignores=[])), str(path), 'exec'), env)
rp = env['certificate']()
main, near = Fraction(rp['main_error']), Fraction(rp['near_error'])
assert main < 8 and near < 4
out = dict(status='PROSPECTIVE_EXACT_LN_ENCLOSURES_NOT_IMPLEMENTED',
           old_main_bound=old['main_error'], old_main_bound_float=old['main_error_float'],
           RP_exact_quotient_main_bound=str(main), RP_exact_quotient_main_bound_float=float(main),
           near_bound=str(near), near_bound_float=float(near),
           proposed_strict_radii=dict(main=8, near=4),
           proposed_closed_integer_guards=dict(main=7, near=3),
           basis='Existing pure propagation, changing only residual error6.500061 to1 for RP exact floor+1.',
           radius_equality_safe='Integer midpoint distance>=radius is safe because each actual error is strictly below radius.',
           normal_exponent_error='Add ceil(abs(k)/2), as before.',
           subnormal_exponent_error='Add ceil(n/2), n1023..1074, as before.',
           generic_M0_unchanged_required=True, no_runtime_changed=True,
           certificate_function_source_sha256=hashlib.sha256(ast.get_source_segment(text,function).encode()).hexdigest(),
           certificate_file_sha256=hashlib.sha256(text.encode()).hexdigest())
(W/'prospective.json').write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps(out, indent=2))
