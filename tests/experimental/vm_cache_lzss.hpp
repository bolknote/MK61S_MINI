#ifndef MK61_EXPERIMENTAL_VM_CACHE_LZSS_HPP
#define MK61_EXPERIMENTAL_VM_CACHE_LZSS_HPP
// Research-only, byte-oriented LZSS: 256-byte lookback, 3..18-byte matches.
// No firmware includes this file. Input/output must not overlap.
#include <stddef.h>
#include <stdint.h>
#include <string.h>
namespace vm_cache_lzss {
struct Workspace { uint16_t head[128]; };
static_assert(sizeof(Workspace) == 256, "bounded dictionary changed");
inline bool overlap(const uint8_t* a, size_t n, const uint8_t* b, size_t m) {
  const uintptr_t x = reinterpret_cast<uintptr_t>(a), y = reinterpret_cast<uintptr_t>(b);
  return n && m && (x <= y ? y - x < n : x - y < m);
}
inline unsigned hash(const uint8_t* p) {
  return (unsigned(p[0]) * 31U ^ unsigned(p[1]) * 11U ^ unsigned(p[2])) & 127U;
}
inline bool encode(const uint8_t* input, size_t size, Workspace& work,
                   uint8_t* output, size_t capacity, size_t& written) {
  written = 0;
  const auto* dictionary = reinterpret_cast<const uint8_t*>(&work);
  if ((!input && size) || size > 65534 || overlap(input,size,dictionary,sizeof(work)) ||
      (output && (overlap(input,size,output,capacity) || overlap(output,capacity,dictionary,sizeof(work))))) return false;
  for (auto& slot : work.head) slot = 0xFFFF;
  size_t cursor = 0;
  while (cursor < size) {
    uint8_t flags = 0, tokens[16]; unsigned used = 0;
    for (unsigned bit = 0; bit < 8 && cursor < size; ++bit) {
      size_t length = 0, offset = 0;
      if (size - cursor >= 3) {
        const unsigned bucket = hash(input + cursor);
        const size_t previous = work.head[bucket];
        if (previous < cursor && cursor - previous <= 256) {
          const size_t maximum = size - cursor < 18 ? size - cursor : 18;
          while (length < maximum && input[previous + length] == input[cursor + length]) ++length;
          if (length >= 3) offset = cursor - previous;
        }
      }
      if (!offset) { length = 1; tokens[used++] = input[cursor]; }
      else {
        flags |= uint8_t(1U << bit);
        tokens[used++] = uint8_t(offset - 1);
        tokens[used++] = uint8_t(length - 3);
      }
      for (size_t n = 0; n < length; ++n)
        if (size - (cursor + n) >= 3) work.head[hash(input + cursor + n)] = uint16_t(cursor + n);
      cursor += length;
    }
    if (output) {
      if (written > capacity || 1U + used > capacity - written) return false;
      output[written] = flags;
      memcpy(output + written + 1, tokens, used);
    }
    written += 1U + used;
  }
  return true;
}
inline bool decode(const uint8_t* input, size_t size, uint8_t* output,
                   size_t capacity, size_t logical_size) {
  if ((!input && size) || (!output && logical_size) || logical_size > capacity ||
      overlap(input,size,output,logical_size)) return false;
  size_t in = 0, out = 0;
  while (out < logical_size) {
    if (in == size) return false;
    const uint8_t flags = input[in++];
    unsigned bit = 0;
    for (; bit < 8 && out < logical_size; ++bit) {
      if (flags & (1U << bit)) {
        if (size - in < 2) return false;
        const size_t offset = size_t(input[in]) + 1;
        const uint8_t token = input[in+1]; in += 2;
        if (token > 15 || offset > out || size_t(token) + 3 > logical_size - out) return false;
        for (size_t n = 0; n < size_t(token) + 3; ++n) { output[out] = output[out-offset]; ++out; }
      } else {
        if (in == size) return false;
        output[out++] = input[in++];
      }
    }
    if (bit < 8 && (flags >> bit)) return false;
  }
  return in == size;
}
}
#endif
