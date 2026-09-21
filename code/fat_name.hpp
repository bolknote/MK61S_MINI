#ifndef FAT_NAME_HPP
#define FAT_NAME_HPP

#include "mk8_codec.hpp"

namespace fat_name {
inline bool equal(const char* left, const char* right) {
  if(left == nullptr || right == nullptr) return left == right;
  while(*left != 0 && *right != 0) {
    if(mk8::fold_case((u8) *left++) != mk8::fold_case((u8) *right++)) {
      return false;
    }
  }
  return *left == *right;
}

// Каждый байт M8 становится ровно одной кодовой единицей UTF-16 в FAT LFN.
inline u16 dirent_count(const char* text) {
  if(text == nullptr || *text == 0) return 0;
  u16 units = 0;
  while(*text != 0) {
    if(!mk8::valid_byte((u8) *text++)) return 0;
    if(units == 0xFFFFU) return 0;
    ++units;
  }
  return (u16) ((units + 12U) / 13U + 1U);
}

} // пространство имён fat_name

#endif
