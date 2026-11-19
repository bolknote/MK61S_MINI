#ifndef MK61_AI_EXP32_HPP
#define MK61_AI_EXP32_HPP
#include <cstdint>

namespace mk61ai {
// Return binary32 bits on a decided rounding interval, or zero to defer to
// the general binary64 exponential. The scale callback supplies the upper
// word of Q62 2^(index/64), giving its Q30 approximation.
template<class Scale>
inline __attribute__((always_inline)) std::uint32_t exp32_negative(std::uint32_t input,Scale scale) {
  const auto magnitude=input&0x7fffffffU;
  if(!magnitude) return 0x3f800000U;
  if(!(input>>31) || magnitude>0x42a00000U) return 0; // [-80,0] keeps the output normal.
  if(magnitude<=0x33000000U) return 0x3f800000U;
  const int exponent=int(magnitude>>23)-127;
  const std::uint32_t significand=(magnitude&0x7fffffU)|0x800000U;

  // 47274 = floor(512 * 64/ln(2)). Using the top 16 significand bits
  // still bounds the reduced argument by 0.0095 on this interval.
  unsigned steps=0;
  if(exponent>=-7) {
    const unsigned shift=24-exponent;
    steps=((significand>>8)*47274U+(1U<<(shift-1)))>>shift;
  }
  const int shift=exponent+7;
  const std::uint32_t argument=shift<0 ? significand>>(-shift) : significand<<shift;
  // Round the Q47 step to Q30 after multiplication. Only the low word
  // of the reduced argument is needed.
  const std::uint32_t center=steps*11629079U+((steps*126884U+65536U)>>17);
  const std::uint32_t residual=center-argument;
  const bool negative=residual>>31;
  const std::uint32_t r=negative ? 0U-residual : residual;
  const std::uint32_t q22=(r+128U)>>8;
  const std::uint32_t quadratic=(q22*q22+(1U<<14))>>15;
  const std::uint32_t third=(q22*21845U+32768U)>>16;
  const std::uint32_t cubic=(quadratic*third+(1U<<21))>>22;
  const std::uint32_t delta=negative ? r+cubic-quadratic : r+cubic+quadratic;

  const std::uint32_t base=scale((0U-steps)&63U);
  const auto a=base>>16,b=base&65535U,c=delta>>16,d=delta&65535U;
  const auto cross=a*d+b*c+((b*d)>>16);
  const auto product=(a*c<<2)+((cross+8192U)>>14);
  std::uint32_t result=negative ? base-product : base+product;
  if(result>>31) return 0;
  unsigned power=(steps+63U)>>6;
  // Reduction error <1.54 Q30, Taylor and fixed-point evaluation <2.8,
  // then a factor below two and <1.6 units for scaling and rounding.
  unsigned error=12;
  if(result<(1U<<30)) {result<<=1;++power;error*=2;}
  if(((result&127U)-(64U-error))<=2*error) return 0;
  return ((126U-power)<<23)+((result+64U)>>7);
}
}
#endif
