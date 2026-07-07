#include "display.hpp"
#include <string.h>

#if defined(MK61_DISPLAY_UC1609)
#include "ERM19264_graphics_font.h"
#endif

#if defined(MK61_DISPLAY_LCD1602)

MK61Display::MK61Display(void)
  : lcd(PIN_LCD_RS, PIN_LCD_E, PIN_LCD_DB4, PIN_LCD_DB5, PIN_LCD_DB6, PIN_LCD_DB7) {}

void MK61Display::begin(u8 cols, u8 rows) {
  lcd.begin(cols, rows);
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

void MK61Display::setCursor(u8 x, u8 y) {
  lcd.setCursor(x, y);
}

void MK61Display::cursorOn(void) {
  lcd.cursor();
}

void MK61Display::cursorOff(void) {
  lcd.noCursor();
  lcd.noBlink();
}

void MK61Display::blinkOn(void) {
  lcd.blink();
}

void MK61Display::blinkOff(void) {
  lcd.noBlink();
}

bool MK61Display::supportsCursor(void) const {
  return true;
}

bool MK61Display::hasHardwareCursor(void) const {
  return true;
}

void MK61Display::createChar(u8 nChar, uint8_t* glyph) {
  lcd.createChar(nChar, glyph);
}

void MK61Display::writeGlyph(const uint8_t*) {
  write((uint8_t) '?');
}

void MK61Display::clearCustomChars(void) {}

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

static inline bool timeReached(t_time_ms now, t_time_ms target) {
  return (i32) (now - target) >= 0;
}

MK61Display::MK61Display(void)
  : render_buffer{0},
    lcd(lcd_display::PIXEL_WIDTH, lcd_display::PIXEL_HEIGHT, PIN_GLCD_CD, PIN_GLCD_RST, PIN_GLCD_CS),
    render_screen(render_buffer, lcd_display::PIXEL_WIDTH, lcd_display::CELL_HEIGHT, 0, 0),
    cells{{0}},
    cell_glyphs{{{0}}},
    cell_glyph_valid{{false}},
    dirty_cols{0},
    custom_glyphs{{0}},
    custom_valid{false},
    initialized(false),
    screen_dirty(false),
    dirty(false),
    update_depth(0),
    active_rows(lcd_display::DEFAULT_ROWS),
    cursor_x(0),
    cursor_y(0),
    cursor_underline(false),
    cursor_blink(false),
    cursor_blink_phase(false),
    cursor_next_blink_ms(0) {}

void MK61Display::begin(u8, u8 rows) {
  active_rows = sanitizeRows(rows);
  lcd.LCDbegin(GLCD_UC1609_BIAS, GLCD_UC1609_ADDRESS_SET);
  lcd.ActiveBuffer = &render_screen;
  lcd.setFontNum(UC1609Font_Default);
  lcd.setTextWrap(false);
  lcd.setTextSize(2);
  lcd.setTextColor(FOREGROUND, BACKGROUND);
  initialized = true;
  clearShadow();
  clearPhysicalScreen();
}

void MK61Display::clear(void) {
  clearShadow();
  cursor_x = 0;
  cursor_y = 0;
  cursor_underline = false;
  cursor_blink = false;
  cursor_blink_phase = false;
  cursor_next_blink_ms = 0;
  markScreenDirty();
}

void MK61Display::flush(void) {
  if(!initialized) return;
  updateCursorBlink();
  if(!dirty && !screen_dirty) return;

  if(screen_dirty) {
    clearPhysicalScreen();
    screen_dirty = false;
  }

  for(u8 row = 0; row < active_rows; row++) {
    uint16_t mask = dirty_cols[row];
    dirty_cols[row] = 0;

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
    }
  }

  dirty = false;
}

void MK61Display::beginUpdate(void) {
  update_depth++;
}

void MK61Display::endUpdate(void) {
  if(update_depth > 0) update_depth--;
  if(update_depth == 0 && initialized) flush();
}

void MK61Display::setRows(u8 rows) {
  const u8 next_rows = sanitizeRows(rows);
  if(next_rows == active_rows) return;

  active_rows = next_rows;
  clearShadow();
  cursor_x = 0;
  cursor_y = 0;
  cursor_underline = false;
  cursor_blink = false;
  cursor_blink_phase = false;
  cursor_next_blink_ms = 0;
  markScreenDirty();
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

bool MK61Display::supportsCursor(void) const {
  return true;
}

bool MK61Display::hasHardwareCursor(void) const {
  return false;
}

void MK61Display::createChar(u8 nChar, uint8_t* glyph) {
  if(nChar >= CUSTOM_GLYPHS || glyph == NULL) return;
  memcpy(custom_glyphs[nChar], glyph, sizeof(custom_glyphs[nChar]));
  custom_valid[nChar] = true;
}

void MK61Display::writeGlyph(const uint8_t* glyph) {
  if(glyph == NULL) {
    write((uint8_t) '?');
    return;
  }

  cells[cursor_y][cursor_x] = 0;
  memcpy(cell_glyphs[cursor_y][cursor_x], glyph, sizeof(cell_glyphs[cursor_y][cursor_x]));
  cell_glyph_valid[cursor_y][cursor_x] = true;
  markCellDirtyDeferred(cursor_x, cursor_y);
  advanceCursor();
  if(update_depth == 0) flush();
}

void MK61Display::clearCustomChars(void) {
  for(u8 i = 0; i < CUSTOM_GLYPHS; i++) custom_valid[i] = false;
}

void MK61Display::clearShadow(void) {
  for(u8 row = 0; row < lcd_display::MAX_ROWS; row++) {
    for(u8 col = 0; col < lcd_display::COLS; col++) {
      cells[row][col] = ' ';
      cell_glyph_valid[row][col] = false;
    }
    dirty_cols[row] = 0;
  }
}

void MK61Display::clearPhysicalScreen(void) {
  memset(render_buffer, 0x00, sizeof(render_buffer));
  for(u8 y = 0; y < lcd_display::PIXEL_HEIGHT; y += lcd_display::CELL_HEIGHT) {
    lcd.LCDBuffer(0, y,
                  lcd_display::PIXEL_WIDTH, lcd_display::CELL_HEIGHT,
                  render_buffer);
  }
}

u8 MK61Display::sanitizeRows(u8 rows) {
  return (rows >= lcd_display::COMPACT_ROWS) ? lcd_display::COMPACT_ROWS : lcd_display::DEFAULT_ROWS;
}

u8 MK61Display::cellHeight(void) const {
  return (u8) (lcd_display::PIXEL_HEIGHT / active_rows);
}

void MK61Display::markScreenDirty(void) {
  screen_dirty = true;
  dirty = true;
  if(update_depth == 0 && initialized) flush();
}

void MK61Display::markCellDirtyDeferred(u8 x, u8 y) {
  if(x >= lcd_display::COLS || y >= active_rows) return;
  dirty_cols[y] |= ((uint16_t) 1 << x);
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
  markCellDirtyDeferred(cursor_x, cursor_y);
}

void MK61Display::moveCursorTo(u8 x, u8 y) {
  const u8 next_x = (x < lcd_display::COLS) ? x : (lcd_display::COLS - 1);
  const u8 next_y = (y < active_rows) ? y : (active_rows - 1);
  if(next_x == cursor_x && next_y == cursor_y) return;

  if(cursorOverlayVisible()) markCursorCellDirty();
  cursor_x = next_x;
  cursor_y = next_y;
  if(cursorOverlayVisible()) markCursorCellDirty();
  if(update_depth == 0) flush();
}

void MK61Display::advanceCursor(void) {
  u8 next_x = cursor_x + 1;
  u8 next_y = cursor_y;
  if(next_x >= lcd_display::COLS) {
    next_x = 0;
    if(next_y + 1 < active_rows) next_y++;
  }
  moveCursorTo(next_x, next_y);
}

void MK61Display::drawGlyph(u8 x, const uint8_t* glyph) {
  const u8 height = cellHeight();
  const u8 scale_y = height / 8;
  lcd.fillRect(x, 0, lcd_display::CELL_WIDTH, height, BACKGROUND);
  for(u8 row = 0; row < 8; row++) {
    const u8 bits = glyph[row];
    for(u8 col = 0; col < 5; col++) {
      if((bits & (0x10 >> col)) != 0) {
        lcd.fillRect(x + col * 2, row * scale_y, 2, scale_y, FOREGROUND);
      }
    }
  }
}

void MK61Display::drawDefaultChar(u8 x, u8 value) {
  static constexpr u8 FONT_WIDTH = 5;
  static constexpr u8 FONT_HEIGHT = 8;
  const u8 height = cellHeight();
  const u8 scale_y = height / FONT_HEIGHT;
  const u8 safe_value = (value < 128) ? value : (u8) '?';
  const unsigned char* glyph = &pFontDefaultptr[(usize) safe_value * FONT_WIDTH];

  lcd.fillRect(x, 0, lcd_display::CELL_WIDTH, height, BACKGROUND);
  for(u8 col = 0; col < FONT_WIDTH; col++) {
    u8 bits = glyph[col];
    for(u8 row = 0; row < FONT_HEIGHT; row++) {
      if((bits & 0x01) != 0) {
        lcd.fillRect(x + col * 2, row * scale_y, 2, scale_y, FOREGROUND);
      }
      bits >>= 1;
    }
  }
}

void MK61Display::drawCursor(u8 x, bool block) {
  static constexpr u8 CURSOR_WIDTH = 10;
  const u8 height = cellHeight();
  const u8 underline_height = (height >= 16) ? 2 : 1;
  if(block) lcd.fillRect(x, 0, CURSOR_WIDTH, height, FOREGROUND);
  else lcd.fillRect(x, height - underline_height, CURSOR_WIDTH, underline_height, FOREGROUND);
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
  if(count == 0) return;

  const u8 run_width = count * lcd_display::CELL_WIDTH;
  const u8 height = cellHeight();
  render_screen.width = run_width;
  render_screen.height = height;
  memset(render_buffer, 0x00, run_width * (height / 8));

  for(u8 i = 0; i < count; i++) {
    const u8 value = cells[row][first_col + i];
    const u8 x = i * lcd_display::CELL_WIDTH;
    const u8 col = first_col + i;
    if(cell_glyph_valid[row][col]) {
      drawGlyph(x, cell_glyphs[row][col]);
    } else if(value < CUSTOM_GLYPHS && custom_valid[value]) {
      drawGlyph(x, custom_glyphs[value]);
    } else {
      drawDefaultChar(x, value);
    }
    if(row == cursor_y && col == cursor_x) {
      if(cursor_blink && cursor_blink_phase) drawCursor(x, true);
      else if(cursor_underline) drawCursor(x, false);
    }
  }

  lcd.LCDBuffer(first_col * lcd_display::CELL_WIDTH, row * height,
                run_width, height, render_buffer);
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

  if(value == '\n') {
    u8 next_y = cursor_y;
    if(next_y + 1 < active_rows) next_y++;
    moveCursorTo(0, next_y);
#if ARDUINO >= 100
    return 1;
#else
    return;
#endif
  }

  cells[cursor_y][cursor_x] = value;
  if(value < CUSTOM_GLYPHS && custom_valid[value]) {
    memcpy(cell_glyphs[cursor_y][cursor_x], custom_glyphs[value], sizeof(cell_glyphs[cursor_y][cursor_x]));
    cell_glyph_valid[cursor_y][cursor_x] = true;
  } else {
    cell_glyph_valid[cursor_y][cursor_x] = false;
  }
  markCellDirtyDeferred(cursor_x, cursor_y);
  advanceCursor();
  if(update_depth == 0) flush();

#if ARDUINO >= 100
  return 1;
#endif
}

#endif
