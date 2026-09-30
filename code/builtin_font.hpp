#ifndef BUILTIN_FONT_HPP
#define BUILTIN_FONT_HPP

#include "fmk_font.hpp"

namespace builtin_font {

enum class FaceId : u8 {
  FONT_5X8,
  FONT_3X5
};

struct Raster {
  u8 width;
  u8 height;
  u8 data[fmk::MAX_BITMAP_SIZE];
};

const u8* rows5x8(u16 codepoint);
FaceId closest(u8 width, u8 height);
bool decode(FaceId face, u16 codepoint, Raster& out);
// Nearest-neighbour 2x enlargement used by the Classic 10x16 UI.  Keeping it
// beside the canonical decoder makes the physical and portable renderers use
// exactly the same pixels as UC_Font_One enlarged by an integer factor of two.
bool scale2x(const Raster& source, Raster& out);

} // пространство имён builtin_font

#endif
