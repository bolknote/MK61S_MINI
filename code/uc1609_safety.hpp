#ifndef UC1609_SAFETY_HPP
#define UC1609_SAFETY_HPP

#include "rust_types.h"

namespace uc1609_safety {

inline bool valid_dimensions(u16 width, u16 height, u16 panel_width, u16 panel_height) {
  return width != 0 && height != 0 &&
    width <= panel_width && height <= panel_height &&
    (height % 8) == 0;
}

inline bool intersects_panel(i16 x, i16 y, u16 width, u16 height, u16 panel_width, u16 panel_height) {
  if(!valid_dimensions(width, height, panel_width, panel_height)) return false;
  const i32 right = (i32) x + width;
  const i32 bottom = (i32) y + height;
  return x < (i32) panel_width && y < (i32) panel_height && right > 0 && bottom > 0;
}

inline usize byte_count(u16 width, u16 height) {
  return (usize) width * (height / 8);
}

inline bool pixel_offset(u16 width, u16 height, i16 x, i16 y, usize& out) {
  if(width == 0 || height == 0 || (height % 8) != 0 || x < 0 || y < 0 ||
     x >= (i32) width || y >= (i32) height) return false;
  const usize offset = (usize) width * ((u16) y / 8) + (u16) x;
  if(offset >= byte_count(width, height)) return false;
  out = offset;
  return true;
}

} // namespace uc1609_safety

#endif
