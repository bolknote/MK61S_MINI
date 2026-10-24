"""Certify every reused reciprocal and the exact signed correction domain."""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import re

W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023/source/code'
table = (P / 'native_eabi_m0_log10_table.inc').read_text()
rows = [[int(n.rstrip('Uu'), 0) for n in row.split(',') if n.strip()]
        for row in re.findall(r'\{([0-9Uu,\s]+)\}', table)]
assert len(rows) == 1024 and all(len(r) == 4 for r in rows)
for index, row in enumerate(rows):
    den = 2049 + 2*index
    reciprocal = (row[1] << 32) | (row[0] & ~63)
    assert reciprocal == ((1 << 75) // den) & ~63
    assert 0 <= F(1 << 75, den)-reciprocal < 64
    assert reciprocal % (1 << 46) != 0
    for delta in ((1 << 41)-1, 1 << 41):
        q = reciprocal >> 5
        if delta < (1 << 41):
            q -= (reciprocal >> 46)+1
        residue = (delta << 29)-q*den
        assert 0 <= residue < 3*den
        assert q+int(residue >= den)+int(residue >= 2*den) == (delta << 29)//den
product = F(9, 2) + F(1, 1 << 14)
bound = product + 2
assert bound < F(6500062, 1000000)
assert (bound+1)*4095 < 1 << 15
assert 4095 << 2 < 1 << 14
assert bound < 7
ratio = (W/'native_eabi_m0_log70_ratio.inc').read_text()
original_ratio = (P/'native_eabi_m0_log70_ratio.inc').read_text()
assert ratio.split('.Llog_ratio70_slow:')[0] == original_ratio.split('.Llog_ratio70_slow:')[0]
assert 'movs r3,r0\n orrs r3,r1\n beq .Llog_ratio70_zero' in ratio
assert '.Llog_ratio70_zero:\n bx lr' in ratio
for den in range(2049, 4096, 2):
    for quotient in range(8):
        for rem in (0, 1, den//2, den-1):
            top = quotient*den+rem
            q, n = 0, top
            for bit in (4, 2, 1):
                accept = n >= den*bit
                if accept:
                    n -= den*bit
                q = 2*q+int(accept)
            assert q == top//den
out = dict(status='PASS_ALL_RECIPROCALS_AND_EXACT_THREE_BIT_CORRECTION_BOUND',
           denominators=1024, delta_domain='0..2^41 inclusive',
           reused_table_bytes=16384, new_table_bytes=0,
           product46_absolute_error=str(product), quotient_seed_absolute_error=str(bound),
           quotient_seed_absolute_error_float=float(bound), correction_magnitude_at_most=7,
           residue_representable_as_signed32=True, rounded_abs_top_below_2_to_15=True,
           exact_result='floor((delta<<29)/den), unchanged from the original helper',
           busy_zero_shortcut_exact=True, hardware_ready_source_prefix_unchanged=True,
           both_dyadic_endpoint_shortcuts_exact_all_denominators=True,
           dyadic_seed_error_interval='0<=H-q<3, then at most two unit increments',
           ratio_ASM_source_sha256=hashlib.sha256(ratio.encode()).hexdigest(),
           source_sha256=hashlib.sha256((W/'native_eabi_m0_log70_center.inc').read_bytes()).hexdigest(),
           table_sha256=hashlib.sha256(table.encode()).hexdigest(),
           seed_kernel_source_sha256=hashlib.sha256((P/'native_eabi_m0_product.inc').read_bytes()).hexdigest(),
           scope='Analytic seed bound and all1024 reciprocal/three-bit transition checks; ARM checks are separate.')
(W / 'certificate.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(out, indent=2))
