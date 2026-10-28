#ifndef MK61_LANGUAGE_SOURCE_SCAN_HPP
#define MK61_LANGUAGE_SOURCE_SCAN_HPP

#include <stddef.h>
#include <stdint.h>

#if (defined(__ARM_FEATURE_SIMD32) || defined(LANGUAGE_VM_TEST_DSP_SCAN)) && \
    defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
  #define MK61_SOURCE_SCAN_FOUR_BYTES 1
#else
  #define MK61_SOURCE_SCAN_FOUR_BYTES 0
#endif
#if MK61_SOURCE_SCAN_FOUR_BYTES && !defined(LANGUAGE_VM_TEST_DSP_SCAN)
  #include <arm_acle.h>
#endif

namespace language_vm {
namespace source_scan {

#if MK61_SOURCE_SCAN_FOUR_BYTES
inline uint32_t line_mask(uint32_t word) {
#if defined(LANGUAGE_VM_TEST_DSP_SCAN)
  // Host-only emulation of USUB8/SEL's independent GE lanes. The same
  // four-byte loop and exact buffer reads are covered by ASan/UBSan.
  uint32_t result = 0;
  for(unsigned lane = 0; lane < 4; ++lane) {
    const uint8_t byte = (uint8_t)(word >> (8 * lane));
    if(byte == '\r' || byte == '\n') result |= 0xFFU << (8 * lane);
  }
  return result;
#else
  // XOR gives zero only in matching lanes. Subtracting one clears their GE
  // bits; SEL fills just those lanes. Neither cross-byte borrow nor M8 high
  // bytes can introduce a false delimiter. Keep each USUB8/SEL pair adjacent.
  (void)__usub8(word ^ 0x0D0D0D0DU, 0x01010101U);
  const uint32_t cr = __sel(0, ~0U);
  (void)__usub8(word ^ 0x0A0A0A0AU, 0x01010101U);
  return __sel(cr, ~0U);
#endif
}
#endif

// Shared by BASIC/FOCAL instead of duplicating the DSP loop in Compiler
// specializations. Returns length if no delimiter exists; a zero-length
// range is valid even with a null pointer. No alignment or trailing padding
// is required, and no load extends beyond the caller's bounded source.
#if MK61_SOURCE_SCAN_FOUR_BYTES
__attribute__((noinline))
#endif
inline size_t line_end(const uint8_t* source, size_t length) {
  size_t at = 0;
#if MK61_SOURCE_SCAN_FOUR_BYTES
  while(length - at >= 4) {
    uint32_t word;
    __builtin_memcpy(&word, source + at, sizeof(word));
    const uint32_t mask = line_mask(word);
    if(mask) return at + (size_t)__builtin_ctz(mask) / 8;
    at += 4;
  }
#endif
  while(at < length && source[at] != '\r' && source[at] != '\n') ++at;
  return at;
}

} // namespace source_scan
} // namespace language_vm

#undef MK61_SOURCE_SCAN_FOUR_BYTES
#endif
