#include "display.hpp"
#include <string.h>

#if defined(MK61_DISPLAY_LCD1602)

MK61Display::MK61Display(void)
  : lcd(PIN_LCD_RS, PIN_LCD_E, PIN_LCD_DB4, PIN_LCD_DB5, PIN_LCD_DB6, PIN_LCD_DB7) {}

void MK61Display::begin(u8 cols, u8 rows) {
  lcd.begin(cols, rows);
}

void MK61Display::clear(void) {
  lcd.clear();
}

void MK61Display::flush(void) {}

void MK61Display::beginUpdate(void) {}

void MK61Display::endUpdate(void) {}

void MK61Display::setCursor(u8 x, u8 y) {
  lcd.setCursor(x, y);
}

void MK61Display::createChar(u8 nChar, uint8_t* glyph) {
  lcd.createChar(nChar, glyph);
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

MK61Display::MK61Display(void)
  : render_buffer{0},
    lcd(lcd_display::PIXEL_WIDTH, lcd_display::PIXEL_HEIGHT, PIN_GLCD_CD, PIN_GLCD_RST, PIN_GLCD_CS),
    render_screen(render_buffer, lcd_display::PIXEL_WIDTH, lcd_display::CELL_HEIGHT, 0, 0),
    cells{{0}},
    dirty_cols{0},
    custom_glyphs{{0}},
    custom_valid{false},
    screen_dirty(false),
    dirty(false),
    update_depth(0),
    cursor_x(0),
    cursor_y(0) {}

void MK61Display::begin(u8, u8) {
  lcd.LCDbegin(GLCD_UC1609_BIAS, GLCD_UC1609_ADDRESS_SET);
  lcd.ActiveBuffer = &render_screen;
  lcd.setFontNum(UC1609Font_Default);
  lcd.setTextWrap(false);
  lcd.setTextSize(2);
  lcd.setTextColor(FOREGROUND, BACKGROUND);
  clearShadow();
  clearPhysicalScreen();
}

void MK61Display::clear(void) {
  clearShadow();
  cursor_x = 0;
  cursor_y = 0;
  markScreenDirty();
}

void MK61Display::flush(void) {
  if(!dirty && !screen_dirty) return;

  if(screen_dirty) {
    clearPhysicalScreen();
    screen_dirty = false;
  }

  for(u8 row = 0; row < lcd_display::ROWS; row++) {
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
  if(update_depth == 0) flush();
}

void MK61Display::setCursor(u8 x, u8 y) {
  cursor_x = (x < lcd_display::COLS) ? x : (lcd_display::COLS - 1);
  cursor_y = (y < lcd_display::ROWS) ? y : (lcd_display::ROWS - 1);
}

void MK61Display::createChar(u8 nChar, uint8_t* glyph) {
  if(nChar >= CUSTOM_GLYPHS || glyph == NULL) return;
  memcpy(custom_glyphs[nChar], glyph, sizeof(custom_glyphs[nChar]));
  custom_valid[nChar] = true;
}

void MK61Display::clearCustomChars(void) {
  for(u8 i = 0; i < CUSTOM_GLYPHS; i++) custom_valid[i] = false;
}

void MK61Display::clearShadow(void) {
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    for(u8 col = 0; col < lcd_display::COLS; col++) {
      cells[row][col] = ' ';
    }
    dirty_cols[row] = 0;
  }
}

void MK61Display::clearPhysicalScreen(void) {
  memset(render_buffer, 0x00, sizeof(render_buffer));
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    lcd.LCDBuffer(0, row * lcd_display::CELL_HEIGHT,
                  lcd_display::PIXEL_WIDTH, lcd_display::CELL_HEIGHT,
                  render_buffer);
  }
}

void MK61Display::markScreenDirty(void) {
  screen_dirty = true;
  dirty = true;
  if(update_depth == 0) flush();
}

void MK61Display::markCellDirty(u8 x, u8 y) {
  dirty_cols[y] |= ((uint16_t) 1 << x);
  dirty = true;
  if(update_depth == 0) flush();
}

void MK61Display::advanceCursor(void) {
  if(++cursor_x >= lcd_display::COLS) {
    cursor_x = 0;
    if(cursor_y + 1 < lcd_display::ROWS) cursor_y++;
  }
}

void MK61Display::drawCustomChar(u8 x, u8 value) {
  lcd.fillRect(x, 0, lcd_display::CELL_WIDTH, lcd_display::CELL_HEIGHT, BACKGROUND);
  for(u8 row = 0; row < 8; row++) {
    const u8 bits = custom_glyphs[value][row];
    for(u8 col = 0; col < 5; col++) {
      if((bits & (0x10 >> col)) != 0) {
        lcd.fillRect(x + col * 2, row * 2, 2, 2, FOREGROUND);
      }
    }
  }
}

void MK61Display::renderRun(u8 row, u8 first_col, u8 count) {
  if(count == 0) return;

  const u8 run_width = count * lcd_display::CELL_WIDTH;
  render_screen.width = run_width;
  render_screen.height = lcd_display::CELL_HEIGHT;
  memset(render_buffer, 0x00, run_width * (lcd_display::CELL_HEIGHT / 8));

  for(u8 i = 0; i < count; i++) {
    const u8 value = cells[row][first_col + i];
    const u8 x = i * lcd_display::CELL_WIDTH;
    if(value < CUSTOM_GLYPHS && custom_valid[value]) {
      drawCustomChar(x, value);
    } else {
      lcd.drawChar(x, 0, value, FOREGROUND, BACKGROUND, 2);
    }
  }

  lcd.LCDBuffer(first_col * lcd_display::CELL_WIDTH, row * lcd_display::CELL_HEIGHT,
                run_width, lcd_display::CELL_HEIGHT, render_buffer);
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
    cursor_x = 0;
    if(cursor_y + 1 < lcd_display::ROWS) cursor_y++;
#if ARDUINO >= 100
    return 1;
#else
    return;
#endif
  }

  cells[cursor_y][cursor_x] = value;
  markCellDirty(cursor_x, cursor_y);
  advanceCursor();

#if ARDUINO >= 100
  return 1;
#endif
}

#endif
