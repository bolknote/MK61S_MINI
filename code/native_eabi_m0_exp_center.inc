// Expand the reduced argument about the nearest multiple of 2^-21.
// Each row stores the low-order even and full odd terms for ±c, leaving
// the dominant dyadic square to an exact integer product.
// A quadratic in the remaining |t| <= 2^-22 is enough for a Q69
// enclosure; certify_m0_exp_center.py bounds the complete fast path.
#define MK61_M0_EXP_CENTER_TABLE __attribute__((section(".m0_exp_center_table")))
#include "native_eabi_m0_exp_center_table.inc"
#undef MK61_M0_EXP_CENTER_TABLE
#include "native_eabi_m0_exp_scale_table.inc"

__attribute__((always_inline)) inline U exp_center_nonlinear(U h, bool negative) {
  const unsigned idx=(uint32_t(h>>32)+32768U)>>16;
  const uint32_t* row=exp_center[idx];
  const uint32_t packed=row[1];
  const U even=(U(idx*idx)<<26)+((packed&0x3FFFFFU)<<1);
  const U odd=(U(packed>>22)<<32)|row[0];
  const U g0=negative?even-odd:even+odd;
  const uint32_t nonlinear_slope=(uint32_t(g0>>25)+1U)>>1;
  const uint32_t coarse=idx<<22;
  const uint32_t lo=negative?coarse-nonlinear_slope:coarse+nonlinear_slope;
  const uint32_t upper=idx>>10;
  const uint32_t hi=negative?upper-uint32_t(coarse<nonlinear_slope):upper+uint32_t(lo<coarse);
  const U residual=h-(U(idx)<<48);
  const bool below=bool(residual>>63);
  const U t=below?U(0)-residual:residual;
  // |t| <= 2^-22. The rounded Q53 magnitude fits uint32_t.
  const uint32_t t53=uint32_t((t+(1U<<15))>>16);
  const uint32_t th=t53>>16,tl=uint16_t(t53);
  // t53 <= 2^31. Its high word and the rounded Q69 square need
  // only the top of the cross products, with no 64-bit carry.
  const uint32_t square_high=th*th+(((th*tl<<1)+(tl*tl>>16))>>16);
  const uint32_t correction=(square_high+32U)>>6;
  // exp(c+t)-1-(c+t) = g0 + g(t) + (exp(c)-1)*(t+g(t)),
  // where g(t)=exp(t)-1-t is approximated by t^2/2.
  const U v=(below!=negative)?t-correction:t+correction;
  const uint32_t head=uint32_t(v>>16), tail=uint32_t(v)&65535U;
  // Split the Q69 residual at bit16. Omitting the lowest 16x16
  // product costs less than 2^-11 of a Q69 unit.
  const U middle=wide32(lo,head)+((lo>>16)*tail)+U(hi*tail)*65536U;
  U product=((middle+(1U<<26))>>27)+(U(hi*head)<<5);
  if(below) product=U(0)-product;
  return g0+correction+product;
}

__attribute__((always_inline)) inline U exp_center_reduction(uint32_t n) {
  constexpr U integer=(exp_step_high<<5)+(exp_step_low>>27);
  constexpr uint32_t fraction=exp_step_low&0x7FFFFFFU;
  const uint32_t nl=uint16_t(n),nh=n>>16;
  const uint32_t fraction_mid=nl*(fraction>>16)+nh*uint16_t(fraction)+(nl*uint16_t(fraction)>>16);
  const uint32_t fraction_units=(nh*(fraction>>16)<<5)+(fraction_mid>>11);
  const uint32_t low=nl*uint16_t(integer)+fraction_units;
  const uint32_t middle=nl*uint16_t(integer>>16)+nh*uint16_t(integer)+(low>>16);
  const uint32_t high=uint32_t(integer>>32)*n+nh*uint16_t(integer>>16)+(middle>>16);
  return (U(high)<<32)|(middle<<16)|uint16_t(low);
}

MK61_M0_EXP_CORE __attribute__((optimize("Os","no-tree-ter","no-reorder-blocks","no-if-conversion")))
MK61_SOFT_PCS double mk61_m0_exp(double x) {
  const U a=bits(x),m=a&D::Magnitude;
  const uint32_t ah=uint32_t(a>>32),mh=ah&0x7FFFFFFFU;
  const int e=int(mh>>20)-1023;
  if(e>=10) {
    if(m>D::Infinity) return real(a|D::Quiet);
    return real(a&D::Sign?0:D::Infinity);
  }
  if(e < -54 || m==UINT64_C(0x3C90000000000000)) return 1.0;
  const U significand=(m&D::Fraction)|D::Hidden;
  uint32_t n=0;
  if(e>=-11) {
    const uint32_t head=uint32_t(significand>>21),lo=head&65535U,hi=head>>16;
    const uint32_t low=lo*0x3B29U;
    const uint32_t cross=hi*0x3B29U+lo*0xB8AAU+(low>>16);
    const uint32_t high=hi*0xB8AAU+(cross>>16);
    n=((high>>unsigned(20-e))+1U)>>1;
  }
  const int shift=e+17;
  U scaled;
  if(shift>0) {
    const uint32_t lo=uint32_t(significand),hi=uint32_t(significand>>32);
    scaled=(U((hi<<unsigned(shift))|(lo>>unsigned(32-shift)))<<32)|(lo<<unsigned(shift));
  } else scaled=significand>>unsigned(-shift);
  // Work modulo 2^64; only the small signed Q69 difference is needed.
  const U r=scaled-exp_center_reduction(n);
  const int k0=(a&D::Sign)?-int(n):int(n);
  const bool r_negative=bool(r>>63),negative=r_negative!=bool(a&D::Sign);
  // The certified reduction bound implies h < 2939*2^47, so the
  // nearest center index is in [0,1469] with no runtime bounds branch.
  const U h=r_negative?U(0)-r:r;
  int k=k0;
  const unsigned index=unsigned(k)&511U;
  k=(k-int(index))>>9;
  if(k < -1022 || k > 1023) return mk61_m0_cr_exp(x);
  const U g=exp_center_nonlinear(h,negative);
  const U d=negative?h-g:h+g;
  const uint32_t* row=exp_center_scale[index];
  const uint32_t al=row[0],high_base=row[1],dl=uint32_t(d),dh=uint32_t(d>>32);
  const U base=(U(high_base)<<32)|al;
  const U cross=wide32(high_base,dl)+wide32(al,dh);
  // Reuse the Q94 reduction table with seven fractional Q62 bits.
  // The omitted low-word product is in [0,4) Q69 units; +2 centers it.
  const U product=(wide32(high_base,dh)<<2)+((cross+(1U<<29))>>30)+2;
  // The missing seven scale bits are initially bounded around their
  // midpoint. Recover all seven only for an ambiguous rounding decision.
  const U correction=(negative?U(0)-product:product)+64U;
  U q=base+U(int64_t(correction)>>7);
  uint32_t fraction=uint32_t(correction)&127;
  uint32_t error=95; // Original error plus at most 64 Q69 units.
  if(q<(U(1)<<62)) {
    if(k==-1022) return mk61_m0_cr_exp(x);
    q=(q<<1)|(fraction>>6);--k;fraction=(fraction<<1)&127;error*=2;
  }
  uint32_t tail=((uint32_t(q)&1023U)<<7)|fraction;
  if(tail-(65536U-error)<=2*error) {
    // Near a midpoint the omitted bits can only change the rounding direction.
    // The midpoint guard fixes the high mantissa and normalization.
    const unsigned shift=error==190;
    const uint32_t omitted=refine_exp_table[index][0]>>25;
    tail+=(omitted-64U)<<shift;
    error=31U<<shift;
    if(tail-(65536U-error)<=2*error) return exp_refine(x,n);
  }
  return real((U(k+1022)<<52)+(q>>10)+U(tail>65536));
}

__attribute__((section(".ai_attention_fast_extension"),optimize("O2")))
MK61_SOFT_PCS float mk61_m0_exp_ai(float x) {
  const auto encoded=mk61ai::exp32_negative(bits(x),[](unsigned index) {
    return exp_center_scale[8*index][1];
  });
  return encoded ? single(encoded) : float(mk61_m0_exp(double(x)));
}
