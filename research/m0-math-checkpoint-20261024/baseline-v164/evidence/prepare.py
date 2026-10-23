"""Tighten only the fully scaled endpoint interval on RP2040."""
import hashlib,json,shutil
from pathlib import Path
root=Path.cwd();work=Path(__file__).resolve().parent;parent=root/'.build/m0-sqrt-zero-tail-v163-20261023'
def hashes(tree):
    return {str(p.relative_to(tree)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(tree.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
expected=json.loads((parent/'preparation.json').read_text())['source_file_hashes'];assert hashes(parent/'source')==expected
source=work/'source';assert not source.exists()
shutil.copytree(parent/'source',source,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
p=source/'code/native_eabi_m0_asin.inc';s=p.read_text()
needle='      angle=r96_sub(asin_half_pi(),asin_q70(small,exponent));error=128;';assert s.count(needle)==1
s=s.replace(needle,'''      angle=r96_sub(asin_half_pi(),asin_q70(small,exponent));
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
      // The relative error is <24 Q63 units. At exponent<=-13,
      // converting to Q70 and folding at most two half-pi constants
      // costs <24/64+1/2+1=1.875 units, so radius2 is sufficient.
      error=exponent<=-13?2U:128U;
#else
      error=128;
#endif''');p.write_text(s)
for name in ('domain-audit.py','M4-isolation.py','generic-isolation.py','special-profile.py','tiny-profile.py',
             'profile-matrix-subsets.py'):
    (work/name).write_text((parent/name).read_text().replace(parent.name,work.name))
proof=work/'proof';proof.mkdir()
for name in ('certify_m0_asin_fast.py','certify_m0_asin_nearest_root.py','certify_m0_atan_fast.py'):
    shutil.copyfile(root/'tools'/name,proof/name)
actual=hashes(source);modified=[n for n in expected if actual[n]!=expected[n]]
assert modified==['code/native_eabi_m0_asin.inc'] and set(actual)==set(expected)
(work/'preparation.json').write_text(json.dumps(dict(status='PREPARED_PRIVATE_SCALED_ENDPOINT_BOUND',parent='V163',
    source_file_hashes=actual,modified_files=modified,added_files=[],
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    proof_producers={n:hashlib.sha256((proof/n).read_bytes()).hexdigest() for n in
        ('certify_m0_asin_fast.py','certify_m0_asin_nearest_root.py','certify_m0_atan_fast.py')},
    previous_goal_turn_classification='progress: V163 accelerated sqrt cold values and measured all174 correct-reference subset means, retaining508 slower inputs.',
    new_tables=0,new_global_RAM=0,hardware_accessed=False,production_promoted=False,goal_complete=False),indent=2)+'\n')
print('PASS:',len(actual),'source files; only RP2040 endpoint radius128->2 when exponent<=-13; arithmetic unchanged.')
