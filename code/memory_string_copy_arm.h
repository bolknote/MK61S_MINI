/* M4 strcpy/strncpy selected by the grouped Classic measurements.
 * Source loads are bytes and stop at NUL / n. strcpy writes its NUL;
 * strncpy writes exactly n bytes, including bounded zero padding.
 * Byte4 is the measured default; F401 and other targets retain C fallback.
 * See research/m4-string-batch-2026-11-06 for the complete regression map. */
#ifndef MK61_MEMORY_STRING_COPY_ARM_H
#define MK61_MEMORY_STRING_COPY_ARM_H
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
#define MK61_ARM_STRCPY 1
#define MK61_ARM_STRNCPY 1

__attribute__((naked, noipa, aligned(16)))
char* strcpy(char* destination __attribute__((unused)),
             const char* source __attribute__((unused))) {
  __asm__(
    "mov r3,r0\n"
    ".Lmk61_scpy_loop:\n"
    "ldrb r2,[r1],#1\n"
    "strb r2,[r3],#1\n"
    "cbz r2,.Lmk61_scpy_return\n"
    "ldrb r2,[r1],#1\n"
    "strb r2,[r3],#1\n"
    "cbz r2,.Lmk61_scpy_return\n"
#if MK61_M4_STRING_BATCH_UNROLL == 4
    "ldrb r2,[r1],#1\n"
    "strb r2,[r3],#1\n"
    "cbz r2,.Lmk61_scpy_return\n"
    "ldrb r2,[r1],#1\n"
    "strb r2,[r3],#1\n"
    "cbz r2,.Lmk61_scpy_return\n"
#endif
    "b .Lmk61_scpy_loop\n"
    ".Lmk61_scpy_return:\n"
    "bx lr\n"
  );
}

__attribute__((naked, noipa, aligned(16)))
char* strncpy(char* destination __attribute__((unused)),
              const char* source __attribute__((unused)),
              size_t count __attribute__((unused))) {
  __asm__(
    "cbz r2,.Lmk61_sncpy_return\n"
    "mov r3,r0\n"
    ".Lmk61_sncpy_loop:\n"
    "ldrb r12,[r1],#1\n"
    "strb r12,[r3],#1\n"
    "subs r2,#1\n"
    "beq .Lmk61_sncpy_return\n"
    "cmp r12,#0\n"
    "beq .Lmk61_sncpy_pad\n"
    "ldrb r12,[r1],#1\n"
    "strb r12,[r3],#1\n"
    "subs r2,#1\n"
    "beq .Lmk61_sncpy_return\n"
    "cmp r12,#0\n"
    "beq .Lmk61_sncpy_pad\n"
#if MK61_M4_STRING_BATCH_UNROLL == 4
    "ldrb r12,[r1],#1\n"
    "strb r12,[r3],#1\n"
    "subs r2,#1\n"
    "beq .Lmk61_sncpy_return\n"
    "cmp r12,#0\n"
    "beq .Lmk61_sncpy_pad\n"
    "ldrb r12,[r1],#1\n"
    "strb r12,[r3],#1\n"
    "subs r2,#1\n"
    "beq .Lmk61_sncpy_return\n"
    "cmp r12,#0\n"
    "beq .Lmk61_sncpy_pad\n"
#endif
    "b .Lmk61_sncpy_loop\n"
    ".Lmk61_sncpy_pad:\n"
    "movs r1,#0\n"
    /* The NUL is already copied, and r2 is strictly positive here. */
    "tst r3,#3\n"
    "beq .Lmk61_sncpy_words\n"
    ".Lmk61_sncpy_peel:\n"
    "strb r1,[r3],#1\n"
    "subs r2,#1\n"
    "beq .Lmk61_sncpy_return\n"
    "tst r3,#3\n"
    "bne .Lmk61_sncpy_peel\n"
    ".Lmk61_sncpy_words:\n"
    "cmp r2,#4\n"
    "blo .Lmk61_sncpy_tail\n"
    ".Lmk61_sncpy_word_loop:\n"
    /* Aligned destination and at least four owned bytes remain. */
    "str r1,[r3],#4\n"
    "subs r2,#4\n"
    "cmp r2,#4\n"
    "bhs .Lmk61_sncpy_word_loop\n"
    ".Lmk61_sncpy_tail:\n"
    "cbz r2,.Lmk61_sncpy_return\n"
    ".Lmk61_sncpy_tail_loop:\n"
    "strb r1,[r3],#1\n"
    "subs r2,#1\n"
    "bne .Lmk61_sncpy_tail_loop\n"
    ".Lmk61_sncpy_return:\n"
    "bx lr\n"
  );
}
#endif
#endif
