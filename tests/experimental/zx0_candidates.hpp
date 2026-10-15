#ifndef MK61_ZX0_CANDIDATES_HPP
#define MK61_ZX0_CANDIDATES_HPP

// Experimental kernels for the existing ZX0 v2 format. Normal memory only;
// each word access stays inside the original byte span. No firmware hooks.
#include "rust_types.h"
#if defined(__ARM_FEATURE_SIMD32)
#include <arm_acle.h>
#endif

namespace zx0_candidates {
typedef u32 Word __attribute__((aligned(1), may_alias));
typedef u16 Half __attribute__((aligned(1), may_alias));
static_assert(sizeof(Word)==4&&alignof(Word)==1,"bounded four-byte access required");
static_assert(__BYTE_ORDER__==__ORDER_LITTLE_ENDIAN__,"prototype requires little endian");
inline u32 load(const void* p) { return *(const Word*)p; }
inline void store(void* p, u32 v) { *(Word*)p = v; }

inline bool copy_scalar(u8*& output, const u8* begin, const u8* end,
                        u32 offset, u32 length) {
  if(offset > (u32)(output - begin) || length > (u32)(end - output)) return false;
  const u8* source = output - offset;
  while(length-- != 0) *output++ = *source++;
  return true;
}

inline bool copy_word(u8*& output, const u8* begin, const u8* end,
                      u32 offset, u32 length) {
  if(offset > (u32)(output - begin) || length > (u32)(end - output)) return false;
  const u8* source = output - offset;
  if(length >= 4 && offset != 0 && offset < 4) {
    u32 pattern;
    if(offset == 1) pattern = (u32)source[0] * 0x01010101U;
    else if(offset == 2) {
      pattern = *(const Half*)source;
      pattern |= pattern << 16;
    } else {
      pattern = (u32)source[0] | ((u32)source[1] << 8) |
                ((u32)source[2] << 16) | ((u32)source[0] << 24);
    }
    do {
      store(output, pattern);
      output += 4; length -= 4;
      if(offset == 3) pattern = (pattern >> 8) | ((pattern & 0xFF00U) << 16);
    } while(length >= 4);
    source = output - offset;
  } else {
    // A store must precede the next load: offsets 4..15 can reuse the word
    // just produced. Preloading a 16-byte block would violate LZ semantics.
    while(length >= 4) {
      const u32 value = load(source);
      store(output, value);
      output += 4; source += 4; length -= 4;
    }
  }
  while(length-- != 0) *output++ = *source++;
  return true;
}

inline u16 match_scalar(const u8* input, u16 size, u16 position, u16 offset) {
  const u8* current = input + position;
  const u8* source = current - offset;
  const u8* const begin = current;
  const u8* const end = input + size;
  while(current < end && *current == *source) { ++current; ++source; }
  return (u16)(current - begin);
}

inline u16 match_word(const u8* input, u16 size, u16 position, u16 offset) {
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

inline void lcp_scalar(const u8* input, u16 position, u16* lcp,
                       u16& near_length, u16& far_length) {
  const u16 maximum = position < 256 ? position : 256;
  near_length = far_length = 0;
  for(u16 offset = 1; offset <= 256; ++offset) {
    if(offset <= maximum && input[position] == input[position - offset]) ++lcp[offset];
    else lcp[offset] = 0;
    if(offset <= 128) {
      if(lcp[offset] > near_length) near_length = lcp[offset];
    } else if(lcp[offset] > far_length) far_length = lcp[offset];
  }
}

template<bool DSP> inline u32 equal_byte_mask(u32 difference) {
#if defined(__ARM_FEATURE_SIMD32)
  if constexpr(DSP) {
    (void)__usub8(difference, 0x01010101U);
    return __sel(0U, 0xFFFFFFFFU);
  }
#endif
  const u32 nonzero = difference | ((difference & 0x7F7F7F7FU) + 0x7F7F7F7FU);
  return ((~nonzero & 0x80808080U) >> 7) * 255U;
}
inline u32 widen_mask_pair(u32 mask) {
  const u32 a = mask & 0xFFU, b = mask & 0xFF00U;
  return a | (a << 8) | (b << 8) | (b << 16);
}
template<bool DSP> inline u32 increment_pair(u32 values) {
#if defined(__ARM_FEATURE_SIMD32)
  if constexpr(DSP) return __uadd16(values, 0x00010001U);
#endif
  // Encoder input is <=8192 bytes, so neither halfword can carry out.
  return values + 0x00010001U;
}
template<bool DSP> inline u32 max_pair(u32 a, u32 b) {
#if defined(__ARM_FEATURE_SIMD32)
  if constexpr(DSP) {
    (void)__usub16(a, b);
    return __sel(a, b);
  }
#endif
  const u32 low = (u16)a > (u16)b ? (u16)a : (u16)b;
  const u32 high = (a >> 16) > (b >> 16) ? a >> 16 : b >> 16;
  return low | (high << 16);
}

template<bool DSP> inline u16 lcp_range(const u8* input, u16 position,
                                       u16* lcp, u16 first, u16 last) {
  const u32 repeated = (u32)input[position] * 0x01010101U;
  u32 largest = 0;
  u16 offset = first;
  while((u32)offset + 3 <= last) {
    const u32 candidates = __builtin_bswap32(load(input + position - offset - 3));
    const u32 mask = equal_byte_mask<DSP>(candidates ^ repeated);
    const u32 a = increment_pair<DSP>(load(lcp + offset)) & widen_mask_pair(mask);
    const u32 b = increment_pair<DSP>(load(lcp + offset + 2)) & widen_mask_pair(mask >> 16);
    store(lcp + offset, a); store(lcp + offset + 2, b);
    largest = max_pair<DSP>(largest, max_pair<DSP>(a, b));
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

template<bool DSP> inline void lcp_blocks(const u8* input, u16 position, u16* lcp,
                                         u16& near_length, u16& far_length) {
  const u16 maximum = position < 256 ? position : 256;
  near_length = maximum ? lcp_range<DSP>(input, position, lcp, 1, maximum < 128 ? maximum : 128) : 0;
  far_length = maximum > 128 ? lcp_range<DSP>(input, position, lcp, 129, maximum) : 0;
  for(u16 offset = maximum + 1; offset <= 256; ++offset) lcp[offset] = 0;
}
} // namespace zx0_candidates
#endif
