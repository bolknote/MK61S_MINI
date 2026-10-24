"""Tighten only RP ln acceptance intervals using the exact residual bound."""
from pathlib import Path
import difflib
import hashlib
import json
import shutil

W = Path(__file__).resolve().parent
ROOT = W.parents[1]
BASE = ROOT/'.build/m0-log-ratio-dirty-20261024'
P = ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
assert hashlib.sha256((BASE/'result.json').read_bytes()).hexdigest() == 'd76525b1cf50b407f9de8421a643b47a7e8503032cb23a3d6c9eb752bcd3fa3e'
for name in ('native_eabi_m0.cpp','native_eabi_m0_log70_center.inc','native_eabi_m0_log10.inc',
             'native_eabi_m0_log70_ratio.inc','ratio.S'):
    shutil.copyfile(BASE/name,W/name)
old = (P/'native_eabi_m0_log70.inc').read_text()
prefix = '''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
enum : uint32_t {ln_main_radius=8U,ln_near_radius=4U};
// The first negative near-center has65 log bits and is deliberately
// excluded. Its entire half-cell uses the certified general kernel.
enum : U {ln_near_lower=UINT64_C(0x3FEF808000000001)};
#else
enum : uint32_t {ln_main_radius=16U,ln_near_radius=8U};
enum : U {ln_near_lower=UINT64_C(0x3FEF800000000000)};
#endif
'''
needle = '  if(uint32_t(tail-(half-error))<=2*error) return ln_refine(x);'
assert old.count(needle) == 2
guard = '''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // Actual error is strictly below the integer radius. The discrete
  // midpoint distance may equal that radius and still be accepted.
  const uint32_t guard=error-1;
#else
  const uint32_t guard=error;
#endif
  if(uint32_t(tail-(half-guard))<=2*guard) return ln_refine(x);'''
new = prefix+old.replace(needle,guard,1)
needle = 'if(b>=UINT64_C(0x3FEF800000000000) && b<=UINT64_C(0x3FF0400000000000))'
assert new.count(needle) == 1
new = new.replace(needle,'if(b>=ln_near_lower && b<=UINT64_C(0x3FF0400000000000))')
for before,after in [
    ('ln_pack70(low,high,negative?D::Sign:0,8,x)','ln_pack70(low,high,negative?D::Sign:0,ln_near_radius,x)'),
    ('ln_pack70(low,high,0,16,x)','ln_pack70(low,high,0,ln_main_radius,x)'),
    ('ln_pack70(result,upper,k<0?D::Sign:0,16+(n+1)/2,x)',
     'ln_pack70(result,upper,k<0?D::Sign:0,ln_main_radius+(n+1)/2,x)')]:
    assert new.count(before) == 1
    new = new.replace(before,after)
(W/'native_eabi_m0_log70.inc').write_text(new)
patch = ''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),
    fromfile='parent/native_eabi_m0_log70.inc',tofile='candidate/native_eabi_m0_log70.inc'))
old = (P/'native_eabi_m0_log_subnormal.inc').read_text()
needle = '  if(uint32_t(tail-(half-error))<=2*error) return mk61_m0_cr_ln(x);'
assert old.count(needle) == 1
new = old.replace(needle,'  const uint32_t guard=error-1;\n  if(uint32_t(tail-(half-guard))<=2*guard) return mk61_m0_cr_ln(x);')
needle = 'ln_subnormal_pack70(result,upper,D::Sign,16+(n+1)/2,x)'
assert new.count(needle) == 1
new = new.replace(needle,'ln_subnormal_pack70(result,upper,D::Sign,ln_main_radius+(n+1)/2,x)')
(W/'native_eabi_m0_log_subnormal.inc').write_text(new)
patch += ''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),
    fromfile='parent/native_eabi_m0_log_subnormal.inc',tofile='candidate/native_eabi_m0_log_subnormal.inc'))
(W/'ln-enclosure-only.patch').write_text(patch)
(W/'preparation.json').write_text(json.dumps(dict(status='PRIVATE_RP_STRICT_LN_ENCLOSURE_CANDIDATE',
    parent_result_sha256=hashlib.sha256((BASE/'result.json').read_bytes()).hexdigest(),
    source_sha256=hashlib.sha256((W/'native_eabi_m0_log70.inc').read_bytes()).hexdigest(),
    polynomial_helpers_tables_unchanged=True,canonical_or_device_changed=False),indent=2)+'\n')
