#include "display.hpp"

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
  : screen_buffer{0},
    lcd(lcd_display::PIXEL_WIDTH, lcd_display::PIXEL_HEIGHT, PIN_GLCD_CD, PIN_GLCD_RST, PIN_GLCD_CS),
    full_screen(screen_buffer, lcd_display::PIXEL_WIDTH, lcd_display::PIXEL_HEIGHT, 0, 0),
    custom_glyphs{{0}},
    custom_valid{false},
    dirty(false),
    update_depth(0),
    cursor_x(0),
    cursor_y(0) {}

void MK61Display::begin(u8, u8) {
  lcd.LCDbegin(GLCD_UC1609_BIAS, GLCD_UC1609_ADDRESS_SET);
  lcd.LCDFillScreen(0x00, 0);
  lcd.ActiveBuffer = &full_screen;
  lcd.setFontNum(UC1609Font_Default);
  lcd.setTextWrap(false);
  lcd.setTextSize(2);
  lcd.setTextColor(FOREGROUND, BACKGROUND);
  clear();
}

void MK61Display::clear(void) {
  lcd.LCDclearBuffer();
  cursor_x = 0;
  cursor_y = 0;
  movePixelCursor();
  markDirty();
}

void MK61Display::flush(void) {
  if(!dirty) return;
  lcd.LCDupdate();
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
  movePixelCursor();
}

void MK61Display::createChar(u8 nChar, uint8_t* glyph) {
  if(nChar >= CUSTOM_GLYPHS || glyph == NULL) return;
  memcpy(custom_glyphs[nChar], glyph, sizeof(custom_glyphs[nChar]));
  custom_valid[nChar] = true;
}

void MK61Display::clearCustomChars(void) {
  for(u8 i = 0; i < CUSTOM_GLYPHS; i++) custom_valid[i] = false;
}

void MK61Display::markDirty(void) {
  dirty = true;
  if(update_depth == 0) flush();
}

void MK61Display::movePixelCursor(void) {
  lcd.setCursor(cursor_x * lcd_display::CELL_WIDTH, cursor_y * lcd_display::CELL_HEIGHT);
}

void MK61Display::advanceCursor(void) {
  if(++cursor_x >= lcd_display::COLS) {
    cursor_x = 0;
    if(cursor_y + 1 < lcd_display::ROWS) cursor_y++;
  }
  movePixelCursor();
}

void MK61Display::drawCustomChar(u8 value) {
  const u8 px = cursor_x * lcd_display::CELL_WIDTH;
  const u8 py = cursor_y * lcd_display::CELL_HEIGHT;

  lcd.fillRect(px, py, lcd_display::CELL_WIDTH, lcd_display::CELL_HEIGHT, BACKGROUND);
  for(u8 row = 0; row < 8; row++) {
    const u8 bits = custom_glyphs[value][row];
    for(u8 col = 0; col < 5; col++) {
      if((bits & (0x10 >> col)) != 0) {
        lcd.fillRect(px + col * 2, py + row * 2, 2, 2, FOREGROUND);
      }
    }
  }
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
    movePixelCursor();
#if ARDUINO >= 100
    return 1;
#else
    return;
#endif
  }

  movePixelCursor();
  if(value < CUSTOM_GLYPHS && custom_valid[value]) {
    drawCustomChar(value);
  } else {
    lcd.write(value);
  }
  advanceCursor();
  markDirty();

#if ARDUINO >= 100
  return 1;
#endif
}

#endif
