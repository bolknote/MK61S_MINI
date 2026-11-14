#ifndef MK61_TINYBASIC_TEXT_HPP
#define MK61_TINYBASIC_TEXT_HPP
#include <stddef.h>
#include <stdint.h>
#include <string.h>
namespace tinybasic_text {
// A carriage return rewinds the write position, preserving the untouched tail.
inline bool append(char* buffer, size_t capacity, uint8_t& cursor, const char* text,
                   size_t length) {
  while (length--) {
    const char c = *text++;
    if (c == '\r') {
      cursor = 0;
      continue;
    }
    if (cursor >= capacity - 1) return false;
    const bool extend = buffer[cursor] == 0;
    buffer[cursor++] = c;
    if (extend) buffer[cursor] = 0;
  }
  return true;
}
}  // namespace tinybasic_text
#endif
