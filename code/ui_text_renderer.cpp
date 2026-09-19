#include "ui_text_renderer.hpp"

#if MK61_PROPORTIONAL_UI_FONTS

#include "builtin_font.hpp"
#include "display_symbols.hpp"
#include "fmk_font.hpp"

#include <string.h>

namespace ui_text_renderer {
namespace {

static constexpr i16 UI_MARGIN = 2;
static constexpr i16 UI_GUTTER = 12;
static constexpr u8 CUSTOM_GLYPHS = 8;

bool legacyToken(u16 value) {
  return value >= display_symbol::uc1609::GE &&
         value <= display_symbol::uc1609::CYR_CHE;
}

u8 advance(const Style& style, u16 value, bool custom) {
  if(custom || !style.font_enabled) return 6U;
  const u16 unicode = display_symbol::uc1609::unicodeCodepoint(value);
  if(style.external != NULL) {
    prepared_font::Glyph glyph;
    if(style.external->glyph(unicode, glyph)) return glyph.advance;
    if(legacyToken(value)) return 6U;
    if(style.external->glyph('?', glyph)) return glyph.advance;
    return 6U;
  }
  if(ui_font::supports(style.face, unicode)) {
    return ui_font::glyph(style.face, unicode).advance;
  }
  if(builtin_font::rows5x8(value) != NULL) return 6U;
  return ui_font::glyph(style.face, '?').advance;
}

bool fallbackRaster(const Style& style, u16 value, bool custom,
                    builtin_font::Raster& raster) {
  memset(raster.data, 0, sizeof(raster.data));
  if(custom) {
    const u8 slot = (u8) value;
    if(style.custom_glyphs != NULL && style.custom_valid != NULL &&
       slot < CUSTOM_GLYPHS && style.custom_valid[slot]) {
      raster.width = 5;
      raster.height = 8;
      for(u8 y = 0; y < 8; ++y) {
        for(u8 x = 0; x < 5; ++x) {
          if((style.custom_glyphs[slot][y] &
              ((u8) 1U << (4U - x))) != 0) {
            raster.data[y] |= (u8) (0x80U >> x);
          }
        }
      }
      return true;
    }
    value = '?';
  }
  if(builtin_font::decode(builtin_font::FaceId::FONT_5X8,
                          value, raster)) return true;
  return value != '?' && builtin_font::decode(
      builtin_font::FaceId::FONT_5X8, '?', raster);
}

void setPixel(u8* output, i16 run_left, i16 run_width,
              i16 x, i16 page_y, i16 y) {
  if(x < run_left || x >= run_left + run_width ||
     y < page_y || y >= page_y + PAGE_HEIGHT) return;
  output[x - run_left] |= (u8) 1U << (y - page_y);
}

void invertPixel(u8* output, i16 run_left, i16 run_width,
                 i16 x, i16 page_y, i16 y) {
  if(x < run_left || x >= run_left + run_width ||
     y < page_y || y >= page_y + PAGE_HEIGHT) return;
  output[x - run_left] ^= (u8) 1U << (y - page_y);
}

} // namespace

void renderPage(const text_screen::Grid& grid, const Style& style,
                u8 page, u8 first_col, u8 count, u8* output) {
  if(output == NULL || page >= 8U || count == 0 || first_col >= 16U ||
     count > 16U - first_col) return;

  const i16 run_left = (i16) first_col * CELL_WIDTH;
  const i16 run_width = (i16) count * CELL_WIDTH;
  const i16 page_y = (i16) page * PAGE_HEIGHT;
  memset(output, 0, (usize) run_width);

  const ui_font::Metrics builtin_metrics = ui_font::metrics(style.face);
  const u8 face_height = style.external != NULL
      ? style.external->metrics().height : builtin_metrics.height;
  const u8 line_gap = style.external != NULL
      ? style.external->metrics().line_gap
      : (style.font_enabled ? builtin_metrics.line_gap : 8U);
  const bool mono = !style.font_enabled;
  const u8 text_height = mono ? 8U : face_height;
  const u16 occupied = (u16) grid.rows() * text_height +
      (grid.rows() > 0 ? (u16) (grid.rows() - 1U) * line_gap : 0U);
  const u8 first_top = mono ? 1U
      : (occupied < 64U ? (u8) ((64U - occupied) / 2U) : 0U);

  for(u8 row = 0; row < grid.rows(); ++row) {
    const i16 top = first_top +
        (i16) row * (text_height + line_gap);
    const i16 mono_top = top + 4;
    const i16 text_top = mono ? mono_top : top;
    if(text_top >= page_y + PAGE_HEIGHT ||
       text_top + text_height <= page_y) continue;
    const bool gutter = (style.row_gutters & ((u16) 1U << row)) != 0;
    const bool tail = (style.row_tails & ((u16) 1U << row)) != 0;
    i16 pen = UI_MARGIN;

    for(u8 col = 0; col < grid.cols(); ++col) {
      const bool tail_cell = tail && col == grid.cols() - 1U;
      if(tail_cell) pen = SCREEN_WIDTH - UI_MARGIN - UI_GUTTER;
      const i16 right = tail && !tail_cell
          ? SCREEN_WIDTH - UI_MARGIN - UI_GUTTER
          : SCREEN_WIDTH - UI_MARGIN;
      const u16 value = grid.cell(col, row);
      const bool custom = grid.cellIsCustom(col, row);
      const u16 unicode = display_symbol::uc1609::unicodeCodepoint(value);

      prepared_font::Glyph external_glyph = {};
      u8 external_bitmap[fmk::MAX_BITMAP_SIZE] = {};
      bool use_external = style.external != NULL && !custom &&
          style.external->glyph(unicode, external_glyph);
      if(!use_external && style.external != NULL && !custom &&
         !legacyToken(value)) {
        use_external = style.external->glyph('?', external_glyph);
      }
      use_external = use_external && style.external->decode(
          external_glyph, external_bitmap, sizeof(external_bitmap));

      const u8 glyph_advance = gutter && col == 0 ? UI_GUTTER
          : (use_external ? external_glyph.advance
                          : advance(style, value, custom));
      const bool proportional = style.external == NULL && !mono && !custom &&
          (ui_font::supports(style.face, unicode) ||
           builtin_font::rows5x8(value) == NULL);
      const ui_font::Glyph glyph = ui_font::glyph(style.face, unicode);
      builtin_font::Raster fallback = {};
      if(!proportional && !use_external) {
        (void) fallbackRaster(style, value, custom, fallback);
      }
      const u8 width = use_external ? external_glyph.width
          : (proportional ? glyph.width : fallback.width);
      const u8 height = use_external ? external_glyph.height
          : (proportional ? glyph.height : fallback.height);
      const i16 left = pen + (proportional ? glyph.bearing_x : 0);
      const i16 glyph_top = use_external ? top : (mono ? mono_top
          : top + builtin_metrics.ascent -
              (proportional ? glyph.bearing_y : 8));

      for(u8 y = 0; y < height; ++y) {
        const i16 py = glyph_top + y;
        if(py < page_y || py >= page_y + PAGE_HEIGHT) continue;
        for(u8 x = 0; x < width && left + x < right; ++x) {
          const bool ink = use_external
              ? fmk::bitmapPixel(external_bitmap, width, x, y)
              : (proportional ? ui_font::pixel(glyph, x, y)
                              : fmk::bitmapPixel(fallback.data, width, x, y));
          if(ink) setPixel(output, run_left, run_width,
                           left + x, page_y, py);
        }
      }

      if(row == style.cursor_y && col == style.cursor_x &&
         (style.cursor_underline || style.cursor_block)) {
        const i16 cursor_width = glyph_advance > 1U
            ? glyph_advance - 1U : 1U;
        if(style.cursor_block) {
          for(i16 y = 0; y < text_height; ++y) {
            for(i16 x = 0; x < cursor_width && pen + x < right; ++x) {
              invertPixel(output, run_left, run_width,
                          pen + x, page_y, text_top + y);
            }
          }
        } else {
          for(i16 x = 0; x < cursor_width && pen + x < right; ++x) {
            setPixel(output, run_left, run_width, pen + x, page_y,
                     text_top + text_height - 1U);
          }
        }
      }
      pen += glyph_advance;
    }
  }
}

} // namespace ui_text_renderer

#endif
