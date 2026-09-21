#ifndef MK61_UI_FONT_HPP
#define MK61_UI_FONT_HPP

#include "font_glyph.hpp"

#include <stdint.h>

// Optional UC1609 UI faces. The calculator face remains independent.
// Storage and implementation are compiled only with
// MK61_PROPORTIONAL_UI_FONTS=1; official UC1609 builds enable it on both MCUs.
namespace ui_font {

enum class Family : uint8_t { PIXEL };
enum class Size : uint8_t { PX12, PX14, PX16 };

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

using Glyph = font_glyph::Glyph;

// Invalid enum values normalize to Ark Pixel / 12 pixels.
Metrics metrics(Face face);
// The reviewed repertoire includes ASCII, Russian, UI symbols and explicit
// ASCII-shaped fallbacks for ≤/≥. False means glyph() substitutes '?'.
bool supports(Face face, uint32_t codepoint);
Glyph glyph(Face face, uint32_t codepoint);

// Coordinates are relative to the ink bitmap, not the line box. Layout draws
// at (pen_x + bearing_x, baseline_y - bearing_y), then advances by advance.
// The generated advance guarantees at least one blank column between glyphs.
// Read pixels with font_glyph::pixel(); fixed and proportional faces share it.

} // namespace ui_font

#endif
