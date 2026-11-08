#include "mk61_ai_half_product.hpp"
#include <cassert>
#include <cstdio>
#include <random>

namespace {
float from_bits(std::uint32_t bits) {
  float value;std::memcpy(&value,&bits,4);return value;
}
std::uint32_t bits(float value) {
  std::uint32_t result;std::memcpy(&result,&value,4);return result;
}
float reference_half(std::uint16_t h) {
  const unsigned e=(h>>10)&31,m=h&1023;
  const float value=e==31?(m?NAN:INFINITY):
      e?from_bits(((e+112)<<23)|(m<<13)):float(m)*0x1p-24f;
  return h&0x8000?-value:value;
}
void check(std::int32_t sum,std::uint16_t h) {
  volatile float input=float(sum),scale=reference_half(h);
  const float expected=input*scale,actual=mk61ai::half_scaled_q4_dot(sum,h);
  assert((std::isnan(expected) && std::isnan(actual)) || bits(expected)==bits(actual));
}
}
int main() {
  const std::int32_t edges[]={-32768,-32767,-16385,-8193,-2049,-513,-17,-1,
      0,1,17,513,2049,8193,16385,32767,32768};
  unsigned checked=0;
  for(unsigned h=0;h<65536;++h) for(auto sum:edges) {
    check(sum,std::uint16_t(h));++checked;
  }
  std::mt19937 rng(6132);
  for(unsigned i=0;i<2000000;++i) {
    check(std::int32_t(rng()%65537)-32768,std::uint16_t(rng()));++checked;
  }
  std::printf("FP16 dot scaling: %u exact results; signed zero, subnormal scales, rounding, extremes and nonfinite fallback PASS\n",checked);
}
