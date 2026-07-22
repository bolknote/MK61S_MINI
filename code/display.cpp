#include "display.hpp"
#include "display_symbols.hpp"
#include "exclusive_buffer.hpp"

#include <string.h>

#if defined(MK61_DISPLAY_LCD1602)

#include "lcd1602_shifted_viewport.hpp"
#include "lcd_charset.hpp"

static_assert(lcd1602_shifted_viewport::COMMAND_RETURN_HOME == LCD_RETURNHOME,
              "HD44780 Return Home command mismatch");
static_assert(lcd1602_shifted_viewport::COMMAND_SET_DDRAM == LCD_SETDDRAMADDR,
              "HD44780 Set DDRAM command mismatch");
static_assert(lcd1602_shifted_viewport::COMMAND_SHIFT_LEFT ==
              (LCD_CURSORSHIFT | LCD_DISPLAYMOVE | LCD_MOVELEFT),
              "HD44780 display-left command mismatch");
static_assert(lcd1602_shifted_viewport::COMMAND_SHIFT_RIGHT ==
              (LCD_CURSORSHIFT | LCD_DISPLAYMOVE | LCD_MOVERIGHT),
              "HD44780 display-right command mismatch");

namespace {

struct LcdAnimationState {
  bool active;
};

static LcdAnimationState animation_state = {};

static u16 canonicalLcdToken(u8 value) {
#if defined(MK61_LCD1602_A02)
  switch(value) {
    case 0x00: return display_symbol::uc1609::GE;
    case 0x01: return display_symbol::uc1609::POWY;
    case 0x02: return display_symbol::uc1609::XOR;
    case 0x03: return display_symbol::uc1609::NOT_EQUAL;
    case 0x04: return display_symbol::uc1609::SQRT;
    case 0x05: return display_symbol::uc1609::CYC_ARROW;
    case 0x06: return display_symbol::uc1609::POW_X;
    case 0x7E: return display_symbol::uc1609::RT_ARROW;
    case 0x7F: return display_symbol::uc1609::LT_ARROW;
    case 0x80: return 0x0411; // Б
    case 0x81: return 0x0414; // Д
    case 0x82: return 0x0416; // Ж
    case 0x83: return 0x0417; // З
    case 0x84: return 0x0418; // И
    case 0x85: return 0x0419; // Й
    case 0x86: return 0x041B; // Л
    case 0x87: return 0x041F; // П
    case 0x88: return 0x0423; // У
    case 0x89: return 0x0426; // Ц
    case 0x8A: return 0x0427; // Ч
    case 0x8B: return 0x0428; // Ш
    case 0x8C: return 0x0429; // Щ
    case 0x8D: return 0x042A; // Ъ
    case 0x8E: return 0x042B; // Ы
    case 0x8F: return 0x042D; // Э
    case 0x92: return 0x0413; // Г
    case 0x93: return display_symbol::uc1609::PI_SYMBOL;
    case 0xAC: return 0x042E; // Ю
    case 0xAD: return 0x042F; // Я
    case 0xB2: return display_symbol::uc1609::POW2;
    case 0xB7: return display_symbol::uc1609::GRAD;
    case 0xB9: return display_symbol::uc1609::EM1;
    case 0xCB: return 0x0401; // Ё
    case 0xD8: return 0x0424; // Ф
    case 0xF7: return display_symbol::uc1609::DIVIDE;
    default: return value;
  }
#else
  switch(value) {
    case 0x00: return display_symbol::uc1609::GE;
    case 0x01: return display_symbol::uc1609::CYR_PE;
    case 0x02: return display_symbol::uc1609::CYR_BE;
    case 0x03: return display_symbol::uc1609::CYR_DE;
    case 0x04: return display_symbol::uc1609::CYR_I;
    case 0x05: return display_symbol::uc1609::CYR_GHE;
    case 0x06: return display_symbol::uc1609::POW2;
    case 0x07: return display_symbol::uc1609::POWY;
    case 0x08: return display_symbol::uc1609::XOR;
    case 0x7E: return display_symbol::uc1609::RT_ARROW;
    case 0x7F: return display_symbol::uc1609::LT_ARROW;
    case 0xB7: return display_symbol::uc1609::NOT_EQUAL;
    case 0xD1: return display_symbol::uc1609::CYR_CHE;
    case 0xDB: return display_symbol::uc1609::CYC_ARROW;
    case 0xDF: return display_symbol::uc1609::GRAD;
    case 0xE8: return display_symbol::uc1609::SQRT;
    case 0xE9: return display_symbol::uc1609::EM1;
    case 0xEB: return display_symbol::uc1609::POW_X;
    case 0xF7: return display_symbol::uc1609::PI_SYMBOL;
    case 0xFD: return display_symbol::uc1609::DIVIDE;
    default: return value;
  }
#endif
}

static u8 lcdByteForCanonicalToken(u16 token) {
  for(u16 value = 0; value <= 0xFF; value++) {
    if(canonicalLcdToken((u8) value) == token) return (u8) value;
  }
  return token <= 0xFF ? (u8) token : (u8) '?';
}

} // анонимное пространство имён

namespace {

struct LcdParallelBus {
  PinName rs;
  PinName rw;
  PinName enable;
  PinName data[4];

  bool validForWrite(void) const {
    return rs != NC && enable != NC &&
           data[0] != NC && data[1] != NC && data[2] != NC && data[3] != NC;
  }

#if MK61_LCD1602_BUSY_FLAG
  bool validForRead(void) const {
    return rw != NC && validForWrite();
  }
#endif

};

#if MK61_LCD1602_BUSY_FLAG
enum class LcdReadyResult : u8 {
  READY_AFTER_BUSY,
  READY_WITHOUT_BUSY,
  TIMEOUT,
};
#endif

static LcdParallelBus lcdParallelBus(void) {
  return {
    digitalPinToPinName(PIN_LCD_RS),
#if MK61_LCD1602_BUSY_FLAG
    digitalPinToPinName(PIN_LCD_RW),
#else
    NC,
#endif
    digitalPinToPinName(PIN_LCD_E),
    {
      digitalPinToPinName(PIN_LCD_DB4),
      digitalPinToPinName(PIN_LCD_DB5),
      digitalPinToPinName(PIN_LCD_DB6),
      digitalPinToPinName(PIN_LCD_DB7),
    },
  };
}

static inline void lcdWritePin(PinName pin, bool high) {
  digitalWriteFast(pin, high ? HIGH : LOW);
}

static inline void lcdSetPinOutput(PinName pin, bool output) {
  GPIO_TypeDef* const port = get_GPIO_Port(STM_PORT(pin));
  const u32 shift = (u32) STM_PIN(pin) * 2u;
  const u32 mask = 0x3u << shift;
  const u32 mode = output ? (0x1u << shift) : 0u;
  port->MODER = (port->MODER & ~mask) | mode;
}

static inline void lcdSetDataOutput(const LcdParallelBus& bus, bool output) {
  for(u8 i = 0; i < 4; i++) lcdSetPinOutput(bus.data[i], output);
}

static inline void lcdWriteNibble(const LcdParallelBus& bus, u8 nibble) {
  lcdWritePin(bus.enable, false);
  lcdWritePin(bus.data[0], (nibble & 0x01u) != 0);
  lcdWritePin(bus.data[1], (nibble & 0x02u) != 0);
  lcdWritePin(bus.data[2], (nibble & 0x04u) != 0);
  lcdWritePin(bus.data[3], (nibble & 0x08u) != 0);
  delayMicroseconds(1);
  lcdWritePin(bus.enable, true);
  delayMicroseconds(1);
  lcdWritePin(bus.enable, false);
  delayMicroseconds(1);
}

static inline void lcdWriteByte(const LcdParallelBus& bus, u8 value, bool data) {
  if(bus.rw != NC) lcdWritePin(bus.rw, false);
  lcdWritePin(bus.rs, data);
  lcdWriteNibble(bus, value >> 4);
  lcdWriteNibble(bus, value & 0x0Fu);
}

#if MK61_LCD1602_BUSY_FLAG
static LcdReadyResult lcdWaitReady(const LcdParallelBus& bus, u32 timeout_us) {
  bool saw_busy = false;
  const u32 started_at = micros();

  lcdWritePin(bus.enable, false);
  lcdSetDataOutput(bus, false);
  lcdWritePin(bus.rs, false);
  lcdWritePin(bus.rw, true);
  delayMicroseconds(1);

  LcdReadyResult result = LcdReadyResult::TIMEOUT;
  do {
    lcdWritePin(bus.enable, true);
    delayMicroseconds(1);
    const bool busy = digitalReadFast(bus.data[3]) != LOW;
    lcdWritePin(bus.enable, false);
    delayMicroseconds(1);

    // В четырёхбитном режиме чтение всегда завершается вторым полубайтом.
    lcdWritePin(bus.enable, true);
    delayMicroseconds(1);
    lcdWritePin(bus.enable, false);
    delayMicroseconds(1);

    if(!busy) {
      result = saw_busy ? LcdReadyResult::READY_AFTER_BUSY
                        : LcdReadyResult::READY_WITHOUT_BUSY;
      break;
    }
    saw_busy = true;
  } while((u32) (micros() - started_at) < timeout_us);

  lcdWritePin(bus.rw, false);
  delayMicroseconds(1);
  lcdSetDataOutput(bus, true);
  return result;
}
#endif

} // анонимное пространство имён

MK61Display::MK61Display(void)
  : lcd(PIN_LCD_RS, PIN_LCD_E, PIN_LCD_DB4, PIN_LCD_DB5, PIN_LCD_DB6, PIN_LCD_DB7),
    ddram_shadow{{0}},
    shadow_cursor_x(0),
    shadow_cursor_y(0),
    custom_glyphs{{0}},
    custom_valid{false},
    display_control(LCD_DISPLAYON | LCD_CURSOROFF | LCD_BLINKOFF),
    busy_flag_active(false),
    busy_flag_timeouts(0),
    shifted_viewport_active(false),
    shifted_viewport_shift(0)
#if MK61_ENABLE_USB_SCREEN
    , usb_framebuffer{0},
    usb_text_profile(lcd_display::defaultSettingsTextProfile()),
    usb_surface(usb_framebuffer),
    usb_screen_active(false),
    display_mode_revision(0),
    physical_screen_enabled(true),
    usb_preview_font(),
    usb_preview_saved_profile(usb_screen::profile5x8()),
    usb_preview_font_active(false)
#endif
    {
  memset(ddram_shadow, ' ', sizeof(ddram_shadow));
}

void MK61Display::begin(u8 cols, u8 rows) {
  (void) cols;
  (void) rows;
#if MK61_LCD1602_BUSY_FLAG
  // RW должен быть прижат к записи ещё до стандартной последовательности
  // инициализации LiquidCrystal.
  pinMode(PIN_LCD_RW, OUTPUT);
  digitalWrite(PIN_LCD_RW, LOW);
#endif
  lcd.begin(lcd_display::COLS, lcd_display::ROWS);
  lcd.noCursor();
  lcd.noBlink();
  display_control = LCD_DISPLAYON | LCD_CURSOROFF | LCD_BLINKOFF;
  busy_flag_timeouts = 0;
  probeBusyFlag();
  memset(ddram_shadow, ' ', sizeof(ddram_shadow));
  shadow_cursor_x = 0;
  shadow_cursor_y = 0;
  shifted_viewport_active = false;
  shifted_viewport_shift = 0;
}

void MK61Display::clear(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.clear();
    usb_surface.flush(millis());
    return;
  }
#endif
  display_control &= (u8) ~(LCD_CURSORON | LCD_BLINKON);
  sendDisplayControl();
  sendCommand(LCD_CLEARDISPLAY, 2000);
  memset(ddram_shadow, ' ', sizeof(ddram_shadow));
  shadow_cursor_x = 0;
  shadow_cursor_y = 0;
  shifted_viewport_active = false;
  shifted_viewport_shift = 0;
}

void MK61Display::flush(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) usb_surface.flush(millis());
#endif
}
void MK61Display::beginUpdate(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) usb_surface.beginUpdate();
#endif
}
void MK61Display::endUpdate(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.endUpdate();
    usb_surface.flush(millis());
  }
#endif
}
void MK61Display::setRows(u8 rows) {
#if MK61_ENABLE_USB_SCREEN
  setTextProfile(lcd_display::defaultSettingsTextProfileForRows(rows));
#else
  (void) rows;
#endif
}
void MK61Display::setTextProfile(lcd_display::TextProfile profile) {
#if MK61_ENABLE_USB_SCREEN
  usb_text_profile = lcd_display::normalizeSettingsTextProfile(profile);
  if(usb_screen_active) {
    usb_surface.setTextProfile(usbTextProfile(usb_text_profile));
    usb_surface.flush(millis());
  }
#else
  (void) profile;
#endif
}

lcd_display::TextProfile MK61Display::textProfile(void) const {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    const usb_screen::TextProfile profile = usb_surface.textProfile();
    return {profile.rows, profile.glyph_width, profile.glyph_height,
            profile.line_gap};
  }
  return usb_text_profile;
#endif
  return lcd_display::defaultTextProfileForRows(lcd_display::ROWS);
}

void MK61Display::setCursor(u8 x, u8 y) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.setCursor(x, y);
    usb_surface.flush(millis());
    return;
  }
#endif
  shadow_cursor_x = x < lcd_display::COLS ? x : (u8) (lcd_display::COLS - 1);
  shadow_cursor_y = y < lcd_display::ROWS ? y : (u8) (lcd_display::ROWS - 1);
  const u8 row_address = shadow_cursor_y == 0 ? 0x00u : 0x40u;
  const u8 physical_x = shifted_viewport_active
                      ? lcd1602_shifted_viewport::physical_address(
                          shifted_viewport_shift, shadow_cursor_x)
                      : shadow_cursor_x;
  sendCommand((u8) (LCD_SETDDRAMADDR | (row_address + physical_x)));
}

void MK61Display::cursorOn(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.cursorOn();
    usb_surface.flush(millis());
    return;
  }
#endif
  display_control |= LCD_CURSORON;
  sendDisplayControl();
}

void MK61Display::cursorOff(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.cursorOff();
    usb_surface.flush(millis());
    return;
  }
#endif
  display_control &= (u8) ~(LCD_CURSORON | LCD_BLINKON);
  sendDisplayControl();
}

void MK61Display::blinkOn(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.blinkOn(millis());
    usb_surface.flush(millis());
    return;
  }
#endif
  display_control |= LCD_BLINKON;
  sendDisplayControl();
}

void MK61Display::blinkOff(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.blinkOff();
    usb_surface.flush(millis());
    return;
  }
#endif
  display_control &= (u8) ~LCD_BLINKON;
  sendDisplayControl();
}
bool MK61Display::supportsCursor(void) const { return true; }
bool MK61Display::hasHardwareCursor(void) const {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) return false;
#endif
  return true;
}

void MK61Display::createChar(u8 nChar, uint8_t* glyph) {
  if(nChar >= 8 || glyph == NULL) return;
  memcpy(custom_glyphs[nChar], glyph, sizeof(custom_glyphs[nChar]));
  custom_valid[nChar] = true;
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.createChar(nChar, glyph);
    usb_surface.flush(millis());
    return;
  }
#endif
  sendCommand((u8) (LCD_SETCGRAMADDR | (nChar << 3)));
  for(u8 row = 0; row < 8; row++) sendData(glyph[row]);
}

void MK61Display::clearCustomChars(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.clearCustomChars();
    usb_surface.flush(millis());
  }
#endif
}

bool MK61Display::readCell(u8 x, u8 y, u8& value) const {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    u16 token = 0;
    bool custom = false;
    if(!usb_surface.readCell(x, y, token, custom) || token > 0xFF) return false;
    value = (u8) token;
    return true;
  }
#endif
  if(x >= lcd_display::COLS || y >= lcd_display::ROWS) return false;
  const u8 physical_x = shifted_viewport_active
                      ? lcd1602_shifted_viewport::physical_address(
                          shifted_viewport_shift, x) : x;
  value = ddram_shadow[y][physical_x];
  return true;
}

bool MK61Display::copyCustomChar(u8 nChar, u8 glyph[8]) const {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) return usb_surface.copyCustomChar(nChar, glyph);
#endif
  if(nChar >= 8 || glyph == NULL || !custom_valid[nChar]) return false;
  memcpy(glyph, custom_glyphs[nChar], sizeof(custom_glyphs[nChar]));
  return true;
}

void MK61Display::clearCustomChar(u8 nChar) {
  if(nChar >= 8) return;
  static uint8_t blank[8] = {};
  memset(custom_glyphs[nChar], 0, sizeof(custom_glyphs[nChar]));
  custom_valid[nChar] = false;
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.clearCustomChar(nChar);
    usb_surface.flush(millis());
    return;
  }
#endif
  sendCommand((u8) (LCD_SETCGRAMADDR | (nChar << 3)));
  for(u8 row = 0; row < 8; row++) sendData(blank[row]);
}

void MK61Display::renderShiftedViewport(
    const u8 cells[lcd_display::ROWS][lcd_display::DDRAM_COLS], u8 shift) {
  if(cells == NULL || shift >= lcd_display::DDRAM_COLS) return;
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.beginUpdate();
    usb_surface.clear();
    for(u8 row = 0; row < lcd_display::ROWS; row++) {
      usb_surface.setCursor(0, row);
      for(u8 col = 0; col < lcd_display::COLS; col++) {
        usb_surface.writeCodepoint(canonicalLcdToken(
          cells[row][(u8) ((shift + col) % lcd_display::DDRAM_COLS)]));
      }
    }
    usb_surface.endUpdate();
    usb_surface.flush(millis());
    return;
  }
#endif

  if((display_control & (LCD_CURSORON | LCD_BLINKON)) != 0) {
    display_control &= (u8) ~(LCD_CURSORON | LCD_BLINKON);
    sendDisplayControl();
  }

  const auto emit = [this](lcd1602_shifted_viewport::BusWrite write) {
    if(write.data) {
      sendData(write.value);
    } else {
      const u32 delay_us = write.value ==
          lcd1602_shifted_viewport::COMMAND_RETURN_HOME ? 2000 : 0;
      sendCommand(write.value, delay_us);
    }
  };
  (void) lcd1602_shifted_viewport::render(
      ddram_shadow, shifted_viewport_active, shifted_viewport_shift,
      cells, shift, emit);
}

void MK61Display::endShiftedViewport(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) return;
#endif
  if(!shifted_viewport_active) return;
  cursorOff();
  const auto emit = [this](lcd1602_shifted_viewport::BusWrite write) {
    sendCommand(write.value, write.value ==
                lcd1602_shifted_viewport::COMMAND_RETURN_HOME ? 2000 : 0);
  };
  lcd1602_shifted_viewport::end(shifted_viewport_active,
                                shifted_viewport_shift, emit);
  shadow_cursor_x = 0;
  shadow_cursor_y = 0;
}

void MK61Display::writeCodepoint(u16 codepoint) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.writeCodepoint(codepoint);
    usb_surface.flush(millis());
    return;
  }
#endif
  write(codepoint <= 0xFF ? (u8) codepoint : (u8) '?');
}

bool MK61Display::installFont(const u8*, u16) { return false; }
bool MK61Display::setFontPreview(const u8* data, u16 size) {
#if MK61_ENABLE_USB_SCREEN
  if(!usb_screen_active || data == NULL || size == 0 ||
     size > fmk::MAX_FILE_SIZE) return false;
  fmk::Face candidate;
  if(!candidate.open(data, size) || !usb_preview_font.open(data, size)) {
    return false;
  }
  if(!usb_preview_font_active) {
    usb_preview_saved_profile = usb_surface.textProfile();
  }
  const fmk::Metrics& metrics = usb_preview_font.metrics();
  const text_screen::FontGeometry geometry = text_screen::fitFontToDisplay(
    metrics.max_width, metrics.height, metrics.line_gap);
  usb_surface.setTextProfile({geometry.rows, geometry.width,
                              geometry.height, geometry.line_gap});
  usb_surface.setFont(&usb_preview_font);
  usb_preview_font_active = true;
  usb_surface.flush(millis());
  return true;
#else
  (void) data;
  (void) size;
  return false;
#endif
}
void MK61Display::clearFontPreview(void) {
#if MK61_ENABLE_USB_SCREEN
  if(!usb_preview_font_active) return;
  usb_surface.setFont(NULL);
  usb_surface.setTextProfile(usb_preview_saved_profile);
  usb_preview_font.reset();
  usb_preview_font_active = false;
  usb_surface.flush(millis());
#endif
}
void MK61Display::useBuiltinFont(void) { clearFontPreview(); }
bool MK61Display::externalFontActive(void) const { return false; }
bool MK61Display::suspendExternalFontForUsb(void) { return true; }
bool MK61Display::beginFullscreenBitmap(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) return usb_surface.beginFullscreenBitmap();
#endif
  return false;
}
bool MK61Display::showFullscreenBitmap(const u8* bitmap, usize size) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) return usb_surface.showFullscreenBitmap(bitmap, size);
#endif
  (void) bitmap;
  (void) size;
  return false;
}
void MK61Display::endFullscreenBitmap(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.endFullscreenBitmap();
    usb_surface.flush(millis());
  }
#endif
}

bool MK61Display::showTopRightOverlay(const u32* rows, u8 width, u8 height,
                                      u8 clear_border) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    const bool shown = usb_surface.showTopRightOverlay(rows, width, height,
                                                       clear_border);
    usb_surface.flush(millis());
    return shown;
  }
#endif
  (void) rows;
  (void) width;
  (void) height;
  (void) clear_border;
  return false;
}

void MK61Display::hideTopRightOverlay(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.hideTopRightOverlay();
    usb_surface.flush(millis());
  }
#endif
}

bool MK61Display::beginCellAnimation(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.clear();
    usb_surface.flush(millis());
    animation_state.active = true;
    return true;
  }
#endif
  if(animation_state.active) return true;
  endShiftedViewport();
  cursorOff();
  blinkOff();
  sendCommand(LCD_CLEARDISPLAY, 2000);
  memset(ddram_shadow, ' ', sizeof(ddram_shadow));
  shadow_cursor_x = 0;
  shadow_cursor_y = 0;
  shifted_viewport_active = false;
  shifted_viewport_shift = 0;
  animation_state.active = true;
  return true;
}

bool MK61Display::writeCellAnimationFrame(const u8* cells, usize count) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    if(!animation_state.active || cells == NULL ||
       count != (usize) lcd_display::ROWS * lcd_display::COLS) return false;
    usb_surface.beginUpdate();
    usb_surface.clear();
    for(u8 row = 0; row < lcd_display::ROWS; row++) {
      usb_surface.setCursor(0, row);
      for(u8 col = 0; col < lcd_display::COLS; col++) {
        usb_surface.writeByte(cells[(usize) row * lcd_display::COLS + col]);
      }
    }
    usb_surface.endUpdate();
    usb_surface.flush(millis());
    return true;
  }
#endif
  if(!animation_state.active || cells == NULL ||
     count != (usize) lcd_display::ROWS * lcd_display::COLS) return false;

  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    sendCommand((u8) (LCD_SETDDRAMADDR | (row == 0 ? 0x00u : 0x40u)));
    for(u8 col = 0; col < lcd_display::COLS; col++) {
      sendData(cells[row * lcd_display::COLS + col]);
    }
    memcpy(ddram_shadow[row], cells + row * lcd_display::COLS,
           lcd_display::COLS);
  }
  shadow_cursor_x = 0;
  shadow_cursor_y = 0;
  return true;
}

bool MK61Display::writeCellAnimationPaletteFrame(const u8 glyphs[8][8],
                                                  const u8* cells,
                                                  usize count) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    if(!animation_state.active || glyphs == NULL || cells == NULL ||
       count != (usize) lcd_display::ROWS * lcd_display::COLS) return false;
    usb_surface.beginUpdate();
    for(u8 slot = 0; slot < 8; slot++) usb_surface.createChar(slot, glyphs[slot]);
    usb_surface.clear();
    for(u8 row = 0; row < lcd_display::ROWS; row++) {
      usb_surface.setCursor(0, row);
      for(u8 col = 0; col < lcd_display::COLS; col++) {
        usb_surface.writeByte(cells[(usize) row * lcd_display::COLS + col]);
      }
    }
    usb_surface.endUpdate();
    usb_surface.flush(millis());
    return true;
  }
#endif
  static constexpr usize GLYPH_COUNT = 8;
  static constexpr usize GLYPH_ROWS = 8;
  if(!animation_state.active || glyphs == NULL || cells == NULL ||
     count != (usize) lcd_display::ROWS * lcd_display::COLS) return false;

  u8 used_slots = 0;
  for(usize cell = 0; cell < count; cell++) {
    if(cells[cell] < GLYPH_COUNT) used_slots |= (u8) (1U << cells[cell]);
  }
  u64 changed_rows = 0;
  for(u8 slot = 0; slot < GLYPH_COUNT; slot++) {
    if((used_slots & ((u8) 1U << slot)) == 0) continue;
    for(u8 row = 0; row < GLYPH_ROWS; row++) {
      if(!custom_valid[slot] || custom_glyphs[slot][row] !=
          (u8) (glyphs[slot][row] & 0x1FU)) {
        changed_rows |= (u64) 1U << (slot * GLYPH_ROWS + row);
      }
    }
  }
  bool cells_changed = false;
  for(u8 row = 0; row < lcd_display::ROWS && !cells_changed; row++) {
    for(u8 col = 0; col < lcd_display::COLS; col++) {
      if(ddram_shadow[row][col] != cells[row * lcd_display::COLS + col]) {
        cells_changed = true;
        break;
      }
    }
  }
  if(changed_rows == 0 && !cells_changed) return true;

  // Гасим экран только на время изменения видимой CGRAM. Основной драйвер
  // сам использует busy flag, а при аппаратной ошибке безопасно возвращается
  // к фиксированным задержкам.
  const bool display_off = changed_rows != 0;
  if(display_off) {
    sendCommand((u8) (LCD_DISPLAYCONTROL |
                       (display_control & (u8) ~LCD_DISPLAYON)));
  }

  for(u8 address = 0; address < 64;) {
    while(address < 64 &&
          (changed_rows & ((u64) 1U << address)) == 0) address++;
    if(address >= 64) break;
    const u8 first = address;
    u8 last = address;
    // Один неизменившийся адрес между изменениями дешевле передать, чем
    // открывать новый диапазон отдельной командой установки адреса.
    while(last < 63) {
      u8 next = (u8) (last + 1U);
      while(next < 64 &&
            (changed_rows & ((u64) 1U << next)) == 0) next++;
      if(next >= 64 || next > (u8) (last + 2U)) break;
      last = next;
    }
    sendCommand((u8) (LCD_SETCGRAMADDR | first));
    for(u8 changed = first; changed <= last; changed++) {
      const u8 slot = (u8) (changed / GLYPH_ROWS);
      const u8 row = (u8) (changed % GLYPH_ROWS);
      sendData((u8) (glyphs[slot][row] & 0x1FU));
    }
    address = (u8) (last + 1U);
  }

  // DDRAM также обновляется только непрерывными изменившимися диапазонами.
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    for(u8 col = 0; col < lcd_display::COLS;) {
      if(ddram_shadow[row][col] ==
         cells[row * lcd_display::COLS + col]) {
        col++;
        continue;
      }
      const u8 first = col;
      while(col < lcd_display::COLS &&
            ddram_shadow[row][col] !=
              cells[row * lcd_display::COLS + col]) col++;
      sendCommand((u8) (LCD_SETDDRAMADDR |
                        (row == 0 ? first : (u8) (0x40u + first))));
      for(u8 changed = first; changed < col; changed++) {
        sendData(cells[row * lcd_display::COLS + changed]);
      }
    }
  }

  if(display_off) sendDisplayControl();

  for(usize slot = 0; slot < GLYPH_COUNT; slot++) {
    if((used_slots & ((u8) 1U << slot)) == 0) continue;
    for(usize row = 0; row < GLYPH_ROWS; row++) {
      custom_glyphs[slot][row] = (u8) (glyphs[slot][row] & 0x1FU);
    }
    custom_valid[slot] = true;
  }
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    memcpy(ddram_shadow[row], cells + row * lcd_display::COLS,
           lcd_display::COLS);
  }
  shadow_cursor_x = 0;
  shadow_cursor_y = 0;
  return true;
}

void MK61Display::endCellAnimation(void) {
  if(!animation_state.active) return;
  animation_state.active = false;
  clear();
}

lcd_display::BusyFlagStatus MK61Display::busyFlagStatus(void) const {
#if MK61_LCD1602_BUSY_FLAG
  return busy_flag_active ? lcd_display::BusyFlagStatus::ACTIVE
                          : lcd_display::BusyFlagStatus::FIXED_DELAYS;
#else
  return lcd_display::BusyFlagStatus::NOT_AVAILABLE;
#endif
}

u32 MK61Display::busyFlagTimeouts(void) const {
  return busy_flag_timeouts;
}

void MK61Display::probeBusyFlag(void) {
  busy_flag_active = false;

#if MK61_LCD1602_BUSY_FLAG
  pinMode(PIN_LCD_RW, OUTPUT);
  digitalWrite(PIN_LCD_RW, LOW);

  const LcdParallelBus bus = lcdParallelBus();
  if(!bus.validForRead()) return;

  // Clear выполняется достаточно долго, чтобы надёжно увидеть переход BF 1 -> 0.
  lcdWriteByte(bus, LCD_CLEARDISPLAY, false);
  const LcdReadyResult result = lcdWaitReady(bus, 3000);
  if(result == LcdReadyResult::READY_AFTER_BUSY) {
    busy_flag_active = true;
    return;
  }

  if(result == LcdReadyResult::TIMEOUT) {
    busy_flag_timeouts++;
  } else {
    // При неподключённом или прижатом к нулю DB7 чтение завершится сразу,
    // хотя только что отправленный Clear ещё может выполняться.
    delayMicroseconds(2000);
  }
#endif
}

void MK61Display::sendByte(u8 value, bool data, u32 fallback_delay_us) {
#if MK61_LCD1602_BUSY_FLAG
  if(busy_flag_active) {
    const LcdParallelBus bus = lcdParallelBus();
    if(bus.validForRead()) {
      lcdWriteByte(bus, value, data);
      if(lcdWaitReady(bus, 3000) != LcdReadyResult::TIMEOUT) return;
      busy_flag_active = false;
      busy_flag_timeouts++;
      // После трёх миллисекунд ожидания повторять уже принятый байт нельзя.
      return;
    }
    busy_flag_active = false;
  }
#endif

  // Не вызываем LiquidCrystal::command/write: в Arduino LiquidCrystal 1.0.7
  // эти методы ошибочно определены как inline только в .cpp. При -O2 их
  // внешние символы исчезают, и прошивка не линкуется. Стандартная
  // инициализация остаётся за библиотекой, последующий обмен идёт через тот же
  // четырёхбитный интерфейс напрямую.
  const LcdParallelBus bus = lcdParallelBus();
  if(!bus.validForWrite()) return;
  lcdWriteByte(bus, value, data);
  delayMicroseconds(fallback_delay_us != 0 ? fallback_delay_us : 50);
}

void MK61Display::sendCommand(u8 value, u32 fallback_delay_us) {
  sendByte(value, false, fallback_delay_us);
}

void MK61Display::sendData(u8 value) {
  sendByte(value, true);
}

void MK61Display::sendDisplayControl(void) {
  sendCommand((u8) (LCD_DISPLAYCONTROL | display_control));
}

#if ARDUINO >= 100
size_t MK61Display::write(uint8_t value) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    u8 custom[8];
    if(value < usb_screen::Surface::CUSTOM_GLYPHS &&
       usb_surface.copyCustomChar(value, custom)) {
      usb_surface.writeByte(value);
    } else {
      usb_surface.writeCodepoint(canonicalLcdToken(value));
    }
    usb_surface.flush(millis());
    return 1;
  }
#endif
  sendData(value);
  const u8 physical_x = shifted_viewport_active
                      ? lcd1602_shifted_viewport::physical_address(
                          shifted_viewport_shift, shadow_cursor_x)
                      : shadow_cursor_x;
  ddram_shadow[shadow_cursor_y][physical_x] = value;
  shadow_cursor_x++;
  if(shadow_cursor_x >= lcd_display::COLS) {
    shadow_cursor_x = 0;
    shadow_cursor_y = (u8) ((shadow_cursor_y + 1) % lcd_display::ROWS);
  }
  return 1;
}
#else
void MK61Display::write(uint8_t value) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    u8 custom[8];
    if(value < usb_screen::Surface::CUSTOM_GLYPHS &&
       usb_surface.copyCustomChar(value, custom)) {
      usb_surface.writeByte(value);
    } else {
      usb_surface.writeCodepoint(canonicalLcdToken(value));
    }
    usb_surface.flush(millis());
    return;
  }
#endif
  sendData(value);
  const u8 physical_x = shifted_viewport_active
                      ? lcd1602_shifted_viewport::physical_address(
                          shifted_viewport_shift, shadow_cursor_x)
                      : shadow_cursor_x;
  ddram_shadow[shadow_cursor_y][physical_x] = value;
  shadow_cursor_x++;
  if(shadow_cursor_x >= lcd_display::COLS) {
    shadow_cursor_x = 0;
    shadow_cursor_y = (u8) ((shadow_cursor_y + 1) % lcd_display::ROWS);
  }
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
#if MK61_ENABLE_WBMP_VIEWER
    fullscreen_bitmap_active(false),
#endif
    screen_dirty(false),
    dirty(false),
    update_depth(0),
    active_profile(lcd_display::defaultTextProfileForRows(lcd_display::DEFAULT_ROWS)),
    preview_saved_profile(active_profile),
    cursor_underline(false),
    cursor_blink(false),
    cursor_blink_phase(false),
    cursor_next_blink_ms(0),
    preview_profile_active(false),
    top_right_overlay_rows{0},
    top_right_overlay_width(0),
    top_right_overlay_height(0),
    top_right_overlay_clear_border(0),
    top_right_overlay_visible(false)
#if MK61_ENABLE_USB_SCREEN
    , usb_surface(render_buffer),
    usb_screen_active(false),
    display_mode_revision(0),
    physical_screen_enabled(true)
#endif
    {
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
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.clear();
    usb_surface.flush(millis());
    return;
  }
#endif
  clearShadow();
  cursor_underline = false;
  cursor_blink = false;
  cursor_blink_phase = false;
  cursor_next_blink_ms = 0;
  markScreenDirty();
}

void MK61Display::flush(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.flush(millis());
    return;
  }
#endif
  if(!initialized) return;
#if MK61_ENABLE_WBMP_VIEWER
  if(fullscreen_bitmap_active) return;
#endif
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
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.beginUpdate();
    return;
  }
#endif
  update_depth++;
}

void MK61Display::endUpdate(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.endUpdate();
    usb_surface.flush(millis());
    return;
  }
#endif
  if(update_depth > 0) update_depth--;
  if(update_depth == 0 && initialized) flush();
}

void MK61Display::setRows(u8 rows) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_screen::TextProfile profile = usb_surface.textProfile();
    if(rows >= 10) profile = usb_screen::profile3x5();
    else if(rows == 7) profile = usb_screen::profile5x9();
    else profile = usb_screen::profile5x8();
    usb_surface.setTextProfile(profile);
    usb_surface.flush(millis());
    return;
  }
#endif
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
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.setTextProfile(usbTextProfile(profile));
    usb_surface.flush(millis());
    return;
  }
#endif
  applyTextProfile(profile);
}

lcd_display::TextProfile MK61Display::textProfile(void) const {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    const usb_screen::TextProfile profile = usb_surface.textProfile();
    return {profile.rows, profile.glyph_width, profile.glyph_height,
            profile.line_gap};
  }
#endif
  return active_profile;
}

void MK61Display::setCursor(u8 x, u8 y) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.setCursor(x, y);
    usb_surface.flush(millis());
    return;
  }
#endif
  moveCursorTo(x, y);
}

void MK61Display::cursorOn(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.cursorOn();
    usb_surface.flush(millis());
    return;
  }
#endif
  if(cursor_underline) return;
  cursor_underline = true;
  markCursorCellDirty();
  if(update_depth == 0) flush();
}

void MK61Display::cursorOff(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.cursorOff();
    usb_surface.flush(millis());
    return;
  }
#endif
  if(!cursor_underline && !cursor_blink && !cursor_blink_phase) return;
  cursor_underline = false;
  cursor_blink = false;
  cursor_blink_phase = false;
  cursor_next_blink_ms = 0;
  markCursorCellDirty();
  if(update_depth == 0) flush();
}

void MK61Display::blinkOn(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.blinkOn(millis());
    usb_surface.flush(millis());
    return;
  }
#endif
  if(cursor_blink) return;
  cursor_blink = true;
  cursor_blink_phase = true;
  cursor_next_blink_ms = millis() + CURSOR_BLINK_MS;
  markCursorCellDirty();
  if(update_depth == 0) flush();
}

void MK61Display::blinkOff(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.blinkOff();
    usb_surface.flush(millis());
    return;
  }
#endif
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
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.createChar(nChar, glyph);
    usb_surface.flush(millis());
    return;
  }
#endif
  grid.markCustomSlot(nChar);
  dirty = dirty || grid.anyDirty();
  if(update_depth == 0) flush();
}

void MK61Display::clearCustomChars(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) usb_surface.clearCustomChars();
#endif
  for(u8 i = 0; i < CUSTOM_GLYPHS; i++) {
    if(custom_valid[i]) grid.markCustomSlot(i);
    custom_valid[i] = false;
  }
  dirty = dirty || grid.anyDirty();
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.flush(millis());
    return;
  }
#endif
  if(update_depth == 0) flush();
}

bool MK61Display::showTopRightOverlay(const u32* rows, u8 width, u8 height,
                                      u8 clear_border) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    const bool shown = usb_surface.showTopRightOverlay(rows, width, height,
                                                       clear_border);
    usb_surface.flush(millis());
    return shown;
  }
#endif
  const u16 total_width = (u16) width + (u16) clear_border * 2U;
  const u16 total_height = (u16) height + (u16) clear_border * 2U;
  if(!initialized || rows == NULL || width == 0 ||
     width > TOP_RIGHT_OVERLAY_MAX_WIDTH || height == 0 ||
     height > TOP_RIGHT_OVERLAY_MAX_HEIGHT ||
     total_width > lcd_display::PIXEL_WIDTH ||
     total_height > lcd_display::PIXEL_HEIGHT) return false;

  const u32 row_mask = width == 32 ? 0xFFFFFFFFUL : (((u32) 1U << width) - 1U);
  bool unchanged = top_right_overlay_visible &&
                   top_right_overlay_width == width &&
                   top_right_overlay_height == height &&
                   top_right_overlay_clear_border == clear_border;
  if(unchanged) {
    for(u8 y = 0; y < height; y++) {
      if(top_right_overlay_rows[y] != (rows[y] & row_mask)) {
        unchanged = false;
        break;
      }
    }
  }
  if(unchanged) return true;

  if(top_right_overlay_visible) {
    markTopRightOverlayDirty(top_right_overlay_width,
                             top_right_overlay_clear_border);
  }
  memset(top_right_overlay_rows, 0, sizeof(top_right_overlay_rows));
  for(u8 y = 0; y < height; y++) top_right_overlay_rows[y] = rows[y] & row_mask;
  top_right_overlay_width = width;
  top_right_overlay_height = height;
  top_right_overlay_clear_border = clear_border;
  top_right_overlay_visible = true;
  markTopRightOverlayDirty(width, clear_border);
  if(update_depth == 0) flush();
  return true;
}

void MK61Display::hideTopRightOverlay(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.hideTopRightOverlay();
    usb_surface.flush(millis());
    return;
  }
#endif
  if(!top_right_overlay_visible) return;
  const u8 old_width = top_right_overlay_width;
  const u8 old_border = top_right_overlay_clear_border;
  top_right_overlay_visible = false;
  top_right_overlay_width = 0;
  top_right_overlay_height = 0;
  top_right_overlay_clear_border = 0;
  memset(top_right_overlay_rows, 0, sizeof(top_right_overlay_rows));
  markTopRightOverlayDirty(old_width, old_border);
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
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) usb_surface.setFont(&active_font);
#endif
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
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) usb_surface.setFont(&preview_font);
#endif
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
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) usb_surface.setFont(selectedFont());
#endif
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
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) usb_surface.setFont(NULL);
#endif
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
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.writeCodepoint(codepoint);
    usb_surface.flush(millis());
    return;
  }
#endif
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
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) return usb_surface.showFullscreenBitmap(bitmap, size);
#endif
  static constexpr usize FULLSCREEN_BYTES =
    (usize) lcd_display::PIXEL_WIDTH * lcd_display::PIXEL_HEIGHT / 8;
  if(!initialized || bitmap == NULL || size != FULLSCREEN_BYTES) return false;
  return lcd.LCDBitmap(0, 0, lcd_display::PIXEL_WIDTH,
                       lcd_display::PIXEL_HEIGHT, bitmap) == LCD_Success;
}

bool MK61Display::beginFullscreenBitmap(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) return usb_surface.beginFullscreenBitmap();
#endif
#if MK61_ENABLE_WBMP_VIEWER
  if(!initialized) return false;
  cursor_underline = false;
  cursor_blink = false;
  cursor_blink_phase = false;
  cursor_next_blink_ms = 0;
  fullscreen_bitmap_active = true;
  return true;
#else
  return false;
#endif
}

void MK61Display::endFullscreenBitmap(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.endFullscreenBitmap();
    usb_surface.flush(millis());
    return;
  }
#endif
#if MK61_ENABLE_WBMP_VIEWER
  if(!fullscreen_bitmap_active) return;
  fullscreen_bitmap_active = false;
  clearShadow();
  markScreenDirty();
#endif
}

bool MK61Display::beginCellAnimation(void) { return false; }
bool MK61Display::writeCellAnimationFrame(const u8*, usize) { return false; }
bool MK61Display::writeCellAnimationPaletteFrame(const u8 (*)[8],
                                                  const u8*, usize) {
  return false;
}
void MK61Display::endCellAnimation(void) {}

lcd_display::BusyFlagStatus MK61Display::busyFlagStatus(void) const {
  return lcd_display::BusyFlagStatus::NOT_AVAILABLE;
}

u32 MK61Display::busyFlagTimeouts(void) const {
  return 0;
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
  if(top_right_overlay_visible) {
    markTopRightOverlayDirty(top_right_overlay_width,
                             top_right_overlay_clear_border);
  }
  if(update_depth == 0 && initialized) flush();
}

void MK61Display::markAllDirty(void) {
  grid.markAll();
  dirty = true;
  if(update_depth == 0 && initialized) flush();
}

void MK61Display::markTopRightOverlayDirty(u8 width, u8 clear_border) {
  const u16 total_width = (u16) width + (u16) clear_border * 2U;
  if(total_width == 0 || total_width > lcd_display::PIXEL_WIDTH) return;
  const u8 left = (u8) (lcd_display::PIXEL_WIDTH - total_width);
  const u8 first_col = left / lcd_display::CELL_WIDTH;
  for(u8 col = first_col; col < lcd_display::COLS; col++) {
    markCellDirtyDeferred(col, 0);
  }
}

void MK61Display::drawTopRightOverlay(u8 first_col, u8 count, u8 page_y) {
  if(!top_right_overlay_visible || count == 0) return;

  const i16 run_left = (i16) first_col * lcd_display::CELL_WIDTH;
  const i16 run_right = run_left + (i16) count * lcd_display::CELL_WIDTH;
  const i16 page_bottom = (i16) page_y + RENDER_PAGE_HEIGHT;
  const i16 total_width = (i16) top_right_overlay_width +
                          (i16) top_right_overlay_clear_border * 2;
  const i16 total_height = (i16) top_right_overlay_height +
                           (i16) top_right_overlay_clear_border * 2;
  const i16 background_left = lcd_display::PIXEL_WIDTH - total_width;
  if(run_right <= background_left || run_left >= lcd_display::PIXEL_WIDTH ||
     page_y >= total_height) return;
  const i16 clear_left = background_left > run_left ? background_left : run_left;
  const i16 clear_right = lcd_display::PIXEL_WIDTH < run_right
                        ? lcd_display::PIXEL_WIDTH : run_right;
  const i16 clear_top = page_y;
  const i16 clear_bottom = total_height < page_bottom ? total_height : page_bottom;
  if(clear_left < clear_right && clear_top < clear_bottom) {
    lcd.fillRect(clear_left - run_left, clear_top - page_y,
                 clear_right - clear_left, clear_bottom - clear_top, BACKGROUND);
  }

  const i16 content_left = background_left + top_right_overlay_clear_border;
  const i16 content_top = top_right_overlay_clear_border;
  for(u8 y = 0; y < top_right_overlay_height; y++) {
    const i16 absolute_y = content_top + y;
    if(absolute_y < page_y || absolute_y >= page_bottom) continue;
    const u32 bits = top_right_overlay_rows[y];
    for(u8 x = 0; x < top_right_overlay_width; x++) {
      if((bits & ((u32) 1U << x)) == 0) continue;
      const i16 absolute_x = content_left + x;
      if(absolute_x < run_left || absolute_x >= run_right) continue;
      lcd.drawPixel(absolute_x - run_left, absolute_y - page_y, FOREGROUND);
    }
  }
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
    drawTopRightOverlay(first_col, count, page_y);
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
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.writeByte(value);
    usb_surface.flush(millis());
#if ARDUINO >= 100
    return 1;
#else
    return;
#endif
  }
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

#if MK61_ENABLE_USB_SCREEN

usb_screen::TextProfile MK61Display::usbTextProfile(
    lcd_display::TextProfile profile) {
#if defined(MK61_DISPLAY_LCD1602)
  // У профиля физического LCD всего две строки; USB-экран намеренно использует
  // обычный профиль 192x64 5x8, не сохраняя это ограничение.
  if(profile.rows <= lcd_display::ROWS) return usb_screen::profile5x8();
#endif
  return usb_screen::normalizeProfile({
    profile.rows,
    profile.glyph_width,
    profile.glyph_height,
    profile.line_gap,
  });
}

bool MK61Display::enterUsbScreen(void) {
  if(usb_screen_active) return true;

#if defined(MK61_DISPLAY_LCD1602)
  u8 seed_cells[lcd_display::ROWS][lcd_display::COLS] = {};
  u8 seed_glyphs[usb_screen::Surface::CUSTOM_GLYPHS][8] = {};
  bool seed_glyph_valid[usb_screen::Surface::CUSTOM_GLYPHS] = {};
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    for(u8 col = 0; col < lcd_display::COLS; col++) {
      if(!readCell(col, row, seed_cells[row][col])) {
        seed_cells[row][col] = ' ';
      }
    }
  }
  for(u8 slot = 0; slot < usb_screen::Surface::CUSTOM_GLYPHS; slot++) {
    seed_glyph_valid[slot] = copyCustomChar(slot, seed_glyphs[slot]);
  }
  const u8 seed_cursor_x = shadow_cursor_x;
  const u8 seed_cursor_y = shadow_cursor_y;
  const bool seed_cursor_underline =
    (display_control & LCD_CURSORON) != 0;
  const bool seed_cursor_blink = (display_control & LCD_BLINKON) != 0;
  const usb_screen::TextProfile profile = usbTextProfile(usb_text_profile);
#else
  const usb_screen::TextProfile profile = usbTextProfile(active_profile);
#endif
  usb_surface.begin(profile);
#if defined(MK61_DISPLAY_UC1609)
  usb_surface.setFont(selectedFont());
  usb_surface.seedText(grid, custom_glyphs, custom_valid,
                       cursor_underline, cursor_blink, millis());
  if(top_right_overlay_visible) {
    usb_surface.showTopRightOverlay(top_right_overlay_rows,
                                    top_right_overlay_width,
                                    top_right_overlay_height,
                                    top_right_overlay_clear_border);
  }
#else
  usb_preview_font.reset();
  usb_preview_font_active = false;
  for(u8 slot = 0; slot < usb_screen::Surface::CUSTOM_GLYPHS; slot++) {
    if(seed_glyph_valid[slot]) {
      usb_surface.createChar(slot, seed_glyphs[slot]);
    }
  }
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    usb_surface.setCursor(0, row);
    for(u8 col = 0; col < lcd_display::COLS; col++) {
      const u8 value = seed_cells[row][col];
      if(value < usb_screen::Surface::CUSTOM_GLYPHS &&
         seed_glyph_valid[value]) {
        usb_surface.writeByte(value);
      } else {
        usb_surface.writeCodepoint(canonicalLcdToken(value));
      }
    }
  }
  usb_surface.setCursor(seed_cursor_x, seed_cursor_y);
  if(seed_cursor_underline) usb_surface.cursorOn();
  if(seed_cursor_blink) usb_surface.blinkOn(millis());
#endif
  usb_screen_active = true;
  display_mode_revision++;
  setPhysicalScreenEnabled(false);
  usb_surface.flush(millis());
  return true;
}

void MK61Display::leaveUsbScreen(void) {
  if(!usb_screen_active) return;
#if defined(MK61_DISPLAY_LCD1602)
  u16 restore_cells[lcd_display::ROWS][lcd_display::COLS] = {};
  bool restore_custom[lcd_display::ROWS][lcd_display::COLS] = {};
  u8 restore_glyphs[usb_screen::Surface::CUSTOM_GLYPHS][8] = {};
  bool restore_glyph_valid[usb_screen::Surface::CUSTOM_GLYPHS] = {};
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    for(u8 col = 0; col < lcd_display::COLS; col++) {
      if(!usb_surface.readCell(col, row, restore_cells[row][col],
                               restore_custom[row][col])) {
        restore_cells[row][col] = ' ';
        restore_custom[row][col] = false;
      }
    }
  }
  for(u8 slot = 0; slot < usb_screen::Surface::CUSTOM_GLYPHS; slot++) {
    restore_glyph_valid[slot] =
      usb_surface.copyCustomChar(slot, restore_glyphs[slot]);
  }
  const u8 restore_cursor_x = usb_surface.cursorX();
  const u8 restore_cursor_y = usb_surface.cursorY();
  const bool restore_cursor_underline = usb_surface.cursorUnderline();
  const bool restore_cursor_blink = usb_surface.cursorBlink();
  usb_preview_font.reset();
  usb_preview_font_active = false;
#else
  // Синхронизируем логический буфер UC1609 со всем, что модальный интерфейс
  // нарисовал, пока подсистемой владел USB-экран. Без этого при отключении хоста
  // снова появился бы устаревший физический экран из состояния до подключения.
  const usb_screen::TextProfile restore_profile = usb_surface.textProfile();
  const u8 restore_cursor_x = usb_surface.cursorX();
  const u8 restore_cursor_y = usb_surface.cursorY();
  const bool restore_cursor_underline = usb_surface.cursorUnderline();
  const bool restore_cursor_blink = usb_surface.cursorBlink();
  active_profile = {restore_profile.rows, restore_profile.glyph_width,
                    restore_profile.glyph_height, restore_profile.line_gap};
  grid.reset(active_profile.rows);
  for(u8 slot = 0; slot < CUSTOM_GLYPHS; slot++) {
    custom_valid[slot] = usb_surface.copyCustomChar(slot,
                                                    custom_glyphs[slot]);
    if(!custom_valid[slot]) memset(custom_glyphs[slot], 0,
                                   sizeof(custom_glyphs[slot]));
  }
  for(u8 row = 0; row < grid.rows(); row++) {
    grid.setCursor(0, row);
    for(u8 col = 0; col < lcd_display::COLS; col++) {
      u16 token = ' ';
      bool custom = false;
      (void) usb_surface.readCell(col, row, token, custom);
      if(custom && token < CUSTOM_GLYPHS && custom_valid[token]) {
        grid.writeByte((u8) token);
      } else {
        grid.writeCodepoint(token);
      }
    }
  }
  grid.setCursor(restore_cursor_x, restore_cursor_y);
  top_right_overlay_visible = usb_surface.copyTopRightOverlay(
    top_right_overlay_rows, top_right_overlay_width,
    top_right_overlay_height, top_right_overlay_clear_border);
#endif
  usb_surface.end();
  usb_screen_active = false;
  display_mode_revision++;
#if defined(MK61_DISPLAY_LCD1602)
  // Восстанавливаем физический текстовый дисплей перед включением. Так на экране
  // остаётся владеющий им интерфейс переднего плана, а не кадр калькулятора при
  // всё ещё активном модальном экране FOCAL/TinyBASIC.
  clear();
  for(u8 slot = 0; slot < usb_screen::Surface::CUSTOM_GLYPHS; slot++) {
    if(restore_glyph_valid[slot]) createChar(slot, restore_glyphs[slot]);
    else clearCustomChar(slot);
  }
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    setCursor(0, row);
    for(u8 col = 0; col < lcd_display::COLS; col++) {
      const u16 token = restore_cells[row][col];
      if(restore_custom[row][col] &&
         token < usb_screen::Surface::CUSTOM_GLYPHS &&
         restore_glyph_valid[token]) {
        write((u8) token);
      } else {
        write(lcdByteForCanonicalToken(token));
      }
    }
  }
  setCursor(restore_cursor_x, restore_cursor_y);
  if(restore_cursor_underline) cursorOn();
  if(restore_cursor_blink) blinkOn();
#else
  cursor_underline = restore_cursor_underline;
  cursor_blink = restore_cursor_blink;
  cursor_blink_phase = restore_cursor_blink;
  cursor_next_blink_ms = restore_cursor_blink
                       ? millis() + CURSOR_BLINK_MS : 0;
  markScreenDirty();
#endif
  setPhysicalScreenEnabled(true);
}

void MK61Display::setPhysicalScreenEnabled(bool enabled) {
  if(physical_screen_enabled == enabled) return;
  physical_screen_enabled = enabled;
#if defined(MK61_DISPLAY_LCD1602)
  if(enabled) display_control |= LCD_DISPLAYON;
  else display_control &= (u8) ~LCD_DISPLAYON;
  sendDisplayControl();
#else
  if(initialized) lcd.LCDEnable(enabled ? 1 : 0);
#endif
}

#endif // MK61_ENABLE_USB_SCREEN
