#ifndef MK61_UI_FONT_HPP
#define MK61_UI_FONT_HPP

#include <stdint.h>

// Optional UC1609 UI faces. The calculator's cell font remains independent.
// Storage and implementation are compiled only for MK61_DISPLAY_UC1609.
namespace ui_font {

enum class Family : uint8_t { DEJAVU, ROBOTO };
enum class Size : uint8_t { PX12, PX14 };

struct Face {
  Family family;
  Size size;
};

struct Metrics {
  uint8_t height;
  uint8_t ascent;
  uint8_t descent;
  uint8_t line_gap;
  uint8_t ppem;
};

struct Glyph {
  const uint8_t* bitmap;
  uint8_t width;
  uint8_t height;
  uint8_t bearing_x;
  int8_t bearing_y;
  uint8_t advance;
  // True when another face or '?' supplies the requested character.
  bool fallback;
};

// Invalid enum values normalize to DejaVu Sans / 12 pixels.
Metrics metrics(Face face);
// Includes the matching-size DejaVu fallback for missing Roboto arrows.
// False means glyph() substitutes '?'.
bool supports(Face face, uint32_t codepoint);
Glyph glyph(Face face, uint32_t codepoint);

// Coordinates are relative to the ink bitmap, not the line box. Layout draws
// at (pen_x + bearing_x, baseline_y - bearing_y), then advances by advance.
// The generated advance guarantees at least one blank column between glyphs.
// No raster decode buffer, allocation, interpolation, or mutable cache exists.
bool pixel(const Glyph& value, uint8_t x, uint8_t y);

} // namespace ui_font

#endif
