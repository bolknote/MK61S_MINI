#ifndef MK61_MEMORY_MOVE_ARM_H
#define MK61_MEMORY_MOVE_ARM_H
#include <stddef.h>
/* Public function body, shared by STM32, RP2040 and standalone APPs. Keeping
 * it at the symbol avoids an extra branch and register save on short copies.
 * Directional loops never overwrite unread bytes; no memcpy overlap assumption. */
#if defined(__GNUC__) && !defined(__clang__) && \
    (defined(__ARM_ARCH_6M__) || \
     (defined(__ARM_ARCH_7EM__) && defined(__ARM_FEATURE_UNALIGNED)))
#define MK61_ARM_MEMMOVE 1
#ifndef MK61_MEMMOVE_NAME
#define MK61_MEMMOVE_NAME memmove
#endif
#ifndef MK61_MEMMOVE_ATTRIBUTES
#define MK61_MEMMOVE_ATTRIBUTES
#endif
__attribute__((naked, noipa, aligned(4))) MK61_MEMMOVE_ATTRIBUTES
void* MK61_MEMMOVE_NAME(void* destination __attribute__((unused)),
                      const void* source __attribute__((unused)),
                      size_t size __attribute__((unused))) {
  __asm__(
#if defined(__ARM_ARCH_6M__)
#include "memmove_m0.inc"
#else
#include "memmove_m4.inc"
#endif
  );
}
#endif
#endif
