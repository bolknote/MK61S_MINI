#include "builtin_font.hpp"

#include <assert.h>
#include <stdio.h>

namespace {

static bool has_ink(const builtin_font::Raster& raster) {
  const usize bytes = (usize) ((raster.width + 7U) / 8U) * raster.height;
  for(usize index = 0; index < bytes; index++) {
    if(raster.data[index] != 0) return true;
  }
  return false;
}

static void expect_glyph(builtin_font::FaceId face, u16 codepoint,
                         u8 width, u8 height) {
  builtin_font::Raster raster = {};
  assert(builtin_font::decode(face, codepoint, raster));
  assert(raster.width == width);
  assert(raster.height == height);
  assert(has_ink(raster));
}

} // namespace

int main(void) {
  expect_glyph(builtin_font::FaceId::FONT_3X5, 'A', 3, 5);
  expect_glyph(builtin_font::FaceId::FONT_3X5, 0x041F, 3, 5);
  expect_glyph(builtin_font::FaceId::FONT_5X8, 'A', 5, 8);
  expect_glyph(builtin_font::FaceId::FONT_5X8, 0x041F, 5, 8);
  printf("ws0010_markdown_font_self_test: ok\n");
  return 0;
}
