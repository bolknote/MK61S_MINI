#ifndef UTF8_VIEW_HPP
#define UTF8_VIEW_HPP

#include "utf8_codec.hpp"

namespace utf8_view {

// Для недопустимых данных возвращается единица, чтобы вызывающий код всегда
// продвигался вперёд. Допустимые четырёхбайтовые последовательности распознаются,
// хотя средство просмотра на ЖКИ отображает их символом замены.
inline u8 sequence_length(const u8* data, u16 len, u16 offset) {
  if(data == nullptr || offset >= len) return 0;
  return utf8_codec::decode(data + offset, (usize) (len - offset)).size;
}

inline u16 next_offset(const u8* data, u16 len, u16 offset) {
  const u8 bytes = sequence_length(data, len, offset);
  if(bytes == 0) return len;
  return (u16) (offset + bytes);
}

inline u16 previous_offset(const u8* data, u16 len, u16 offset) {
  if(data == nullptr || offset == 0) return 0;
  if(offset > len) offset = len;
  u16 candidate = (u16) (offset - 1);
  while(candidate > 0 && utf8_codec::is_continuation(data[candidate])) candidate--;
  const u16 next = next_offset(data, len, candidate);
  return next == offset ? candidate : (u16) (offset - 1);
}

inline u16 codepoint_count(const char* text, u16 byte_limit = 0xFFFF) {
  if(text == nullptr) return 0;
  u16 bytes = 0;
  while(bytes < byte_limit && text[bytes] != 0) bytes++;
  u16 count = 0;
  for(u16 offset = 0; offset < bytes; count++) {
    const u16 next = next_offset((const u8*) text, bytes, offset);
    offset = next > offset ? next : (u16) (offset + 1);
  }
  return count;
}

inline u16 byte_offset(const char* text, u16 codepoint_index,
                       u16 byte_limit = 0xFFFF) {
  if(text == nullptr) return 0;
  u16 bytes = 0;
  while(bytes < byte_limit && text[bytes] != 0) bytes++;
  u16 offset = 0;
  while(codepoint_index-- != 0 && offset < bytes) {
    const u16 next = next_offset((const u8*) text, bytes, offset);
    offset = next > offset ? next : (u16) (offset + 1);
  }
  return offset;
}

} // пространство имён utf8_view

#endif
