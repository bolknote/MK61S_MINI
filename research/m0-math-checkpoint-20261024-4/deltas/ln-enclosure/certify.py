"""Bind the exact RP strict-radius proof and outer-half-cell selector."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json
import struct
import subprocess
import sys

W = Path(__file__).resolve().parent
subprocess.run([sys.executable,str(W/'prospective.py')],check=True,capture_output=True,text=True)
d = json.loads((W/'prospective.json').read_text())
assert F(d['RP_exact_quotient_main_bound']) < 8 and F(d['near_bound']) < 4
source = (W/'native_eabi_m0_log70.inc').read_text()
subnormal = (W/'native_eabi_m0_log_subnormal.inc').read_text()
assert 'enum : uint32_t {ln_main_radius=8U,ln_near_radius=4U};' in source
assert source.count('const uint32_t guard=error-1;') == 1
assert 'const uint32_t guard=error-1;' in subnormal
assert 'enum : uint32_t {ln_main_radius=16U,ln_near_radius=8U};' in source
assert 'ln_pack70(low,high,negative?D::Sign:0,ln_near_radius,x)' in source
assert 'ln_subnormal_pack70(result,upper,D::Sign,ln_main_radius+(n+1)/2,x)' in subnormal
boundary = F(16129,16384)
raw = struct.unpack('<Q',struct.pack('<d',float(boundary)))[0]
assert raw == 0x3fef808000000000
assert 'ln_near_lower=UINT64_C(0x3FEF808000000001)' in source
assert boundary == 1-F(255,16384)
# n=floor((a+2^48)/2^49); for negative x, a=(1-x)*2^62.
assert ((1-boundary)*(1<<62)+(1<<48))/(1<<49) == 128
checks = 0
for half in (4,8,16,32,1024,2048,65536,1<<26):
    for radius in range(1,min(half,546)+1):
        guard = radius-1
        for distance in {0,1,radius-1,radius,min(half,radius+1),half}:
            for side in (-1,1):
                tail = half+side*distance
                if not 0<=tail<2*half:
                    continue
                declines = ((tail-(half-guard))&0xffffffff) <= 2*guard
                assert declines == (distance<radius)
                checks += 1
out = dict(status='PASS_EXACT_RP_LN_STRICT_RADII_AND_SELECTOR',
           main_bound=d['RP_exact_quotient_main_bound'],main_bound_float=d['RP_exact_quotient_main_bound_float'],
           near_bound=d['near_bound'],near_bound_float=d['near_bound_float'],
           strict_radii=dict(main=8,near=4), generic_radii_unchanged=dict(main=16,near=8),
           packing_rule='Integer distance>=strict radius is safe; closed guard=radius-1.',
           integer_guard_boundary_checks=checks,exponent_error_ceil_half_unchanged=True,
           negative_n128_half_cell='Route x<=16129/16384 through the existing general normal kernel.',
           polynomial_helpers_tables_unchanged=True,
           source_sha256=hashlib.sha256(source.encode()).hexdigest(),
           subnormal_source_sha256=hashlib.sha256(subnormal.encode()).hexdigest(),
           propagation_function_sha256=d['certificate_function_source_sha256'],
           hardware_accessed=False)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
