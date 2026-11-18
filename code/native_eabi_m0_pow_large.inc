// For finite |y| >= 2^62 all representable exponents are even integers.
#pragma once
#include "native_eabi_m0_pow_large_constants.inc"

extern "C" uint64_t mk61_m0_pow_large_subnormal(uint64_t);

namespace m0_pow_large {

static inline bool subnormal_input(uint64_t x,uint64_t y) {
  return x==ExceptionalBase && y>=SubnormalBand && y<Underflow;
}

static uint64_t saturate(uint64_t x,uint64_t y) {
  constexpr uint64_t mask=UINT64_C(0x7fffffffffffffff);
  constexpr uint64_t infinity=UINT64_C(0x7ff0000000000000);
  constexpr uint64_t one=UINT64_C(0x3ff0000000000000);
  const uint64_t xm=x&mask,ym=y&mask;
  if(xm>=infinity || ym>=infinity) return UINT64_MAX;
  if(xm==one) return one;
  const bool decreasing=(xm<one)^bool(y>>63);
  if(xm!=ExceptionalBase) return decreasing?0:infinity;
  if(!decreasing) return ym>=Overflow?infinity:UINT64_MAX;
  return ym>=Underflow?0:UINT64_MAX;
}

}
