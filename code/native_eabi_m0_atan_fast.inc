#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
#include "native_eabi_m0_atan_correct.inc"
#endif
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
  result=atan_pack70(q,sign,64);
  if(result) return real(result);
  result=atan_round_correct(sign,q,numerator,denominator,h,z,c7,negative!=invert);
  if(result) return real(result);
#else
  if(r96_pack(q,24,sign,64,result)) return real(result);
#endif
  return atan_refine(original,index);
}
