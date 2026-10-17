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
