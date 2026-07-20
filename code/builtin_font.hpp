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

} // пространство имён builtin_font

#endif
