#ifndef MK61_ZX0_ENCODE_KERNELS_HPP
#define MK61_ZX0_ENCODE_KERNELS_HPP

// Private bounded encoder kernels. Word accesses are enabled only on the
// qualified little-endian DSP/unaligned ARM target, or by host validation.
#include "rust_types.h"
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__ && \
    ((defined(__ARM_FEATURE_SIMD32) && defined(__ARM_FEATURE_UNALIGNED)) || \
     defined(MK61_ZX0_WORD_TEST))
#define MK61_ZX0_WORD_KERNELS 1
#else
#define MK61_ZX0_WORD_KERNELS 0
#endif

#if MK61_ZX0_WORD_KERNELS
#if defined(__ARM_FEATURE_SIMD32)
#include <arm_acle.h>
#endif
namespace zx0_encode_kernels {
// Buffer bytes can have any alignment and may alias the 16-bit LCP array.
typedef u32 Word __attribute__((aligned(1), may_alias));
static_assert(sizeof(Word) == 4 && alignof(Word) == 1,
              "bounded four-byte accesses required");
static constexpr u16 MAX_OFFSET = 256;
static constexpr u32 MAX_INPUT_SIZE = 8192;
inline u32 load(const void* p) { return *(const Word*)p; }
inline void store(void* p, u32 value) { *(Word*)p = value; }

inline u16 match_length(const u8* input, u16 size, u16 position, u16 offset) {
  const u8* current = input + position;
  const u8* source = current - offset;
  const u8* const begin = current;
  u32 remaining = size - position;
  // Most candidates differ immediately; avoid setting up a word scan then.
  if(remaining == 0 || *current != *source) return 0;
  ++current; ++source; --remaining;
  while(remaining >= 4) {
    const u32 difference = load(current) ^ load(source);
    if(difference != 0) {
      // Both supported hosts and Cortex-M4 are little endian.
      return (u16)(current - begin + __builtin_ctz(difference) / 8);
    }
    current += 4; source += 4; remaining -= 4;
  }
  while(remaining != 0 && *current == *source) {
    ++current; ++source; --remaining;
  }
  return (u16)(current - begin);
}

inline u32 equal_byte_mask(u32 difference) {
#if defined(__ARM_FEATURE_SIMD32)
  (void)__usub8(difference, 0x01010101U);
  return __sel(0U, 0xFFFFFFFFU);
#else
  const u32 nonzero = difference | ((difference & 0x7F7F7F7FU) + 0x7F7F7F7FU);
  return ((~nonzero & 0x80808080U) >> 7) * 255U;
#endif
}
inline u32 widen_mask_pair(u32 mask) {
  const u32 a = mask & 0xFFU, b = mask & 0xFF00U;
  return a | (a << 8) | (b << 8) | (b << 16);
}
inline u32 increment_pair(u32 values) {
#if defined(__ARM_FEATURE_SIMD32)
  return __uadd16(values, 0x00010001U);
#else
  // Encoder input is <=8192 bytes, so neither halfword can carry out.
  return values + 0x00010001U;
#endif
}
inline u32 max_pair(u32 a, u32 b) {
#if defined(__ARM_FEATURE_SIMD32)
  (void)__usub16(a, b);
  return __sel(a, b);
#else
  const u32 low = (u16)a > (u16)b ? (u16)a : (u16)b;
  const u32 high = (a >> 16) > (b >> 16) ? a >> 16 : b >> 16;
  return low | (high << 16);
#endif
}

inline u16 lcp_range(const u8* input, u16 position,
                     u16* lcp, u16 first, u16 last) {
  // The caller caps last at position, so every four-byte input load is
  // inside the original span. LCP counters stay below MAX_INPUT_SIZE.
  const u32 repeated = (u32)input[position] * 0x01010101U;
  u32 largest = 0;
  u16 offset = first;
  while((u32)offset + 3 <= last) {
    const u32 candidates = __builtin_bswap32(load(input + position - offset - 3));
    const u32 mask = equal_byte_mask(candidates ^ repeated);
    const u32 a = increment_pair(load(lcp + offset)) & widen_mask_pair(mask);
    const u32 b = increment_pair(load(lcp + offset + 2)) & widen_mask_pair(mask >> 16);
    store(lcp + offset, a); store(lcp + offset + 2, b);
    largest = max_pair(largest, max_pair(a, b));
    offset += 4;
  }
  u16 result = (u16)largest > (largest >> 16) ? (u16)largest : (u16)(largest >> 16);
  while(offset <= last) {
    lcp[offset] = input[position] == input[position - offset] ? (u16)(lcp[offset] + 1) : 0;
    if(lcp[offset] > result) result = lcp[offset];
    ++offset;
  }
  return result;
}

inline void lcp_blocks(const u8* input, u16 position, u16* lcp,
                      u16& near_length, u16& far_length) {
  const u16 maximum = position < 256 ? position : 256;
  near_length = maximum ? lcp_range(input, position, lcp, 1, maximum < 128 ? maximum : 128) : 0;
  far_length = maximum > 128 ? lcp_range(input, position, lcp, 129, maximum) : 0;
  for(u16 offset = maximum + 1; offset <= 256; ++offset) lcp[offset] = 0;
}
} // namespace zx0_encode_kernels
#endif
#endif
