/* Freestanding support required by GCC. The SDK links only used functions.
 * Compile with -fno-builtin so these loops cannot become recursive calls. */
#include <stddef.h>
#include <stdint.h>
#include "memory_word_ops.h"

#ifndef MK61_APP_SHARED_RUNTIME
#include "memory_copy_arm.h"
#ifndef MK61_ARM_MEMCPY
void* memcpy(void* dst, const void* src, size_t size) {
  return mk61_memory_copy(dst, src, size);
}
#endif

#if defined(__ARM_ARCH_6M__) && defined(__GNUC__) && !defined(__clang__)
/* Keep the measured M0+ function at the public entry: a C forwarding wrapper
 * would add a saved LR and a BL/return on this Thumb-1 target. */
__attribute__((naked, noipa, aligned(4)))
void* memset(void* dst __attribute__((unused)),
             int value __attribute__((unused)), size_t size __attribute__((unused))) {
  __asm__(
#include "memset_m0.inc"
  );
}
#else
void* memset(void* dst, int value, size_t size) {
  return mk61_memory_fill(dst, value, size);
}
#endif

#include "memory_move_arm.h"
#ifndef MK61_ARM_MEMMOVE
void* memmove(void* dst, const void* src, size_t size) {
  return mk61_memory_move(dst, src, size);
}
#endif

#include "memory_compare_arm.h"
#ifndef MK61_ARM_MEMCMP
int memcmp(const void* left, const void* right, size_t size) {
  return mk61_memory_compare(left, right, size);
}
#endif

/* Newlib's Cortex-M string routines are optimized for throughput and pull
 * substantially more code into the 20-KiB system APPs. Keep the few string
 * operations they use here with standard bytewise semantics. */
size_t strlen(const char* text) {
  const char* end = text;
  while(*end != 0) ++end;
  return (size_t) (end - text);
}
#endif

/* The 26-slot runtime has no memchr. Keep the measured M4 body local to both
 * standalone and shared APPs; the optional public extension is separate. */
#include "memory_search_arm.h"

int strcmp(const char* left, const char* right) {
  const unsigned char* a = (const unsigned char*) left;
  const unsigned char* b = (const unsigned char*) right;
  while(*a != 0 && *a == *b) { ++a; ++b; }
  return (int) *a - (int) *b;
}

#ifndef MK61_APP_SHARED_RUNTIME
char* strchr(const char* text, int character) {
  const unsigned char wanted = (unsigned char) character;
  do {
    if((unsigned char) *text == wanted) return (char*) text;
  } while(*text++ != 0);
  return NULL;
}
#endif
