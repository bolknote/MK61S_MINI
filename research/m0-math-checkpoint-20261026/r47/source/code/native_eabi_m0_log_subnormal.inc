// RP2040-only cold logarithms. Existing normal-input kernels stay intact.
// x=N*2^-1074; conversion of N is exact. The old Q70 center/residual
// enclosures therefore apply with n=1074-floor(log2(N)) in[1023,1074].
// The full interval must fit an RNE cell; uncertainty goes directly to
// CORE-MATH on the original input, not the normal-only Q94 refinement.
__attribute__((always_inline)) inline double ln_subnormal_pack70(U low,uint32_t high,U sign,uint32_t error,double x) {
  const unsigned shift=27;const int bias=1039;
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
  const uint32_t guard=error-1;
  if(uint32_t(tail-(half-guard))<=2*guard) return mk61_m0_cr_ln(x);
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-8)<<52)+q);
}
__attribute__((always_inline)) inline double log10_direct_subnormal_pack70(U low,uint32_t high,U sign,uint32_t error,double x) {
  const unsigned shift=26;const int bias=1038;
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
  if(uint32_t(tail-(half-error))<=2*error) return mk61_m0_cr_log10(x);
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-8)<<52)+q);
}
extern "C" __attribute__((optimize("Os"),noinline,noipa,cold,section(".m0_log_subnormal")))
MK61_SOFT_PCS double mk61_m0_ln_special(double x) {
  const U raw=bits(x);
  if(!raw || raw>=UINT64_C(0x0010000000000000)) {
    const U magnitude=raw&D::Magnitude;
    if(!magnitude) return real(D::Sign|D::Infinity);
    if(magnitude>D::Infinity) return real(raw|D::Quiet);
    if(raw&D::Sign) return real(D::Infinity|D::Quiet);
    if(magnitude==D::Infinity) return x;
    return mk61_m0_cr_ln(x);
  }
  // N is an integer below2^52, exactly representable by the old converter.
  // Its significand is unchanged; actual exponent is floor(log2(N))-1074.
  const U b=bits(__aeabi_ul2d(raw));
  const unsigned index=unsigned((b&D::Fraction)>>42);
  const U offset=b&((U(1)<<42)-1),half_segment=U(1)<<41;
  const bool negative=offset<half_segment;
  const U delta=negative?half_segment-offset:offset-half_segment;
  // The distance from the exact dyadic center is kept unrounded.
  // RP2040 divides it exactly; generic ARMv6-M uses the certified reciprocal.
  const U h=log70_residual(delta,index);
  const uint32_t t=uint32_t(h>>27);
  const U z=(wide32(t,t)>>16)+(wide32(t,uint32_t(h)&0x7FFFFFFU)>>42)+1;
  const U cube=mk61_m0_log_cube70(h,z);
  const U third=math62_third(cube);
  const uint32_t fourth=uint32_t(wide32(uint32_t(cube>>6),t)>>37);
  const uint32_t fifth=uint32_t(wide32(fourth,t)>>43);
  const U even=((z+1)>>1)+((fourth+2)>>2);
  const U odd=h+third+((fifth+2)*52429U>>18);
  const U correction=negative?U(0)-odd-even:odd-even;
  const Log70Center center=log70_center(index);
  U low=center.low;uint32_t high=center.high;
  if(negative) {const U old=low;low+=correction;high-=low>old;}
  else {const U old=low;low+=correction;high+=low<old;}
  const uint32_t n=2097U-unsigned(b>>52);
  const U p0=wide32(uint32_t(log70_two_low),n),p1=wide32(uint32_t(log70_two_low>>32),n)+(p0>>32);
  U result=(p1<<32)|uint32_t(p0);uint32_t upper=uint32_t(p1>>32)+log70_two_high*n;
  const U old=result;
  result-=low;upper-=high+uint32_t(old<low);
  return ln_subnormal_pack70(result,upper,D::Sign,ln_main_radius+(n+1)/2,x);
}

extern "C" __attribute__((optimize("Os"),noinline,noipa,cold,section(".m0_log_subnormal")))
MK61_SOFT_PCS double mk61_m0_log10_special(double x) {
  const U raw=bits(x);
  if(!raw || raw>=UINT64_C(0x0010000000000000)) {
    const U magnitude=raw&D::Magnitude;
    if(!magnitude) return real(D::Sign|D::Infinity);
    if(magnitude>D::Infinity) return real(raw|D::Quiet);
    if(raw&D::Sign) return real(D::Infinity|D::Quiet);
    if(magnitude==D::Infinity) return x;
    return mk61_m0_cr_log10(x);
  }
  // N is an integer below2^52, exactly representable by the old converter.
  // Its significand is unchanged; actual exponent is floor(log2(N))-1074.
  const U b=bits(__aeabi_ul2d(raw));
  const uint32_t* row=log10_table[unsigned((b&D::Fraction)>>42)];
  const U reciprocal=(U(row[1])<<32)|(row[0]&~63U);
  const U offset=b&((U(1)<<42)-1),half_segment=U(1)<<41;
  const bool negative=offset<half_segment;
  const U delta=negative?half_segment-offset:offset-half_segment;
  // Multiply the distance from the exact dyadic center, not the complete
  // mantissa. Clearing six reciprocal bits costs <2 Q70 residual units
  // and leaves room for the high log bits in a 16-byte table row.
  const U h=mk61_m0_log_product46(delta,reciprocal);
  const uint32_t t=uint32_t(h>>27);
  const U z=(wide32(t,t)>>16)+(wide32(t,uint32_t(h)&0x7FFFFFFU)>>42)+1;
  const U cube=mk61_m0_log_cube70(h,z);
  const U third=math62_third(cube);
  const uint32_t fourth=uint32_t(wide32(uint32_t(cube>>6),t)>>37);
  const uint32_t fifth=uint32_t(wide32(fourth,t)>>43);
  const U even=((z+1)>>1)+((fourth+2)>>2);
  const U odd=h+third+((fifth+2)*52429U>>18);
  const U correction=math62_product(negative?odd+even:odd-even,log10_inverse>>2);
  U low=(U(row[3])<<32)|row[2];uint32_t high=row[0]&63U;
  if(negative) {const U old=low;low-=correction;high-=low>old;}
  else {const U old=low;low+=correction;high+=low<old;}
  const uint32_t n=2097U-unsigned(b>>52);
  const U p0=wide32(uint32_t(log10_two_low),n),p1=wide32(uint32_t(log10_two_low>>32),n)+(p0>>32);
  U result=(p1<<32)|uint32_t(p0);uint32_t upper=uint32_t(p1>>32)+log10_two_high*n;
  const U old=result;
  result-=low;upper-=high+uint32_t(old<low);
  return log10_direct_subnormal_pack70(result,upper,D::Sign,12+(n+1)/2,x);
}
