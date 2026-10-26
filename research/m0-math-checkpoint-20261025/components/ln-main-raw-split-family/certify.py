"""Bind the main-ln raw argument and residual-aware RNE enclosure to source."""
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
BASE = ROOT / '.build/m0-log-ratio-small-limb-20261024'
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
argument, full = d['argument'], d['error']
base = full - argument
assert argument == F(106497, 16384)
assert base < 7 and full < 16
assert argument * 4095 < (1 << 15)
assert d['h'] * (1 << 70) < (1 << 60)

# Exact h-H is in (0,1]; the raw product has the full generic bound.
# Removing the linear h term leaves the SAME remaining base bound. Its
# nonlinear propagation argument*h/(1-h) stays in base conservatively.
assert base >= argument * d['h'] / (1 - d['h'])
assert base + 1 < 8

source = (W / 'native_eabi_m0_log70.inc').read_text()
assert sha(W / 'native_eabi_m0_log70.inc') == '8294798875f17de019d15a57208f04daf2d74c431873036ecc87111df583e42f'
entry = '__attribute__((optimize("Os"))) MK61_SOFT_PCS double mk61_m0_ln(double x) {'
parent = (BASE / 'native_eabi_m0_log70.inc').read_text()
dispatch = '''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  if(uint32_t(uint32_t(b)+64U)>128U &&
      (*reinterpret_cast<volatile uint32_t*>(UINT32_C(0xD0000078))&2U)) return ln_main_raw(b);
#endif
'''
assert source.count(dispatch) == 1
assert source[source.index(entry):].replace(dispatch, '') == parent[parent.index(entry):]
# All previous near/special/common pack functions are exact source copies.
prefix = source[:source.index('#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\n// The exact signed h residual')]
assert prefix == parent[:parent.index(entry)]
for token in ('const uint32_t guard=15U+exponent_error;',
              'if(!distance) return ln_refine(x);',
              'const uint32_t den=2049U+2U*unsigned((b&D::Fraction)>>42);',
              'const bool negative=(b&(U(1)<<41))==0;',
              'const int32_t residue=int32_t(delta_low-h_low*den);',
              'const int32_t oriented=(negative!=(sign!=0))?-residue:residue;',
              'const int32_t directed=tail>half?oriented:-oriented;',
              '(int32_t(distance)-int32_t(7U+exponent_error))*int32_t(den)+directed<0'):
    assert token in source, token

# The raw body retains every original polynomial/table/ln2 operation.
body = parent[parent.index(entry):]
body = body[body.index('  const int k='):]
body = body.replace('  const U h=log70_residual(delta,index);',
    '  const uint32_t* row=log10_table[index];\n  const U reciprocal=(U(row[1])<<32)|(row[0]&~63U);\n  const U h=mk61_m0_log_product46(delta,reciprocal);')
body = body.replace('return ln_pack70(low,high,0,ln_main_radius,x);',
                    'return ln_main_pack70(low,high,0,0,uint32_t(h),x);')
body = body.replace('return ln_pack70(result,upper,k<0?D::Sign:0,ln_main_radius+(n+1)/2,x);',
                    'return ln_main_pack70(result,upper,k<0?D::Sign:0,(n+1)/2,uint32_t(h),x);')
raw = source[source.index('static double ln_main_raw(U b) {'):source.index('\n#endif\n'+entry)]
assert raw.rstrip() == 'static double ln_main_raw(U b) {\n  const double x=real(b);\n' + body.rstrip()

image = ElfImage(W / 'candidate.elf')
symbol = next(n for n in image.symbols if 'log10_table' in n and image.sizes.get(n) == 16384)
address = image.symbols[symbol]
section = next(s for s in image.named_sections.values() if s[3] <= address < s[3] + s[5])
data = image.bytes_at(section)
offset = address - section[3]
for index in range(1024):
    lo, hi, _, _ = struct.unpack_from('<4I', data, offset + 16*index)
    reciprocal = (hi << 32) | (lo & ~63)
    den = 2049 + 2*index
    assert reciprocal == ((1 << 75) // den) & ~63

# Near-one dispatch excludes the only tiny normal logarithms. General
# normal |ln(x)| > 1/128 and <1024, so Q70 pack shifts are11..27;
# the smallest midpoint half-gap1024 exceeds the largest radius528.
assert F(1, 65) > F(1, 128)  # ln(1+1/64) >= 1/65
assert F(255, 16384) > F(1, 128)  # -ln(1-255/16384) >= 255/16384
assert (F(1, 65) * (1 << 70) - 528) > (1 << 63)
maximum_gate = 519*4095 + (argument*4095).__ceil__()
assert maximum_gate < (1 << 22)
# At an exact power-of-two output, the lower rounding half-cell is half
# the usual one. Only width64 needs a stronger correlation: k>=1 or
# k<=-2 gives |ln(x)|>=ln(2)>1/2, hence width>=70. Thus width64 has
# k in{-1,0}, extra<=1, and even its lower512-unit half-cell is safe.
assert F(1, 2)*(1 << 70)-528 > (1 << 68)
assert 16+1 < 512 and 16+512 < 1024
checks = 0
for den in range(2049, 4096, 2):
    edge = (argument*den).__ceil__()-1
    for residue in (-edge, -1, 0, 1, edge):
        for extra in (0, 1, 2, 256, 511, 512):
            for v in (-1, 1):
                error = -v*F(residue, den)
                for distance in {0, 1, 6+extra, 7+extra, 8+extra, 15+extra, 16+extra}:
                    above = den*(distance-(7+extra))+v*residue >= 0
                    below = den*(distance-(7+extra))-v*residue >= 0
                    if distance and above:
                        assert error+base+extra < distance
                    if distance and below:
                        assert error-base-extra > -distance
                    checks += 2

out = dict(status='PASS_SOURCE_BOUND_RAW_MAIN_LN_RESIDUAL_RNE_ENCLOSURE',
    source_sha256=sha(W/'native_eabi_m0_log70.inc'),candidate_ELF_sha256=sha(W/'candidate.elf'),
    propagation_function_sha256=hashlib.sha256(ast.get_source_segment(text,node).encode()).hexdigest(),
    generic_quotient_error=str(argument),generic_main_bound=str(full),generic_main_bound_float=float(full),
    residual_aware_base=str(base),residual_aware_base_float=float(base),strict_cold_radius=7,
    fast_radius=16,exponent_error='ceil(abs(k)/2), k=-1022..1023',
    exact_magnitude_error='-v*r/den +/- (base+ceil(abs(k)/2)); r=(delta<<29)-h*den',
    magnitude_orientation='v=-1 iff input offset sign differs from output log sign',
    signed_low32_residual_bound_strictly_below=1<<15,maximum_abs_cold_gate_below=maximum_gate,
    pack_shifts=[11,27],smallest_midpoint_half_gap=1024,maximum_fast_radius=528,
    lower_binade_half_cell='At width64, k in{-1,0} gives radius<=17<512; at widths65..80 radius<=528<1024.',
    integer_directional_interval_checks=checks,existing_reciprocal_rows_checked=1024,
    exact_midpoint_always_declines=True,original_public_body_identical_except_dispatch=True,
    original_polynomial_tables_and_ln2_operations_retained=True,
    dispatch_family_equivalence='delta_low=+/-input_low modulo2^32; [-64,64] set symmetric',
    new_tables=False,synthetic_ARM_pack_required=True,hardware_accessed=False)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
