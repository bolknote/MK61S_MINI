#include <stdint.h>
using U=uint64_t;
struct Refine96 {U low;uint32_t high;};
__attribute__((always_inline)) inline U wide32(uint32_t a,uint32_t b) {
  const uint32_t al=a&0xFFFFU,ah=a>>16,bl=b&0xFFFFU,bh=b>>16;
  const uint32_t p=al*bl,t=ah*bl+(p>>16),v=al*bh+(t&0xFFFFU);
  return (U(ah*bh+(t>>16)+(v>>16))<<32)|(uint32_t(v<<16)|(p&0xFFFFU));
}
// top/den has at most six quotient bits. den<2^26 makes den<<5
// safe; binary compare/subtract needs no SIO divider or general division.
__attribute__((always_inline)) inline uint32_t atan_tail_divide(uint32_t top,uint32_t den) {
#if defined(__arm__) || defined(__thumb__)
  uint32_t q;
  asm volatile(".syntax unified\nlsls %[d],%[d],#5\nmovs %[q],#0\ncmp %[n],%[d]\nblo 1f\nsubs %[n],%[n],%[d]\n1:\nadcs %[q],%[q]\nlsrs %[d],%[d],#1\ncmp %[n],%[d]\nblo 1f\nsubs %[n],%[n],%[d]\n1:\nadcs %[q],%[q]\nlsrs %[d],%[d],#1\ncmp %[n],%[d]\nblo 1f\nsubs %[n],%[n],%[d]\n1:\nadcs %[q],%[q]\nlsrs %[d],%[d],#1\ncmp %[n],%[d]\nblo 1f\nsubs %[n],%[n],%[d]\n1:\nadcs %[q],%[q]\nlsrs %[d],%[d],#1\ncmp %[n],%[d]\nblo 1f\nsubs %[n],%[n],%[d]\n1:\nadcs %[q],%[q]\nlsrs %[d],%[d],#1\ncmp %[n],%[d]\nblo 1f\nsubs %[n],%[n],%[d]\n1:\nadcs %[q],%[q]\n.syntax divided\n" : [n]"+&l"(top),[d]"+&l"(den),[q]"=&l"(q) : : "cc");
  return q;
#else
  uint32_t q=0;
  for(unsigned bit=32;bit;bit>>=1) if(top>=den*bit) {top-=den*bit;q|=bit;}
  return q;
#endif
}

// Internal domain: every fast reduction geometry, quotient error <33.
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
  // d>=2^58, hence the truncated divisor is at least2^20.
  const uint32_t top=(uint32_t(high)<<26)|uint32_t(low>>38);
  const uint32_t den=uint32_t(d>>38);
  const uint32_t rounded=top+(den>>1);
  if(rounded<den) return 0;
  const uint32_t delta=atan_tail_divide(rounded,den);
  return negative?-int32_t(delta):int32_t(delta);
}

// Inverted N,D are multiples of64. The signed low64 product is the
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

// Pack the bounded atan domain without the general96-bit CLZ path.
// Non-inverted inputs have output exponent e or e-1. Inverted inputs
// have output exponent0 or-1 and use base e=0. Enclosures remain in
// Q73 units, including the fractional121/8 Q70 directional bound.
__attribute__((always_inline)) inline bool atan_fast_pack(Refine96 q,int source_e,bool invert,bool negative,U h,U numerator,U denominator,U sign,uint32_t poly_meta,U &result) {
  const int e=invert?0:source_e;
  const uint32_t numerator_high=uint32_t(numerator>>32);
  const unsigned lower=unsigned(q.high<(1U<<unsigned(e+6)));
  const unsigned shift=unsigned(e+18)-lower;
  const uint32_t half=1U<<(shift-1);
  uint32_t tail=uint32_t(q.low)&((half<<1)-1);
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
      if(distance73<radius73) {
        // A cheap inverted low64 residual can certify the unchanged q.
        if(!(invert && h<=UINT64_C(6558842337318951685) && distance>=7 &&
             atan_inverse_half(h,denominator))) {
          const bool reverse=negative!=invert;
          const bool normal=normalization<5;
          const int32_t r5=int32_t(poly_meta&15U)-4;
          int32_t delta=atan_fast_tail_repair(numerator,denominator,h);
          if(reverse) delta=-delta;
          tail=uint32_t(int32_t(tail)+delta);
          uint32_t repaired_distance=tail>half?tail-half:half-tail;
          const uint32_t repaired_radius=h>UINT64_C(7378697629483820646)?23U:
            h>UINT64_C(4722366482869645213)?9U:6U;
          bool safe=repaired_distance>=repaired_radius;
          if(!safe && bool(tail<half)==reverse)
            safe=int32_t(5*repaired_distance)+r5>=(normal?11:14);
          // For h<1/512 the old polynomial's lower error is below
          // 1.900690+r5/5-r3/3 Q70 (2.400690 in the wider geometry).
          if(!safe && h<(U(1)<<61) && bool(tail<half)!=reverse) {
            const int32_t r3_shifted=int32_t(poly_meta>>4);
            safe=int32_t(15*repaired_distance)+5*r3_shifted-3*r5>=(normal?34:42);
          }
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
      }
    }
  }
  const uint32_t lo=uint32_t(q.low),hi=uint32_t(q.low>>32);
  const uint32_t packed_low=(lo>>shift)|(hi<<(32-shift));
  const uint32_t packed_high=(hi>>shift)|(q.high<<(32-shift));
  result=sign+(U(unsigned(e+1022)-lower)<<52)+
    ((U(packed_high)<<32)|packed_low)+U(tail>half);
  return true;
}
struct Case {U low,h,n,d,sign;uint32_t high,meta;int32_t e;uint32_t invert,negative,pad;};
static_assert(sizeof(Case)==64);
extern "C" U check_pack(const Case* p) {
  U out=~U(0);bool ok=atan_fast_pack({p->low,p->high},p->e,p->invert,p->negative,p->h,p->n,p->d,p->sign,p->meta,out);
  return ok?out:~U(0);
}
