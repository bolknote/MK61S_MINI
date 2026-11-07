#ifndef MK61_AI_SWAR_HPP
#define MK61_AI_SWAR_HPP
#include <cstdint>
#include <cstring>
#if defined(__GNUC__) || defined(__clang__)
#define MK61_SWAR_INLINE inline __attribute__((always_inline))
#else
#define MK61_SWAR_INLINE inline
#endif
namespace mk61ai::swar {
// XP is a polynomial modulo 2^32, not two independent unsigned halfwords:
// negative low lanes must borrow into the high half. All MUL/ADD/SHL below
// are unsigned so the discarded high product cannot cause signed C++ UB.
MK61_SWAR_INLINE std::uint32_t pair(std::int8_t a, std::int8_t b) {
  return std::uint32_t(std::int32_t(b)) +
         (std::uint32_t(std::int32_t(a)) << 16);
}
MK61_SWAR_INLINE int prepare32(const std::int8_t *input, std::uint32_t *packed) {
  int sum = 0;
  for (unsigned word = 0; word < 4; ++word)
    for (unsigned lane = 0; lane < 4; ++lane) {
      const auto a = input[8 * word + lane], b = input[8 * word + lane + 4];
      packed[4 * word + lane] = pair(a, b);sum += int(a) + int(b);
    }
  return sum;
}
MK61_SWAR_INLINE std::int32_t rounded_high(std::uint32_t value) {
  value += 0x8000U;
  std::int32_t signed_value;std::memcpy(&signed_value, &value, 4);
  static_assert((-1 >> 1) == -1, "SWAR requires arithmetic signed right shift");
  return signed_value >> 16;
}
MK61_SWAR_INLINE std::int32_t dot16(std::uint32_t a, std::uint32_t b,
                                  const std::uint32_t *x) {
  constexpr std::uint32_t mask = 0x000f000fU;
  std::uint32_t sum = (a & mask) * x[0];
  sum += ((a >> 4) & mask) * x[1];
  sum += ((a >> 8) & mask) * x[2];
  sum += ((a >> 12) & mask) * x[3];
  sum += (b & mask) * x[4];
  sum += ((b >> 4) & mask) * x[5];
  sum += ((b >> 8) & mask) * x[6];
  sum += ((b >> 12) & mask) * x[7];
  // Eight products: low interference is in [-15360,15240], strictly
  // inside +/-32768. Desired high sum is in [-30720,30480], fitting int16.
  return rounded_high(sum);
}
MK61_SWAR_INLINE std::int32_t dot32(const std::uint8_t *weights,
                                  const std::uint32_t *packed, int input_sum) {
  std::uint32_t a, b, c, d;
  std::memcpy(&a, weights, 4);std::memcpy(&b, weights + 4, 4);
  std::memcpy(&c, weights + 8, 4);std::memcpy(&d, weights + 12, 4);
  return dot16(a, b, packed) + dot16(c, d, packed + 8) - 8 * input_sum;
}
// Production tiles/rows are 4-byte aligned. Preserve that information for
// Cortex-M0+, where an arbitrary byte pointer otherwise needs four LDRBs.
MK61_SWAR_INLINE std::int32_t dot32_aligned(const std::uint8_t *weights,
                                          const std::uint32_t *packed, int input_sum) {
#if defined(__GNUC__) || defined(__clang__)
  weights = static_cast<const std::uint8_t *>(__builtin_assume_aligned(weights, 4));
#endif
  return dot32(weights, packed, input_sum);
}
}
#endif
