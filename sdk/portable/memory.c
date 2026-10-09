/* Freestanding support required by GCC. The SDK links only used functions.
 * Compile with -fno-builtin so these loops cannot become recursive calls. */
#include <stddef.h>
#include <stdint.h>
#include "memory_word_ops.h"

#ifndef MK61_APP_SHARED_RUNTIME
void* memcpy(void* dst, const void* src, size_t size) {
  return mk61_memory_copy(dst, src, size);
}

void* memset(void* dst, int value, size_t size) {
  unsigned char* out = dst;
  for(size_t i = 0; i < size; ++i) out[i] = (unsigned char) value;
  return dst;
}

void* memmove(void* dst, const void* src, size_t size) {
  unsigned char* out = dst;
  const unsigned char* in = src;
  /* Compare addresses as integers: unrelated pointers have no C ordering. */
  if((uintptr_t) out < (uintptr_t) in) return memcpy(dst, src, size);
  while(size != 0) { --size; out[size] = in[size]; }
  return dst;
}

int memcmp(const void* left, const void* right, size_t size) {
  return mk61_memory_compare(left, right, size);
}

/* Newlib's Cortex-M string routines are optimized for throughput and pull
 * substantially more code into the 20-KiB system APPs. Keep the few string
 * operations they use here with standard bytewise semantics. */
size_t strlen(const char* text) {
  const char* end = text;
  while(*end != 0) ++end;
  return (size_t) (end - text);
}
#endif

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
