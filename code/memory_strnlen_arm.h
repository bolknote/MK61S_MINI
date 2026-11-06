/* Byte-only M4 strnlen selected by the grouped Classic measurements.
 * A remaining-count check guards every load, and a NUL ends the scan before
 * another byte is read. F401 and unsupported targets keep their C fallback.
 * Byte4 is the measured default; byte2 remains available for comparison.
 * See research/m4-string-batch-2026-11-06 for the complete regression map. */
#ifndef MK61_MEMORY_STRNLEN_ARM_H
#define MK61_MEMORY_STRNLEN_ARM_H
#include <stddef.h>

#if defined(__ARM_ARCH_7EM__) && defined(__GNUC__) && !defined(__clang__) && \
    !defined(STM32F401xC) && \
    (!defined(MK61_M4_STRING_BATCH_DISABLE) || !MK61_M4_STRING_BATCH_DISABLE)
#ifndef MK61_M4_STRING_BATCH_UNROLL
#define MK61_M4_STRING_BATCH_UNROLL 4
#endif
#if MK61_M4_STRING_BATCH_UNROLL != 2 && MK61_M4_STRING_BATCH_UNROLL != 4
#error "MK61_M4_STRING_BATCH_UNROLL must be 2 or 4"
#endif
#define MK61_ARM_STRNLEN 1

__attribute__((naked, noipa, aligned(16)))
size_t strnlen(const char* text __attribute__((unused)),
               size_t maximum __attribute__((unused))) {
  __asm__(
    "mov r2,r0\n"
    "cbz r1,.Lmk61_nlen_end\n"
    ".Lmk61_nlen_loop:\n"
    "ldrb r3,[r0],#1\n"
    "cbz r3,.Lmk61_nlen_nul\n"
    "subs r1,#1\n"
    "beq .Lmk61_nlen_end\n"
#if MK61_M4_STRING_BATCH_UNROLL == 4
    "ldrb r3,[r0],#1\n"
    "cbz r3,.Lmk61_nlen_nul\n"
    "subs r1,#1\n"
    "beq .Lmk61_nlen_end\n"
    "ldrb r3,[r0],#1\n"
    "cbz r3,.Lmk61_nlen_nul\n"
    "subs r1,#1\n"
    "beq .Lmk61_nlen_end\n"
#endif
    "ldrb r3,[r0],#1\n"
    "cbz r3,.Lmk61_nlen_nul\n"
    "subs r1,#1\n"
    "bne .Lmk61_nlen_loop\n"
    ".Lmk61_nlen_end:\n"
    "subs r0,r0,r2\n"
    "bx lr\n"
    ".Lmk61_nlen_nul:\n"
    "subs r0,#1\n"
    "subs r0,r0,r2\n"
    "bx lr\n"
  );
}
#endif
#endif
