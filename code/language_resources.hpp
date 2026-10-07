#ifndef MK61_LANGUAGE_RESOURCES_HPP
#define MK61_LANGUAGE_RESOURCES_HPP
#include "language_bytecode.hpp"
namespace language_vm {
inline uint16_t resource_word(const uint8_t* p) {
  return (uint16_t)(p[0] | ((uint16_t)p[1] << 8));
}
// Reads a span from the immutable M8 source identified in an image header.
inline bool valid_resource_recipe(const uint8_t* r, uint16_t available, uint16_t source_size) {
  if(!r || available < 3 || r[2] > (available - 3) / 3) return false;
  unsigned total = 0;
  for(uint8_t i = 0; i < r[2]; ++i) {
    const uint16_t at = resource_word(r + 3 + i * 3);
    const uint8_t n = r[5 + i * 3];
    if(!n || ((at & 0x8000) ? (at & 0x7F00) || n != 1 :
                     at > source_size || n > source_size - at)) return false;
    total += n;
  }
  return total == resource_word(r);
}
using ResourceRead = bool (*)(void*, uint16_t, uint8_t*, uint16_t);
using ResourceAppend = bool (*)(void*, const char*, uint16_t, bool first);
inline bool resource_text(const uint8_t* recipe, ResourceRead read,
                          void* source, ResourceAppend append, void* output) {
  char bytes[32];
  bool first = true;
  for (uint8_t i = 0; i < recipe[2]; ++i) {
    uint16_t at = resource_word(recipe + 3 + i * 3);
    uint8_t left = recipe[5 + i * 3];
    while (left) {
      const uint8_t n = left < sizeof(bytes) ? left : sizeof(bytes);
      if (at & 0x8000) bytes[0] = (char)at;
      else if (!read(source, at, (uint8_t*)bytes, n)) return false;
      if (!append(output, bytes, n, first)) return false;
      first = false; left -= n; at += n;
    }
  }
  return !first || append(output, "", 0, true);
}
inline bool resource_prompt(const uint8_t* recipe, char* output,
                            ResourceRead read, void* context) {
  uint16_t used = 0;
  if(resource_word(recipe) > 95) return false;
  for (uint8_t i = 0; i < recipe[2]; ++i) {
    const uint16_t at = resource_word(recipe + 3 + i * 3);
    const uint8_t n = recipe[5 + i * 3];
    if(!n || n > 95 - used || ((at & 0x8000) && n != 1)) return false;
    if (at & 0x8000) output[used] = (char)at;
    else if (!read(context, at, (uint8_t*)output + used, n)) return false;
    used += n;
  }
  if(used != resource_word(recipe)) return false;
  output[used] = 0;
  return true;
}
} // namespace language_vm
#endif
