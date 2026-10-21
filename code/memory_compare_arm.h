#ifndef MK61_MEMORY_COMPARE_ARM_H
#define MK61_MEMORY_COMPARE_ARM_H
#include <stddef.h>
/* Share the actual public entry between firmware and standalone APPs.
 * The first differing unsigned byte determines the sign. No input writes,
 * out-of-range reads, global state or nested calls are needed. */
#if defined(__GNUC__) && !defined(__clang__) && \
    (defined(__ARM_ARCH_7EM__) && defined(__ARM_FEATURE_UNALIGNED))
#define MK61_ARM_MEMCMP 1
#ifndef MK61_MEMCMP_NAME
#define MK61_MEMCMP_NAME memcmp
#endif
#ifndef MK61_MEMCMP_ATTRIBUTES
#define MK61_MEMCMP_ATTRIBUTES
#endif
__attribute__((naked, noipa, aligned(4))) MK61_MEMCMP_ATTRIBUTES
int MK61_MEMCMP_NAME(const void* left __attribute__((unused)),
                    const void* right __attribute__((unused)),
                    size_t size __attribute__((unused))) {
  __asm__(
#if defined(MK61_MEMCMP_M4_FLASH)
/* The Flash instruction buffer hides the wider r12 loads. Avoid the
 * r4 save/restore here; SRAM APPs benefit from the narrow r4 loads. */
#include "memcmp_m4_flash.inc"
#else
#include "memcmp_m4.inc"
#endif
  );
}
#endif
#endif
