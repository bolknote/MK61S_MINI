#include <stdint.h>
using U=uint64_t;
__attribute__((always_inline)) inline U wide32(uint32_t a,uint32_t b) {
  const uint32_t al=a&0xFFFFU,ah=a>>16,bl=b&0xFFFFU,bh=b>>16;
  const uint32_t p=al*bl,t=ah*bl+(p>>16),v=al*bh+(t&0xFFFFU);
  return (U(ah*bh+(t>>16)+(v>>16))<<32)|(uint32_t(v<<16)|(p&0xFFFFU));
}
__attribute__((always_inline)) inline U math62_third(U a) {
  const uint32_t hi=uint32_t(a>>32),lo=uint32_t(a);
  const uint32_t qh=uint32_t(wide32(hi,0xAAAAAAABU)>>33);
  const uint32_t ql=uint32_t(wide32(lo,0xAAAAAAABU)>>33);
  const uint32_t rh=hi-3*qh,tail=rh+lo-3*ql,carry=tail>=3;
  const U q=(U(qh)<<32)|uint32_t(ql+rh*0x55555555U+carry);
  return q+U(tail-3*carry>=2);
}
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


extern "C" uint64_t check_ninth(U h,int32_t r5) {
  const AtanTailCorrection q=atan_fast_ninth(h,r5);
  return (uint64_t(uint32_t(q.remainder))<<32)|uint32_t(q.delta);
}
extern "C" uint64_t check_third(U a) {return math62_third(a);}
