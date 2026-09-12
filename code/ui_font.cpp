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
  unsigned first = 95;
  unsigned last = GLYPH_COUNT;
  while (first < last) {
    const unsigned middle = first + (last - first) / 2;
    if (CODEPOINTS[middle] < codepoint) first = middle + 1;
    else last = middle;
  }
  return first < GLYPH_COUNT && CODEPOINTS[first] == codepoint
    ? static_cast<int>(first) : -1;
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
    // Ark deliberately omits ≤/≥. Preserve their direction with the matching
    // ASCII comparison sign instead of carrying a second font for two glyphs.
    index = codepoint == 0x2264U ? '<' - ' '
          : codepoint == 0x2265U ? '>' - ' ' : '?' - ' ';
    fallback = true;
  }
  const GlyphRecord& record = FACES[selected].records[index];
  return {FACES[selected].bitmap + record.offset, record.width, record.height,
          record.bearing_x, record.bearing_y, record.advance, fallback};
}

bool pixel(const Glyph& value, uint8_t x, uint8_t y) {
  if (value.bitmap == nullptr || x >= value.width || y >= value.height) {
    return false;
  }
  const unsigned bit = static_cast<unsigned>(y) * value.width + x;
  return (value.bitmap[bit / 8U] & (0x80U >> (bit % 8U))) != 0;
}

} // namespace ui_font

#endif
