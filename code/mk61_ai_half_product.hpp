#ifndef MK61_AI_HALF_PRODUCT_HPP
#define MK61_AI_HALF_PRODUCT_HPP
#include <cmath>
#include <cstdint>
#include <cstring>

namespace mk61ai {
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
    const float rounded=float(product);
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
