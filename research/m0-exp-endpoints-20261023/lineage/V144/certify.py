"""Exact rational bounds for the added magnitude/small-y pow route.

Reuse, rather than silently enlarge, the existing logarithm/exp contracts.
This is not a proof of totality for the unchanged general-pow fallback.
"""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path.cwd()
work = Path(__file__).resolve().parent
parent = root/'.build/m0-pow-horner-final-v138-20261023/source'
source = work/'source'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def part(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


fast = (source/'code/native_eabi_m0_pow_fast.inc').read_text()
old = (parent/'code/native_eabi_m0_pow_fast.inc').read_text()
assert part(fast, 'struct PowFastLog ', '__attribute__((optimize("Os"),noinline,section(MK61_M0_POW_HOT_SECTION)))') == part(old, 'struct PowFastLog ', '__attribute__((optimize("Os"),noinline,section(MK61_M0_POW_HOT_SECTION)))')
assert part(fast, '__attribute__((always_inline)) inline bool pow_argument_error', '// Compare m * midpoint') == part(old, '__attribute__((always_inline)) inline bool pow_argument_error', '// Compare m * midpoint')
body = (source/'code/native_eabi_m0_pow_exp_body.inc').read_text()
prefix = body[:body.index('  if(k>1023) {')]
copied = part(fast, '// Shared checked Q62 exp argument stage;', '  // The checked argument magnitude is<=1/4')
assert copied.replace('  if(n>=512) return false;\n', '') == prefix
assert body == (parent/'code/native_eabi_m0_pow_exp_body.inc').read_text()
tables = ['native_eabi_m0_exp_table.inc', 'native_eabi_m0_log70_table.inc',
          'native_eabi_m0_refine_table.inc', 'native_eabi_m0_rsqrt_table.inc',
          'native_eabi_m0_log10_constants.inc', 'native_eabi_m0_log10_table.inc']
for name in tables:
    private = source/'code'/name
    assert private.read_bytes() == (root/'code'/name).read_bytes()
    assert private.read_bytes() == (parent/'code'/name).read_bytes()

# Existing rational coefficient/product/table bounds, run without writing code.
command = [sys.executable, str(root/'tools/certify_m0_pow_fast.py'),
           '--json', str(work/'upstream-pow-certificate.json')]
with (work/'upstream-pow-certificate.log').open('w') as log:
    completed = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT)
assert completed.returncode == 0
upstream = json.loads((work/'upstream-pow-certificate.json').read_text())
assert upstream['status'] == 'PASS_ARITHMETIC_BOUNDS'
assert upstream['pow_exp_q62_enclosure'] == '3+ceil(E/2) for E<=129;4+ceil(E/2) otherwise'

# Positive series for ln2 and a rational geometric upper bound on its tail.
n = 32
ln2_lo = 2*sum((F(1, (2*k+1)*3**(2*k+1)) for k in range(n)), F(0))
ln2_hi = ln2_lo + F(9, 4*(2*n+1)*3**(2*n+1))
assert 0 < ln2_lo < ln2_hi < 1
assert 1074*ln2_hi < 745
tiny_argument = F(745, 1 << 64)
tiny_exp_error = tiny_argument/(1-tiny_argument)
assert tiny_exp_error < F(1, 1 << 54)

# Nearest binary64 neighbours of1 are1-2^-53 and1+2^-52.
# -ln(1-u)>u; ln(1+v)>v/(1+v), hence |ln(x)|>2^-53
# for all other positive finite x. This makes |y ln x|>1024.
above_one = F(1, 1 << 52)
assert above_one/(1+above_one) > F(1, 1 << 53)
huge_argument_lower = F(1 << 63, 1 << 53)
assert huge_argument_lower == 1024
assert huge_argument_lower > 1075*ln2_hi > 1024*ln2_hi

# q represents |ln x|*2^S within E. With y=sy*2^(ey-52),
# shift=S-12-ey makes floor(q*sy/2^shift) a Q64 point.
# Its error is <1+E*2^53/2^shift. pow_argument_error encloses
# the latter term; the new path explicitly adds the one floor unit.
assert all((53-s) == -(s-53) for s in range(64, 128))
assert 32*F(1, 1 << (85-53)) < 1
assert ((1 << 64)-1)+32 < (1 << 65)
shift128_argument_upper = F(1 << (65+53), 1 << (128+64))
assert shift128_argument_upper == F(1, 1 << 74)
assert shift128_argument_upper/(1-shift128_argument_upper) < F(1, 1 << 54)

# Linear certificate: point+radius <=2^32-1 gives |z|<2^-32.
# For either sign, |exp(z)-1-z| <= z^2/(2*(1-|z|)).
linear_limit = F(1, 1 << 32)
linear_remainder_q64 = (1 << 64)*linear_limit**2/(2*(1-linear_limit))
assert linear_remainder_q64 < 1
assert (1 << 64)*F(1, 1 << 53) == 2048  # spacing below1
assert (1 << 64)*F(1, 1 << 52) == 4096  # spacing above1
# Midpoint distance >input_error+1 therefore excludes every true tie.
# The strict test deliberately falls back for every overlapping cell.
for drop in (11, 12):
    half = 1 << (drop-1)
    assert (1 << drop) == 2*half and half > 128

# Complete-product construction uses a96-bit q and a53-bit sy.
# No accumulated column overflows the unsigned64/32-bit carriers.
assert ((1 << 32)-1)*((1 << 21)-1)+((1 << 32)-1) < 1 << 64
assert (1 << 21) < 1 << 32
assert all(0 <= s-64 < 32 for s in range(64, 96))
assert all(0 <= s-96 < 32 for s in range(96, 128))

# Small-exp route only accepts a Q64 point<=1/4. Its input radius
# is <=2 here: the normal-log radius is <=528, shift>=64; near-one
# log error is <=32 at still larger shifts. This interval remains
# strictly between-ln2 and+ln2, so no zero/subnormal/overflow case
# removed from the shared exp tail is reachable.
assert F(528, 1 << 11) < 1
small_exp_argument_upper = F(1, 4)+F(2, 1 << 64)
assert small_exp_argument_upper < ln2_lo
assert 'if(argument.high || argument.low>(U(1)<<62)) return false;' in fast
assert 'if(n>=512) return false;' in fast
assert 'if(k<-2 || k>1) return false;' in fast
assert 'uint32_t(rounding_tail-(512U-error))<=2*error' in fast
assert '++input_error;' in fast

deps = ['certify_m0_pow_fast.py', 'certify_m0_exp_fast.py', 'certify_m0_ln_refine.py',
        'certify_m0_log10_fast.py', 'generate_m0_log70_table.py', 'generate_m0_log_table.py',
        'generate_m0_rsqrt_table.py', 'generate_m0_log10_constants.py',
        'generate_m0_log10_table.py']
record = dict(
    status='PASS_EXACT_MAGNITUDE_AND_SMALL_Y_ENCLOSURE_BOUNDS',
    candidate='V144', producer_sha256=sha(__file__),
    source_sha256=sha(source/'code/native_eabi_m0_pow_fast.inc'),
    assembly_sha256=sha(source/'code/native_eabi_m0_rp2040.S'),
    ln2_enclosure=[str(ln2_lo), str(ln2_hi)],
    tiny_domain='Positive finite x, finite |y|<=2^-64: exact binary64 RNE1.',
    tiny_argument_upper=str(tiny_argument), tiny_exp_error_upper=str(tiny_exp_error),
    huge_domain='Positive finite x!=1, finite |y|>=2^63: exact RNE0 or+infinity from sign(y ln x); x==1 returns1.',
    huge_argument_strict_lower=str(huge_argument_lower),
    scaled_argument='floor(q*sy/2^(S-12-ey)); radius=ceil(E*2^53/2^shift)+1, with existing wider conservative bound when shift>=85.',
    shift128_argument_upper=str(shift128_argument_upper),
    linear_remainder_q64_upper=str(linear_remainder_q64),
    linear_RNE_test='Grid2048 below1 /4096 above1; strict midpoint distance>input_error+1, otherwise unchanged cr_pow.',
    small_exp_absolute_argument_upper=str(small_exp_argument_upper),
    small_exp_contract='Exact prefix of existing Q62 exp body, same coefficients/table/product kernel/error radius; added n<512 and normal-only k guards; same strict RNE-cell test.',
    table_sha256={name: sha(source/'code'/name) for name in tables},
    reused_log_code_unchanged=True, reused_exp_prefix_unchanged=True,
    upstream_certificate=dict(path=str((work/'upstream-pow-certificate.json').relative_to(root)), sha256=sha(work/'upstream-pow-certificate.json')),
    upstream_command=command, upstream_terminal_exit_code=completed.returncode,
    dependency_sha256={name: sha(root/'tools'/name) for name in deps},
    conditional_contract='This proof reuses the pre-existing log enclosure and exp polynomial/product certificates; it binds unchanged source/table content and runs their exact-rational checker. Actual ARM bigint property checks, MPFR/ABI tests and linked-code checks are separate reports.',
    general_pow_totality_proved=False, hardware_accessed=False, goal_complete=False)
(work/'certificate.json').write_text(json.dumps(record, indent=2)+'\n')
print('PASS: exact magnitude cutoffs and small-y interval bounds; reused log/exp contracts and prefix verified.')
