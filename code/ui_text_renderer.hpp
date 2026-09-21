#ifndef MK61_UI_TEXT_RENDERER_HPP
#define MK61_UI_TEXT_RENDERER_HPP

#include "config.h"
#if MK61_PROPORTIONAL_UI_FONTS

#include "prepared_font.hpp"
#include "rust_types.h"
#include "text_screen.hpp"
#include "ui_font.hpp"

// One page renderer is shared by the physical UC1609 and USB Screen.  Both
// targets use the controller's native page format: one byte per x coordinate,
// bit 0..7 for the eight rows in that page.
namespace ui_text_renderer {

static constexpr u8 PAGE_HEIGHT = 8;
static constexpr u8 SCREEN_WIDTH = 192;
static constexpr u8 CELL_WIDTH = 12;

struct Style {
  bool font_enabled;
  ui_font::Face face;
  const prepared_font::Face* external;
  const u8 (*custom_glyphs)[8];
  const bool* custom_valid;
  u16 row_gutters;
  u16 row_tails;
  u8 cursor_x;
  u8 cursor_y;
  bool cursor_underline;
  bool cursor_block;
};

// Measurement and painting deliberately resolve through the same glyph
// source.  This keeps wrapping, ellipsis placement and pixels in agreement
// for fixed, proportional and external faces.
u8 glyphAdvance(const Style& style, u16 value, bool custom = false);

void renderPage(const text_screen::Grid& grid, const Style& style,
                u8 page, u8 first_col, u8 count, u8* output);

} // namespace ui_text_renderer

#endif
#endif
