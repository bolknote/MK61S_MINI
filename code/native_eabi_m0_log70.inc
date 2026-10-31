// A ten-bit segment index keeps |h| < 1/2048. All fast paths certify a
// complete error interval before returning a binary64 rounding.
__attribute__((always_inline)) inline double ln_pack70(U low,uint32_t high,U sign,uint32_t error,double x) {
  unsigned width,shift;int bias;
  if(high) {width=32-clz32(high);shift=width+11;bias=int(width)+1023;}
  else {width=64-clz64(low);shift=width-53;bias=int(width)+959;}
  const uint32_t tail=uint32_t(low)&((1U<<shift)-1),half=1U<<(shift-1);
  if(uint32_t(tail-(half-error))<=2*error) return ln_refine(x);
  const uint32_t lo=uint32_t(low),hi=uint32_t(low>>32);
  const U retained=(U((hi>>shift)|(high<<(32-shift)))<<32)|uint32_t((lo>>shift)|(hi<<(32-shift)));
  const U q=retained+U(tail>half || (tail==half && (retained&1)));
  return real(sign+(U(bias-8)<<52)+q);
}
__attribute__((always_inline)) inline double ln_pack_relative(U q,int e,U sign,unsigned error,double x) {
  if(q<(U(1)<<62)) {q<<=1;--e;error*=2;}
  const unsigned high=unsigned(q>>63),shift=10+high;
  const uint32_t half=1U<<(shift-1),tail=uint32_t(q)&((half<<1)-1);
  if(uint32_t(tail-(half-error))<=2*error) return ln_refine(x);
  const U rounded=(q>>shift)+U(tail>half || (tail==half && ((q>>shift)&1)));
  return real(sign+(U(e+1021+int(high))<<52)+rounded);
}
__attribute__((optimize("Os"),noinline)) static double ln_near_one(double x,U b) {
  const bool negative=b<UINT64_C(0x3FF0000000000000);
  const U s=(b&D::Fraction)|D::Hidden;
  const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
  if(!a) return 0.;
  const unsigned leading=clz64(a);
  const U q=a<<(leading-1),one=U(1)<<62,half=a>>1;
  U factor=one+(negative?half:U(0)-half);unsigned error=4;
  if(a>(U(1)<<27)) {
    const uint32_t t=uint32_t(a>>25);
    const U z=(wide32(t,t)>>12)+(wide32(t,uint32_t(a)&0x1FFFFFFU)>>36)+1;
    factor+=math62_third(z);error=8;
    if(a>(U(1)<<42)) {
      const U quarter=(math62_product(a,z)+2)>>2;
      factor+=negative?quarter:U(0)-quarter;error=32;
    }
  }
  return ln_pack_relative(math62_product(q,factor),2-int(leading),negative?D::Sign:0,error,x);
}
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
#include "native_eabi_m0_ln_near77.inc"
#else
__attribute__((optimize("Os"),noinline)) static double ln_near_interval(double x,U b) {
  const bool negative=b<UINT64_C(0x3FF0000000000000);
  const U s=(b&D::Fraction)|D::Hidden;
  const U a=negative?((D::Hidden<<1)-s)<<9:(s-D::Hidden)<<10;
  unsigned n=unsigned((a+(U(1)<<48))>>49);
  if(!n) return ln_near_one(x,b);
  // The outer negative center has a 65-bit log value. Clamping to the
  // preceding center would need a 49-bit distance and invalidate the
  // short product and quartic remainder bounds below.
  if(negative && n==128) return ln_refine(x);
  const unsigned index=negative?128-n:128+n;
  const U center=U(n)<<49;
  const bool small=a<center,subtract=negative^small;
  const U delta=small?center-a:a-center;
  U low=log_near_table[index-1][1];uint32_t high=0;
  if(delta) {
    const U h=mk61_m0_log_product54(delta,log_near_table[index-1][0]);
    const uint32_t t=uint32_t(h>>26);
    const U z=(wide32(t,t)>>18)+(wide32(t,uint32_t(h)&0x3FFFFFFU)>>43)+1;
    const uint32_t hr=uint32_t((h+(1U<<25))>>26),zr=uint32_t((z+(1U<<12))>>13);
    const uint32_t cube=uint32_t((wide32(hr,zr)+(U(1)<<30))>>31);
    const uint32_t q=uint32_t(wide32(cube,0xAAAAAAABU)>>33);
    const U third=q+U(cube-3*q>=2);
    const U fourth=(wide32(zr,zr)+(U(1)<<43))>>44;
    const U even=((z+1)>>1)+((fourth+2)>>2),odd=h+third;
    const U correction=subtract?odd+even:odd-even;
    if(subtract==negative) {const U before=low;low+=correction;high=low<before;}
    else low-=correction;
  }
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // Strict bounds<4 (near) and<8 (main), certified with the RP exact residual.
  return ln_pack70(low,high,negative?D::Sign:0,3,x);
#else
  return ln_pack70(low,high,negative?D::Sign:0,8,x);
#endif
}
#endif
__attribute__((optimize("Os"))) MK61_SOFT_PCS double mk61_m0_ln(double x) {
  const U b=bits(x);
  if(b<UINT64_C(0x0010000000000000) || b>=D::Infinity) return mk61_m0_cr_ln(x);
  if(b>=UINT64_C(0x3FEF800000000000) && b<=UINT64_C(0x3FF0400000000000))
    return ln_near_interval(x,b);
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
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // Strict bounds<4 (near) and<8 (main), certified with the RP exact residual.
  if(!k) return ln_pack70(low,high,0,7,x);
#else
  if(!k) return ln_pack70(low,high,0,16,x);
#endif
  const uint32_t n=uint16_t(k<0?-k:k);
  const U p0=wide32(uint32_t(log70_two_low),n),p1=wide32(uint32_t(log70_two_low>>32),n)+(p0>>32);
  U result=(p1<<32)|uint32_t(p0);uint32_t upper=uint32_t(p1>>32)+log70_two_high*n;
  const U old=result;
  if(k<0) {result-=low;upper-=high+uint32_t(old<low);}
  else {result+=low;upper+=high+uint32_t(result<old);}
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // Strict bounds<4 (near) and<8 (main), certified with the RP exact residual.
  return ln_pack70(result,upper,k<0?D::Sign:0,7+(n+1)/2,x);
#else
  return ln_pack70(result,upper,k<0?D::Sign:0,16+(n+1)/2,x);
#endif
}
