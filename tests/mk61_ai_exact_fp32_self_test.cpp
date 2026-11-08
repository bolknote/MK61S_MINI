#include "mk61_ai_exact_fp32.hpp"
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
  const float want[]={__aeabi_fmul(a,b),__aeabi_fadd(a,b)};
  const float got[]={mk61ai::exact_fp32::product(a,b),mk61ai::exact_fp32::sum(a,b)};
  for(unsigned op=0;op<2;++op) {
    if(std::isnan(want[op])&&std::isnan(got[op]))continue;
    if(bits(want[op])!=bits(got[op])) {
      std::printf("mismatch op=%u x=%08x y=%08x want=%08x got=%08x\n",op,x,y,bits(want[op]),bits(got[op]));
      std::fflush(stdout);assert(false);
    }
  }
  ++pairs;
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
}
