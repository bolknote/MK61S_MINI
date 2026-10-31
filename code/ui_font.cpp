#include "ui_build_config.hpp"

#if MK61_PROPORTIONAL_UI_FONTS

#include "ui_font.hpp"

namespace ui_font {
namespace {

struct FaceData {
  const uint8_t* records;
  const uint8_t* shapes;
  Metrics metrics;
};

// F401 stores only the exceptional codepoints; its 64 Cyrillic glyphs
// already occupy one consecutive range. Keep other targets' lookup unchanged.
#if defined(STM32F401xC) || defined(STM32F401xE) || \
    (!defined(__arm__) && !defined(__thumb__) && defined(MK61_TEST_FONT_CYRILLIC_RANGE))
#define MK61_UI_FONT_CYRILLIC_RANGE 1
#else
#define MK61_UI_FONT_CYRILLIC_RANGE 0
#endif
#include "ui_font_data.inc"

unsigned faceIndex(Face face) {
  (void) face.family;
  const unsigned size = face.size == Size::PX16 ? 2U
                      : face.size == Size::PX14 ? 1U : 0U;
  return size;
}

#if MK61_UI_FONT_CYRILLIC_RANGE
int glyphIndex(uint32_t codepoint) {
  if(codepoint >= 0x20U && codepoint <= 0x7EU)
    return (int)(codepoint - 0x20U);
  if(codepoint >= 0x0410U && codepoint <= 0x044FU)
    return (int)(CYRILLIC_GLYPH_INDEX + codepoint - 0x0410U);
  unsigned first = 0, last = NON_CYRILLIC_GLYPH_COUNT;
  while(first < last) {
    const unsigned middle = first + (last-first)/2;
    if(NON_CYRILLIC_CODEPOINTS[middle] < codepoint) first = middle+1;
    else last = middle;
  }
  return first < NON_CYRILLIC_GLYPH_COUNT && NON_CYRILLIC_CODEPOINTS[first] == codepoint
      ? (int)(ASCII_GLYPH_COUNT + first + (first >= NON_CYRILLIC_PREFIX_COUNT ? 64U : 0U)) : -1;
}

#else
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

#endif

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
  const FaceData& data = FACES[selected];
  const unsigned bit = (unsigned) index * 18U;
  const uint8_t* encoded = data.records + bit / 8U;
  const uint32_t value = ((uint32_t) encoded[0] | ((uint32_t) encoded[1] << 8) |
      ((uint32_t) encoded[2] << 16)) >> (bit & 7U);
  const unsigned offset = value & 0xFFFU;
  const unsigned metric_bit = ((value >> 12) & 0x3FU) * 21U;
  const uint8_t* metric = data.shapes + metric_bit / 8U;
  const uint32_t fields = ((uint32_t) metric[0] | ((uint32_t) metric[1] << 8) |
      ((uint32_t) metric[2] << 16) | ((uint32_t) metric[3] << 24)) >> (metric_bit & 7U);
  const int bearing_y = (int) (((fields >> 11) & 0x1FU) ^ 16U) - 16;
  return {PIXEL_BITMAP + offset,
          static_cast<uint8_t>(fields & 0xFU), static_cast<uint8_t>((fields >> 4) & 0xFU),
          static_cast<int8_t>((fields >> 8) & 7U), static_cast<int8_t>(bearing_y),
          static_cast<uint8_t>((fields >> 16) & 0x1FU),
          font_glyph::BitmapLayout::TIGHT_MSB, fallback};
}

} // namespace ui_font

#endif
