#include "mk61_ai_exact_fp32.hpp"
#include "mk61_ai_exp32.hpp"
#include "native_eabi_m0.hpp"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <random>
std::uint32_t bits(float f) { std::uint32_t x;std::memcpy(&x,&f,4);return x; }
float real(std::uint32_t x) {float f;std::memcpy(&f,&x,4);return f;}
unsigned long pairs=0;
void check(std::uint32_t x,std::uint32_t y) {
  volatile float a=real(x),b=real(y);
  const float want[]={__aeabi_fmul(a,b),__aeabi_fadd(a,b),__aeabi_fadd(a,b),__aeabi_fmul(a,b)};
  const float got[]={mk61ai::exact_fp32::product(a,b),mk61ai::exact_fp32::sum(a,b),
                     mk61ai::exact_fp32::attention_sum(a,b),
                     mk61ai::exact_fp32::attention_product(mk61ai::exact_fp32::ProductOperand(a),b)};
  for(unsigned op=0;op<4;++op) {
    if(std::isnan(want[op])&&std::isnan(got[op]))continue;
    if(bits(want[op])!=bits(got[op])) {
      std::printf("mismatch op=%u x=%08x y=%08x want=%08x got=%08x\n",op,x,y,bits(want[op]),bits(got[op]));
      std::fflush(stdout);assert(false);
    }
  }
  ++pairs;
}
void check_exp32() {
  std::uint32_t table[64];
  for(unsigned i=0;i<64;++i)
    table[i]=std::uint32_t(std::ldexp(std::exp2(double(i)/64),30));
  const auto scale=[&](unsigned i){return table[i];};
  using mk61ai::exp32_negative;
  assert(exp32_negative(0,scale)==0x3f800000U);
  assert(exp32_negative(0xb3000000U,scale)==0x3f800000U);
  assert(!exp32_negative(0xb3000001U,scale)); // Ambiguous at the midpoint below one.
  assert(!exp32_negative(0xc2a00001U,scale));
  assert(!exp32_negative(0x3f800000U,scale));
  std::mt19937 rng(0x619032U);
  unsigned accepted=0;
  for(unsigned i=0;i<100000;++i) {
    const std::uint32_t input=0xb3000000U+rng()%0x0fa00001U;
    const auto result=exp32_negative(input,scale);
    if(!result) continue;
    assert(result==bits(float(std::exp(double(real(input))))));
    ++accepted;
  }
  assert(accepted>65000 && accepted<99000);
  std::printf("FP32 negative exponential: %u decided intervals and boundary fallbacks PASS\n",accepted);
}
int main() {
  const std::uint32_t edges[]={0,0x80000000,1,0x7fffff,0x800000,0x800001,0x3f000000,0x3f7fffff,0x3f800000,0x3f800001,0x40000000,0x7f7fffff,0x7f800000,0xff800000,0x7fc01234,0x7f800001};
  for(auto x:edges)for(auto y:edges)check(x,y);
  std::mt19937 rng(610714);
  for(unsigned i=0;i<5000000;++i)check(rng(),rng());
  for(unsigned e=1;e<255;++e)for(unsigned m=0;m<64;++m)for(unsigned n=0;n<64;++n)
    check((e<<23)|0x7fffc0|m,((255-e)<<23)|n);
  for(unsigned e=1;e<255;++e)for(unsigned d=0;d<33;++d)for(unsigned i=0;i<64;++i) {
    const unsigned x=(e<<23)|(rng()&0x7fffff),ee=e>d?e-d:1;
    check(x,(ee<<23)|(rng()&0x7fffff));
    check(x,0x80000000U|(ee<<23)|(rng()&0x7fffff));
    check(x,0x80000000U|x);check(x,0x80000000U|(x+1));check(x,0x80000000U|(x-1));
  }
  std::printf("Exact FP32 multiply/add vs production M0 EABI: %lu operand pairs, signed zero/subnormal/nonfinite/boundaries/ties/cancellation PASS\n",pairs);
  check_exp32();
}
