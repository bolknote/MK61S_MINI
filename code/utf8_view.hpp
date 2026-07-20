#ifndef UTF8_VIEW_HPP
#define UTF8_VIEW_HPP

#include "rust_types.h"

namespace utf8_view {

inline bool continuation(u8 value) {
  return (value & 0xC0) == 0x80;
}

// Для недопустимых данных возвращается единица, чтобы вызывающий код всегда
// продвигался вперёд. Допустимые четырёхбайтовые последовательности распознаются,
// хотя средство просмотра на ЖКИ отображает их символом замены.
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
    if(first == 0xE0 && second < 0xA0) return 1; // Избыточное кодирование
    if(first == 0xED && second >= 0xA0) return 1; // Суррогат UTF-16
    return 3;
  }

  if(first >= 0xF0 && first <= 0xF4 && offset + 3 < len &&
     continuation(data[offset + 1]) && continuation(data[offset + 2]) && continuation(data[offset + 3])) {
    const u8 second = data[offset + 1];
    if(first == 0xF0 && second < 0x90) return 1; // Избыточное кодирование
    if(first == 0xF4 && second > 0x8F) return 1; // За пределами U+10FFFF
    return 4;
  }

  return 1;
}

inline u16 next_offset(const u8* data, u16 len, u16 offset) {
  const u8 bytes = sequence_length(data, len, offset);
  if(bytes == 0) return len;
  return (u16) (offset + bytes);
}

inline u16 previous_offset(const u8* data, u16 len, u16 offset) {
  if(data == NULL || offset == 0) return 0;
  if(offset > len) offset = len;
  u16 candidate = (u16) (offset - 1);
  while(candidate > 0 && continuation(data[candidate])) candidate--;
  const u16 next = next_offset(data, len, candidate);
  return next == offset ? candidate : (u16) (offset - 1);
}

inline u16 codepoint_count(const char* text, u16 byte_limit = 0xFFFF) {
  if(text == NULL) return 0;
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
  if(text == NULL) return 0;
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
