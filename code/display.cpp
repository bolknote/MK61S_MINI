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
    render_screen(render_buffer, lcd_display::PIXEL_WIDTH, MAX_RENDER_PAGES * 8, 0, 0),
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

      uint16_t run_mask = 0;
      for(u8 run_col = first_col; run_col < col; run_col++) {
        run_mask |= ((uint16_t) 1 << run_col);
      }
      for(u8 dirty_row = 0; dirty_row < active_rows; dirty_row++) {
        dirty_cols[dirty_row] &= (uint16_t) ~run_mask;
      }
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
  switch(rows) {
    case lcd_display::SPACED_ROWS_5:
    case lcd_display::SPACED_ROWS_7:
    case lcd_display::COMPACT_ROWS:
      return rows;
    default:
      return lcd_display::DEFAULT_ROWS;
  }
}

u8 MK61Display::glyphHeightForRows(u8 rows) {
  switch(rows) {
    case lcd_display::DEFAULT_ROWS:
      return 16;
    case lcd_display::SPACED_ROWS_5:
      return 10;
    case lcd_display::SPACED_ROWS_7:
    case lcd_display::COMPACT_ROWS:
    default:
      return 8;
  }
}

u8 MK61Display::glyphWidthForRows(u8 rows) {
  (void) rows;
  return 10;
}

u8 MK61Display::rowTop(u8 row) const {
  return (u8) (((u16) row * lcd_display::PIXEL_HEIGHT) / active_rows);
}

u8 MK61Display::rowPitch(u8 row) const {
  const u8 top = rowTop(row);
  const u8 bottom = (u8) ((((u16) row + 1) * lcd_display::PIXEL_HEIGHT) / active_rows);
  return bottom - top;
}

u8 MK61Display::glyphHeight(u8 row) const {
  const u8 pitch = rowPitch(row);
  const u8 height = glyphHeightForRows(active_rows);
  return (height < pitch) ? height : pitch;
}

u8 MK61Display::glyphTop(u8 row) const {
  return (u8) ((rowPitch(row) - glyphHeight(row)) / 2);
}

u8 MK61Display::glyphWidth(void) const {
  return glyphWidthForRows(active_rows);
}

u8 MK61Display::glyphLeft(void) const {
  return (u8) ((lcd_display::CELL_WIDTH - glyphWidth()) / 2);
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

void MK61Display::drawGlyph(u8 x, u8 row_y, u8 row, const uint8_t* glyph) {
  const u8 pitch = rowPitch(row);
  const u8 height = glyphHeight(row);
  const u8 width = glyphWidth();
  const u8 glyph_x = x + glyphLeft();
  const u8 glyph_y = row_y + glyphTop(row);
  lcd.fillRect(x, row_y, lcd_display::CELL_WIDTH, pitch, BACKGROUND);
  for(u8 dest_y = 0; dest_y < height; dest_y++) {
    const u8 src_y = (u8) (((u16) dest_y * 8) / height);
    const u8 bits = glyph[src_y];
    for(u8 dest_x = 0; dest_x < width; dest_x++) {
      const u8 src_x = (u8) (((u16) dest_x * 5) / width);
      if((bits & (0x10 >> src_x)) != 0) {
        lcd.drawPixel(glyph_x + dest_x, glyph_y + dest_y, FOREGROUND);
      }
    }
  }
}

void MK61Display::drawDefaultChar(u8 x, u8 row_y, u8 row, u8 value) {
  static constexpr u8 FONT_WIDTH = 5;
  static constexpr u8 FONT_HEIGHT = 8;
  const u8 pitch = rowPitch(row);
  const u8 height = glyphHeight(row);
  const u8 width = glyphWidth();
  const u8 glyph_x = x + glyphLeft();
  const u8 glyph_y = row_y + glyphTop(row);
  const u8 safe_value = (value < 128) ? value : (u8) '?';
  const unsigned char* glyph = &pFontDefaultptr[(usize) safe_value * FONT_WIDTH];

  lcd.fillRect(x, row_y, lcd_display::CELL_WIDTH, pitch, BACKGROUND);
  for(u8 dest_x = 0; dest_x < width; dest_x++) {
    const u8 src_x = (u8) (((u16) dest_x * FONT_WIDTH) / width);
    const u8 bits = glyph[src_x];
    for(u8 dest_y = 0; dest_y < height; dest_y++) {
      const u8 src_y = (u8) (((u16) dest_y * FONT_HEIGHT) / height);
      if((bits & ((u8) 1 << src_y)) != 0) {
        lcd.drawPixel(glyph_x + dest_x, glyph_y + dest_y, FOREGROUND);
      }
    }
  }
}

void MK61Display::drawCursor(u8 x, u8 row_y, u8 row, bool block) {
  const u8 cursor_width = glyphWidth();
  const u8 cursor_x = x + glyphLeft();
  const u8 height = glyphHeight(row);
  const u8 glyph_y = row_y + glyphTop(row);
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
  if(count == 0) return;
  (void) row;

  const u8 run_width = count * lcd_display::CELL_WIDTH;
  render_screen.width = run_width;
  render_screen.height = lcd_display::PIXEL_HEIGHT;
  memset(render_buffer, 0x00, run_width * MAX_RENDER_PAGES);

  for(u8 render_row = 0; render_row < active_rows; render_row++) {
    const u8 row_y = rowTop(render_row);
    for(u8 i = 0; i < count; i++) {
      const u8 col = first_col + i;
      const u8 value = cells[render_row][col];
      const u8 x = i * lcd_display::CELL_WIDTH;
      if(cell_glyph_valid[render_row][col]) {
        drawGlyph(x, row_y, render_row, cell_glyphs[render_row][col]);
      } else if(value < CUSTOM_GLYPHS && custom_valid[value]) {
        drawGlyph(x, row_y, render_row, custom_glyphs[value]);
      } else {
        drawDefaultChar(x, row_y, render_row, value);
      }
      if(render_row == cursor_y && col == cursor_x) {
        if(cursor_blink && cursor_blink_phase) drawCursor(x, row_y, render_row, true);
        else if(cursor_underline) drawCursor(x, row_y, render_row, false);
      }
    }
  }

  lcd.LCDBuffer(first_col * lcd_display::CELL_WIDTH, 0,
                run_width, lcd_display::PIXEL_HEIGHT, render_buffer);
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
