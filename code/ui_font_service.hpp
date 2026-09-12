#ifndef MK61_UI_FONT_SERVICE_HPP
#define MK61_UI_FONT_SERVICE_HPP

#include "loadable_app_services.h"
#include "fmk_font.hpp"
#include "ui_font.hpp"
#include <string.h>

namespace ui_font_service {

static_assert(sizeof(mk61_service_ui_glyph) == 40, "UI glyph wire layout");
static_assert(sizeof(mk61_service_ui_font_info) == 6, "UI font wire layout");

inline bool valid_external(const fmk::Face* external, uint8_t size) {
  return external != nullptr && external->valid() &&
      external->metrics().height == size && size <= 16 &&
      external->metrics().line_gap <= 4;
}

inline bool valid_choice(uint8_t family, uint8_t size,
                         const fmk::Face* external = nullptr) {
  return (size == 12 || size == 14 || size == 16) &&
      ((family == 1 || family == 2) ||
       (family == 3 && valid_external(external, size)));
}

inline ui_font::Face face(uint8_t family, uint8_t size) {
  (void) family; // family 2 remains a wire-compatible alias for old APPs
  return {ui_font::Family::PIXEL,
          size == 16 ? ui_font::Size::PX16
                     : size == 14 ? ui_font::Size::PX14 : ui_font::Size::PX12};
}

// Pure, bounded serializer shared by resident dispatch and host contract tests.
// Malformed requests leave their output untouched.
inline uint32_t call(uint8_t family, uint8_t size, uint32_t operation,
                     uint32_t codepoint, uint32_t capacity, void* payload,
                     const fmk::Face* external = nullptr) {
  if(payload == nullptr) return 0;
  if(operation == MK61_UI_FONT_INFO) {
    if(capacity != sizeof(mk61_service_ui_font_info)) return 0;
    auto& out = *static_cast<mk61_service_ui_font_info*>(payload);
    out = {};
    if(family == 3 && valid_choice(family, size, external)) {
      const auto& metrics = external->metrics();
      out = {family, size, metrics.height, 0,
             metrics.line_gap, metrics.height};
    } else if(valid_choice(family, size)) {
      const auto metrics = ui_font::metrics(face(family, size));
      out = {family, size, metrics.ascent, metrics.descent,
             metrics.line_gap, metrics.height};
    }
    return 1;
  }
  if(operation != MK61_UI_FONT_GLYPH ||
     capacity != sizeof(mk61_service_ui_glyph)) return 0;
  auto& out = *static_cast<mk61_service_ui_glyph*>(payload);
  if(!valid_choice(out.family, out.size, external)) return 0;
  if(out.family == 3) {
    fmk::Glyph glyph = {};
    bool fallback = false;
    if(codepoint > 0xFFFFU ||
       !external->glyph(static_cast<uint16_t>(codepoint), glyph)) {
      fallback = true;
      if(!external->glyph('?', glyph)) return 0;
    }
    if(glyph.width == 0 || glyph.width > 16 || glyph.height == 0 ||
       glyph.height > 16 || glyph.advance == 0 || glyph.advance > 16) {
      return 0;
    }
    const uint8_t requested_family = out.family;
    const uint8_t requested_size = out.size;
    out = {};
    out.family = requested_family;
    out.size = requested_size;
    out.width = glyph.width;
    out.height = glyph.height;
    out.bearing_x = 0;
    out.bearing_y = static_cast<int8_t>(glyph.height);
    out.advance = glyph.advance;
    out.fallback = fallback ? 1 : 0;
    return external->decode(glyph, out.pixels, sizeof(out.pixels)) ? 1 : 0;
  }
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
