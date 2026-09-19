#include "config.h"
#if defined(MK61_DISPLAY_UC1609)
#include "display.hpp"
#if MK61_PROPORTIONAL_UI_FONTS
#include "display_symbols.hpp"
#include "ui_text_renderer.hpp"
#include "utf8_codec.hpp"
#include <string.h>

namespace {
constexpr u8 UI_MARGIN = 2;
constexpr u8 UI_GUTTER = 12;

u16 textLength(const char* text) {
  u16 size = 0;
  if(text) while(size < 0xFFFFU && text[size]) ++size;
  return size;
}

u16 nextCodepoint(const char* text, u16 length, u16& offset) {
  const auto* bytes = (const u8*) text;
  const utf8_codec::Decoded decoded =
      utf8_codec::decode(bytes + offset, (usize) (length - offset));
  if(decoded.size == 0) return '?';
  offset = (u16) (offset + decoded.size);
  return decoded.valid && decoded.codepoint <= 0xFFFFU
      ? (u16) decoded.codepoint : (u16) '?';
}

bool legacyUiToken(u16 codepoint) {
  return codepoint >= display_symbol::uc1609::GE &&
      codepoint <= display_symbol::uc1609::CYR_CHE;
}
}

void MK61Display::setUiFont(u8 family, u8 size) {
  if(family == 2) family = 1; // migrate the retired Roboto setting
  if(family > 3) family = 0;
  if(size != 12 && size != 14 && size != 16) size = 14;
#if MK61_FIXED_CALCULATOR_FACE
  const u8 preserved = ui_font_state & 24U;
#else
  const u8 preserved = ui_font_state & 8U;
#endif
  const u8 size_bits = size == 16 ? 32U : (size == 14 ? 4U : 0U);
  const u8 next = (u8) (preserved | family | size_bits);
  if(next == ui_font_state) return;
  ui_font_state = next;
#if MK61_ENABLE_USB_SCREEN
  if(usbScreenActive() && uiTextContext()) {
    const prepared_font::Face* external = externalUiFont();
    const u8 width = external != NULL ? external->metrics().max_width
        : (uiFontEnabled() ? 10U : 5U);
    usb_surface.setFont(external);
    usb_surface.setTextLayout(
        {uiRows(), width, uiHeight(), uiLineGap()}, uiCols());
    usb_surface.setUiTextStyle(true, uiFontEnabled(), uiFontFace());
    usb_surface.clear();
    usb_surface.flush(millis());
    return;
  }
#endif
  if(uiTextContext()) clear();
}

u8 MK61Display::uiLineGap(void) const {
  if(uiFontFamily() == 3) {
    if(const prepared_font::Face* external = externalUiFont()) {
      return external->metrics().line_gap;
    }
  }
  return uiFontEnabled() ? ui_font::metrics(uiFontFace()).line_gap : 8U;
}

u8 MK61Display::uiHeight(void) const {
  if(uiFontFamily() == 3) {
    if(const prepared_font::Face* external = externalUiFont()) {
      return external->metrics().height;
    }
  }
  return uiFontEnabled() ? ui_font::metrics(uiFontFace()).height : 8U;
}

u8 MK61Display::uiRows(void) const {
  if(!uiFontEnabled()) return 4U;
  const u8 height = uiHeight();
  const u8 line_gap = uiLineGap();
  const u8 pitch = (u8) (height + line_gap);
  const u8 rows = pitch ? (u8) ((lcd_display::PIXEL_HEIGHT + line_gap) / pitch) : 1U;
  return rows ? rows : 1U;
}

u8 MK61Display::uiCols(void) const {
  const u8 capacity_cols = (u8) (text_screen::CELL_CAPACITY / uiRows());
  u8 pixel_cols = text_screen::MAX_COLS;
  if(uiFontFamily() == 3) {
    if(const prepared_font::Face* external = externalUiFont()) {
      const prepared_font::Metrics& metrics = external->metrics();
      // A proportional line has no single character count: printUiLine()
      // measures every glyph in pixels.  COLS is meaningful for BASIC and
      // other cell-oriented clients only when the selected face is mono.
      if(metrics.monospaced && metrics.default_advance != 0) {
        const u8 usable = lcd_display::PIXEL_WIDTH - 2U * UI_MARGIN;
        pixel_cols = (u8) (usable / metrics.default_advance);
        if(pixel_cols == 0) pixel_cols = 1;
      }
    }
  }
  if(pixel_cols > text_screen::MAX_COLS) pixel_cols = text_screen::MAX_COLS;
  return capacity_cols < pixel_cols ? capacity_cols : pixel_cols;
}

u8 MK61Display::uiTop(void) const {
  if(!uiFontEnabled()) return 1U;
  const u8 height = uiHeight();
  const u8 line_gap = uiLineGap();
  const u8 rows = uiRows();
  const u16 occupied = (u16) rows * height +
      (u16) (rows - 1U) * line_gap;
  return occupied < lcd_display::PIXEL_HEIGHT
      ? (u8) ((lcd_display::PIXEL_HEIGHT - occupied) / 2U) : 0U;
}

void MK61Display::beginUiText(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usbScreenActive()) {
    const bool was_context = uiTextContext();
    ui_font_state |= 8U;
#if MK61_FIXED_CALCULATOR_FACE
    // USB Screen has its own calculator-face renderer.  Merely changing the
    // text geometry does not disable that renderer, so subsequent writes can
    // update the hidden text grid while every transmitted frame still shows
    // the old calculator face.  Entering UI text is the same mode boundary as
    // the physical clear() path below: discard the calculator presentation
    // before the menu or a runtime FMK starts drawing.
    ui_font_state &= (u8) ~16U;
#endif
    const prepared_font::Face* external = externalUiFont();
    const u8 width = external != NULL ? external->metrics().max_width
        : (uiFontEnabled() ? 10U : 5U);
    usb_surface.setFont(external);
    usb_surface.setTextLayout(
        {uiRows(), width, uiHeight(), uiLineGap()}, uiCols());
    usb_surface.setUiTextStyle(true, uiFontEnabled(), uiFontFace());
    if(!was_context) usb_surface.clear();
    usb_surface.flush(millis());
    return;
  }
#endif
  const bool was_active = uiTextActive();
  ui_font_state |= 8U;
  if(was_active != uiTextActive() ||
     (uiTextActive() &&
      (grid.rows() != uiRows() || grid.cols() != uiCols()))) clear();
}

void MK61Display::endUiText(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usbScreenActive()) {
    const bool was_context = uiTextContext();
    ui_font_state &= (u8) ~8U;
    usb_surface.setUiTextStyle(false, false, uiFontFace());
    usb_surface.setFont(selectedFont());
    usb_surface.setTextLayout(
        {active_profile.rows, active_profile.glyph_width,
         active_profile.glyph_height, active_profile.line_gap},
        lcd_display::COLS);
    if(was_context) usb_surface.clear();
    usb_surface.flush(millis());
    return;
  }
#endif
  const bool was_active = uiTextActive();
  ui_font_state &= (u8) ~8U;
  if(was_active != uiTextActive()) clear();
}
#endif

#if MK61_FIXED_CALCULATOR_FACE
void MK61Display::beginCalculatorFace(void) {
  if(uiTextContext()) endUiText();
  if(calculatorFaceActive()) {
#if MK61_ENABLE_USB_SCREEN
    if(usbScreenActive()) usb_surface.beginCalculatorFace();
#endif
    return;
  }
  ui_font_state |= 16U;
  cursor_underline = false;
  cursor_blink = false;
  cursor_blink_phase = false;
  cursor_next_blink_ms = 0;
#if MK61_ENABLE_USB_SCREEN
  if(usbScreenActive()) {
    usb_surface.beginCalculatorFace();
    usb_surface.flush(millis());
    return;
  }
#endif
  markScreenDirty();
}
#endif

#if MK61_PROPORTIONAL_UI_FONTS
u8 MK61Display::uiAdvance(u16 codepoint, bool custom) const {
  if(custom) return 6;
  if(!uiFontEnabled()) return 6;
  const u16 unicode = display_symbol::uc1609::unicodeCodepoint(codepoint);
  if(uiFontFamily() == 3) {
    if(const prepared_font::Face* external = externalUiFont()) {
      prepared_font::Glyph glyph;
      if(external->glyph(unicode, glyph)) return glyph.advance;
      if(legacyUiToken(codepoint)) return 6;
      if(external->glyph('?', glyph)) return glyph.advance;
      return 6;
    }
  }
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
  if(!uiTextActive()) return;
#if MK61_ENABLE_USB_SCREEN
  if(usbScreenActive()) {
    if(row >= usb_surface.rows()) return;
    MK61DisplayUpdate update(*this);
    const u8 cols = usb_surface.cols();
    if(cols == 0) return;
    usb_surface.setUiLineDecorations(row, marker != 0, trailing != 0);
    usb_surface.setCursor(0, row);
    for(u8 col = 0; col < cols; ++col) usb_surface.writeCodepoint(' ');
    u8 col = marker ? 1U : 0U;
    if(marker) {
      usb_surface.setCursor(0, row);
      usb_surface.writeCodepoint((u8) marker);
    }
    const u8 end_col = trailing ? cols - 1U : cols;
    const u16 width = lcd_display::PIXEL_WIDTH - 2U*UI_MARGIN -
        (marker ? UI_GUTTER : 0U) - (trailing ? UI_GUTTER : 0U);
    u16 length = textLength(text);
    while(length && text[length - 1U] == ' ') --length;
    u16 offset = 0;
    u16 used = 0;
    bool clipped = false;
    usb_surface.setCursor(col, row);
    while(offset < length && col < end_col) {
      const u16 cp = nextCodepoint(text, length, offset);
      const u8 advance = uiAdvance(cp, false);
      if(used + advance > width) { clipped = true; break; }
      usb_surface.writeCodepoint(cp);
      used = (u16) (used + advance);
      ++col;
    }
    if(clipped || offset < length) {
      const u8 advance = uiAdvance(0x2026, false);
      const u8 first = marker ? 1U : 0U;
      while(col > first && (col >= end_col || used + advance > width)) {
        --col;
        u16 previous = ' ';
        bool custom = false;
        (void) usb_surface.readCell(col, row, previous, custom);
        used = (u16) (used - uiAdvance(previous, custom));
        usb_surface.setCursor(col, row);
        usb_surface.writeCodepoint(' ');
      }
      usb_surface.setCursor(col, row);
      usb_surface.writeCodepoint(0x2026);
    }
    if(trailing) {
      usb_surface.setCursor(cols - 1U, row);
      usb_surface.writeCodepoint(trailing);
    }
    usb_surface.setCursor(0, row);
    return;
  }
#endif
  if(row >= grid.rows()) return;
  MK61DisplayUpdate update(*this);
  const u8 cols = grid.cols();
  const u16 row_bit = (u16) (1U << row);
  if(marker) ui_row_gutters |= row_bit;
  else ui_row_gutters &= (u16) ~row_bit;
  if(trailing) ui_row_tails |= row_bit;
  else ui_row_tails &= (u16) ~row_bit;
  // One bounded text grid is shared by all graphical text modes. Narrow
  // runtime faces may use the complete 40x10 grid without another cache.
  grid.setCursor(0, row);
  for(u8 col = 0; col < cols; ++col) grid.writeCodepoint(' ');
  u8 col = marker ? 1U : 0U;
  if(marker) {
    grid.setCursor(0, row);
    grid.writeCodepoint((u8) marker);
  }
  const u8 end_col = trailing ? cols - 1U : cols;
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
    grid.setCursor(cols - 1U, row);
    grid.writeCodepoint(trailing);
  }
  grid.setCursor(0, row);
  // Gutters can change without changing the token array; invalidate the row.
  grid.markCell(0, row);
  dirty = true;
}

void MK61Display::renderUiPage(u8 page, u8 first_col, u8 count) {
  const u8 run_width = count * lcd_display::CELL_WIDTH;
  const i16 page_y = page * RENDER_PAGE_HEIGHT;
  const u8 saved_width = render_width;
  render_width = run_width;
  const prepared_font::Face* const external = uiFontFamily() == 3
      ? externalUiFont() : NULL;
  const ui_text_renderer::Style style = {
    uiFontEnabled(), uiFontFace(), external,
    custom_glyphs, custom_valid, ui_row_gutters, ui_row_tails,
    grid.cursorX(), grid.cursorY(), cursor_underline,
    cursor_blink && cursor_blink_phase
  };
  ui_text_renderer::renderPage(
      grid, style, page, first_col, count, render_buffer);
  drawTopRightOverlay(first_col, count, (u8) page_y);
  lcd.LCDBuffer((u8) (first_col * lcd_display::CELL_WIDTH),
                (u8) page_y, run_width, RENDER_PAGE_HEIGHT, render_buffer);
  render_width = saved_width;
}
#endif
#endif
