"""Extend the immutable residual stage to the other reduction geometries."""
from pathlib import Path
import difflib,hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
BASE=ROOT/'.build/m0-atan-residual-original-goal-20261024'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASE/'result.json')=='e047da61a015906cac349efa0331625bd625c53a7e42de622fb94268225d669c'
assert sha(BASE/'native_eabi_m0_atan_fast.inc')=='aa6ce7be864f7f364e106711d7173f66b78f1fe512f29779e7793dd99835c517'
old=(BASE/'native_eabi_m0_atan_fast.inc').read_text()
new=old.replace('// Internal domain: non-inverted exponent -5..-1 and quotient error <33.',
                '// Internal domain: every fast reduction geometry, quotient error <33.')
new=new.replace('// d>=2^59, hence the truncated divisor is never zero.',
                '// d>=2^58, hence the truncated divisor is at least2^20.')
needle='        if(normalization>=5 || h>(U(1)<<62)+(U(1)<<40)) return false;'
assert new.count(needle)==1
cap=(1<<70)//250
new=new.replace(needle,'''        uint32_t repaired_radius=6;
        if(h>(U(1)<<62)+(U(1)<<40)) {
          if(h>UINT64_C(@CAP@)) return false;
          repaired_radius=7;
        }'''.replace('@CAP@',str(cap)))
assert new.count('if(repaired_distance<6) return false;')==1
new=new.replace('if(repaired_distance<6) return false;','if(repaired_distance<repaired_radius) return false;')
for name in ('native_eabi_m0.cpp','native_eabi_m0_atan.inc'):(W/name).write_bytes((BASE/name).read_bytes())
(W/'native_eabi_m0_atan_fast.inc').write_text(new)
(W/'geometry-only.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='residual-parent/code/native_eabi_m0_atan_fast.inc',tofile='candidate/code/native_eabi_m0_atan_fast.inc')))
report=dict(status='PREPARED_PRIVATE_ATAN_GEOMETRY_EXTENSION',parent_result_sha256=sha(BASE/'result.json'),source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),
            small_h_cap=(1<<62)+(1<<40),outer_h_cap=cap,new_tables=0,new_global_RAM=0,
            canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False)
(W/'preparation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
