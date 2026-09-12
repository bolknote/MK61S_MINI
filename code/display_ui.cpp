#include "config.h"
#if defined(MK61_DISPLAY_UC1609)
#include "display.hpp"
#include "display_symbols.hpp"
#include "utf8_view.hpp"
#include <string.h>

namespace {
constexpr u8 UI_ROWS = 4;
constexpr u8 UI_COLS = 40;
constexpr u8 UI_MARGIN = 2;
constexpr u8 UI_GUTTER = 12;

u16 textLength(const char* text) {
  u16 size = 0;
  if(text) while(size < 0xFFFFU && text[size]) ++size;
  return size;
}

u16 nextCodepoint(const char* text, u16 length, u16& offset) {
  const auto* bytes = (const u8*) text;
  const u8 count = utf8_view::sequence_length(bytes, length, offset);
  if(count == 0) return '?';
  const u8 first = bytes[offset];
  u16 value = first < 0x80 ? first : '?';
  if(count == 2) value = (u16) (((first & 0x1FU) << 6) | (bytes[offset + 1U] & 0x3FU));
  if(count == 3) value = (u16) (((first & 0x0FU) << 12) |
      ((bytes[offset + 1U] & 0x3FU) << 6) | (bytes[offset + 2U] & 0x3FU));
  offset = (u16) (offset + count);
  return value;
}
}

void MK61Display::setUiFont(u8 family, u8 size) {
  if(family > 2) family = 0;
  const u8 next = (u8) ((ui_font_state & 8U) | family | (size == 12 ? 0U : 4U));
  if(next == ui_font_state) return;
  ui_font_state = next;
  if(uiTextContext() && !usbScreenActive()) clear();
}

void MK61Display::beginUiText(void) {
  const bool was_active = uiTextActive();
  ui_font_state |= 8U;
  if(was_active != uiTextActive() || (uiTextActive() && grid.cols() != UI_COLS)) clear();
}

void MK61Display::endUiText(void) {
  const bool was_active = uiTextActive();
  ui_font_state &= (u8) ~8U;
  if(was_active != uiTextActive()) clear();
}

u8 MK61Display::uiAdvance(u16 codepoint, bool custom) const {
  if(custom) return 6;
  const u16 unicode = display_symbol::uc1609::unicodeCodepoint(codepoint);
  if(ui_font::supports(uiFontFace(), unicode)) return ui_font::glyph(uiFontFace(), unicode).advance;
  // Legacy private tokens (folder, calculator signs) keep their existing art.
  if(builtin_font::rows5x8(codepoint) != nullptr) return 6;
  return ui_font::glyph(uiFontFace(), '?').advance;
}

u16 MK61Display::measureUiText(const char* text) const {
  const u16 length = textLength(text);
  u16 offset = 0;
  u32 width = 0;
  while(offset < length && width < 0xFFFFU) width += uiAdvance(nextCodepoint(text, length, offset), false);
  return width > 0xFFFFU ? 0xFFFFU : (u16) width;
}

void MK61Display::printUiLine(u8 row, const char* text, char marker, u16 trailing) {
  if(!uiTextActive() || row >= UI_ROWS) return;
  MK61DisplayUpdate update(*this);
  const u8 row_bit = (u8) (1U << row);
  if(marker) ui_row_gutters |= row_bit;
  else ui_row_gutters &= (u8) ~row_bit;
  if(trailing) ui_row_tails |= row_bit;
  else ui_row_tails &= (u8) ~row_bit;
  // The same 160-token storage as the calculator grid, not a second cache.
  grid.setCursor(0, row);
  for(u8 col = 0; col < UI_COLS; ++col) grid.writeCodepoint(' ');
  u8 col = marker ? 1U : 0U;
  if(marker) {
    grid.setCursor(0, row);
    grid.writeCodepoint((u8) marker);
  }
  const u8 end_col = trailing ? UI_COLS - 1U : UI_COLS;
  const u16 width = lcd_display::PIXEL_WIDTH - 2U*UI_MARGIN -
      (marker ? UI_GUTTER : 0U) - (trailing ? UI_GUTTER : 0U);
  u16 length = textLength(text);
  while(length && text[length - 1U] == ' ') --length;
  u16 offset = 0;
  u16 used = 0;
  bool clipped = false;
  grid.setCursor(col, row);
  while(offset < length && col < end_col) {
    const u16 cp = nextCodepoint(text, length, offset);
    const u8 advance = uiAdvance(cp, false);
    if(used + advance > width) { clipped = true; break; }
    grid.writeCodepoint(cp);
    used = (u16) (used + advance);
    ++col;
  }
  if(clipped || offset < length) {
    const u8 advance = uiAdvance(0x2026, false);
    const u8 first = marker ? 1U : 0U;
    while(col > first && (col >= end_col || used + advance > width)) {
      --col;
      used = (u16) (used - uiAdvance(grid.cell(col, row), false));
      grid.setCursor(col, row);
      grid.writeCodepoint(' ');
    }
    grid.setCursor(col, row);
    grid.writeCodepoint(0x2026);
  }
  if(trailing) {
    grid.setCursor(UI_COLS - 1U, row);
    grid.writeCodepoint(trailing);
  }
  grid.setCursor(0, row);
  // Gutters can change without changing the token array; invalidate the row.
  grid.markCell(0, row);
  dirty = true;
}

void MK61Display::renderUiPage(u8 page, u8 first_col, u8 count) {
  const u8 run_width = count * lcd_display::CELL_WIDTH;
  const i16 run_left = first_col * lcd_display::CELL_WIDTH;
  const i16 page_y = page * RENDER_PAGE_HEIGHT;
  const u8 saved_width = render_width;
  render_width = run_width;
  memset(render_buffer, 0, run_width);
  const auto face = uiFontFace();
  const auto metrics = ui_font::metrics(face);
  for(u8 row = 0; row < grid.rows(); ++row) {
    const i16 top = rowTop(row);
    if(top >= page_y + RENDER_PAGE_HEIGHT || top + metrics.height <= page_y) continue;
    const bool gutter = (ui_row_gutters & (1U << row)) != 0;
    const bool tail = (ui_row_tails & (1U << row)) != 0;
    i16 pen = UI_MARGIN;
    for(u8 col = 0; col < grid.cols(); ++col) {
      const bool tail_cell = tail && col == UI_COLS - 1U;
      if(tail_cell) pen = lcd_display::PIXEL_WIDTH - UI_MARGIN - UI_GUTTER;
      const i16 right = tail && !tail_cell
          ? lcd_display::PIXEL_WIDTH - UI_MARGIN - UI_GUTTER
          : lcd_display::PIXEL_WIDTH - UI_MARGIN;
      const u16 cp = grid.cell(col, row);
      const bool custom = grid.cellIsCustom(col, row);
      const u8 advance = gutter && col == 0 ? UI_GUTTER : uiAdvance(cp, custom);
      const u16 unicode = display_symbol::uc1609::unicodeCodepoint(cp);
      const bool proportional = !custom &&
          (ui_font::supports(face, unicode) || builtin_font::rows5x8(cp) == nullptr);
      const auto glyph = ui_font::glyph(face, unicode);
      builtin_font::Raster fallback = {};
      if(!proportional) {
        // UI icons do not inherit the user's calculator FMK face/geometry.
        if(custom && cp < CUSTOM_GLYPHS && custom_valid[cp]) {
          resolveToken(cp, true, fallback);
        } else {
          builtin_font::decode(builtin_font::FaceId::FONT_5X8,
                               custom ? (u16) '?' : cp, fallback);
        }
      }
      const u8 width = proportional ? glyph.width : fallback.width;
      const u8 height = proportional ? glyph.height : fallback.height;
      const i16 left = pen + (proportional ? glyph.bearing_x : 0);
      const i16 glyph_top = top + metrics.ascent - (proportional ? glyph.bearing_y : 8);
      for(u8 y = 0; y < height; ++y) {
        const i16 py = glyph_top + y - page_y;
        if(py < 0 || py >= RENDER_PAGE_HEIGHT) continue;
        for(u8 x = 0; x < width; ++x) {
          if(left + x >= right) break;
          if(proportional ? ui_font::pixel(glyph, x, y)
                          : fmk::bitmapPixel(fallback.data, width, x, y)) {
            setRenderPixel(left + x - run_left, py);
          }
        }
      }
      if(row == grid.cursorY() && col == grid.cursorX() && cursorOverlayVisible()) {
        const i16 cursor_width = advance > 1 ? advance - 1U : 1U;
        if(cursor_blink && cursor_blink_phase) {
          // Invert, not erase: the selected character remains recognizable.
          for(i16 y = 0; y < metrics.height; ++y) {
            const i16 py = top + y - page_y;
            if(py < 0 || py >= RENDER_PAGE_HEIGHT) continue;
            for(i16 x = 0; x < cursor_width && pen + x < right; ++x) {
              const i16 px = pen + x - run_left;
              if(px >= 0 && px < run_width) render_buffer[px] ^= (u8) (1U << py);
            }
          }
        } else if(cursor_underline) {
          fillRenderRect(pen - run_left, top + metrics.height - 1U - page_y, cursor_width, 1, true);
        }
      }
      pen += advance;
    }
  }
  drawTopRightOverlay(first_col, count, (u8) page_y);
  lcd.LCDBuffer((u8) run_left, (u8) page_y, run_width, RENDER_PAGE_HEIGHT, render_buffer);
  render_width = saved_width;
}
#endif
