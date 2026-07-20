#ifndef FAT_NAME_HPP
#define FAT_NAME_HPP

#include "rust_types.h"

namespace fat_name {
namespace detail {

// Простое приведение регистра Unicode для письменностей, обычно встречающихся
// в длинных именах FAT. Письменности без регистра (например, CJK) естественным
// образом сравниваются без изменений. Здесь намеренно нет зависимых от локали
// правил и выделения памяти.
inline u32 fold(u32 codepoint) {
  if(codepoint >= 'A' && codepoint <= 'Z') return codepoint + 0x20;
  if((codepoint >= 0x00C0 && codepoint <= 0x00D6) ||
     (codepoint >= 0x00D8 && codepoint <= 0x00DE)) return codepoint + 0x20;
  if(codepoint == 0x0178) return 0x00FF;

  if(codepoint >= 0x0100 && codepoint <= 0x012F &&
     (codepoint & 1U) == 0) return codepoint + 1;
  if(codepoint >= 0x0132 && codepoint <= 0x0137 &&
     (codepoint & 1U) == 0) return codepoint + 1;
  if(codepoint >= 0x0139 && codepoint <= 0x0148 &&
     (codepoint & 1U) != 0) return codepoint + 1;
  if(codepoint >= 0x014A && codepoint <= 0x0177 &&
     (codepoint & 1U) == 0) return codepoint + 1;

  switch(codepoint) {
    case 0x0386: return 0x03AC;
    case 0x0388: return 0x03AD;
    case 0x0389: return 0x03AE;
    case 0x038A: return 0x03AF;
    case 0x038C: return 0x03CC;
    case 0x038E: return 0x03CD;
    case 0x038F: return 0x03CE;
    case 0x03C2: return 0x03C3; // конечная сигма
    case 0x04C0: return 0x04CF;
    default: break;
  }
  if((codepoint >= 0x0391 && codepoint <= 0x03A1) ||
     (codepoint >= 0x03A3 && codepoint <= 0x03AB)) return codepoint + 0x20;

  if(codepoint >= 0x0400 && codepoint <= 0x040F) return codepoint + 0x50;
  if(codepoint >= 0x0410 && codepoint <= 0x042F) return codepoint + 0x20;
  if(codepoint >= 0x0460 && codepoint <= 0x0481 &&
     (codepoint & 1U) == 0) return codepoint + 1;
  if(codepoint >= 0x048A && codepoint <= 0x04BF &&
     (codepoint & 1U) == 0) return codepoint + 1;
  if(codepoint >= 0x04C1 && codepoint <= 0x04CE &&
     (codepoint & 1U) != 0) return codepoint + 1;
  if(codepoint >= 0x04D0 && codepoint <= 0x052F &&
     (codepoint & 1U) == 0) return codepoint + 1;

  if(codepoint >= 0x0531 && codepoint <= 0x0556) return codepoint + 0x30;
  if(codepoint >= 0xFF21 && codepoint <= 0xFF3A) return codepoint + 0x20;
  return codepoint;
}

inline u32 next(const char*& text) {
  const u8 first = (u8) *text++;
  if(first < 0x80) return first;

  u8 continuation = 0;
  u32 codepoint = 0;
  u32 minimum = 0;
  if(first >= 0xC2 && first <= 0xDF) {
    continuation = 1;
    codepoint = first & 0x1F;
    minimum = 0x80;
  } else if(first >= 0xE0 && first <= 0xEF) {
    continuation = 2;
    codepoint = first & 0x0F;
    minimum = 0x800;
  } else if(first >= 0xF0 && first <= 0xF4) {
    continuation = 3;
    codepoint = first & 0x07;
    minimum = 0x10000;
  } else {
    return 0x110000UL + first;
  }

  const char* cursor = text;
  for(u8 index = 0; index < continuation; index++) {
    const u8 byte = (u8) *cursor++;
    if((byte & 0xC0) != 0x80) return 0x110000UL + first;
    codepoint = (codepoint << 6) | (byte & 0x3F);
  }
  if(codepoint < minimum || codepoint > 0x10FFFFUL ||
     (codepoint >= 0xD800 && codepoint <= 0xDFFF)) {
    return 0x110000UL + first;
  }
  text = cursor;
  return codepoint;
}

} // пространство имён detail

inline bool equal(const char* left, const char* right) {
  if(left == nullptr || right == nullptr) return left == right;
  while(*left != 0 && *right != 0) {
    if(detail::fold(detail::next(left)) !=
       detail::fold(detail::next(right))) return false;
  }
  return *left == *right;
}

// Каждый объект C5 представлен длинным именем LFN и стабильным коротким
// псевдонимом на основе ID. Подсчитываем точное число 32-байтовых записей
// каталога FAT для видимого имени UTF-8, не выделяя буфер преобразования UTF-16.
inline u16 dirent_count(const char* text) {
  if(text == nullptr || *text == 0) return 0;
  u16 units = 0;
  while(*text != 0) {
    const u32 codepoint = detail::next(text);
    if(codepoint > 0x10FFFFUL) return 0;
    const u8 added = codepoint > 0xFFFF ? 2 : 1;
    if(units > (u16) (0xFFFFU - added)) return 0;
    units = (u16) (units + added);
  }
  return (u16) ((units + 12U) / 13U + 1U);
}

} // пространство имён fat_name

#endif
