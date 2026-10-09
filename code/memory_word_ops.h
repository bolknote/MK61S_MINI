#ifndef MK61_MEMORY_WORD_OPS_H
#define MK61_MEMORY_WORD_OPS_H

#include <stddef.h>
#include <stdint.h>

// Cortex-M4 supports unaligned ordinary-memory loads. The one-byte-aligned,
// may-alias type makes bounded word access explicit without calling memcpy
// from its own replacement. Other targets keep the portable byte path.
#if (defined(__ARM_ARCH_7EM__) && defined(__ARM_FEATURE_UNALIGNED)) || \
    defined(MK61_MEMORY_TEST_WORDS)
  #if defined(__GNUC__) || defined(__clang__)
    #define MK61_MEMORY_WORDS 1
    typedef uint32_t mk61_memory_word __attribute__((__aligned__(1), __may_alias__));
  #endif
#endif
#ifndef MK61_MEMORY_WORDS
  #define MK61_MEMORY_WORDS 0
#endif

static inline void* mk61_memory_copy(void* destination, const void* source,
                                     size_t size) {
  unsigned char* out = (unsigned char*) destination;
  const unsigned char* in = (const unsigned char*) source;
#if MK61_MEMORY_WORDS
  // Keep tiny dynamic copies away from the register-heavy bulk loop. At -Os,
  // GCC otherwise computes the bulk-loop end even when no bulk is copied.
  if(size < 4) {
    if(size > 0) out[0] = in[0];
    if(size > 1) out[1] = in[1];
    if(size > 2) out[2] = in[2];
    return destination;
  }
  if(size < 16) {
    if(size >= 8) {
      *(mk61_memory_word*) out = *(const mk61_memory_word*) in;
      *(mk61_memory_word*) (out + 4) = *(const mk61_memory_word*) (in + 4);
      out += 8;
      in += 8;
      size -= 8;
    }
    if(size >= 4) {
      *(mk61_memory_word*) out = *(const mk61_memory_word*) in;
      out += 4;
      in += 4;
      size -= 4;
    }
    if(size > 0) out[0] = in[0];
    if(size > 1) out[1] = in[1];
    if(size > 2) out[2] = in[2];
    return destination;
  }
  while(size >= 16) {
    const uint32_t a = *(const mk61_memory_word*) in;
    const uint32_t b = *(const mk61_memory_word*) (in + 4);
    const uint32_t c = *(const mk61_memory_word*) (in + 8);
    const uint32_t d = *(const mk61_memory_word*) (in + 12);
    *(mk61_memory_word*) out = a;
    *(mk61_memory_word*) (out + 4) = b;
    *(mk61_memory_word*) (out + 8) = c;
    *(mk61_memory_word*) (out + 12) = d;
    in += 16;
    out += 16;
    size -= 16;
  }
  while(size >= 4) {
    *(mk61_memory_word*) out = *(const mk61_memory_word*) in;
    in += 4;
    out += 4;
    size -= 4;
  }
#endif
  while(size != 0) {
    *out++ = *in++;
    --size;
  }
  return destination;
}

static inline int mk61_memory_compare(const void* left, const void* right,
                                      size_t size) {
  const unsigned char* a = (const unsigned char*) left;
  const unsigned char* b = (const unsigned char*) right;
  if(size == 0) return 0;
  // Short names and mismatches at byte zero must avoid word-loop setup.
  const int first = (int) a[0] - b[0];
  if(first != 0 || size == 1) return first;
#if MK61_MEMORY_WORDS
  if(size >= 8) {
    do {
      const uint32_t x = *(const mk61_memory_word*) a;
      const uint32_t y = *(const mk61_memory_word*) b;
      const uint32_t difference = x ^ y;
      if(difference != 0) {
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
        const unsigned shift = (unsigned) __builtin_ctz(difference) & ~7U;
        return (int) ((x >> shift) & 255U) - (int) ((y >> shift) & 255U);
#else
        for(unsigned i = 0; i < 4; ++i)
          if(a[i] != b[i]) return (int) a[i] - b[i];
#endif
      }
      a += 4;
      b += 4;
      size -= 4;
    } while(size >= 4);
  } else {
    ++a;
    ++b;
    --size;
  }
#else
  ++a;
  ++b;
  --size;
#endif
  while(size != 0) {
    if(*a != *b) return (int) *a - *b;
    ++a;
    ++b;
    --size;
  }
  return 0;
}

#if MK61_MEMORY_WORDS
#if defined(__GNUC__) && !defined(__clang__)
#define MK61_MEMORY_BULK __attribute__((noipa))
#else
#define MK61_MEMORY_BULK __attribute__((noinline))
#endif
static MK61_MEMORY_BULK void* mk61_memory_fill_small(void* destination, int value,
                                                   size_t size) {
  unsigned char* out = (unsigned char*) destination;
  unsigned char* end = out + size; // callers have already handled size == 0
  while(out != end) *out++ = (unsigned char) value;
  return destination;
}
static MK61_MEMORY_BULK void* mk61_memory_move_small(void* destination,
                                             const void* source, size_t size) {
  unsigned char* out = (unsigned char*) destination;
  const unsigned char* in = (const unsigned char*) source;
  if((uintptr_t) out < (uintptr_t) in ||
     (uintptr_t) out - (uintptr_t) in >= size) {
    unsigned char* end = out + size;
    while(out != end) *out++ = *in++;
  } else {
    while(size != 0) { --size; out[size] = in[size]; }
  }
  return destination;
}
// Separate bulk functions keep their register saves off the short paths at
// -Os. Otherwise GCC reserves bulk-loop registers even for a one-byte clear.
static MK61_MEMORY_BULK void* mk61_memory_fill_bulk(void* destination, int value,
                                                  size_t size) {
  unsigned char* out = (unsigned char*) destination;
  const uint32_t word = (uint32_t) (unsigned char) value * 0x01010101U;
  while(size >= 16) {
    *(mk61_memory_word*) out = word;
    *(mk61_memory_word*) (out + 4) = word;
    *(mk61_memory_word*) (out + 8) = word;
    *(mk61_memory_word*) (out + 12) = word;
    out += 16;
    size -= 16;
  }
  while(size >= 4) {
    *(mk61_memory_word*) out = word;
    out += 4;
    size -= 4;
  }
  while(size != 0) { *out++ = (unsigned char) value; --size; }
  return destination;
}
static MK61_MEMORY_BULK void* mk61_memory_move_backward_bulk(void* destination,
                                            const void* source, size_t size) {
  unsigned char* out = (unsigned char*) destination;
  const unsigned char* in = (const unsigned char*) source;
  while(size >= 16) {
    size -= 16;
    // Preserve the order inside the block too: gaps of 1..15 bytes can
    // overlap a word that has not yet been read.
    *(mk61_memory_word*) (out + size + 12) = *(const mk61_memory_word*) (in + size + 12);
    *(mk61_memory_word*) (out + size + 8) = *(const mk61_memory_word*) (in + size + 8);
    *(mk61_memory_word*) (out + size + 4) = *(const mk61_memory_word*) (in + size + 4);
    *(mk61_memory_word*) (out + size) = *(const mk61_memory_word*) (in + size);
  }
  while(size >= 4) {
    size -= 4;
    *(mk61_memory_word*) (out + size) = *(const mk61_memory_word*) (in + size);
  }
  while(size != 0) { --size; out[size] = in[size]; }
  return destination;
}
static MK61_MEMORY_BULK void* mk61_memory_move_bulk(void* destination,
                                            const void* source, size_t size) {
  if((uintptr_t) destination < (uintptr_t) source ||
     (uintptr_t) destination - (uintptr_t) source >= size)
    return mk61_memory_copy(destination, source, size);
  return mk61_memory_move_backward_bulk(destination, source, size);
}
#undef MK61_MEMORY_BULK
#endif

static inline void* mk61_memory_fill(void* destination, int value, size_t size) {
  if(size == 0) return destination;
#if MK61_MEMORY_WORDS
  if(size < 16) return mk61_memory_fill_small(destination, value, size);
  return mk61_memory_fill_bulk(destination, value, size);
#else
  // Same bounded byte loop as newlib; do not set up word-pattern registers.
  unsigned char* out = (unsigned char*) destination;
  unsigned char* end = out + size;
  while(out != end) *out++ = (unsigned char) value;
  return destination;
#endif
}

static inline void* mk61_memory_move(void* destination, const void* source,
                                     size_t size) {
  unsigned char* out = (unsigned char*) destination;
  const unsigned char* in = (const unsigned char*) source;
  if(size == 0 || out == in) return destination;
#if MK61_MEMORY_WORDS
  if(size < 16) return mk61_memory_move_small(destination, source, size);
  return mk61_memory_move_bulk(destination, source, size);
#else
  // Integer address ordering also works for distinct objects. Use the
  // internal forward primitive for leftward overlap, not ISO C memcpy.
  if((uintptr_t) out < (uintptr_t) in ||
     (uintptr_t) out - (uintptr_t) in >= size) {
    unsigned char* end = out + size;
    while(out != end) *out++ = *in++;
    return destination;
  }
  while(size != 0) { --size; out[size] = in[size]; }
  return destination;
#endif
}

#undef MK61_MEMORY_WORDS
#endif
