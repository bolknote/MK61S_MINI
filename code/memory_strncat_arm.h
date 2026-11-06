/* Unmeasured Classic F411 strncat batch candidate. Byte-only guarded
 * reads/writes; original destination returned; n0 touches neither buffer.
 * No stack/helper calls. Retain C fallbacks on other targets. */
#ifndef MK61_MEMORY_STRNCAT_ARM_H
#define MK61_MEMORY_STRNCAT_ARM_H
#include <stddef.h>
#ifndef MK61_M4_STRING_BATCH_UNROLL
#define MK61_M4_STRING_BATCH_UNROLL 4
#endif
#if MK61_M4_STRING_BATCH_UNROLL != 2 && MK61_M4_STRING_BATCH_UNROLL != 4
#error MK61_M4_STRING_BATCH_UNROLL must be 2 or 4
#endif
#if defined(__ARM_ARCH_7EM__) && defined(__GNUC__) && !defined(__clang__) && \
    !defined(STM32F401xC) && \
    (!defined(MK61_M4_STRING_BATCH_DISABLE) || !MK61_M4_STRING_BATCH_DISABLE)
#define MK61_ARM_STRNCAT 1
__attribute__((naked, noipa, aligned(16)))
char* strncat(char* destination __attribute__((unused)),
              const char* source __attribute__((unused)),
              size_t count __attribute__((unused))) {
  __asm__(
    "cbz r2,.Lmk61_ncat_return\n"
    "mov r12,r0\n"
    ".Lmk61_ncat_scan:\n"
    "ldrb r3,[r12],#1\n"
    "cbz r3,.Lmk61_ncat_found\n"
    "ldrb r3,[r12],#1\n"
    "cbz r3,.Lmk61_ncat_found\n"
#if MK61_M4_STRING_BATCH_UNROLL == 4
    "ldrb r3,[r12],#1\n"
    "cbz r3,.Lmk61_ncat_found\n"
    "ldrb r3,[r12],#1\n"
    "cbz r3,.Lmk61_ncat_found\n"
#endif
    "b .Lmk61_ncat_scan\n"
    ".Lmk61_ncat_found:\n"
    "sub.w r12,r12,#1\n"
    ".Lmk61_ncat_copy:\n"
    "ldrb r3,[r1],#1\n"
    "strb r3,[r12],#1\n"
    "cbz r3,.Lmk61_ncat_return\n"
    "subs r2,#1\n"
    "beq .Lmk61_ncat_terminate\n"
    "ldrb r3,[r1],#1\n"
    "strb r3,[r12],#1\n"
    "cbz r3,.Lmk61_ncat_return\n"
    "subs r2,#1\n"
    "beq .Lmk61_ncat_terminate\n"
#if MK61_M4_STRING_BATCH_UNROLL == 2
    "b .Lmk61_ncat_copy\n"
#endif
#if MK61_M4_STRING_BATCH_UNROLL == 4
    "ldrb r3,[r1],#1\n"
    "strb r3,[r12],#1\n"
    "cbz r3,.Lmk61_ncat_return\n"
    "subs r2,#1\n"
    "beq .Lmk61_ncat_terminate\n"
    "ldrb r3,[r1],#1\n"
    "strb r3,[r12],#1\n"
    "cbz r3,.Lmk61_ncat_return\n"
    "subs r2,#1\n"
    "bne .Lmk61_ncat_copy\n"
#endif
    ".Lmk61_ncat_terminate:\n"
    "movs r3,#0\n"
    "strb r3,[r12]\n"
    ".Lmk61_ncat_return:\n"
    "bx lr\n"
  );
}
#endif
#endif
