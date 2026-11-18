// Direct subnormal rounding of the only nonsaturating base in the large band.
#pragma once
#include "native_eabi_m0_pow_large_constants.inc"
#include "native_eabi_m0_pow_power_bounds.inc"

namespace m0_pow_large {

using LargePower = m0_pow_power_bounds::PowerBounds<10>;

static uint64_t round_subnormal(const LargePower::Number& value) {
  // The scale is a two's-complement exponent. A value below 2^-1075
  // rounds to zero. The guard bit is included in the extracted integer.
  if(value.scale.high!=UINT64_MAX) return UINT64_MAX;
  if(value.scale.low<uint64_t(-1075)) return 0;
  if(value.scale.low>uint64_t(-1023)) return UINT64_MAX;
  const unsigned guard_shift=63-unsigned(value.scale.low+1075);
  uint64_t high=0;
  for(unsigned i=10;i-->6;) high=(high<<16)|value.word[i];
  const uint64_t digits=high>>guard_shift;
  bool sticky=(high&((UINT64_C(1)<<guard_shift)-1))!=0;
  for(unsigned i=0;i<6;++i) sticky|=value.word[i]!=0;
  return (digits>>1)+unsigned((digits&1) && (sticky || (digits&2)));
}

static uint64_t subnormal(uint64_t y) {
  // Both cutoffs are in the 2^62 binade, with spacing 1024.
  if(y<SubnormalBand || y>=Underflow) return UINT64_MAX;
  constexpr uint64_t hidden=UINT64_C(1)<<52;
  const uint64_t exponent=((y&(hidden-1))|hidden)<<10;
  LargePower::Number base,value;
  LargePower::from_dyadic(base,(hidden<<1)-1,-53);
  LargePower::power(value,base,exponent);
  const uint64_t lower=round_subnormal(value);
  if(value.exact) return lower;
  LargePower::raise_bound(value,mk61_u128(exponent));
  return lower==round_subnormal(value)?lower:UINT64_MAX;
}

}
