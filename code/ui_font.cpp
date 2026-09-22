#include "config.h"

#if MK61_PROPORTIONAL_UI_FONTS

#include "ui_font.hpp"

namespace ui_font {
namespace {

struct GlyphRecord {
  uint16_t offset;
  uint8_t width;
  uint8_t height;
  uint8_t bearing_x;
  int8_t bearing_y;
  uint8_t advance;
};

struct FaceData {
  const GlyphRecord* records;
  const uint8_t* bitmap;
  Metrics metrics;
};

#include "ui_font_data.inc"

unsigned faceIndex(Face face) {
  (void) face.family;
  const unsigned size = face.size == Size::PX16 ? 2U
                      : face.size == Size::PX14 ? 1U : 0U;
  return size;
}

int glyphIndex(uint32_t codepoint) {
  // The common ASCII path avoids even binary search.
  if (codepoint >= 0x20U && codepoint <= 0x7EU) {
    return static_cast<int>(codepoint - 0x20U);
  }
  unsigned first = 0;
  unsigned last = NON_ASCII_GLYPH_COUNT;
  while (first < last) {
    const unsigned middle = first + (last - first) / 2;
    if (NON_ASCII_CODEPOINTS[middle] < codepoint) first = middle + 1;
    else last = middle;
  }
  return first < NON_ASCII_GLYPH_COUNT &&
         NON_ASCII_CODEPOINTS[first] == codepoint
    ? static_cast<int>(ASCII_GLYPH_COUNT + first) : -1;
}

} // namespace

Metrics metrics(Face face) {
  return FACES[faceIndex(face)].metrics;
}

bool supports(Face, uint32_t codepoint) {
  return glyphIndex(codepoint) >= 0;
}

Glyph glyph(Face face, uint32_t codepoint) {
  const unsigned selected = faceIndex(face);
  int index = glyphIndex(codepoint);
  bool fallback = index < 0;
  if (index < 0) index = '?' - ' ';
  if (FACES[selected].records[index].offset == MISSING_OFFSET) {
    // The reviewed atlas is complete; keep a safe fallback if it ever isn't.
    index = '?' - ' ';
    fallback = true;
  }
  const GlyphRecord& record = FACES[selected].records[index];
  return {FACES[selected].bitmap + record.offset, record.width, record.height,
          static_cast<int8_t>(record.bearing_x), record.bearing_y,
          record.advance, font_glyph::BitmapLayout::TIGHT_MSB, fallback};
}

} // namespace ui_font

#endif
