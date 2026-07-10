#ifndef UTF8_VIEW_HPP
#define UTF8_VIEW_HPP

#include "rust_types.h"

namespace utf8_view {

inline bool continuation(u8 value) {
  return (value & 0xC0) == 0x80;
}

// Returns one for invalid input so callers always make progress. Valid four
// byte sequences are recognized even though the LCD viewer renders them as a
// replacement character.
inline u8 sequence_length(const u8* data, u16 len, u16 offset) {
  if(data == NULL || offset >= len) return 0;
  const u8 first = data[offset];
  if(first < 0x80) return 1;

  if(first >= 0xC2 && first <= 0xDF && offset + 1 < len && continuation(data[offset + 1])) {
    return 2;
  }

  if(first >= 0xE0 && first <= 0xEF && offset + 2 < len &&
     continuation(data[offset + 1]) && continuation(data[offset + 2])) {
    const u8 second = data[offset + 1];
    if(first == 0xE0 && second < 0xA0) return 1; // overlong
    if(first == 0xED && second >= 0xA0) return 1; // UTF-16 surrogate
    return 3;
  }

  if(first >= 0xF0 && first <= 0xF4 && offset + 3 < len &&
     continuation(data[offset + 1]) && continuation(data[offset + 2]) && continuation(data[offset + 3])) {
    const u8 second = data[offset + 1];
    if(first == 0xF0 && second < 0x90) return 1; // overlong
    if(first == 0xF4 && second > 0x8F) return 1; // beyond U+10FFFF
    return 4;
  }

  return 1;
}

inline u16 next_offset(const u8* data, u16 len, u16 offset) {
  const u8 bytes = sequence_length(data, len, offset);
  if(bytes == 0) return len;
  return (u16) (offset + bytes);
}

} // namespace utf8_view

#endif
