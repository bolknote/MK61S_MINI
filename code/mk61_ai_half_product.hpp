#ifndef MK61_AI_HALF_PRODUCT_HPP
#define MK61_AI_HALF_PRODUCT_HPP
#include <cmath>
#include <cstdint>
#include <cstring>

namespace mk61ai {
namespace half_product_detail {
// AI-local int32 -> binary32, round to nearest, ties to even. The general
// firmware EABI conversion uses a64-bit packer. Share one SRAM body on the
// MCU so the LUT8 and direct kernels keep their existing memory budget.
// Unsigned magnitude also handles INT32_MIN without signed overflow.
#if defined(PICO_ON_DEVICE)
inline __attribute__((section(".time_critical.mk61ai_from_integer"),noinline))
#else
inline __attribute__((always_inline))
#endif
float from_integer(std::int32_t value) {
  std::uint32_t n=std::uint32_t(value),encoded=n&0x80000000U;
  if(value<0)n=0U-n;
  if(!n)return 0.0f;
  unsigned exponent=158;
  if(!(n&0xffff0000U)){n<<=16;exponent-=16;}
  if(!(n&0xff000000U)){n<<=8;exponent-=8;}
  if(!(n&0xf0000000U)){n<<=4;exponent-=4;}
  if(!(n&0xc0000000U)){n<<=2;exponent-=2;}
  if(!(n&0x80000000U)){n<<=1;--exponent;}
  std::uint32_t significand=n>>8;
  const auto remainder=n&255U;
  significand+=remainder>128U || (remainder==128U && (significand&1U));
  // significand includes the hidden bit; addition also carries rounding
  // overflow into the exponent, including INT32_MAX -> 2^31.
  encoded|=((exponent-1U)<<23)+significand;
  float result;std::memcpy(&result,&encoded,sizeof(result));return result;
}
}
// For a32-element INT4 x INT8 dot, |sum|<=32768. Multiplying its
// integer value by the FP16 significand fits int32. One rounded int-to-float
// conversion followed by an exact exponent adjustment matches float(sum)*h.
// Finite nonzero products remain normal FP32, including subnormal FP16 h.
inline float half_scaled_q4_dot(std::int32_t sum,std::uint16_t h) {
  const unsigned exponent=(h>>10)&31U,mantissa=h&1023U;
  const std::uint32_t sign=std::uint32_t(h&0x8000U)<<16;
  if(exponent==31) {
    float scale=mantissa?NAN:INFINITY;
    if(sign) scale=-scale;
    return float(sum)*scale;
  }
  std::uint32_t encoded;
  if(!sum || (!exponent && !mantissa)) {
    encoded=sign^(std::uint32_t(sum<0)<<31);
  } else {
    const std::int32_t product=sum*std::int32_t(mantissa+(exponent?1024U:0U));
    const float rounded=half_product_detail::from_integer(product);
    std::memcpy(&encoded,&rounded,sizeof(encoded));
    const int power=exponent?int(exponent)-25:-24;
    encoded+=std::uint32_t(power)*0x800000U;
    encoded^=sign;
  }
  float result;
  std::memcpy(&result,&encoded,sizeof(result));
  return result;
}
}
#endif
