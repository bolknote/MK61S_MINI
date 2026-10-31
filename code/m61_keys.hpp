#ifndef MK61_M61_KEYS_HPP
#define MK61_M61_KEYS_HPP

#include "keyboard_layout.hpp"

// Stable logical key numbers, in hex in M61. 00..1E retain the APP/BASIC
// numbering. 1F/20 were redundant step aliases: use 11/12 for those keys.
namespace m61_keys {
static constexpr u8 COUNT = 0x2A;
static constexpr u8 MASK_BYTES = (COUNT + 7U) / 8U;
static constexpr u8 OK = MK61_APP_KEY_OK;
static constexpr u8 ESC = MK61_APP_KEY_ESC;
static constexpr u8 CLEAR = MK61_APP_KEY_CLEAR;
static constexpr u8 ENTER = 0x21, SWAP = 0x22, EXPONENT = 0x23,
    NEGATE = 0x24, DEGREE = 0x25, GRADE = 0x26, RADIAN = 0x27,
    SAVE = 0x28, LOAD = 0x29;

constexpr bool valid(unsigned code) {
  return code < COUNT && code != 0x1F && code != 0x20;
}

inline i32 scan_code(const keyboard_layout::Mapping& keys, unsigned code) {
  if(!valid(code)) return -1;
  if(code <= 9) return keys.digit[code];
  static const u8 fields[] = {
    offsetof(keyboard_layout::Mapping, dot), offsetof(keyboard_layout::Mapping, add),
    offsetof(keyboard_layout::Mapping, sub), offsetof(keyboard_layout::Mapping, mul),
    offsetof(keyboard_layout::Mapping, div), offsetof(keyboard_layout::Mapping, left),
    offsetof(keyboard_layout::Mapping, right), offsetof(keyboard_layout::Mapping, shg_left),
    offsetof(keyboard_layout::Mapping, shg_right), offsetof(keyboard_layout::Mapping, ok),
    offsetof(keyboard_layout::Mapping, esc), offsetof(keyboard_layout::Mapping, run),
    offsetof(keyboard_layout::Mapping, cx), offsetof(keyboard_layout::Mapping, k),
    offsetof(keyboard_layout::Mapping, alpha), offsetof(keyboard_layout::Mapping, user),
    offsetof(keyboard_layout::Mapping, pp), offsetof(keyboard_layout::Mapping, bp),
    offsetof(keyboard_layout::Mapping, x_to_p), offsetof(keyboard_layout::Mapping, p_to_x),
    offsetof(keyboard_layout::Mapping, ret), 0, 0,
    offsetof(keyboard_layout::Mapping, bx), offsetof(keyboard_layout::Mapping, xy),
    offsetof(keyboard_layout::Mapping, power), offsetof(keyboard_layout::Mapping, neg),
    offsetof(keyboard_layout::Mapping, degree), offsetof(keyboard_layout::Mapping, grade),
    offsetof(keyboard_layout::Mapping, radian), offsetof(keyboard_layout::Mapping, save),
    offsetof(keyboard_layout::Mapping, load)
  };
  static_assert(sizeof(fields) == COUNT - 10U, "complete M61 key table");
  return reinterpret_cast<const u8*>(&keys)[fields[code - 10U]];
}

inline i32 logical_key(const keyboard_layout::Mapping& keys, i32 scan) {
  if(scan < 0 || scan >= 40) return -1;
  for(u8 code = 0; code < COUNT; ++code)
    if(valid(code) && scan_code(keys, code) == scan) return code;
  return -1;
}
} // namespace m61_keys
#endif
