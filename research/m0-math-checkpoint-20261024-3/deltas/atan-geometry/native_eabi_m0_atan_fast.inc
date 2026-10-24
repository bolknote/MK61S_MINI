// Bounded integer argument reduction for 1/64 <= |x| <= 64. The exact
// dyadic geometry is shared with the independent refinement. No rounded
// binary64 reciprocal, multiplication, addition or division is needed.
// tools/certify_m0_atan_fast.py certifies the complete Q70 error interval.
__attribute__((optimize("Os"),noinline)) static U atan_fast_reciprocal(U d) {
  const uint32_t high=uint32_t(d>>32);
  uint32_t r=mk61_m0_math_udiv32(1U<<30,uint32_t(d>>48))<<16;
  U p=wide32(high,r);bool negative=p>(U(1)<<62);
  U error=negative?p-(U(1)<<62):(U(1)<<62)-p;
  uint32_t correction=uint32_t((wide32(r,uint32_t(error>>16))+(U(1)<<45))>>46);
  r=negative?r-correction:r+correction;
  p=wide32(high,r);negative=p>(U(1)<<62);
  error=negative?p-(U(1)<<62):(U(1)<<62)-p;
  correction=uint32_t((wide32(r,uint32_t(error>>8))+(U(1)<<53))>>54);
  r=negative?r-correction:r+correction;

  const U p0=wide32(uint32_t(d),r);
  const U p1=wide32(high,r)+(p0>>32);
  const U low=(p1<<32)|uint32_t(p0);
  const uint32_t upper=uint32_t(p1>>32);
  negative=upper>(1U<<30) || (upper==(1U<<30) && low);
  U error_low;uint32_t error_high;
  if(negative) {error_low=low;error_high=upper-(1U<<30);}
  else {error_low=U(0)-low;error_high=(1U<<30)-upper-uint32_t(low!=0);}
  const U top=(U(error_high)<<32)|(error_low>>32);
  const U final_correction=low_product(top,r)>>30;
  const U seed=U(r)<<32;
  return negative?seed-final_correction:seed+final_correction;
}

__attribute__((optimize("Os"),noinline)) static U atan_fast_ratio(U numerator,U denominator) {
  const unsigned shift=clz64(denominator);
  return mk61_m0_product62(numerator<<shift,atan_fast_reciprocal(denominator<<shift));
}

#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
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
  const uint32_t delta=atan_tail_divide(top,uint32_t(d>>38));
  return negative?-int32_t(delta):int32_t(delta);
}

// Pack the bounded atan domain without the general96-bit CLZ path.
// Non-inverted inputs have output exponent e or e-1. Inverted inputs
// have output exponent0 or-1 and use base e=0. Enclosures remain in
// Q73 units, including the fractional121/8 Q70 directional bound.
__attribute__((always_inline)) inline bool atan_fast_pack(Refine96 q,int source_e,bool invert,bool negative,U h,U numerator,U denominator,U sign,U &result) {
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
        uint32_t repaired_radius=6;
        if(h>(U(1)<<62)+(U(1)<<40)) {
          if(h>UINT64_C(4722366482869645213)) return false;
          repaired_radius=7;
        }
        int32_t delta=atan_fast_tail_repair(numerator,denominator,h);
        if(negative!=invert) delta=-delta;
        // This path starts within54 units of a midpoint. abs(delta)<=33,
        // half>=1024: the quantum index, binade and retained bits cannot
        // change. Reuse them, update only the tail and rounding increment.
        tail=uint32_t(int32_t(tail)+delta);
        const uint32_t repaired_distance=tail>half?tail-half:half-tail;
        if(repaired_distance<repaired_radius) return false;
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
#endif

__attribute__((optimize("Os"),noinline)) static double atan_fast(double original) {
  const U b=bits(original),m=b&D::Magnitude,sign=b&D::Sign;
  const bool invert=m>UINT64_C(0x3FF0000000000000);
  const int e=int(m>>52)-1023;
  const U s=(m&D::Fraction)|D::Hidden;
  unsigned index;
  if(invert) {
    const uint32_t seed=mk61_m0_math_udiv32(1U<<30,uint32_t(s>>37));
    index=(seed+(1U<<unsigned(8+e)))>>unsigned(9+e);
  } else index=(unsigned(s>>unsigned(45-e))+1)/2;

  U numerator,denominator;bool negative;
  if(invert) {
    const U a=U(1)<<unsigned(58-e),c=low_product(s,index);
    negative=a<c;numerator=(negative?c-a:a-c)<<6;
    denominator=(s<<6)+(U(index)<<unsigned(52-e));
  } else {
    const U a=s<<6,c=U(index)<<unsigned(52-e);
    negative=a<c;const U n=negative?c-a:a-c;
    const U product=low_product(s,index);
    if(e==-6) {numerator=n<<5;denominator=(U(1)<<63)|(product>>1);}
    else {numerator=n<<6;denominator=(U(1)<<unsigned(58-e))+product;}
  }
  const U h=numerator?atan_fast_ratio(numerator,denominator):0;
  if(h>=(U(1)<<63)) return atan_refine(original,index);
  const U z=math62_right(mk61_m0_product62(h,h),8);
  const U c3=math62_right(mk61_m0_product62(h,z),8);
  const U c5=(wide32(uint32_t(c3>>17),uint32_t(z>>24))+(U(1)<<28))>>29;
  const uint32_t c7=uint32_t((wide32(uint32_t(c5>>3),uint32_t(z>>24))+(U(1)<<42))>>43);
  const U third=math62_third(c3);
  const U fifth=(wide32(uint32_t(c5>>3),0xCCCCCCCDU)+(U(1)<<30))>>31;
  const U seventh=wide32(c7+3,2454267027U)>>34;
  const U reduction=third-fifth+seventh;
  if(reduction>h) return atan_refine(original,index);
  const U correction=h-reduction;
  const uint32_t* row=refine_atan_table[index];
  Refine96 q={(U(row[1])<<32)|row[0],row[2]};
  q=negative?r96_sub_low(q,correction):r96_add_low(q,correction);
  if(invert) q=r96_sub({(U(refine_atan_half_pi[1])<<32)|refine_atan_half_pi[0],refine_atan_half_pi[2]},q);
  U result;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  if(atan_fast_pack(q,e,invert,negative,h,numerator,denominator,sign,result)) return real(result);
#else
  if(r96_pack(q,24,sign,64,result)) return real(result);
#endif
  return atan_refine(original,index);
}
