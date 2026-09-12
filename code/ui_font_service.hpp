#ifndef MK61_UI_FONT_SERVICE_HPP
#define MK61_UI_FONT_SERVICE_HPP

#include "loadable_app_services.h"
#include "ui_font.hpp"
#include <string.h>

namespace ui_font_service {

static_assert(sizeof(mk61_service_ui_glyph) == 40, "UI glyph wire layout");
static_assert(sizeof(mk61_service_ui_font_info) == 6, "UI font wire layout");

inline bool valid_choice(uint8_t family, uint8_t size) {
  return (family == 1 || family == 2) &&
         (size == 12 || size == 14 || size == 16);
}

inline ui_font::Face face(uint8_t family, uint8_t size) {
  return {family == 2 ? ui_font::Family::ROBOTO : ui_font::Family::DEJAVU,
          size == 16 ? ui_font::Size::PX16
                     : size == 14 ? ui_font::Size::PX14 : ui_font::Size::PX12};
}

// Pure, bounded serializer shared by resident dispatch and host contract tests.
// Malformed requests leave their output untouched.
inline uint32_t call(uint8_t family, uint8_t size, uint32_t operation,
                     uint32_t codepoint, uint32_t capacity, void* payload) {
  if(payload == nullptr) return 0;
  if(operation == MK61_UI_FONT_INFO) {
    if(capacity != sizeof(mk61_service_ui_font_info)) return 0;
    auto& out = *static_cast<mk61_service_ui_font_info*>(payload);
    out = {};
    if(valid_choice(family, size)) {
      const auto metrics = ui_font::metrics(face(family, size));
      out = {family, size, metrics.ascent, metrics.descent, metrics.line_gap, 0};
    }
    return 1;
  }
  if(operation != MK61_UI_FONT_GLYPH ||
     capacity != sizeof(mk61_service_ui_glyph)) return 0;
  auto& out = *static_cast<mk61_service_ui_glyph*>(payload);
  if(!valid_choice(out.family, out.size)) return 0;
  const auto value = ui_font::glyph(face(out.family, out.size), codepoint);
  if(value.width > 16 || value.height > 16) return 0;
  out.width = value.width;
  out.height = value.height;
  out.bearing_x = value.bearing_x;
  out.bearing_y = value.bearing_y;
  out.advance = value.advance;
  out.fallback = value.fallback ? 1 : 0;
  memset(out.pixels, 0, sizeof(out.pixels));
  // Canonical row-padded raster matches the existing FMK/builtin renderer.
  // Conversion lives in resident Flash, not in every portable viewer.
  const unsigned stride = (value.width + 7U) / 8U;
  for(uint8_t y = 0; y < value.height; ++y) {
    for(uint8_t x = 0; x < value.width; ++x) {
      if(ui_font::pixel(value, x, y)) out.pixels[y * stride + x / 8U] |= 0x80U >> (x % 8U);
    }
  }
  return 1;
}

} // namespace ui_font_service

#endif
