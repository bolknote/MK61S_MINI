"""Private RP2040-only checked exp endpoint packing; keep frozen V144 intact."""
import hashlib
import json
from pathlib import Path
import shutil

root = Path.cwd()
work = Path(__file__).resolve().parent
parent = root/'.build/m0-pow-small-y-stable-v144-20261023'


def files(tree):
    return {str(p.relative_to(tree)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(tree.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


expected = json.loads((parent/'preparation.json').read_text())['source_file_hashes']
assert files(parent/'source') == expected
source = work/'source'
assert not source.exists()
shutil.copytree(parent/'source',source,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
path = source/'code/native_eabi_m0.cpp'
text = path.read_text()
marker = '// On ARMv6-M, -O3 expands wide products into substantially more spills than'
assert text.count(marker)==1
decl = '''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
extern "C" MK61_SOFT_PCS U mk61_m0_exp_endpoint(U,int,unsigned);
#endif
'''
text = text.replace(marker,decl+marker)
old = '''  return mk61_m0_cr_exp(x);
}
#include "native_eabi_m0_pow_fast.inc"'''
new = '''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  const U endpoint=mk61_m0_exp_endpoint(q,k,error);
  if(endpoint!=(D::Infinity|D::Quiet)) return real(endpoint);
#endif
  return mk61_m0_cr_exp(x);
}
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// The existing Q62 interval already encloses exp(x), including gradual
// underflow. Round its entire interval to the uniform subnormal grid.
extern "C" __attribute__((optimize("Os"),noinline,noipa,cold,section(".m0_exp_endpoints")))
MK61_SOFT_PCS U mk61_m0_exp_endpoint(U q,int k,unsigned error) {
  const U decline=D::Infinity|D::Quiet;
  if(k>1023) {
    // At binade1024 the overflow midpoint is Q62(2^62-256).
    if(k>1024 || q-(U(1)<<62)+256>error) return D::Infinity;
    return decline;
  }
  if(k>=-1022) return decline;
  if(k<-1075) {
    if(k<-1076 || ((U(1)<<63)-q>error && q<(U(1)<<63))) return 0;
    return decline;
  }
  const unsigned shift=unsigned(-k-1012); //11..63
  const uint32_t lo=uint32_t(q),hi=uint32_t(q>>32);
  U retained,tail,half;
  if(shift<32) {
    const uint32_t mask=(1U<<shift)-1;
    tail=lo&mask;half=1U<<(shift-1);
    retained=(U(hi>>shift)<<32)|(lo>>shift)|(hi<<(32-shift));
  } else {
    const unsigned s=shift-32;
    const uint32_t mask=s?(1U<<s)-1:0;
    tail=(U(hi&mask)<<32)|lo;
    half=s?U(1U<<(s-1))<<32:U(1U<<31);
    retained=s?hi>>s:hi;
  }
  const U distance=tail>half?tail-half:half-tail;
  if(distance<=error) return decline;
  return retained+U(tail>half);
}
#endif
#include "native_eabi_m0_pow_fast.inc"'''
assert text.count(old)==1
path.write_text(text.replace(old,new))
path = source/'ports/picocalc/m0_math_extension.ld'
text = path.read_text()
assert text.count('        *(.m0_exp_core)')==1
path.write_text(text.replace('        *(.m0_exp_core)','        *(.m0_exp_core)\n        *(.m0_exp_endpoints)'))
for name in ('M4-isolation.py','generic-isolation.py'):
    shutil.copyfile(parent/name,work/name)
text = (parent/'domain-audit.py').read_text().replace(parent.name,work.name)
(work/'domain-audit.py').write_text(text)
actual = files(source)
changed = sorted(n for n in expected if actual[n]!=expected[n])
assert changed == ['code/native_eabi_m0.cpp','ports/picocalc/m0_math_extension.ld']
(work/'preparation.json').write_text(json.dumps(dict(
    status='PREPARED_PRIVATE_EXP_ENDPOINT_CANDIDATE',parent='V144/4CA2268A',
    modified_files=changed,source_file_hashes=actual,
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    hardware_accessed=False,production_promoted=False,goal_complete=False),indent=2)+'\n')
print('PASS: private RP2040 exp endpoint candidate prepared; V144 untouched.',flush=True)
