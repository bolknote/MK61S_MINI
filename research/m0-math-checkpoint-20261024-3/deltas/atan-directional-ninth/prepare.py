"""Private directional rounding and Q16 ninth term, over a sealed parent."""
from pathlib import Path
import difflib,hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
BASE=ROOT/'.build/m0-atan-residual-geometry-20261024'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASE/'result.json')=='2f3f8deb8a78125c6a55c1f146c6dd1c72d9b56ff4f677bba3bacd84ce34f22d'
assert sha(BASE/'native_eabi_m0_atan_fast.inc')=='b8a45df5715c7fbf3e7c5a6d29cd7f063daf8695c7f9324cd4a4647ffb682f7b'
old=(BASE/'native_eabi_m0_atan_fast.inc').read_text();new=old
needle='  const uint32_t delta=atan_tail_divide(top,uint32_t(d>>38));'
assert new.count(needle)==1
new=new.replace(needle,'''  const uint32_t den=uint32_t(d>>38);
  const uint32_t rounded=top+(den>>1);
  if(rounded<den) return 0;
  const uint32_t delta=atan_tail_divide(rounded,den);''')
helpers='''// Inverted N,D are multiples of64. The signed low64 product is the
// exact residual divided by64, since its magnitude is below2^60.
__attribute__((optimize("Os"),noinline,cold)) static bool atan_inverse_half(U h,U d) {
  const U factor=d>>6;
  const uint32_t al=uint32_t(h),ah=uint32_t(h>>32);
  const uint32_t bl=uint32_t(factor),bh=uint32_t(factor>>32);
  U residue=wide32(al,bl)+(U(ah*bl+al*bh)<<32);
  // The unsigned shifted interval is a safe subset of |R'|<=factor/2.
  return residue+(factor>>1)<factor;
}

// Four Q16 products approximate h^9/9 within .51 Q70, without wide MUL.
struct AtanTailCorrection {int32_t delta,remainder;};
__attribute__((always_inline)) inline AtanTailCorrection atan_fast_ninth(U h,int32_t r5) {
  const uint32_t x=uint32_t(h>>47);
  const uint32_t q2=(x*x+32768U)>>16;
  const uint32_t q4=(q2*q2+32768U)>>16;
  const uint32_t q8=(q4*q4+32768U)>>16;
  const uint32_t q9=(q8*x+32768U)>>16;
  const uint32_t ninth=((((q9+2304U)>>9)*7282U)>>16);
  const uint32_t v=uint32_t(r5+7),q5=(v*13108U)>>16;
  return {int32_t(q5+ninth)-1,int32_t(v)-int32_t(5*q5)-2};
}

'''
needle='// Pack the bounded atan domain without the general96-bit CLZ path.'
assert new.count(needle)==1;new=new.replace(needle,helpers+needle)
needle='atan_fast_pack(Refine96 q,int source_e,bool invert,bool negative,U h,U numerator,U denominator,U sign,U &result)'
assert new.count(needle)==1
new=new.replace(needle,'atan_fast_pack(Refine96 q,int source_e,bool invert,bool negative,U h,U numerator,U denominator,U sign,uint32_t poly_meta,U &result)')
begin=new.index('        uint32_t repaired_radius=6;')
end=new.index('      }\n    }\n  }\n  const uint32_t lo=',begin)
new=new[:begin]+'''        // A cheap inverted low64 residual can certify the unchanged q.
        if(!(invert && h<=UINT64_C(@INVERSE_CAP@) && distance>=7 &&
             atan_inverse_half(h,denominator))) {
          const bool reverse=negative!=invert;
          const bool normal=normalization<5;
          const int32_t r5=int32_t(poly_meta&15U)-4;
          int32_t delta=atan_fast_tail_repair(numerator,denominator,h);
          if(reverse) delta=-delta;
          tail=uint32_t(int32_t(tail)+delta);
          uint32_t repaired_distance=tail>half?tail-half:half-tail;
          const uint32_t repaired_radius=h>UINT64_C(@MIDDLE_CAP@)?23U:
            h>UINT64_C(@SMALL_CAP@)?9U:6U;
          bool safe=repaired_distance>=repaired_radius;
          if(!safe && bool(tail<half)==reverse)
            safe=int32_t(5*repaired_distance)+r5>=(normal?11:14);
          if(!safe) {
            const AtanTailCorrection ninth=atan_fast_ninth(h,r5);
            int32_t extra=ninth.delta;
            const int32_t corrected_r5=ninth.remainder;
            if(reverse) extra=-extra;
            tail=uint32_t(int32_t(tail)+extra);
            repaired_distance=tail>half?tail-half:half-tail;
            const int32_t r3=int32_t(poly_meta>>4)-1;
            if(repaired_distance<7 && !(bool(tail<half)==reverse &&
                int32_t(15*repaired_distance)>=(normal?35:42)+5*r3-3*corrected_r5))
              return false;
          }
        }
'''.replace('@INVERSE_CAP@',str((1<<70)//180)).replace('@SMALL_CAP@',str((1<<70)//250)).replace('@MIDDLE_CAP@',str((1<<70)//160))+new[end:]
needle='  const U reduction=third-fifth+seventh;'
assert new.count(needle)==1
new=new.replace(needle,'''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  const int32_t r3=int32_t(uint32_t(c3)-3U*uint32_t(third));
  const int32_t r5=int32_t(uint32_t(c5)-5U*uint32_t(fifth));
  const uint32_t poly_meta=uint32_t(r5+4)|(uint32_t(r3+1)<<4);
#endif
'''+needle)
needle='atan_fast_pack(q,e,invert,negative,h,numerator,denominator,sign,result)'
assert new.count(needle)==1;new=new.replace(needle,'atan_fast_pack(q,e,invert,negative,h,numerator,denominator,sign,poly_meta,result)')
for name in ('native_eabi_m0.cpp','native_eabi_m0_atan.inc'):(W/name).write_bytes((BASE/name).read_bytes())
(W/'native_eabi_m0_atan_fast.inc').write_text(new)
(W/'directional-ninth-only.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='geometry-parent/code/native_eabi_m0_atan_fast.inc',tofile='candidate/code/native_eabi_m0_atan_fast.inc')))
report=dict(status='PREPARED_PRIVATE_DIRECTIONAL_NINTH_ATAN',source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),
            parent_result_sha256=sha(BASE/'result.json'),new_tables=0,new_global_RAM=0,
            canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False)
(W/'preparation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
