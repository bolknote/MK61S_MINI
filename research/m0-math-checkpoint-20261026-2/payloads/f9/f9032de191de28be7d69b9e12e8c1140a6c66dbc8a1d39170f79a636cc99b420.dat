#ifndef MK61_FONT_GLYPH_HPP
#define MK61_FONT_GLYPH_HPP

#include "rust_types.h"

// One renderer-facing glyph description for resident fixed faces, built-in
// proportional faces and prepared FMK faces.  Monospacing is a face metric
// (equal advances), not a different kind of drawable object.
namespace font_glyph {

enum class BitmapLayout : u8 {
  // Every raster row starts at a byte boundary.  PFK2 and decoded resident
  // 3x5/5x8 glyphs use this layout.
  ROW_MSB,
  // Rows follow each other bit-for-bit.  The compiled UI atlases use this
  // denser layout so narrow glyphs do not pay for padding on every row.
  TIGHT_MSB,
};

struct Glyph {
  const u8* bitmap;
  u8 width;
  u8 height;
  i8 bearing_x;
  i8 bearing_y;
  u8 advance;
  BitmapLayout layout;
  bool fallback;
};

inline bool pixel(const Glyph& glyph, u8 x, u8 y) {
  if(glyph.bitmap == nullptr || x >= glyph.width || y >= glyph.height) {
    return false;
  }
  usize bit = 0;
  if(glyph.layout == BitmapLayout::TIGHT_MSB) {
    bit = (usize) y * glyph.width + x;
  } else {
    bit = ((usize) y * ((glyph.width + 7U) / 8U) * 8U) + x;
  }
  return (glyph.bitmap[bit / 8U] & (0x80U >> (bit & 7U))) != 0;
}

} // namespace font_glyph

#endif
