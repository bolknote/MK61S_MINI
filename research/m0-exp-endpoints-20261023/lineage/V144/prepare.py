"""Preserve the original veneer layout while extending the small-y interval path."""
import hashlib
import json
from pathlib import Path
import shutil

root = Path.cwd()
work = Path(__file__).resolve().parent
parent = root/'.build/m0-pow-small-y-v143-20261023'
expected = json.loads((parent/'preparation.json').read_text())['source_file_hashes']


def files(tree):
    return {str(p.relative_to(tree)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(tree.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


assert files(parent/'source') == expected
source = work/'source'
assert not source.exists()
shutil.copytree(parent/'source', source, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
path = source/'code/native_eabi_m0_pow_fast.inc'
text = path.read_text()
marker = '// Reuse the certified logarithm, but retain the complete product before a'
assert text.count(marker) == 1
support = '''// Complete scaled product, using variable32-bit shifts only. q.high is
// uint32_t, sy<2^53 and64<=shift<128. The caller requires a Q64 magnitude<1.
__attribute__((always_inline)) inline bool pow_small_argument(const PowFastLog &q,U sy,unsigned shift,Product &out) {
  const Product low=multiply(q.low,sy);
  const U p0=wide32(q.high,uint32_t(sy));
  const U cross=wide32(q.high,uint32_t(sy>>32))+(p0>>32);
  const U high_low=(cross<<32)|uint32_t(p0);
  const U middle=low.high+high_low;
  const uint32_t upper=uint32_t(cross>>32)+uint32_t(middle<low.high);
  const uint32_t ml=uint32_t(middle),mh=uint32_t(middle>>32);
  uint32_t lo,hi;
  if(shift<96) {
    const unsigned s=shift-64;
    if(!s) {if(upper) return false;lo=ml;hi=mh;}
    else {
      if(upper>>s) return false;
      lo=(ml>>s)|(mh<<(32-s));hi=(mh>>s)|(upper<<(32-s));
    }
  } else {
    const unsigned s=shift-96;
    lo=s?(mh>>s)|(upper<<(32-s)):mh;
    hi=upper>>s;
  }
  out={0,(U(hi)<<32)|lo};return true;
}
extern "C" MK61_SOFT_PCS U mk61_m0_pow_exp_product_flash(U,U);
__attribute__((always_inline)) inline bool pow_small_exp_normal(const Product &argument,unsigned input_error,bool negative_argument,U &out) {
  if(argument.high || argument.low>(U(1)<<62)) return false;
#define M0_POW_EXP_REJECT() return false
#define M0_POW_EXP_RESULT(value) do {out=(value);return true;} while(0)
#define mk61_m0_pow_exp_product mk61_m0_pow_exp_product_flash
'''
body = (source/'code/native_eabi_m0_pow_exp_body.inc').read_text()
body = body[:body.index('  if(k>1023) {')]
needle = '  const uint32_t n=uint32_t((p1+(1U<<21))>>22);'
assert body.count(needle) == 1
body = body.replace(needle, needle+'\n  if(n>=512) return false;')
support += body
support += '''  // The checked argument magnitude is<=1/4, so exp stays in(1/2,2).
  // Keep a defensive normal-range test; no variable64-bit shift is needed.
  if(k<-2 || k>1) return false;
  const uint32_t rounding_tail=uint32_t(q)&1023U;
  if(uint32_t(rounding_tail-(512U-error))<=2*error) return false;
  const U rounded=(q+511+((q>>10)&1))>>10;
  out=(U(k+1022)<<52)+rounded;return true;
#undef mk61_m0_pow_exp_product
#undef M0_POW_EXP_RESULT
#undef M0_POW_EXP_REJECT
}
'''
text = text.replace(marker, support+marker)
old = '''  if(!pow_scaled_argument({logarithm.high,logarithm.low},(ym&D::Fraction)|D::Hidden,
                          unsigned(shift),argument) ||'''
new = '''  if(!pow_small_argument(logarithm,(ym&D::Fraction)|D::Hidden,unsigned(shift),argument) ||'''
assert text.count(old) == 1
text = text.replace(old, new)
text = text.replace('if(ey<=-43 && !argument.high && !uint32_t(argument.low>>32) && input_error<128) {',
                    'if(!argument.high && !uint32_t(argument.low>>32) && input_error<128 &&\n     uint32_t(argument.low)<=0xFFFFFFFFU-input_error) {')
text = text.replace('''    // |y|<2^-42 gives |z|<745*2^-42 and
    // |exp(z)-1-z|*2^64 <745^2/2^20<1. Below1 the Q64 grid''',
                    '''    // The entire Q64 magnitude enclosure is<2^32, so |z|<2^-32
    // and |exp(z)-1-z|*2^64<1. Below1 the Q64 grid''')
text = text.replace('return pow_exp_argument_checked(argument,input_error,negative,result)?real(result):mk61_m0_cr_pow(x,y);',
                    'return pow_small_exp_normal(argument,input_error,negative,result)?real(result):mk61_m0_cr_pow(x,y);')
path.write_text(text)
path = source/'code/native_eabi_m0_rp2040.S'
text = path.read_text()
marker = '#endif\n.section .note.GNU-stack,"",%progbits'
assert text.count(marker) == 1
thunk = '''
/* A private Flash thunk avoids adding an automatic ld veneer request.
 * The original SRAM kernel and every existing veneer remain unchanged. */
.section .m0_pow_small_y_cold,"ax",%progbits
.p2align 2
.hidden mk61_m0_pow_exp_product_flash
regular_func mk61_m0_pow_exp_product_flash
 push {r0}
 ldr r0,=mk61_m0_pow_exp_product
 mov ip,r0
 pop {r0}
 bx ip
 nop
 .ltorg
.size mk61_m0_pow_exp_product_flash,.-mk61_m0_pow_exp_product_flash
'''
path.write_text(text.replace(marker, thunk+marker))
for name in ['M4-isolation.py', 'generic-isolation.py']:
    shutil.copyfile(parent/name, work/name)
for name in ['tiny-profile.py', 'qualify-tiny.py', 'domain-audit.py']:
    text = (parent/name).read_text().replace(parent.name, work.name).replace('private V143', 'private V144')
    (work/name).write_text(text)
actual = files(source)
changed = sorted(n for n in expected if expected[n] != actual[n])
assert changed == ['code/native_eabi_m0_pow_fast.inc', 'code/native_eabi_m0_rp2040.S']
meta = dict(status='PREPARED_PRIVATE_SMALL_Y_STABLE_LAYOUT', parent='V143/3DE4C253',
            modified_files=changed, added_files=[], source_file_hashes=actual,
            original_exp_prefix_sha256=hashlib.sha256(body.encode()).hexdigest(),
            producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            hardware_accessed=False, production_promoted=False, goal_complete=False)
(work/'preparation.json').write_text(json.dumps(meta, indent=2)+'\n')
print('PASS: complete product with32-bit shifts; private Flash thunk; normal exp contract.', flush=True)
