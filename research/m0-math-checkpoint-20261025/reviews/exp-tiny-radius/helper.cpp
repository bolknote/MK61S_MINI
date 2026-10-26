#include "native_eabi_m0.hpp"
using U=uint64_t;
extern "C" {
__attribute__((noinline,noipa,section(".m0_exp_tiny"))) static U exp_tiny_rne(U a) {
  const bool negative=bool(a>>63);
  const int e=int((a>>52)&0x7FFU)-1023;
  const unsigned shift=unsigned(-e)-unsigned(negative)-32U;
  const uint32_t hi=(uint32_t(a>>32)&0xFFFFFU)|0x100000U,lo=uint32_t(a);
  const uint32_t tail=hi&((1U<<shift)-1U),half=1U<<(shift-1U),retained=hi>>shift;
  if(negative) {
    bool up=tail>half || (tail==half && lo);
    if(tail==half && lo && lo<16385U) {
      const uint32_t odd=(retained<<1)|1U;
      const uint32_t quadratic=(odd*odd)>>unsigned(e+57);
      up=lo>quadratic;
    }
    return UINT64_C(0x3FF0000000000000)-U(retained+unsigned(up));
  }
  bool up=tail>=half;
  if(tail+1U==half && lo>0U-16385U) {
    const uint32_t odd=(retained<<1)|1U;
    const uint32_t quadratic=(odd*odd)>>unsigned(e+55);
    up=(0U-lo)<=quadratic;
  }
  return UINT64_C(0x3FF0000000000000)+U(retained+unsigned(up));
}
U independent_retention_anchor(U a) { return exp_tiny_rne(a); }
}
