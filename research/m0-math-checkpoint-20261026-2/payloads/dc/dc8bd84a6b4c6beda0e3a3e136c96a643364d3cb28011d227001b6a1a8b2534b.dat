// RP2040-only: exact residual division permits a tighter argument bound.
// Full fourth/fifth products and the sixth Taylor term certify radius6.
__attribute__((optimize("Os"),noinline,noipa,section(".m0_pow_log6")))
PowFastLog mk61_m0_pow_log_ordinary(int,U b) {
  const int k=int((b>>52)&0x7FFU)-1023;
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
  const U third=pow_log_third70(cube);
  const uint32_t fourth=uint32_t(wide32(uint32_t(cube>>6),t)>>37);
  const uint32_t fifth=uint32_t(wide32(fourth,t)>>43);
  unsigned base_error=5;uint32_t sixth_term=0;
  if(h>(U(1)<<58)) {
    const uint32_t lo=uint32_t(cube),hi=uint32_t(cube>>32);
    const uint32_t c0=(lo&65535U)*hi,c1=(lo>>16)*hi+(c0>>16);
    const uint32_t sixth=(hi*hi+(c1>>15))>>6;
    sixth_term=((sixth+3)*43U)>>8;base_error=6;
  }
  const U even=((z+1)>>1)+((fourth+2)>>2)+sixth_term;
  const U odd=h+third+((fifth+2)*52429U>>18);
  const U correction=negative?U(0)-odd-even:odd-even;
  const Log70Center center=log70_center(index);
  uint32_t l0=uint32_t(center.low),l1=uint32_t(center.low>>32),l2=center.high;
  const uint32_t c0=uint32_t(correction),c1=uint32_t(correction>>32),c2=negative?0xFFFFFFFFU:0;
  asm("add %0,%0,%3\n\tadc %1,%4\n\tadc %2,%5"
      : "+&l"(l0),"+&l"(l1),"+&l"(l2) : "l"(c0),"l"(c1),"l"(c2) : "cc");
  if(!k) return {(U(l1)<<32)|l0,l2,base_error,false,70};
  const uint32_t n=uint16_t(k<0?-k:k);
  const Product scaled=pow_log_two70(n);
  uint32_t s0=uint32_t(scaled.low),s1=uint32_t(scaled.low>>32),s2=uint32_t(scaled.high);
  if(k<0) {
    asm("sub %0,%0,%3\n\tsbc %1,%4\n\tsbc %2,%5"
        : "+&l"(s0),"+&l"(s1),"+&l"(s2) : "l"(l0),"l"(l1),"l"(l2) : "cc");
  } else {
    asm("add %0,%0,%3\n\tadc %1,%4\n\tadc %2,%5"
        : "+&l"(s0),"+&l"(s1),"+&l"(s2) : "l"(l0),"l"(l1),"l"(l2) : "cc");
  }
  return {(U(s1)<<32)|s0,s2,base_error+(n+1)/2,k<0,70};
}
extern "C" PowFastLog mk61_m0_pow_log_select(int ey,U b);
