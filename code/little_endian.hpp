#ifndef MK61_LITTLE_ENDIAN_HPP
#define MK61_LITTLE_ENDIAN_HPP

#include <stdint.h>

// Caller-owned ordinary-memory fields, exactly two/four bytes wide. Match
// the native M4 memory primitives' unaligned-access contract without changing
// the wire format or requiring alignment of a byte buffer.
namespace little_endian {
#if ((defined(__ARM_ARCH_7EM__) && defined(__ARM_FEATURE_UNALIGNED)) || \
     defined(MK61_MEMORY_TEST_WORDS)) && \
    defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__ && \
    (defined(__GNUC__) || defined(__clang__))
  #define MK61_LE_WORDS 1
  typedef uint16_t Word16 __attribute__((aligned(1), may_alias));
  typedef uint32_t Word32 __attribute__((aligned(1), may_alias));
#else
  #define MK61_LE_WORDS 0
#endif
#if defined(__GNUC__) || defined(__clang__)
  #define MK61_LE_INLINE inline __attribute__((always_inline))
#else
  #define MK61_LE_INLINE inline
#endif

MK61_LE_INLINE uint16_t read16(const uint8_t* bytes) {
#if MK61_LE_WORDS
  return *(const Word16*)bytes;
#else
  return (uint16_t)(bytes[0] | ((uint16_t)bytes[1] << 8));
#endif
}
MK61_LE_INLINE uint32_t read32(const uint8_t* bytes) {
#if MK61_LE_WORDS
  return *(const Word32*)bytes;
#else
  return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) |
         ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
#endif
}
MK61_LE_INLINE void write16(uint8_t* bytes, uint16_t value) {
#if MK61_LE_WORDS
  *(Word16*)bytes = value;
#else
  bytes[0] = (uint8_t)value;
  bytes[1] = (uint8_t)(value >> 8);
#endif
}
MK61_LE_INLINE void write32(uint8_t* bytes, uint32_t value) {
#if MK61_LE_WORDS
  *(Word32*)bytes = value;
#else
  bytes[0] = (uint8_t)value;
  bytes[1] = (uint8_t)(value >> 8);
  bytes[2] = (uint8_t)(value >> 16);
  bytes[3] = (uint8_t)(value >> 24);
#endif
}
#undef MK61_LE_INLINE
#undef MK61_LE_WORDS
} // namespace little_endian
#endif
