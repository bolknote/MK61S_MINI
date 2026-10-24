"""Private bounded quotient residual; the parent review target is read-only."""
from pathlib import Path
import difflib,hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
BASE=ROOT/'.build/m0-atan-original-goal-20261024'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASE/'result.json')=='82dbe45fe869c8984cc94b38be5003d633e8232c16bbf5834e0cb2760e5fe3a9'
assert sha(BASE/'native_eabi_m0_atan_fast.inc')=='502deb2e33c2736eb7d7f672e250a61c716e616362a8574ad1367620bc7ae541'
old=(BASE/'native_eabi_m0_atan_fast.inc').read_text()
instructions=['.syntax unified','lsls %[d],%[d],#5','movs %[q],#0']
for bit in range(5,-1,-1):
 instructions+=['cmp %[n],%[d]','blo 1f','subs %[n],%[n],%[d]','1:','adcs %[q],%[q]']
 if bit:instructions+=['lsrs %[d],%[d],#1']
instructions+=['.syntax divided']
assembly='asm volatile('+json.dumps('\n'.join(instructions)+'\n')+' : [n]"+&l"(top),[d]"+&l"(den),[q]"=&l"(q) : : "cc");'
helper='''// top/den has at most six quotient bits. den<2^26 makes den<<5
// safe; binary compare/subtract needs no SIO divider or general division.
__attribute__((always_inline)) inline uint32_t atan_tail_divide(uint32_t top,uint32_t den) {
#if defined(__arm__) || defined(__thumb__)
  uint32_t q;
  @BOUNDED_ASM@
  return q;
#else
  uint32_t q=0;
  for(unsigned bit=32;bit;bit>>=1) if(top>=den*bit) {top-=den*bit;q|=bit;}
  return q;
#endif
}

// Internal domain: non-inverted exponent -5..-1 and quotient error <33.
// Reuse the parent's exact dyadic numerator and denominator.
__attribute__((optimize("Os"),noinline,cold)) static int32_t atan_fast_tail_repair(U n,U d,U h) {
  const uint32_t al=uint32_t(h),ah=uint32_t(h>>32),bl=uint32_t(d),bh=uint32_t(d>>32);
  const U p=wide32(al,bl),t=wide32(ah,bl)+(p>>32);
  const U v=wide32(al,bh)+uint32_t(t);
  const U product_low=(v<<32)|uint32_t(p);
  const uint32_t product_high=ah*bh+uint32_t(t>>32)+uint32_t(v>>32);
  U low=U(0)-product_low;
  // Only71 residual bits are needed: abs(R)<33*d<2^70. The low7
  // high-word bits determine its sign; the high-high product needs one
  // 32-bit MULS rather than a full wide multiplication.
  int32_t high=int32_t((uint32_t(n)-product_high-uint32_t(product_low!=0))<<25)>>25;
  const bool negative=high<0;
  if(negative) {low=U(0)-low;high=~high+int32_t(!low);}
  // abs(residual)<33*d, so high<=32 and this top word fits uint32.
  // d>=2^59, hence the truncated divisor is never zero.
  const uint32_t top=(uint32_t(high)<<26)|uint32_t(low>>38);
  const uint32_t delta=atan_tail_divide(top,uint32_t(d>>38));
  return negative?-int32_t(delta):int32_t(delta);
}

'''.replace('@BOUNDED_ASM@',assembly)
needle='// Pack the bounded atan domain without the general96-bit CLZ path.'
assert old.count(needle)==1
new=old.replace(needle,helper+needle)
needle='atan_fast_pack(Refine96 q,int source_e,bool invert,bool negative,U h,uint32_t numerator_high,U sign,U &result)'
assert new.count(needle)==1
new=new.replace(needle,'atan_fast_pack(Refine96 q,int source_e,bool invert,bool negative,U h,U numerator,U denominator,U sign,U &result)')
new=new.replace('  const int e=invert?0:source_e;','  const int e=invert?0:source_e;\n  const uint32_t numerator_high=uint32_t(numerator>>32);')
new=new.replace('const uint32_t half=1U<<(shift-1),tail=uint32_t(q.low)&((half<<1)-1);','const uint32_t half=1U<<(shift-1);\n  uint32_t tail=uint32_t(q.low)&((half<<1)-1);')
needle='      if(distance73<radius73) return false;'
assert new.count(needle)==1
new=new.replace(needle,'''      if(distance73<radius73) {
        if(normalization>=5 || h>(U(1)<<62)+(U(1)<<40)) return false;
        int32_t delta=atan_fast_tail_repair(numerator,denominator,h);
        if(negative!=invert) delta=-delta;
        // This path starts within54 units of a midpoint. abs(delta)<=33,
        // half>=1024: the quantum index, binade and retained bits cannot
        // change. Reuse them, update only the tail and rounding increment.
        tail=uint32_t(int32_t(tail)+delta);
        const uint32_t repaired_distance=tail>half?tail-half:half-tail;
        if(repaired_distance<6) return false;
      }''')
needle='atan_fast_pack(q,e,invert,negative,h,uint32_t(numerator>>32),sign,result)'
assert new.count(needle)==1
new=new.replace(needle,'atan_fast_pack(q,e,invert,negative,h,numerator,denominator,sign,result)')
for name in ('native_eabi_m0.cpp','native_eabi_m0_atan.inc'):(W/name).write_bytes((BASE/name).read_bytes())
(W/'native_eabi_m0_atan_fast.inc').write_text(new)
(W/'residual-only.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='atan-parent/code/native_eabi_m0_atan_fast.inc',tofile='candidate/code/native_eabi_m0_atan_fast.inc')))
report=dict(status='PREPARED_PRIVATE_ATAN_RESIDUAL_REPAIR',parent_result_sha256=sha(BASE/'result.json'),parent_source_sha256=sha(BASE/'native_eabi_m0_atan_fast.inc'),source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),new_tables=0,new_global_RAM=0,canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False)
(W/'preparation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
