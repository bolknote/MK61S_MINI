#ifndef MK61_AI_QUANTIZE_HPP
#define MK61_AI_QUANTIZE_HPP
#include "mk61_ai_math.hpp"
#include <algorithm>
#include <cstdint>
#include <cstring>

namespace mk61ai {
namespace quantize_detail {
inline std::uint32_t bits(float value) {
  std::uint32_t encoded;
  std::memcpy(&encoded, &value, sizeof(encoded));
  return encoded;
}

inline float value(std::uint32_t encoded) {
  float result;
  std::memcpy(&result, &encoded, sizeof(result));
  return result;
}

constexpr std::int8_t use_float = -128;

// Round to the same int8 as binary32 division followed by round-away-from-zero.
// The input scale is positive and comes from the maximum magnitude of the
// current group divided by 127. Keep the original path for unusual operands.
template <class Divide>
inline std::int8_t round_normal(std::uint32_t input, unsigned scale_exponent,
                                std::uint32_t divisor, Divide divide) {
  const std::uint32_t magnitude = input & 0x7fffffffU;
  const unsigned exponent = magnitude >> 23;
  if (!magnitude) return 0;
  if (!exponent || exponent == 255) return use_float;
  if (exponent + 1U < scale_exponent) return 0;
  const unsigned shift = exponent + 1U - scale_exponent;
  if (shift > 8) return use_float;

  // q=floor(2*|x|/scale). Even q means the quotient is below a half-integer.
  // Binary32 division can round up to that half-integer from half a ULP below.
  const std::uint32_t numerator = ((magnitude & 0x7fffffU) | 0x800000U) << shift;
  const unsigned q = divide(numerator, divisor);
  if (q >= 255) return use_float;
  unsigned rounded = (q + 1U) >> 1;
  if (!(q & 1U) && q >= 2) {
    // At the next half-integer the exponent is shift-1 or shift-2.
    // Scale the half-ULP by two to match the doubled quotient. The
    // half-integer is the even binary32 value at the rounding boundary.
    // Below 0.5 the integer distance is always greater than half a ULP.
    const unsigned ulp_shift = ((q + 1U) >> shift) ? 24U - shift : 25U - shift;
    const unsigned distance = divisor * (q + 1U) - numerator;
    rounded += distance <= (divisor >> ulp_shift);
  }
  return std::int8_t(input >> 31 ? -int(rounded) : int(rounded));
}

template <class Divide>
inline bool group(const float *input, float &scale, std::int8_t *output,
                  std::int32_t &sum, Divide divide) {
  std::uint32_t maximum = 0;
  for (unsigned j = 0; j < 32; ++j)
    maximum = std::max(maximum, bits(input[j]) & 0x7fffffffU);
  if (maximum >= 0x7f800000U) return false;
  scale = math::div(value(maximum), 127.0f);
  const auto encoded = bits(scale);
  const unsigned scale_exponent = encoded >> 23;
  const auto divisor = (encoded & 0x7fffffU) | 0x800000U;
  sum = 0;
  if (!encoded) {
    std::memset(output, 0, 32);
    return true;
  }
  for (unsigned j = 0; j < 32; ++j) {
    auto quantized = scale_exponent ? round_normal(bits(input[j]), scale_exponent,
                                                  divisor, divide) : use_float;
    if (quantized == use_float) {
      const float rounded = math::round(math::div(input[j], scale));
      if (!(rounded >= -128.0f && rounded < 128.0f)) return false;
      quantized = std::int8_t(rounded);
    }
    output[j] = quantized;
    sum += quantized;
  }
  return true;
}
}

#if MK61_AI_FAST_MATH && defined(PICO_ON_DEVICE)
bool quantize_int8_group(const float *input, float &scale, std::int8_t *output,
                         std::int32_t &sum);
#else
inline bool quantize_int8_group(const float *input, float &scale, std::int8_t *output,
                                std::int32_t &sum) {
  return quantize_detail::group(input, scale, output, sum,
                               [](std::uint32_t n, std::uint32_t d) { return n / d; });
}
#endif
}
#endif
