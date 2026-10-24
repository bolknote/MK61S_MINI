"""Derive a small-h lower gate from the sealed directional/ninth parent."""
from pathlib import Path
import difflib
import hashlib
import json

W = Path(__file__).resolve().parent
ROOT = W.parents[1]
BASE = ROOT / '.build/m0-atan-directional-ninth-20261024'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


assert sha(BASE / 'native_eabi_m0_atan_fast.inc') == '996dcd240df881b6592b61aeca95fd446c7522b6fff71bc1c6de8eeed9001d23'
for name in ('native_eabi_m0.cpp', 'native_eabi_m0_atan.inc'):
    (W / name).write_bytes((BASE / name).read_bytes())
old = (BASE / 'native_eabi_m0_atan_fast.inc').read_text()
needle = '''          if(!safe) {
            const AtanTailCorrection ninth=atan_fast_ninth(h,r5);'''
replace = '''          // For h<1/512 the old polynomial's lower error is below
          // 1.900690+r5/5-r3/3 Q70 (2.400690 in the wider geometry).
          if(!safe && h<(U(1)<<61) && bool(tail<half)!=reverse) {
            const int32_t r3_shifted=int32_t(poly_meta>>4);
            safe=int32_t(15*repaired_distance)+5*r3_shifted-3*r5>=(normal?34:42);
          }
          if(!safe) {
            const AtanTailCorrection ninth=atan_fast_ninth(h,r5);'''
assert old.count(needle) == 1
new = old.replace(needle, replace)
(W / 'native_eabi_m0_atan_fast.inc').write_text(new)
(W / 'small-h-lower-only.patch').write_text(''.join(difflib.unified_diff(
    old.splitlines(True), new.splitlines(True), fromfile='parent/native_eabi_m0_atan_fast.inc',
    tofile='candidate/native_eabi_m0_atan_fast.inc')))
for name in ('build.py', 'probe.py', 'bind-public.py', 'isolate.py', 'qualify.py'):
    code = (BASE / name).read_text()
    code = code.replace("BASE=ROOT/'.build/m0-atan-residual-geometry-20261024'",
                        "BASE=ROOT/'.build/m0-atan-directional-ninth-20261024'")
    if name == 'probe.py':
        anchor = 'inputs=list(dict.fromkeys(inputs))'
        code = code.replace(anchor, "inputs += [int(v,16) for v in ('3FEF1BCDCF0D1830','BFEF1BCDCF0D1830')]\n" + anchor)
    if name == 'isolate.py':
        code = code.replace("assert added=={'.text.unlikely.atan_inverse_half'} and not removed and set(changed)=={'.text.atan_fast','.text.unlikely.atan_fast_tail_repair'}",
                            "assert not added and not removed and set(changed)=={'.text.atan_fast'}")
        code = code.replace('PASS_ONLY_RP2040_ATAN_DIRECTIONAL_REPAIR_NINTH_CHANGED', 'PASS_ONLY_RP2040_ATAN_SMALL_H_LOWER_GATE_CHANGED')
    if name == 'qualify.py':
        code = code.replace('3dcdbe6abf7aec1d07029c0cd2f47cf10052aea482f3a2d72c45d57d471189a6', sha(BASE / 'qualification.json'))
        code = code.replace("assert json.loads((W/'certificate.json').read_text())['status']=='PASS_EXACT_FRACTION_DIRECTIONAL_NINTH_ATAN'",
                            "assert json.loads((W/'low-certificate.json').read_text())['status']=='PASS_EXACT_SMALL_H_LOWER_ATAN'")
        code = code.replace("for cap,tag in [(F(1,250),'directional_small_cap')", "for cap,tag in [(F(1,512),'small_h_lower_cap'),(F(1,250),'directional_small_cap')")
        code = code.replace("o=Oracle();rows=[]", "\nfor delta in range(-128,129):\n for sign in (0,SIGN):add((int('3FEF1BCDCF0D1830',16)+delta)|sign,'small_h_hard_neighbors')\no=Oracle();rows=[]")
        code = code.replace('PASS_ATAN_DIRECTIONAL_NINTH_ALL_INPUTS_PROFILED_NOT_PRODUCTION', 'PASS_ATAN_SMALL_H_LOWER_ALL_INPUTS_PROFILED_NOT_PRODUCTION')
    (W / name).write_text(code)
(W / 'preparation.json').write_text(json.dumps(dict(
    status='PRIVATE_SMALL_H_LOWER_GATE_CANDIDATE', parent_source_sha256=sha(BASE / 'native_eabi_m0_atan_fast.inc'),
    source_sha256=sha(W / 'native_eabi_m0_atan_fast.inc'), no_canonical_or_frozen_changed=True), indent=2) + '\n')
