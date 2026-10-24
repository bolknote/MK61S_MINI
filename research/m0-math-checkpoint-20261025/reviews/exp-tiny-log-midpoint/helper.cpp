#include "native_eabi_m0.hpp"
using U=uint64_t;
__attribute__((always_inline)) inline U wide32(uint32_t a,uint32_t b) {
  const uint32_t al=a&0xFFFFU,ah=a>>16,bl=b&0xFFFFU,bh=b>>16;
  const uint32_t p=al*bl,t=ah*bl+(p>>16),v=al*bh+(t&0xFFFFU);
  return (U(ah*bh+(t>>16)+(v>>16))<<32)|(uint32_t(v<<16)|(p&0xFFFFU));
}
extern "C" {
__attribute__((always_inline)) inline uint32_t exp_tiny_log_floor(uint32_t odd,int e,bool negative) {
  const unsigned q=unsigned(e+55)+2U*unsigned(negative);
  // Here odd^3/(3*2^(52+negative))<1, so its certified floor is0.
  if(odd<65536U) return (odd*odd)>>q;
  const U square=wide32(odd,odd);
  const uint32_t low=uint32_t(square),high=uint32_t(square>>32);
  uint32_t result=(low>>q)|(high<<(32U-q));
  const uint32_t tail=low&((1U<<q)-1U);
  const U cube_low=wide32(low,odd);
  const U cube_high=wide32(high,odd)+(cube_low>>32);
  const uint32_t scaled20=uint32_t(cube_high>>20);
  const uint32_t scaled=scaled20>>unsigned(negative);
  const uint32_t cubic=(scaled*43691U)>>17; // exact /3, scaled<65536
  if(negative) result+=unsigned(tail+cubic>=(1U<<q));
  else result-=unsigned(tail<=cubic);
  return result;
}
// Called only for 2^-54 < |x| < 2^-32, hence s=-e-negative is32..54.
// The exact logarithmic correction is strictly between0 and1048577
// input ulps. Only the affected side of a linear midpoint needs products.
__attribute__((noinline,noipa,section(".m0_exp_tiny"))) static U exp_tiny_rne(U a) {
  const bool negative=bool(a>>63);
  const int e=int((a>>52)&0x7FFU)-1023;
  const unsigned s=unsigned(-e)-unsigned(negative);
  const uint32_t hi=(uint32_t(a>>32)&0xFFFFFU)|0x100000U,lo=uint32_t(a);
  uint32_t retained,distance=0;
  bool up,near=false;
  if(s==32) {
    retained=hi;
    const uint32_t half=0x80000000U;
    up=negative?lo>half:lo>=half;
    distance=negative?lo-half:half-lo;
    near=distance && distance<=1048576U;
  } else {
    const unsigned shift=s-32U;
    const uint32_t tail=hi&((1U<<shift)-1U),half=1U<<(shift-1U);
    retained=hi>>shift;
    if(negative) {
      up=tail>half || (tail==half && lo);
      distance=lo;
      near=tail==half && lo && lo<=1048576U;
    } else {
      up=tail>=half;
      distance=0U-lo;
      near=tail+1U==half && lo>0U-1048577U;
    }
  }
  if(near) {
    const uint32_t threshold=exp_tiny_log_floor((retained<<1)|1U,e,negative);
    up=negative?distance>threshold:distance<=threshold;
  }
  const uint32_t displacement=retained+unsigned(up);
  return negative?UINT64_C(0x3FF0000000000000)-displacement:
                  UINT64_C(0x3FF0000000000000)+displacement;
}
U independent_retention_anchor(U a){return exp_tiny_rne(a);}
}
