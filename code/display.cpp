#include "display.hpp"
#include "display_symbols.hpp"
#include "exclusive_buffer.hpp"

#include <string.h>

#if defined(MK61_DISPLAY_LCD1602)

MK61Display::MK61Display(void)
  : lcd(PIN_LCD_RS, PIN_LCD_E, PIN_LCD_DB4, PIN_LCD_DB5, PIN_LCD_DB6, PIN_LCD_DB7) {}

void MK61Display::begin(u8 cols, u8 rows) {
  (void) cols;
  (void) rows;
  lcd.begin(lcd_display::COLS, lcd_display::ROWS);
  lcd.noCursor();
  lcd.noBlink();
}

void MK61Display::clear(void) {
  lcd.noCursor();
  lcd.noBlink();
  lcd.clear();
}

void MK61Display::flush(void) {}
void MK61Display::beginUpdate(void) {}
void MK61Display::endUpdate(void) {}
void MK61Display::setRows(u8) {}
void MK61Display::setTextProfile(lcd_display::TextProfile) {}

lcd_display::TextProfile MK61Display::textProfile(void) const {
  return lcd_display::defaultTextProfileForRows(lcd_display::ROWS);
}

void MK61Display::setCursor(u8 x, u8 y) {
  lcd.setCursor(x < lcd_display::COLS ? x : (u8) (lcd_display::COLS - 1),
                y < lcd_display::ROWS ? y : (u8) (lcd_display::ROWS - 1));
}
void MK61Display::cursorOn(void) { lcd.cursor(); }

void MK61Display::cursorOff(void) {
  lcd.noCursor();
  lcd.noBlink();
}

void MK61Display::blinkOn(void) { lcd.blink(); }
void MK61Display::blinkOff(void) { lcd.noBlink(); }
bool MK61Display::supportsCursor(void) const { return true; }
bool MK61Display::hasHardwareCursor(void) const { return true; }

void MK61Display::createChar(u8 nChar, uint8_t* glyph) {
  if(nChar >= 8 || glyph == NULL) return;
  lcd.createChar(nChar, glyph);
}

void MK61Display::clearCustomChars(void) {}

void MK61Display::writeCodepoint(u16 codepoint) {
  write(codepoint <= 0xFF ? (u8) codepoint : (u8) '?');
}

bool MK61Display::installFont(const u8*, u16) { return false; }
bool MK61Display::setFontPreview(const u8*, u16) { return false; }
void MK61Display::clearFontPreview(void) {}
void MK61Display::useBuiltinFont(void) {}
bool MK61Display::externalFontActive(void) const { return false; }
bool MK61Display::suspendExternalFontForUsb(void) { return true; }
bool MK61Display::showFullscreenBitmap(const u8*, usize) { return false; }

#if ARDUINO >= 100
size_t MK61Display::write(uint8_t value) {
  return lcd.write(value);
}
#else
void MK61Display::write(uint8_t value) {
  lcd.write(value);
}
#endif

#else

static constexpr t_time_ms CURSOR_BLINK_MS = 500;
static_assert(text_screen::COLS == lcd_display::COLS, "text grid width must match display layout");
static_assert(text_screen::MAX_ROWS == lcd_display::MAX_ROWS, "text grid height must match display layout");

static inline bool timeReached(t_time_ms now, t_time_ms target) {
  return (i32) (now - target) >= 0;
}

MK61Display::MK61Display(void)
  : render_buffer{0},
    lcd(lcd_display::PIXEL_WIDTH, lcd_display::PIXEL_HEIGHT, PIN_GLCD_CD, PIN_GLCD_RST, PIN_GLCD_CS),
    render_screen(render_buffer, lcd_display::PIXEL_WIDTH, RENDER_PAGE_HEIGHT, 0, 0),
    grid(),
    custom_glyphs{{0}},
    custom_valid{false},
    active_font(),
    preview_font(),
    active_font_enabled(false),
    external_font_suspended(false),
    preview_font_enabled(false),
    initialized(false),
    screen_dirty(false),
    dirty(false),
    update_depth(0),
    active_profile(lcd_display::defaultTextProfileForRows(lcd_display::DEFAULT_ROWS)),
    preview_saved_profile(active_profile),
    cursor_underline(false),
    cursor_blink(false),
    cursor_blink_phase(false),
    cursor_next_blink_ms(0),
    preview_profile_active(false) {
  grid.reset(active_profile.rows);
}

void MK61Display::begin(u8, u8 rows) {
  const u8 safe_rows = sanitizeRows(rows);
  active_profile = lcd_display::defaultTextProfileForRows(safe_rows);
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  active_profile.rows = safe_rows;
  active_profile = lcd_display::normalizeTextProfile(active_profile);
#endif
  grid.reset(active_profile.rows);
  lcd.LCDbegin(GLCD_UC1609_BIAS, GLCD_UC1609_ADDRESS_SET);
  lcd.ActiveBuffer = &render_screen;
  initialized = true;
  clearPhysicalScreen();
}

void MK61Display::clear(void) {
  clearShadow();
  cursor_underline = false;
  cursor_blink = false;
  cursor_blink_phase = false;
  cursor_next_blink_ms = 0;
  markScreenDirty();
}

void MK61Display::flush(void) {
  if(!initialized) return;
  updateCursorBlink();
  if(!dirty && !screen_dirty && !grid.anyDirty()) return;

  if(screen_dirty) {
    clearPhysicalScreen();
    screen_dirty = false;
  }

  for(u8 row = 0; row < grid.rows(); row++) {
    const uint16_t mask = grid.dirtyMask(row);
    grid.clearDirty(row);

    for(u8 col = 0; col < lcd_display::COLS;) {
      if((mask & ((uint16_t) 1 << col)) == 0) {
        col++;
        continue;
      }

      const u8 first_col = col;
      do {
        col++;
      } while(col < lcd_display::COLS && (mask & ((uint16_t) 1 << col)) != 0);
      renderRun(row, first_col, col - first_col);

      uint16_t run_mask = 0;
      for(u8 run_col = first_col; run_col < col; run_col++) run_mask |= (uint16_t) 1 << run_col;
      grid.clearColumns(run_mask);
    }
  }

  dirty = grid.anyDirty();
}

void MK61Display::beginUpdate(void) {
  update_depth++;
}

void MK61Display::endUpdate(void) {
  if(update_depth > 0) update_depth--;
  if(update_depth == 0 && initialized) flush();
}

void MK61Display::setRows(u8 rows) {
  const u8 safe_rows = sanitizeRows(rows);
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  lcd_display::TextProfile profile = active_profile;
  profile.rows = safe_rows;
  const u8 max_height = lcd_display::PIXEL_HEIGHT / safe_rows;
  if(profile.glyph_height > max_height) profile.glyph_height = max_height;
  profile.line_gap = lcd_display::clamp_u8(profile.line_gap, 0,
    lcd_display::maxLineGap(profile.rows, profile.glyph_height));
  applyTextProfile(profile);
#else
  applyTextProfile(lcd_display::defaultTextProfileForRows(safe_rows));
#endif
}

void MK61Display::applyTextProfile(lcd_display::TextProfile profile, bool exact_geometry) {
  lcd_display::TextProfile next;
  if(exact_geometry) {
    const text_screen::FontGeometry geometry = text_screen::sanitizeFontGeometry({
      profile.rows, profile.glyph_width, profile.glyph_height, profile.line_gap
    });
    next = {geometry.rows, geometry.width, geometry.height, geometry.line_gap};
  } else {
    next = lcd_display::normalizeTextProfile(profile);
  }
  if(next.rows == active_profile.rows &&
     next.glyph_width == active_profile.glyph_width &&
     next.glyph_height == active_profile.glyph_height &&
     next.line_gap == active_profile.line_gap) return;

  active_profile = next;
  clearShadow();
  cursor_underline = false;
  cursor_blink = false;
  cursor_blink_phase = false;
  cursor_next_blink_ms = 0;
  markScreenDirty();
}

void MK61Display::setTextProfile(lcd_display::TextProfile profile) {
  applyTextProfile(profile);
}

lcd_display::TextProfile MK61Display::textProfile(void) const {
  return active_profile;
}

void MK61Display::setCursor(u8 x, u8 y) {
  moveCursorTo(x, y);
}

void MK61Display::cursorOn(void) {
  if(cursor_underline) return;
  cursor_underline = true;
  markCursorCellDirty();
  if(update_depth == 0) flush();
}

void MK61Display::cursorOff(void) {
  if(!cursor_underline && !cursor_blink && !cursor_blink_phase) return;
  cursor_underline = false;
  cursor_blink = false;
  cursor_blink_phase = false;
  cursor_next_blink_ms = 0;
  markCursorCellDirty();
  if(update_depth == 0) flush();
}

void MK61Display::blinkOn(void) {
  if(cursor_blink) return;
  cursor_blink = true;
  cursor_blink_phase = true;
  cursor_next_blink_ms = millis() + CURSOR_BLINK_MS;
  markCursorCellDirty();
  if(update_depth == 0) flush();
}

void MK61Display::blinkOff(void) {
  if(!cursor_blink && !cursor_blink_phase) return;
  cursor_blink = false;
  cursor_blink_phase = false;
  cursor_next_blink_ms = 0;
  markCursorCellDirty();
  if(update_depth == 0) flush();
}

bool MK61Display::supportsCursor(void) const { return true; }
bool MK61Display::hasHardwareCursor(void) const { return false; }

void MK61Display::createChar(u8 nChar, uint8_t* glyph) {
  if(nChar >= CUSTOM_GLYPHS || glyph == NULL) return;
  memcpy(custom_glyphs[nChar], glyph, sizeof(custom_glyphs[nChar]));
  custom_valid[nChar] = true;
  grid.markCustomSlot(nChar);
  dirty = dirty || grid.anyDirty();
  if(update_depth == 0) flush();
}

void MK61Display::clearCustomChars(void) {
  for(u8 i = 0; i < CUSTOM_GLYPHS; i++) {
    if(custom_valid[i]) grid.markCustomSlot(i);
    custom_valid[i] = false;
  }
  dirty = dirty || grid.anyDirty();
  if(update_depth == 0) flush();
}

lcd_display::TextProfile MK61Display::recommendedProfile(const fmk::Metrics& metrics) const {
  const text_screen::FontGeometry geometry =
    text_screen::fitFontToDisplay(metrics.max_width, metrics.height, metrics.line_gap);
  return {geometry.rows, geometry.width, geometry.height, geometry.line_gap};
}

bool MK61Display::installFont(const u8* data, u16 size) {
  if(data == NULL || size == 0 || size > fmk::MAX_FILE_SIZE) return false;
  fmk::Face source;
  if(!source.open(data, size)) return false;
  if(!exclusive_buffer::acquire(exclusive_buffer::Owner::DISPLAY_FONT, fmk::MAX_FILE_SIZE)) return false;
  u8* const font_data = exclusive_buffer::data(exclusive_buffer::Owner::DISPLAY_FONT);
  if(font_data == NULL) return false;
  memmove(font_data, data, size);
  if(!active_font.open(font_data, size)) {
    exclusive_buffer::release(exclusive_buffer::Owner::DISPLAY_FONT);
    return false;
  }

  active_font_enabled = true;
  external_font_suspended = false;
  preview_font_enabled = false;
  preview_profile_active = false;
  preview_font.reset();
  applyTextProfile(recommendedProfile(active_font.metrics()), true);
  markAllDirty();
  return true;
}

bool MK61Display::setFontPreview(const u8* data, u16 size) {
  if(data == NULL || size == 0 || size > fmk::MAX_FILE_SIZE) return false;
  fmk::Face candidate;
  if(!candidate.open(data, size)) return false;
  // Проводник удерживает аренду shared-scratch до clearFontPreview().
  // Сохраняем представление этих байтов, чтобы не делать вторую копию на 1536 байт.
  if(!preview_font.open(data, size)) return false;
  if(!preview_profile_active) {
    preview_saved_profile = active_profile;
    preview_profile_active = true;
  }
  preview_font_enabled = true;
  applyTextProfile(recommendedProfile(preview_font.metrics()), true);
  markAllDirty();
  return true;
}

void MK61Display::clearFontPreview(void) {
  if(!preview_font_enabled && !preview_profile_active) return;
  const bool restore_profile = preview_profile_active;
  const lcd_display::TextProfile saved_profile = preview_saved_profile;
  preview_font_enabled = false;
  preview_profile_active = false;
  preview_font.reset();
  if(restore_profile) applyTextProfile(saved_profile, true);
  markAllDirty();
}

void MK61Display::useBuiltinFont(void) {
  const bool restore_profile = preview_profile_active;
  const lcd_display::TextProfile saved_profile = preview_saved_profile;
  const bool had_active_font = active_font_enabled || external_font_suspended;
  const bool changed = had_active_font || preview_font_enabled || preview_profile_active;
  if(active_font_enabled) exclusive_buffer::release(exclusive_buffer::Owner::DISPLAY_FONT);
  active_font_enabled = false;
  external_font_suspended = false;
  preview_font_enabled = false;
  preview_profile_active = false;
  active_font.reset();
  preview_font.reset();
  if(had_active_font) applyTextProfile(lcd_display::defaultTextProfileForRows(lcd_display::DEFAULT_ROWS));
  else if(restore_profile) applyTextProfile(saved_profile, true);
  if(changed) markAllDirty();
}

bool MK61Display::externalFontActive(void) const {
  return active_font_enabled;
}

bool MK61Display::suspendExternalFontForUsb(void) {
  if(preview_font_enabled || preview_profile_active) return false;
  if(external_font_suspended) return true;
  if(!active_font_enabled) return true;
  active_font_enabled = false;
  external_font_suspended = true;
  active_font.reset();
  exclusive_buffer::release(exclusive_buffer::Owner::DISPLAY_FONT);
  return true;
}

const fmk::Face* MK61Display::selectedFont(void) const {
  if(preview_font_enabled) return &preview_font;
  return active_font_enabled ? &active_font : NULL;
}

builtin_font::FaceId MK61Display::fallbackFont(void) const {
  if(const fmk::Face* font = selectedFont()) {
    return builtin_font::closest(font->metrics().max_width, font->metrics().height);
  }
  return lcd_display::isTextProfile3x5(active_profile)
    ? builtin_font::FaceId::FONT_3X5
    : builtin_font::FaceId::FONT_5X8;
}

bool MK61Display::resolveToken(u16 value, bool custom, builtin_font::Raster& raster) const {
  memset(raster.data, 0, sizeof(raster.data));
  if(custom) {
    const u8 slot = (u8) value;
    if(slot < CUSTOM_GLYPHS && custom_valid[slot]) {
      raster.width = 5;
      raster.height = 8;
      for(u8 y = 0; y < 8; y++) {
        for(u8 x = 0; x < 5; x++) {
          if((custom_glyphs[slot][y] & ((u8) 1 << (4 - x))) != 0) {
            raster.data[y] |= (u8) (0x80 >> x);
          }
        }
      }
      return true;
    }
    value = '?';
  }

  if(const fmk::Face* font = selectedFont()) {
    fmk::Glyph glyph;
    u16 font_value = value;
#if defined(MK61_DISPLAY_UC1609)
    font_value = display_symbol::uc1609::unicodeCodepoint(value);
#endif
    if(font->glyph(font_value, glyph) || (font_value != value && font->glyph(value, glyph))) {
      raster.width = glyph.width;
      raster.height = glyph.height;
      if(font->decode(glyph, raster.data, sizeof(raster.data))) return true;
    }
  }

  const builtin_font::FaceId fallback = fallbackFont();
  if(builtin_font::decode(fallback, value, raster)) return true;
  return value != '?' && builtin_font::decode(fallback, '?', raster);
}

void MK61Display::writeCodepoint(u16 codepoint) {
  if(codepoint == '\r') return;
  if(cursorOverlayVisible()) markCursorCellDirty();
  if(codepoint == '\n') grid.newline();
  else grid.writeCodepoint(codepoint);
  if(cursorOverlayVisible()) markCursorCellDirty();
  dirty = true;
  if(update_depth == 0) flush();
}

void MK61Display::clearShadow(void) {
  grid.reset(active_profile.rows);
}

void MK61Display::clearPhysicalScreen(void) {
  memset(render_buffer, 0x00, sizeof(render_buffer));
  for(u8 y = 0; y < lcd_display::PIXEL_HEIGHT; y += RENDER_PAGE_HEIGHT) {
    lcd.LCDBuffer(0, y, lcd_display::PIXEL_WIDTH, RENDER_PAGE_HEIGHT, render_buffer);
  }
}

bool MK61Display::showFullscreenBitmap(const u8* bitmap, usize size) {
  static constexpr usize FULLSCREEN_BYTES =
    (usize) lcd_display::PIXEL_WIDTH * lcd_display::PIXEL_HEIGHT / 8;
  if(!initialized || bitmap == NULL || size != FULLSCREEN_BYTES) return false;
  return lcd.LCDBitmap(0, 0, lcd_display::PIXEL_WIDTH,
                       lcd_display::PIXEL_HEIGHT, bitmap) == LCD_Success;
}

u8 MK61Display::sanitizeRows(u8 rows) {
  return lcd_display::clamp_u8(rows, lcd_display::MIN_ROWS, lcd_display::MAX_ROWS);
}

u8 MK61Display::rowTop(u8 row) const {
  return (u8) ((u16) row * (active_profile.glyph_height + active_profile.line_gap));
}

u8 MK61Display::rowPitch(u8 row) const {
  const u8 top = rowTop(row);
  const u8 pitch = active_profile.glyph_height + active_profile.line_gap;
  if(row + 1 >= grid.rows()) return lcd_display::PIXEL_HEIGHT - top;
  return (top + pitch > lcd_display::PIXEL_HEIGHT) ? (lcd_display::PIXEL_HEIGHT - top) : pitch;
}

u8 MK61Display::glyphHeight(u8 row) const {
  const u8 pitch = rowPitch(row);
  return active_profile.glyph_height < pitch ? active_profile.glyph_height : pitch;
}

u8 MK61Display::glyphTop(u8 row) const {
  (void) row;
  return 0;
}

u8 MK61Display::glyphWidth(void) const { return active_profile.glyph_width; }

u8 MK61Display::glyphLeft(void) const {
  return (u8) ((lcd_display::CELL_WIDTH - glyphWidth()) / 2);
}

void MK61Display::markScreenDirty(void) {
  screen_dirty = true;
  dirty = true;
  if(update_depth == 0 && initialized) flush();
}

void MK61Display::markAllDirty(void) {
  grid.markAll();
  dirty = true;
  if(update_depth == 0 && initialized) flush();
}

void MK61Display::markCellDirtyDeferred(u8 x, u8 y) {
  grid.markCell(x, y);
  dirty = true;
}

void MK61Display::markCellDirty(u8 x, u8 y) {
  markCellDirtyDeferred(x, y);
  if(update_depth == 0) flush();
}

bool MK61Display::cursorOverlayVisible(void) const {
  return cursor_underline || (cursor_blink && cursor_blink_phase);
}

void MK61Display::markCursorCellDirty(void) {
  markCellDirtyDeferred(grid.cursorX(), grid.cursorY());
}

void MK61Display::moveCursorTo(u8 x, u8 y) {
  const u8 old_x = grid.cursorX();
  const u8 old_y = grid.cursorY();
  grid.setCursor(x, y);
  if(old_x == grid.cursorX() && old_y == grid.cursorY()) return;
  if(cursorOverlayVisible()) markCellDirtyDeferred(old_x, old_y);
  if(cursorOverlayVisible()) markCursorCellDirty();
  if(update_depth == 0) flush();
}

void MK61Display::drawGlyph(u8 x, i16 row_y, u8 row, const uint8_t* bitmap,
                            u8 source_width, u8 source_height) {
  const u8 pitch = rowPitch(row);
  const u8 height = glyphHeight(row);
  const u8 max_width = glyphWidth();
  const u8 width = source_width < max_width ? source_width : max_width;
  const u8 glyph_x = x + (u8) ((lcd_display::CELL_WIDTH - width) / 2);
  const i16 glyph_y = row_y + glyphTop(row);
  lcd.fillRect(x, row_y, lcd_display::CELL_WIDTH, pitch, BACKGROUND);
  if(bitmap == NULL || source_width == 0 || source_height == 0 || width == 0 || height == 0) return;

  for(u8 dest_y = 0; dest_y < height; dest_y++) {
    const u8 source_y = (u8) (((u16) dest_y * source_height) / height);
    for(u8 dest_x = 0; dest_x < width; dest_x++) {
      const u8 source_x = (u8) (((u16) dest_x * source_width) / width);
      if(fmk::bitmapPixel(bitmap, source_width, source_x, source_y)) {
        lcd.drawPixel(glyph_x + dest_x, glyph_y + dest_y, FOREGROUND);
      }
    }
  }
}

void MK61Display::drawToken(u8 x, i16 row_y, u8 row, u16 value, bool custom) {
  builtin_font::Raster raster;
  if(resolveToken(value, custom, raster)) drawGlyph(x, row_y, row, raster.data, raster.width, raster.height);
  else drawGlyph(x, row_y, row, NULL, 0, 0);
}

void MK61Display::drawCursor(u8 x, i16 row_y, u8 row, bool block) {
  const u8 cursor_width = glyphWidth();
  const u8 cursor_x = x + glyphLeft();
  const u8 height = glyphHeight(row);
  if(cursor_width == 0 || height == 0) return;
  const i16 glyph_y = row_y + glyphTop(row);
  const u8 underline_height = (height >= 16) ? 2 : 1;
  if(block) lcd.fillRect(cursor_x, glyph_y, cursor_width, height, FOREGROUND);
  else lcd.fillRect(cursor_x, glyph_y + height - underline_height, cursor_width, underline_height, FOREGROUND);
}

void MK61Display::updateCursorBlink(void) {
  if(!cursor_blink) return;
  const t_time_ms now = millis();
  if(cursor_next_blink_ms == 0) cursor_next_blink_ms = now + CURSOR_BLINK_MS;
  if(!timeReached(now, cursor_next_blink_ms)) return;
  do {
    cursor_next_blink_ms += CURSOR_BLINK_MS;
  } while(timeReached(now, cursor_next_blink_ms));
  cursor_blink_phase = !cursor_blink_phase;
  markCursorCellDirty();
}

void MK61Display::renderRun(u8 row, u8 first_col, u8 count) {
  if(count == 0 || first_col >= lcd_display::COLS || count > lcd_display::COLS - first_col) return;
  (void) row;

  const u8 run_width = count * lcd_display::CELL_WIDTH;
  const u8 saved_width = render_screen.width;
  const u8 saved_height = render_screen.height;
  render_screen.width = run_width;
  render_screen.height = RENDER_PAGE_HEIGHT;

  for(u8 page_y = 0; page_y < lcd_display::PIXEL_HEIGHT; page_y += RENDER_PAGE_HEIGHT) {
    memset(render_buffer, 0x00, run_width);
    for(u8 render_row = 0; render_row < grid.rows(); render_row++) {
      const u8 absolute_row_y = rowTop(render_row);
      const u8 absolute_row_bottom = absolute_row_y + rowPitch(render_row);
      if(absolute_row_bottom <= page_y || absolute_row_y >= page_y + RENDER_PAGE_HEIGHT) continue;
      const i16 row_y = (i16) absolute_row_y - page_y;
      for(u8 i = 0; i < count; i++) {
        const u8 col = first_col + i;
        const u8 x = i * lcd_display::CELL_WIDTH;
        drawToken(x, row_y, render_row, grid.cell(col, render_row), grid.cellIsCustom(col, render_row));
        if(render_row == grid.cursorY() && col == grid.cursorX()) {
          if(cursor_blink && cursor_blink_phase) drawCursor(x, row_y, render_row, true);
          else if(cursor_underline) drawCursor(x, row_y, render_row, false);
        }
      }
    }
    lcd.LCDBuffer(first_col * lcd_display::CELL_WIDTH, page_y,
                  run_width, RENDER_PAGE_HEIGHT, render_buffer);
  }
  render_screen.width = saved_width;
  render_screen.height = saved_height;
}

#if ARDUINO >= 100
size_t MK61Display::write(uint8_t value) {
#else
void MK61Display::write(uint8_t value) {
#endif
  if(value == '\r') {
#if ARDUINO >= 100
    return 1;
#else
    return;
#endif
  }

  if(cursorOverlayVisible()) markCursorCellDirty();
  if(value == '\n') grid.newline();
  else if(value < CUSTOM_GLYPHS && custom_valid[value]) grid.writeByte(value);
  else grid.writeCodepoint(value);
  if(cursorOverlayVisible()) markCursorCellDirty();
  dirty = true;
  if(update_depth == 0) flush();

#if ARDUINO >= 100
  return 1;
#endif
}

#endif
