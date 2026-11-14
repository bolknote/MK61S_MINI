#ifndef MK61_STORAGE_NAME_HPP
#define MK61_STORAGE_NAME_HPP

#include "mk8_codec.hpp"
#include "rust_types.h"

#include <string.h>

namespace storage_name {
namespace detail {

inline char ascii_upper(char value) {
  return value >= 'a' && value <= 'z'
      ? (char) (value - 'a' + 'A') : value;
}

inline bool reserved_dos_name(const char* name, usize len) {
  usize base_len = 0;
  while(base_len < len && name[base_len] != '.') ++base_len;
  char base[5] = {};
  if(base_len == 0 || base_len >= sizeof(base)) return false;
  for(usize i = 0; i < base_len; ++i) base[i] = ascii_upper(name[i]);
  if(strcmp(base, "CON") == 0 || strcmp(base, "PRN") == 0 ||
     strcmp(base, "AUX") == 0 || strcmp(base, "NUL") == 0) return true;
  return base_len == 4 && (memcmp(base, "COM", 3) == 0 ||
                           memcmp(base, "LPT", 3) == 0) &&
         base[3] >= '1' && base[3] <= '9';
}

} // namespace detail

// Canonical C6 basename policy shared by the resident store and USBDISK.APP.
// capacity includes the terminating zero.
inline bool valid_basename(const char* name, usize capacity) {
  if(name == nullptr || capacity < 2 || name[0] == 0 ||
     strcmp(name, ".") == 0 || strcmp(name, "..") == 0) return false;
  usize len = 0;
  while(name[len] != 0) {
    const u8 value = (u8) name[len];
    if(value < 0x20 || strchr("<>:\"/\\|?*", value) != nullptr) return false;
    if(++len >= capacity) return false;
  }
  return name[len - 1] != ' ' && name[len - 1] != '.' &&
         mk8::text_valid((const u8*) name, len) &&
         !detail::reserved_dos_name(name, len);
}

} // namespace storage_name

#endif
