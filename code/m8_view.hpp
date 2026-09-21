#ifndef MK61_M8_VIEW_HPP
#define MK61_M8_VIEW_HPP

#include "rust_types.h"

// M8 is single-byte: character, cursor and byte offsets are identical.  This
// small facade keeps callers explicit and prevents UTF-8 navigation from
// creeping back into the resident UI and C6 editors.
namespace m8_view {

inline u8 sequence_length(const u8* data, u16 len, u16 offset) {
  return data != nullptr && offset < len ? 1U : 0U;
}

inline u16 next_offset(const u8* data, u16 len, u16 offset) {
  return sequence_length(data, len, offset) ? (u16) (offset + 1U) : len;
}

inline u16 previous_offset(const u8* data, u16 len, u16 offset) {
  if(data == nullptr || offset == 0) return 0;
  if(offset > len) offset = len;
  return (u16) (offset - 1U);
}

inline u16 codepoint_count(const char* text, u16 byte_limit = 0xFFFFU) {
  if(text == nullptr) return 0;
  u16 length = 0;
  while(length < byte_limit && text[length] != 0) ++length;
  return length;
}

inline u16 byte_offset(const char* text, u16 character_index,
                       u16 byte_limit = 0xFFFFU) {
  const u16 length = codepoint_count(text, byte_limit);
  return character_index < length ? character_index : length;
}

} // namespace m8_view

#endif
