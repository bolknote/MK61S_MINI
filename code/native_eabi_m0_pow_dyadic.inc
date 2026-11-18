// Evaluate (2^s)^y without approximating the product s*y.
#pragma once
#include "native_eabi_m0_pow_large_power.inc"

namespace m0_pow_dyadic {
namespace {
using U = uint64_t;
using Power = m0_pow_power_bounds::PowerBounds<10>;
constexpr U Infinity = UINT64_C(0x7ff0000000000000);
constexpr U One = UINT64_C(0x3ff0000000000000);
constexpr U Hidden = UINT64_C(1) << 52;
constexpr U Undecided = UINT64_MAX;
#include "native_eabi_m0_pow_dyadic_table.inc"
constexpr unsigned MaximumShift = sizeof(Roots)/sizeof(Roots[0]);
static_assert(MaximumShift == 116, "Root table covers the active exponent range");
static_assert(sizeof(InverseRoots) == sizeof(Roots), "Both signs need all roots");

__attribute__((noinline,cold,section(".m0_pow_refine_extension")))
static U round(const Power::Number& value, int exponent) {
  if(exponent < -1022)
    return m0_pow_large::round_subnormal(value);

  U head = 0;
  for(unsigned i=10; i-->6;)
    head = (head<<16) | value.word[i];
  unsigned sticky = unsigned(head & 1023U);
  for(unsigned i=0; i<6; ++i)
    sticky |= value.word[i];
  const U retained = head>>11;
  const U carry = ((head>>10)&1) && (sticky || (retained&1));
  return (U(exponent+1022)<<52) + retained + carry;
}

__attribute__((noinline,cold,section(".m0_pow_refine_extension")))
static U evaluate(U xb, U yb) {
  const U magnitude = yb & UINT64_C(0x7fffffffffffffff);
  if(!xb || xb >= Infinity || magnitude >= Infinity)
    return Undecided;
  const unsigned field = unsigned(xb>>52);
  const U coefficient = (xb & (Hidden-1)) | (field ? Hidden : 0);
  if(coefficient & (coefficient-1))
    return Undecided;
  // For every positive finite base and |y| < 2^-64, even the midpoint
  // immediately below 1 is out of reach.
  if(xb == One || magnitude < UINT64_C(0x3bf0000000000000))
    return One;

  int s = int(field)-1023;
  if(!field) {
    s = -1074;
    for(U bits=coefficient; bits>>=1;)
      ++s;
  }
  const bool negative = (s<0) != bool(yb>>63);
  const unsigned abs_s = unsigned(s<0 ? -s : s);
  const int shift = 1075-int(magnitude>>52);
  if(shift <= 0)
    return negative ? 0 : Infinity;
  const U product = ((magnitude & (Hidden-1)) | Hidden)*abs_s;
  const U whole = shift<64 ? product>>shift : 0;
  if(whole > (negative ? 1074U : 1023U))
    return negative ? 0 : Infinity;
  const U tail = shift<64 ? product & ((U(1)<<shift)-1) : product;
  const int exponent = negative ? -int(whole)-int(tail!=0) : int(whole);
  if(!tail)
    return exponent < -1022 ? U(1)<<(exponent+1074) : U(exponent+1023)<<52;

  // Use the fractional magnitude and directed inverse roots for a
  // negative t. The numerator has at most 64 bits for either sign.
  const auto* roots = negative ? InverseRoots : Roots;
  Power::Number value, factor;
  Power::from_dyadic(value, 1, negative ? -int(whole) : int(whole));
  factor.scale = negative ? -1 : 0;
  factor.exact = false;
  U fraction = tail;
  unsigned terms = 0;
  for(unsigned i=unsigned(shift); fraction; --i, fraction>>=1) {
    if(fraction & 1) {
      __builtin_memcpy(factor.word, roots[i-1], sizeof(factor.word));
      Power::multiply(value, factor, 0);
      ++terms;
    }
  }

  // Each factor contributes <6 Q159 units after propagation. A
  // nonzero f on this grid keeps the upper bound strictly below 2.
  if(value.scale != exponent)
    return Undecided;
  const U lower = round(value, exponent);
  if(Power::add_units(value, 6*terms))
    return Undecided;
  return lower == round(value, exponent) ? lower : Undecided;
}
}
}
