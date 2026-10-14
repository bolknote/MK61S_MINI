#ifndef MK61_VM_SCAN_CANDIDATES_HPP
#define MK61_VM_SCAN_CANDIDATES_HPP

// Qualification kernels only: no compiler/runtime behavior is changed.
#include <stddef.h>
#include <stdint.h>
#if defined(__ARM_FEATURE_SIMD32)
#include <arm_acle.h>
#endif

namespace vm_scan_candidates {
#define VM_SCAN_INLINE inline __attribute__((always_inline))
using u8 = uint8_t;
using u32 = uint32_t;
using usize = size_t;

VM_SCAN_INLINE u32 load(const u8* p) {
  u32 result;
  __builtin_memcpy(&result, p, sizeof(result));
  return result;
}
VM_SCAN_INLINE bool space(u8 c) { return c == ' ' || c == '\t'; }
VM_SCAN_INLINE bool alpha(u8 c) { c |= 0x20; return c >= 'a' && c <= 'z'; }
VM_SCAN_INLINE u8 upper(u8 c) { return c >= 'a' && c <= 'z' ? (u8)(c - 32) : c; }

// Exact per-byte mask, including adjacent 0/1 bytes. Unlike the common
// subtract-one zero detector, this is safe for accepting ALL four lanes.
VM_SCAN_INLINE u32 zero_mask(u32 x) {
  return ~(((x & 0x7F7F7F7FU) + 0x7F7F7F7FU) | x | 0x7F7F7F7FU);
}
VM_SCAN_INLINE u32 ge_select(u32 a, u32 b, u32 yes, u32 no) {
#if defined(__ARM_FEATURE_SIMD32)
  (void)__usub8((uint8x4_t)a, (uint8x4_t)b);
  return __sel(yes, no);
#else
  // Independent lane emulation lets host sanitizers cover the DSP algorithm.
  u32 mask = 0;
  for(unsigned lane = 0; lane < 4; ++lane)
    if((u8)(a >> (lane * 8)) >= (u8)(b >> (lane * 8)))
      mask |= 0xFFU << (lane * 8);
  return (yes & mask) | (no & ~mask);
#endif
}
VM_SCAN_INLINE u32 equal_mask_dsp(u32 word, u32 a, u32 b) {
  const u32 first = ge_select(word ^ a, 0x01010101U, 0, ~0U);
  return ge_select(word ^ b, 0x01010101U, first, ~0U);
}
VM_SCAN_INLINE usize first_lane(u32 mask) { return (usize)__builtin_ctz(mask) / 8; }

VM_SCAN_INLINE usize line_scalar(const u8* p, usize n) {
  usize at = 0;
  while(at < n && p[at] != '\r' && p[at] != '\n') ++at;
  return at;
}
VM_SCAN_INLINE usize line_word(const u8* p, usize n) {
  usize at = 0;
  while(n - at >= 4) {
    const u32 word = load(p + at);
    const u32 mask = zero_mask(word ^ 0x0D0D0D0DU) | zero_mask(word ^ 0x0A0A0A0AU);
    if(mask) return at + first_lane(mask);
    at += 4;
  }
  return at + line_scalar(p + at, n - at);
}
VM_SCAN_INLINE usize line_dsp(const u8* p, usize n) {
  usize at = 0;
  while(n - at >= 4) {
    const u32 mask = equal_mask_dsp(load(p + at), 0x0D0D0D0DU, 0x0A0A0A0AU);
    if(mask) return at + first_lane(mask);
    at += 4;
  }
  return at + line_scalar(p + at, n - at);
}

VM_SCAN_INLINE usize spaces_scalar(const u8* p, usize n) {
  usize at = 0;
  while(at < n && space(p[at])) ++at;
  return at;
}
VM_SCAN_INLINE usize spaces_word(const u8* p, usize n) {
  usize at = 0;
  while(n - at >= 4) {
    const u32 word = load(p + at);
    const u32 mask = zero_mask(word ^ 0x20202020U) | zero_mask(word ^ 0x09090909U);
    if(mask != 0x80808080U) return at + first_lane((~mask) & 0x80808080U);
    at += 4;
  }
  return at + spaces_scalar(p + at, n - at);
}
VM_SCAN_INLINE usize spaces_dsp(const u8* p, usize n) {
  usize at = 0;
  while(n - at >= 4) {
    const u32 mask = equal_mask_dsp(load(p + at), 0x20202020U, 0x09090909U);
    if(mask != ~0U) return at + first_lane(~mask);
    at += 4;
  }
  return at + spaces_scalar(p + at, n - at);
}

VM_SCAN_INLINE u32 alpha_mask_word(u32 word) {
  const u32 lower = word | 0x20202020U;
  return ((lower | 0x80808080U) - 0x61616161U) &
         (0xFAFAFAFAU - (lower & 0x7F7F7F7FU)) & ~lower & 0x80808080U;
}
VM_SCAN_INLINE u32 alpha_mask_dsp(u32 word) {
  const u32 lower = word | 0x20202020U;
  const u32 a = ge_select(lower, 0x61616161U, ~0U, 0);
  return ge_select(0x7A7A7A7AU, lower, a, 0);
}
VM_SCAN_INLINE usize alpha_scalar(const u8* p, usize n) {
  usize at = 0;
  while(at < n && alpha(p[at])) ++at;
  return at;
}
VM_SCAN_INLINE usize alpha_word(const u8* p, usize n) {
  usize at = 0;
  while(n - at >= 4) {
    const u32 mask = alpha_mask_word(load(p + at));
    if(mask != 0x80808080U) return at + first_lane((~mask) & 0x80808080U);
    at += 4;
  }
  return at + alpha_scalar(p + at, n - at);
}
VM_SCAN_INLINE usize alpha_dsp(const u8* p, usize n) {
  usize at = 0;
  while(n - at >= 4) {
    const u32 mask = alpha_mask_dsp(load(p + at));
    if(mask != ~0U) return at + first_lane(~mask);
    at += 4;
  }
  return at + alpha_scalar(p + at, n - at);
}

VM_SCAN_INLINE bool upper_equal_scalar(const u8* p, const u8* q, usize n) {
  for(usize at = 0; at < n; ++at) if(upper(p[at]) != q[at]) return false;
  return true;
}
VM_SCAN_INLINE bool upper_equal_word(const u8* p, const u8* q, usize n) {
  usize at = 0;
  while(n - at >= 4) {
    const u32 word = load(p + at);
    const u32 upper_word = word & ~(alpha_mask_word(word) >> 2);
    if(upper_word != load(q + at)) return false;
    at += 4;
  }
  return upper_equal_scalar(p + at, q + at, n - at);
}
VM_SCAN_INLINE bool upper_equal_dsp(const u8* p, const u8* q, usize n) {
  usize at = 0;
  while(n - at >= 4) {
    const u32 word = load(p + at);
    const u32 upper_word = word & ~(alpha_mask_dsp(word) & 0x20202020U);
    if(upper_word != load(q + at)) return false;
    at += 4;
  }
  return upper_equal_scalar(p + at, q + at, n - at);
}

VM_SCAN_INLINE bool equal_scalar(const u8* p, const u8* q, usize n) {
  for(usize at = 0; at < n; ++at) if(p[at] != q[at]) return false;
  return true;
}
VM_SCAN_INLINE bool equal_word(const u8* p, const u8* q, usize n) {
  usize at = 0;
  while(n - at >= 4) {
    if(load(p + at) != load(q + at)) return false;
    at += 4;
  }
  return equal_scalar(p + at, q + at, n - at);
}
VM_SCAN_INLINE bool equal_dsp(const u8* p, const u8* q, usize n) {
  usize at = 0;
  while(n - at >= 4) {
#if defined(__ARM_FEATURE_SIMD32)
    if(__usad8((uint8x4_t)load(p + at), (uint8x4_t)load(q + at))) return false;
#else
    unsigned difference = 0;
    for(unsigned lane = 0; lane < 4; ++lane) {
      const int d = (int)p[at + lane] - q[at + lane];
      difference += (unsigned)(d < 0 ? -d : d);
    }
    if(difference) return false;
#endif
    at += 4;
  }
  return equal_scalar(p + at, q + at, n - at);
}
#undef VM_SCAN_INLINE
} // namespace vm_scan_candidates
#endif
