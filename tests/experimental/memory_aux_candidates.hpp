#ifndef MK61_MEMORY_AUX_CANDIDATES_HPP
#define MK61_MEMORY_AUX_CANDIDATES_HPP
#include "memory_word_ops.h"
#include <stddef.h>
#include <stdint.h>

// Experimental bounded normal-memory kernels, not global libc replacements.
namespace memory_aux {
using Byte = unsigned char;
typedef uint32_t Word __attribute__((aligned(1), may_alias));
static_assert(alignof(Word) == 1, "word access must allow byte alignment");
#define AUX_INLINE inline __attribute__((always_inline))
AUX_INLINE void* move_scalar(void* destination, const void* source, size_t n) {
  Byte* out = (Byte*) destination;
  const Byte* in = (const Byte*) source;
  if((uintptr_t) out <= (uintptr_t) in || (uintptr_t) out - (uintptr_t) in >= n)
    for(size_t i = 0; i < n; ++i) out[i] = in[i];
  else while(n) { --n; out[n] = in[n]; }
  return destination;
}
AUX_INLINE void* move_word(void* destination, const void* source, size_t n) {
  Byte* out = (Byte*) destination;
  const Byte* in = (const Byte*) source;
  if(!n || out == in) return destination;
  if((uintptr_t) out < (uintptr_t) in || (uintptr_t) out - (uintptr_t) in >= n)
    return mk61_memory_copy(destination, source, n);
  while(n >= 16) {
    n -= 16;
    // Walk backwards even inside each block: a later store must not destroy
    // an earlier word that has yet to be read when the gap is 1..15 bytes.
    *(Word*) (out + n + 12) = *(const Word*) (in + n + 12);
    *(Word*) (out + n + 8) = *(const Word*) (in + n + 8);
    *(Word*) (out + n + 4) = *(const Word*) (in + n + 4);
    *(Word*) (out + n) = *(const Word*) (in + n);
  }
  while(n >= 4) { n -= 4; *(Word*) (out + n) = *(const Word*) (in + n); }
  while(n) { --n; out[n] = in[n]; }
  return destination;
}
AUX_INLINE void* fill_scalar(void* destination, int value, size_t n) {
  Byte* out = (Byte*) destination;
  for(size_t i = 0; i < n; ++i) out[i] = (Byte) value;
  return destination;
}
AUX_INLINE void* fill_word(void* destination, int value, size_t n) {
  Byte* out = (Byte*) destination;
  const uint32_t word = (uint32_t) (Byte) value * 0x01010101U;
  while(n >= 16) {
    *(Word*) out = word; *(Word*) (out + 4) = word;
    *(Word*) (out + 8) = word; *(Word*) (out + 12) = word;
    out += 16; n -= 16;
  }
  while(n >= 4) { *(Word*) out = word; out += 4; n -= 4; }
  while(n) { *out++ = (Byte) value; --n; }
  return destination;
}
// String interfaces do not promise readable bytes after NUL. These controls
// remove loop overhead without loading a whole word beyond the terminator.
AUX_INLINE size_t length_scalar(const char* s) {
  const char* p = s; while(*p) ++p; return (size_t) (p - s);
}
AUX_INLINE size_t length_unrolled(const char* s) {
  const char* p = s;
  for(;;) {
    if(!p[0]) return (size_t) (p - s);
    if(!p[1]) return (size_t) (p - s + 1);
    if(!p[2]) return (size_t) (p - s + 2);
    if(!p[3]) return (size_t) (p - s + 3);
    p += 4;
  }
}
AUX_INLINE size_t bounded_length_scalar(const char* s, size_t maximum) {
  size_t n = 0; while(n < maximum && s[n]) ++n; return n;
}
AUX_INLINE size_t bounded_length_unrolled(const char* s, size_t maximum) {
  size_t n = 0;
  while(maximum - n >= 4) {
    if(!s[n]) return n;
    if(!s[n + 1]) return n + 1;
    if(!s[n + 2]) return n + 2;
    if(!s[n + 3]) return n + 3;
    n += 4;
  }
  while(n < maximum && s[n]) ++n;
  return n;
}
AUX_INLINE int string_compare_scalar(const char* a, const char* b) {
  const auto* x = (const Byte*) a; const auto* y = (const Byte*) b;
  while(*x && *x == *y) { ++x; ++y; }
  return (int) *x - *y;
}
AUX_INLINE int string_compare_unrolled(const char* a, const char* b) {
  const auto* x = (const Byte*) a; const auto* y = (const Byte*) b;
  for(;;) {
    if(!x[0] || x[0] != y[0]) return (int) x[0] - y[0];
    if(!x[1] || x[1] != y[1]) return (int) x[1] - y[1];
    if(!x[2] || x[2] != y[2]) return (int) x[2] - y[2];
    if(!x[3] || x[3] != y[3]) return (int) x[3] - y[3];
    x += 4; y += 4;
  }
}
AUX_INLINE int bounded_compare_scalar(const char* a, const char* b, size_t n) {
  const auto* x = (const Byte*) a; const auto* y = (const Byte*) b;
  while(n) { if(!*x || *x != *y) return (int) *x - *y; ++x; ++y; --n; }
  return 0;
}
AUX_INLINE int bounded_compare_unrolled(const char* a, const char* b, size_t n) {
  const auto* x = (const Byte*) a; const auto* y = (const Byte*) b;
  while(n >= 4) {
    if(!x[0] || x[0] != y[0]) return (int) x[0] - y[0];
    if(!x[1] || x[1] != y[1]) return (int) x[1] - y[1];
    if(!x[2] || x[2] != y[2]) return (int) x[2] - y[2];
    if(!x[3] || x[3] != y[3]) return (int) x[3] - y[3];
    x += 4; y += 4; n -= 4;
  }
  return bounded_compare_scalar((const char*) x, (const char*) y, n);
}
#undef AUX_INLINE
}
#endif
