"""Exact one-sided error bounds, source binding and existing table check."""
from pathlib import Path
from fractions import Fraction as F
import ast
import copy
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


p = ROOT / 'tools/generate_m0_log70_table.py'
text = p.read_text()
node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == 'certificate')
function = copy.deepcopy(node)
function.body[-1].value = ast.Call(func=ast.Name(id='locals', ctx=ast.Load()), args=[], keywords=[])
env = {'Fraction': F}
exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), str(p), 'exec'), env)
d = env['certificate']()
argument, nh, scale = d['near_argument'], d['nh'], 1 << 70
assert argument == F(69, 128) + F(1, 1 << 22)
derivative = argument * nh / (1 - nh)
upper = derivative + F(1, 2) + d['nsquare'] / 2 + d['ncube'] / 3 + d['nfourth'] / 4
lower = upper + d['nremainder']
assert upper < F(3, 2) and lower < F(7, 4)
assert 0 < nh < 1 and scale * nh + argument < 1 << 57
assert scale * nh ** 2 + d['nsquare'] < 1 << 43
assert scale * nh ** 3 + d['ncube'] < 1 << 29
assert scale * nh ** 4 + d['nfourth'] < 1 << 15
max_residue = max((argument * den).__ceil__() for den in range(8065, 8321))
assert max_residue < 1 << 13
max_gate = 8320 * (36 + 16) + 12 * max_residue
assert max_gate < 1 << 20
# With C<2^29 the reciprocal's error C/(3*2^33) cannot reach the next integer.
assert F((1 << 29) - 1, 3 * (1 << 33)) + F(2, 3) < 1

# Verify all 256 existing reciprocals and Q70 center logs using rational
# log-series bounds. Import only the two pure definitions, never main().
p = ROOT / 'tools/generate_m0_log_table.py'
text2 = p.read_text()
nodes = [n for n in ast.parse(text2).body if isinstance(n, ast.FunctionDef) and n.name in ('nearest', 'logarithm')]
e = {'Fraction': F}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(p), 'exec'), e)
image = ElfImage(W / 'candidate.elf')
symbol = next(n for n in image.symbols if 'log_near_table' in n)
address = image.symbols[symbol]
section = next(s for s in image.named_sections.values() if s[3] <= address < s[3] + s[5])
data = image.bytes_at(section)
offset = address - section[3]
for index in range(256):
    reciprocal, value = struct.unpack_from('<QQ', data, offset + 16 * index)
    c = F(8065 + index, 8192)
    assert reciprocal == e['nearest'](F(1 << 62) / c)
    assert value == e['logarithm'](c if c >= 1 else 1 / c, 70)

source = (W / 'native_eabi_m0_log70.inc').read_text()
assert sha(W / 'native_eabi_m0_log70.inc') == 'ba084abda5a2c3d71071ae800224c552efce2652d2838735782cd16e764b090e'
for required in ['bool safe=distance>=4;', 'if(!safe && distance)',
                 'if(exact_center) safe=true;', 'bool(tail>half)==add',
                 'int32_t(den)*(int32_t(12*distance)-bias12)+12*residue>=18*int32_t(den)',
                 'int32_t(den)*(int32_t(12*distance)+bias12)-12*residue>=21*int32_t(den)',
                 'const int32_t r2=-int32_t(z&1U);',
                 'const int32_t r3=int32_t(cube)-3*int32_t(third);',
                 'const int32_t r4=int32_t((fourth+2)&3U)-2;',
                 'bias12=-4*r3+(subtract?-even_bias:even_bias);',
                 'residue=int32_t((uint32_t(delta)<<21)-uint32_t(h)*den);']:
    assert required in source, required

# All possible new discrete bias/residue extrema satisfy the required
# one-sided interval inclusion. The source accepts integer distance 1..3.
checks = 0
biases = sorted({-4*r3 + s*(6*r2 + 3*r4)
                 for r2 in (-1, 0) for r3 in (-1, 0, 1)
                 for r4 in (-2, -1, 0, 1) for s in (-1, 1)})
for den in range(8065, 8321):
    edge = (argument * den).__ceil__() - 1
    for residue in (-edge, -1, 0, 1, edge):
        for bias in biases:
            center = F(bias, 12) - F(residue, den)
            for distance in (1, 2, 3):
                if den*(12*distance-bias)+12*residue >= 18*den:
                    assert center + upper < distance
                if den*(12*distance+bias)-12*residue >= 21*den:
                    assert center - lower > -distance
                checks += 2
            assert center + upper < 4 and center - lower > -4

# Every n>=1 near interval has |x-1|>=1/16384. Thus its true magnitude
# is >=u-u^2/2; half=4 lies well above that binade's lower boundary.
u = F(1, 16384)
assert (u-u*u/2)*scale - 4 > (1 << 55) + 4
out = dict(status='PASS_SOURCE_BOUND_NEAR_LN_DIRECTIONAL_ERROR_INTERVAL',
    source_sha256=sha(W / 'native_eabi_m0_log70.inc'),
    candidate_ELF_sha256=sha(W / 'candidate.elf'),
    propagation_function_sha256=hashlib.sha256(ast.get_source_segment(text, node).encode()).hexdigest(),
    quotient_error_bound=str(argument), quotient_error_bound_float=float(argument),
    exact_signed_h_error='-r/den; r=(delta<<21)-h*den, den=8065..8320',
    reduced_argument_bound=str(nh), upper=str(upper), upper_float=float(upper),
    lower=str(lower), lower_float=float(lower), strict_gate_bases=['3/2', '7/4'],
    correction_error_interval='bias12/12-r/den + [-lower,upper]; includes table error',
    exact_remainders=dict(r2=[-1,0], r3=[-1,0,1], r4=[-2,-1,0,1]),
    integer_gate_interval_checks=checks, maximum_abs_residue_strictly_below=max_residue,
    maximum_abs_cold_gate_expression_below=max_gate, exact_center_error_at_most='1/2',
    exact_midpoints_always_decline=True, synthetic_packing_test_required=True,
    existing_near_table_rows_certified=256, new_tables=False, new_scalar_thresholds=[18,21],
    lower_binade_edge='half4 away from lower boundary; later lower half-gaps>=4 exceed strict error',
    inherited_product54_bound=True, hardware_accessed=False)
(W / 'certificate.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(out, indent=2))
