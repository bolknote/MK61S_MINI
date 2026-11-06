/* Byte-only M4 strncmp body measured on Classic F411. Each load is guarded
 * by n; no word read, prefix read, saved register or helper call is needed.
 * F401 residents retain their C body and existing Flash reserve. */
#ifndef MK61_MEMORY_STRNCMP_ARM_H
#define MK61_MEMORY_STRNCMP_ARM_H
#if defined(__ARM_ARCH_7EM__) && defined(__GNUC__) && !defined(__clang__) && \
    !defined(STM32F401xC)
#define MK61_ARM_STRNCMP 1
__attribute__((naked, noipa, aligned(16)))
int strncmp(const char* left __attribute__((unused)),
            const char* right __attribute__((unused)),
            size_t count __attribute__((unused))) {
  __asm__(
    "cbz r2,.Lmk61_ncmp_zero\n"
    "mov r12,r0\n"
    ".Lmk61_ncmp_loop:\n"
    "ldrb r3,[r12],#1\n"
    "ldrb r0,[r1],#1\n"
    "cmp r3,r0\n"
    "bne .Lmk61_ncmp_diff\n"
    "cbz r0,.Lmk61_ncmp_return\n"
    "subs r2,#1\n"
    "beq .Lmk61_ncmp_zero\n"
    "ldrb r3,[r12],#1\n"
    "ldrb r0,[r1],#1\n"
    "cmp r3,r0\n"
    "bne .Lmk61_ncmp_diff\n"
    "cbz r0,.Lmk61_ncmp_return\n"
    "subs r2,#1\n"
    "beq .Lmk61_ncmp_zero\n"
    "ldrb r3,[r12],#1\n"
    "ldrb r0,[r1],#1\n"
    "cmp r3,r0\n"
    "bne .Lmk61_ncmp_diff\n"
    "cbz r0,.Lmk61_ncmp_return\n"
    "subs r2,#1\n"
    "beq .Lmk61_ncmp_zero\n"
    "ldrb r3,[r12],#1\n"
    "ldrb r0,[r1],#1\n"
    "cmp r3,r0\n"
    "bne .Lmk61_ncmp_diff\n"
    "cbz r0,.Lmk61_ncmp_return\n"
    "subs r2,#1\n"
    "bne .Lmk61_ncmp_loop\n"
    ".Lmk61_ncmp_zero:\n"
    "movs r0,#0\n"
    ".Lmk61_ncmp_return:\n"
    "bx lr\n"
    ".Lmk61_ncmp_diff:\n"
    "subs r0,r3,r0\n"
    "bx lr\n"
  );
}
#endif
#endif
