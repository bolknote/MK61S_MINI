"""Private RP2040 atan packing bounds, retaining the original fallback."""
from pathlib import Path
import difflib,hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
old=(P/'native_eabi_m0_atan_fast.inc').read_text()
helper='''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
// Pack the bounded atan domain without the general96-bit CLZ path.
// Non-inverted inputs have output exponent e or e-1. Inverted inputs
// have output exponent0 or-1 and use base e=0. Enclosures remain in
// Q73 units, including the fractional121/8 Q70 directional bound.
__attribute__((always_inline)) inline bool atan_fast_pack(Refine96 q,int source_e,bool invert,bool negative,U h,uint32_t numerator_high,U sign,U &result) {
  const int e=invert?0:source_e;
  const unsigned lower=unsigned(q.high<(1U<<unsigned(e+6)));
  const unsigned shift=unsigned(e+18)-lower;
  const uint32_t half=1U<<(shift-1),tail=uint32_t(q.low)&((half<<1)-1);
  const uint32_t distance=tail>half?tail-half:half-tail;
  const uint32_t distance73=distance<<3;
  const bool small=h<=(U(1)<<62);
  // Most cells need only the cheap symmetric enclosure. Calculate the
  // tighter direction/region only when that enclosure is undecided.
  if(distance73<(small?288U:426U)) {
    const bool favored=bool(tail<half)==(negative!=invert);
    uint32_t radius73=small?(favored?144U:288U):(favored?282U:426U);
    if(distance73<radius73) {
      const unsigned normalization=unsigned(source_e+5);
      if(normalization<5 && h<=(U(47)<<57) &&
         (numerator_high>>unsigned(24-normalization))<49) {
        radius73=favored?121U:176U;
        if(distance73<radius73 && (numerator_high>>unsigned(27-normalization))==0)
          radius73=favored?91U:100U;
      }
      // True errors are strictly below the radius, so equality of the
      // midpoint distance with the radius remains safe.
      if(distance73<radius73) return false;
    }
  }
  const uint32_t lo=uint32_t(q.low),hi=uint32_t(q.low>>32);
  const uint32_t packed_low=(lo>>shift)|(hi<<(32-shift));
  const uint32_t packed_high=(hi>>shift)|(q.high<<(32-shift));
  result=sign+(U(unsigned(e+1022)-lower)<<52)+
    ((U(packed_high)<<32)|packed_low)+U(tail>half);
  return true;
}
#endif

'''
needle='__attribute__((optimize("Os"),noinline)) static double atan_fast(double original) {'
assert old.count(needle)==1
new=old.replace(needle,helper+needle)
needle='  if(r96_pack(q,24,sign,64,result)) return real(result);\n  return atan_refine(original,index);'
assert new.count(needle)==1
new=new.replace(needle,'''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  if(atan_fast_pack(q,e,invert,negative,h,uint32_t(numerator>>32),sign,result)) return real(result);
#else
  if(r96_pack(q,24,sign,64,result)) return real(result);
#endif
  return atan_refine(original,index);''')
for name in ('native_eabi_m0.cpp','native_eabi_m0_atan.inc'):(W/name).write_bytes((P/name).read_bytes())
(W/'native_eabi_m0_atan_fast.inc').write_text(new)
(W/'atan-packing-only.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='V164/code/native_eabi_m0_atan_fast.inc',tofile='candidate/code/native_eabi_m0_atan_fast.inc')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
(W/'preparation.json').write_text(json.dumps(dict(status='PRIVATE_RP2040_ATAN_PACKING_BOUND_CANDIDATE',source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),parent_sha256=sha(P/'native_eabi_m0_atan_fast.inc'),new_tables=0,new_global_RAM=0,canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False),indent=2)+'\n')
print('Prepared private atan packing bounds; no arithmetic or table replaced.')
