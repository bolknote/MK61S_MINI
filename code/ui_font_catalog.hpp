#ifndef MK61_UI_FONT_CATALOG_HPP
#define MK61_UI_FONT_CATALOG_HPP

#include "fmk_font.hpp"
#include "rust_types.h"

namespace ui_font_catalog {

static constexpr const char* DIRECTORY_NAME = "Fonts";

inline char ascii_fold(char value) {
  return value >= 'A' && value <= 'Z' ? (char) (value - 'A' + 'a') : value;
}

inline bool name_equal(const char* left, const char* right) {
  if(left == nullptr || right == nullptr) return left == right;
  while(*left != 0 && *right != 0) {
    if(ascii_fold(*left++) != ascii_fold(*right++)) return false;
  }
  return *left == *right;
}

inline int name_compare(const char* left, const char* right) {
  if(left == nullptr) return right == nullptr ? 0 : -1;
  if(right == nullptr) return 1;
  for(usize index = 0;; ++index) {
    const u8 left_byte = (u8) left[index];
    const u8 right_byte = (u8) right[index];
    const u8 left_folded = (u8) ascii_fold((char) left_byte);
    const u8 right_folded = (u8) ascii_fold((char) right_byte);
    if(left_folded != right_folded) return left_folded < right_folded ? -1 : 1;
    if(left_byte == 0 || right_byte == 0) {
      if(left_byte != right_byte) return left_byte < right_byte ? -1 : 1;
      // Make names which differ only in ASCII case deterministic as well.
      for(usize exact = 0;; ++exact) {
        const u8 a = (u8) left[exact];
        const u8 b = (u8) right[exact];
        if(a != b) return a < b ? -1 : 1;
        if(a == 0) return 0;
      }
    }
  }
}

// Stable across C5 reformatting and catalog reordering.  Zero and erased
// Flash are excluded so the settings journal can reserve both as "no file".
inline u32 name_key(const char* name) {
  u32 hash = 2166136261UL; // FNV-1a, ASCII case-insensitive like VFAT.
  if(name != nullptr) {
    while(*name != 0) {
      hash ^= (u8) ascii_fold(*name++);
      hash *= 16777619UL;
    }
  }
  if(hash == 0 || hash == 0xFFFFFFFFUL) hash ^= 0xA5A55A5AUL;
  return hash;
}

inline bool supported_height(u8 height) {
  return height == 12 || height == 14 || height == 16;
}

inline u16 read_le16(const u8* bytes) {
  return (u16) bytes[0] | ((u16) bytes[1] << 8);
}

// Cheap catalog preflight. Full ranges, bitstream and CRC are deliberately
// checked only by fmk::Face when the user applies the file; enumerating a menu
// must not seize the shared 8-KiB font/USB arena for every entry.
inline bool inspect_header(const u8* header, usize header_size,
                           u16 file_size, u8& height) {
  if(header == nullptr || header_size < fmk::HEADER_SIZE ||
     file_size < fmk::HEADER_SIZE || file_size > fmk::MAX_FILE_SIZE ||
     header[0] != 'F' || header[1] != 'M' ||
     header[2] != 'K' || header[3] != '1' ||
     (header[4] & (u8) ~fmk::FLAG_MONOSPACED) != 0 ||
     header[5] == 0 || header[5] > fmk::MAX_GLYPH_WIDTH ||
     !supported_height(header[6]) ||
     (header[7] & 0x0FU) > 4 ||
     read_le16(header + 8) == 0 || header[10] == 0 || header[11] != 0 ||
     read_le16(header + 12) != file_size) return false;
  const u8 pitch = (u8) (header[6] + (header[7] & 0x0FU));
  if(pitch == 0 || (64U + (header[7] & 0x0FU)) / pitch < 3U) return false;
  height = header[6];
  return true;
}

} // namespace ui_font_catalog

#endif
