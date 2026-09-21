#include "ui_text_renderer.hpp"

#if MK61_PROPORTIONAL_UI_FONTS

#include "builtin_font.hpp"
#include "display_symbols.hpp"
#include "fmk_font.hpp"
#include "mk8_codec.hpp"

#include <string.h>

namespace ui_text_renderer {
namespace {

static constexpr i16 UI_MARGIN = 2;
static constexpr i16 UI_GUTTER = 12;
static constexpr u8 CUSTOM_GLYPHS = 8;

struct LineMetrics {
  u8 height;
  u8 ascent;
  u8 line_gap;
  u8 first_top;
};

struct ResolvedGlyph {
  font_glyph::Glyph glyph;
  u8 bitmap[fmk::MAX_BITMAP_SIZE];
};

bool legacyToken(u16 value) {
  return value >= display_symbol::uc1609::GE &&
         value <= display_symbol::uc1609::CYR_CHE;
}

bool privateM8Symbol(u16 codepoint) {
  u8 byte = 0;
  return mk8::from_codepoint(codepoint, byte) &&
      byte >= mk8::BYTE_LEFT_ARROW && byte <= mk8::BYTE_RETURN_ARROW;
}

LineMetrics lineMetrics(const Style& style, u8 rows) {
  if(!style.font_enabled) return {8U, 8U, 8U, 5U};

  u8 height = 0;
  const u8 ascent = ui_font::metrics(style.face).ascent;
  u8 line_gap = 0;
  if(style.external != NULL) {
    const prepared_font::Metrics& metrics = style.external->metrics();
    height = metrics.height;
    line_gap = metrics.line_gap;
  } else {
    const ui_font::Metrics metrics = ui_font::metrics(style.face);
    height = metrics.height;
    line_gap = metrics.line_gap;
  }
  const u16 occupied = (u16) rows * height +
      (rows > 0 ? (u16) (rows - 1U) * line_gap : 0U);
  const u8 first_top = occupied < 64U
      ? (u8) ((64U - occupied) / 2U) : 0U;
  return {height, ascent, line_gap, first_top};
}

bool fixedGlyph(const Style& style, u16 value, bool custom, bool pixels,
                ResolvedGlyph& out) {
  builtin_font::Raster raster = {};
  if(custom) {
    const u8 slot = (u8) value;
    if(style.custom_glyphs != NULL && style.custom_valid != NULL &&
       slot < CUSTOM_GLYPHS && style.custom_valid[slot]) {
      raster.width = 5;
      raster.height = 8;
      if(pixels) {
        for(u8 y = 0; y < 8; ++y) {
          for(u8 x = 0; x < 5; ++x) {
            if((style.custom_glyphs[slot][y] &
                ((u8) 1U << (4U - x))) != 0) {
              raster.data[y] |= (u8) (0x80U >> x);
            }
          }
        }
      }
    } else {
      value = '?';
      custom = false;
    }
  }
  if(!custom) {
    raster.width = 5;
    raster.height = 8;
    if(pixels &&
       !builtin_font::decode(builtin_font::FaceId::FONT_5X8,
                             value, raster) &&
       (value == '?' ||
        !builtin_font::decode(builtin_font::FaceId::FONT_5X8,
                              '?', raster))) return false;
  }
  if(pixels) memcpy(out.bitmap, raster.data, sizeof(out.bitmap));
  out.glyph = {pixels ? out.bitmap : NULL, raster.width, raster.height,
               0, 8, 6, font_glyph::BitmapLayout::ROW_MSB, false};
  return true;
}

bool externalGlyph(const Style& style, const prepared_font::Glyph& source,
                   bool fallback, bool pixels, ResolvedGlyph& out) {
  if(pixels &&
     !style.external->decode(source, out.bitmap, sizeof(out.bitmap))) {
    return false;
  }
  out.glyph = {pixels ? out.bitmap : NULL, source.width, source.height,
               0, (i8) ui_font::metrics(style.face).ascent, source.advance,
               font_glyph::BitmapLayout::ROW_MSB, fallback};
  return true;
}

bool resolveGlyph(const Style& style, u16 value, bool custom, bool pixels,
                  ResolvedGlyph& out) {
  memset(&out, 0, sizeof(out));
  if(custom || !style.font_enabled) {
    return fixedGlyph(style, value, custom, pixels, out);
  }

  const u16 unicode = display_symbol::uc1609::unicodeCodepoint(value);
  if(style.external != NULL) {
    prepared_font::Glyph source = {};
    if(prepared_font::glyphForCodepoint(*style.external, unicode, source)) {
      return externalGlyph(style, source, false, pixels, out) ||
          fixedGlyph(style, '?', false, pixels, out);
    }
    if(legacyToken(value)) {
      return fixedGlyph(style, value, false, pixels, out);
    }
    if(privateM8Symbol(unicode)) {
      return fixedGlyph(style, unicode, false, pixels, out);
    }
    return (style.external->glyph('?', source) &&
            externalGlyph(style, source, true, pixels, out)) ||
        fixedGlyph(style, '?', false, pixels, out);
  }

  // A private M8 sign must not turn into '?' or an ASCII approximation when
  // the proportional atlas has no exact raster for it.
  const ui_font::Glyph glyph = ui_font::glyph(style.face, unicode);
  if(glyph.fallback && privateM8Symbol(unicode)) {
    return fixedGlyph(style, unicode, false, pixels, out);
  }
  // Legacy private tokens with resident 5x8 art keep that art. Every other
  // missing character uses the selected proportional face's '?' fallback.
  if(glyph.fallback &&
     builtin_font::rows5x8(value) != NULL) {
    return fixedGlyph(style, value, false, pixels, out);
  }
  out.glyph = glyph;
  return true;
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

u8 glyphAdvance(const Style& style, u16 value, bool custom) {
  ResolvedGlyph resolved = {};
  return resolveGlyph(style, value, custom, false, resolved)
      ? resolved.glyph.advance : 6U;
}

void renderPage(const text_screen::Grid& grid, const Style& style,
                u8 page, u8 first_col, u8 count, u8* output) {
  if(output == NULL || page >= 8U || count == 0 || first_col >= 16U ||
     count > 16U - first_col) return;

  const i16 run_left = (i16) first_col * CELL_WIDTH;
  const i16 run_width = (i16) count * CELL_WIDTH;
  const i16 page_y = (i16) page * PAGE_HEIGHT;
  memset(output, 0, (usize) run_width);

  const LineMetrics metrics = lineMetrics(style, grid.rows());

  for(u8 row = 0; row < grid.rows(); ++row) {
    const i16 text_top = metrics.first_top +
        (i16) row * (metrics.height + metrics.line_gap);
    if(text_top >= page_y + PAGE_HEIGHT ||
       text_top + metrics.height <= page_y) continue;
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
      ResolvedGlyph resolved = {};
      if(!resolveGlyph(style, value, custom, true, resolved)) continue;
      const font_glyph::Glyph& glyph = resolved.glyph;
      const u8 glyph_advance = gutter && col == 0 ? UI_GUTTER
          : glyph.advance;
      const i16 left = pen + glyph.bearing_x;
      const i16 glyph_top = text_top + metrics.ascent - glyph.bearing_y;

      for(u8 y = 0; y < glyph.height; ++y) {
        const i16 py = glyph_top + y;
        if(py < page_y || py >= page_y + PAGE_HEIGHT) continue;
        for(u8 x = 0; x < glyph.width && left + x < right; ++x) {
          if(font_glyph::pixel(glyph, x, y)) {
            setPixel(output, run_left, run_width, left + x, page_y, py);
          }
        }
      }

      if(row == style.cursor_y && col == style.cursor_x &&
         (style.cursor_underline || style.cursor_block)) {
        const i16 cursor_width = glyph_advance > 1U
            ? glyph_advance - 1U : 1U;
        if(style.cursor_block) {
          for(i16 y = 0; y < metrics.height; ++y) {
            for(i16 x = 0; x < cursor_width && pen + x < right; ++x) {
              invertPixel(output, run_left, run_width,
                          pen + x, page_y, text_top + y);
            }
          }
        } else {
          for(i16 x = 0; x < cursor_width && pen + x < right; ++x) {
            setPixel(output, run_left, run_width, pen + x, page_y,
                     text_top + metrics.height - 1U);
          }
        }
      }
      pen += glyph_advance;
    }
  }
}

} // namespace ui_text_renderer

#endif
