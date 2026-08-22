#include "display.hpp"
#include "display_symbols.hpp"
#include "exclusive_buffer.hpp"
#include "page_damage.hpp"
#if defined(MK61_DISPLAY_UC1609)
  #include "shared_scratch.hpp"
#endif

#include <string.h>

#if defined(MK61_DISPLAY_LCD1602)

#include "lcd1602_shifted_viewport.hpp"
#include "lcd_6800_4bit_bus.hpp"
#include "lcd_charset.hpp"
#if defined(MK61_OLED1602_WS0010)
  #include "crash_dump.hpp"
  #include "ws0010_charset.hpp"
  #include "ws0010_controller.hpp"
  #include "ws0010_graphics.hpp"
  #include "ws0010_shifted_viewport.hpp"
#endif

static_assert(lcd1602_shifted_viewport::COMMAND_RETURN_HOME == LCD_RETURNHOME,
              "HD44780 Return Home command mismatch");
#if defined(MK61_OLED1602_WS0010)
static_assert(ws0010_shifted_viewport::COMMAND_RETURN_HOME == LCD_RETURNHOME,
              "WS0010 Return Home command mismatch");
static_assert(ws0010_shifted_viewport::DDRAM_COLS == lcd_display::DDRAM_COLS,
              "WS0010 viewport must expose all 64 DDRAM columns");

static void noteWs0010InitializationPhase(ws0010::InitializationPhase phase) {
  // "DS" + profile byte + phase fits the existing compact crash detail.
  // No new retained fields or RAM journal are required.
  crash_dump::update_runtime(
    crash_dump::RUNTIME_DISPLAY,
    0x44530000UL | (u32) phase,
    millis());
}
#else
static_assert(lcd1602_shifted_viewport::DDRAM_COLS ==
              lcd_display::DDRAM_COLS,
              "HD44780 viewport geometry mismatch");
#endif
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

static constexpr u8 LCD_BUSY_ACTIVE = 0x01u;
static constexpr u8 LCD_BUSY_OBSERVED = 0x02u;
static constexpr u8 LCD_BUSY_FAULTED = 0x04u;

static constexpr u32 lcdClearDelayUs(void) {
#if defined(MK61_OLED1602_WS0010)
  return ws0010::CLEAR_DELAY_US;
#else
  return 2000;
#endif
}

static constexpr u32 lcdReturnHomeDelayUs(void) {
#if defined(MK61_OLED1602_WS0010)
  return ws0010::COMMAND_DELAY_US;
#else
  return 2000;
#endif
}

static inline u8 lcdLogicalColumn(u8 shift, u8 visible_column) {
  return character_display_geometry::physicalAddress(shift, visible_column);
}

static inline u8 lcdHardwareColumn(u8 shift, u8 visible_column) {
  return lcdLogicalColumn(shift, visible_column);
}

#if MK61_ENABLE_USB_SCREEN
static u16 canonicalLcdToken(u8 value) {
#if defined(MK61_OLED1602_WS0010)
  switch(value) {
    case ws0010_charset::cgram::GREATER_OR_EQUAL:
      return display_symbol::uc1609::GE;
    case ws0010_charset::cgram::POWER_Y:
      return display_symbol::uc1609::POWY;
    case ws0010_charset::cgram::XOR:
      return display_symbol::uc1609::XOR;
    case ws0010_charset::cgram::NOT_EQUAL:
      return display_symbol::uc1609::NOT_EQUAL;
    case ws0010_charset::cgram::SQUARE_ROOT:
      return display_symbol::uc1609::SQRT;
    case ws0010_charset::cgram::CYCLE_ARROW:
      return display_symbol::uc1609::CYC_ARROW;
    case ws0010_charset::cgram::POWER_X:
      return display_symbol::uc1609::POW_X;
    case ws0010_charset::cgram::POWER_2:
      return display_symbol::uc1609::POW2;
    case ws0010_charset::RIGHT_ARROW:
      return display_symbol::uc1609::RT_ARROW;
    case ws0010_charset::LEFT_ARROW:
      return display_symbol::uc1609::LT_ARROW;
    case ws0010_charset::PI_SYMBOL: return display_symbol::uc1609::PI_SYMBOL;
    case ws0010_charset::DEGREE: return display_symbol::uc1609::GRAD;
    case ws0010_charset::DIVIDE: return display_symbol::uc1609::DIVIDE;
    default: return ws0010_charset::canonicalForByte(value);
  }
#elif defined(MK61_LCD1602_A02)
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
#if defined(MK61_OLED1602_WS0010)
  u8 value = 0;
  // canonicalLcdToken() represents otherwise-unknown WS0010 CGROM cells as
  // U+E000..U+E0FF.  Accept that private-use form here as well as Unicode so
  // a USB Screen round-trip preserves every physical controller byte.
  if(ws0010_charset::canonicalToByte(token, value)) return value;
  switch(token) {
    case display_symbol::uc1609::GE:
      return ws0010_charset::cgram::GREATER_OR_EQUAL;
    case display_symbol::uc1609::POWY:
      return ws0010_charset::cgram::POWER_Y;
    case display_symbol::uc1609::XOR:
      return ws0010_charset::cgram::XOR;
    case display_symbol::uc1609::NOT_EQUAL:
      return ws0010_charset::cgram::NOT_EQUAL;
    case display_symbol::uc1609::SQRT:
      return ws0010_charset::cgram::SQUARE_ROOT;
    case display_symbol::uc1609::CYC_ARROW:
      return ws0010_charset::cgram::CYCLE_ARROW;
    case display_symbol::uc1609::POW_X:
      return ws0010_charset::cgram::POWER_X;
    case display_symbol::uc1609::RT_ARROW:
      return ws0010_charset::RIGHT_ARROW;
    case display_symbol::uc1609::LT_ARROW:
      return ws0010_charset::LEFT_ARROW;
    case display_symbol::uc1609::UP_ARROW:
      return ws0010_charset::UP_ARROW_FALLBACK;
    case display_symbol::uc1609::EM1:
      return ws0010_charset::INVERSE_MARKER_FALLBACK;
    case display_symbol::uc1609::PI_SYMBOL: return ws0010_charset::PI_SYMBOL;
    case display_symbol::uc1609::POW2:
      return ws0010_charset::cgram::POWER_2;
    case display_symbol::uc1609::GRAD:      return ws0010_charset::DEGREE;
    case display_symbol::uc1609::DIVIDE:    return ws0010_charset::DIVIDE;
    default: return token <= 0xFF ? (u8) token : (u8) '?';
  }
#else
  for(u16 value = 0; value <= 0xFF; value++) {
    if(canonicalLcdToken((u8) value) == token) return (u8) value;
  }
  return token <= 0xFF ? (u8) token : (u8) '?';
#endif
}
#endif

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
#if MK61_LCD1602_BUSY_FLAG || defined(MK61_OLED1602_WS0010)
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

static inline void lcdPrepareOutputPinLow(PinName pin) {
  if(pin == NC) return;

  // Unlike pinMode(), digitalWriteFast() and direct MODER access do not
  // enable the GPIO peripheral clock.  The WS0010 backend does not construct
  // LiquidCrystal, so GPIOA (DB5..DB7 on mini V3) can still be clock-gated at
  // the first display transaction.  Enable the port before preloading ODR,
  // then establish the complete push-pull/no-pull configuration explicitly.
  (void) set_GPIO_Port_Clock(STM_PORT(pin));
  lcdWritePin(pin, false);
  pin_function(pin, STM_PIN_DATA(STM_MODE_OUTPUT_PP, GPIO_NOPULL, 0));
  lcdWritePin(pin, false);
}

static inline void lcdSetPinOutput(PinName pin, bool output) {
  GPIO_TypeDef* const port = get_GPIO_Port(STM_PORT(pin));
  const u32 shift = (u32) STM_PIN(pin) * 2u;
  const u32 mask = 0x3u << shift;
  const u32 mode = output ? (0x1u << shift) : 0u;
  port->MODER = (port->MODER & ~mask) | mode;
}

static inline void lcdDisablePull(PinName pin) {
  GPIO_TypeDef* const port = get_GPIO_Port(STM_PORT(pin));
  const u32 shift = (u32) STM_PIN(pin) * 2u;
  port->PUPDR &= ~(0x3u << shift);
}

static inline void lcdSetDataOutput(const LcdParallelBus& bus, bool output) {
  for(u8 i = 0; i < 4; i++) lcdSetPinOutput(bus.data[i], output);
}

struct LcdHardwareWriteSink {
  const LcdParallelBus& bus;

  void setOutputLow(PinName pin) {
    lcdPrepareOutputPinLow(pin);
  }

  void setRwOutputLow(void) { setOutputLow(bus.rw); }
  void setRsOutputLow(void) { setOutputLow(bus.rs); }
  void setEnableOutputLow(void) { setOutputLow(bus.enable); }
  void setDataOutputLow(u8 bit) { setOutputLow(bus.data[bit]); }
  void rw(bool high) {
    if(bus.rw != NC) lcdWritePin(bus.rw, high);
  }
  void rs(bool high) { lcdWritePin(bus.rs, high); }
  void enable(bool high) { lcdWritePin(bus.enable, high); }
  void data(u8 bit, bool high) { lcdWritePin(bus.data[bit], high); }
  void delayMicroseconds(u8 duration) { ::delayMicroseconds(duration); }
};

struct LcdHardwareBusySource {
  const LcdParallelBus& bus;

  void enable(bool high) { lcdWritePin(bus.enable, high); }
  bool busyBit(void) { return digitalReadFast(bus.data[3]) != LOW; }
  void delayMicroseconds(u8 duration) { ::delayMicroseconds(duration); }
};

static inline void lcdWriteNibble(const LcdParallelBus& bus, u8 nibble) {
  LcdHardwareWriteSink sink = {bus};
  lcd_6800_4bit_bus::writeNibble(sink, nibble);
}

static inline void lcdWriteByte(const LcdParallelBus& bus, u8 value, bool data) {
  LcdHardwareWriteSink sink = {bus};
  lcd_6800_4bit_bus::writeByte(sink, value, data);
}

#if MK61_LCD1602_BUSY_FLAG
static LcdReadyResult lcdWaitReady(const LcdParallelBus& bus, u32 timeout_us) {
  bool saw_busy = false;
  const u32 started_at = micros();

  lcdWritePin(bus.enable, false);
  // FT pins tolerate the 5 V WS0010 outputs only as digital inputs without
  // internal pull-up/pull-down resistors.  Force that state explicitly rather
  // than inheriting an Arduino pin mode from a previous owner.
  for(u8 i = 0; i < 4; i++) lcdDisablePull(bus.data[i]);
  lcdSetDataOutput(bus, false);
  lcdWritePin(bus.rs, false);
  lcdWritePin(bus.rw, true);
  delayMicroseconds(1);

  LcdReadyResult result = LcdReadyResult::TIMEOUT;
  do {
    LcdHardwareBusySource source = {bus};
    const bool busy = lcd_6800_4bit_bus::readBusyFlagByte(source);

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
#if defined(MK61_OLED1602_WS0010)
  : ddram_shadow{{0}},
    ddram_home_shadow{{0}},
#else
  : lcd(PIN_LCD_RS, PIN_LCD_E, PIN_LCD_DB4, PIN_LCD_DB5, PIN_LCD_DB6, PIN_LCD_DB7),
    ddram_shadow{{0}},
#endif
    shadow_cursor_x(0),
    shadow_cursor_y(0),
    custom_glyphs{{0}},
    custom_valid{false},
    display_control(LCD_DISPLAYON | LCD_CURSOROFF | LCD_BLINKOFF),
    busy_flag_state(0),
    busy_flag_timeouts(0),
    shifted_viewport_active(false),
    shifted_viewport_shift(0)
#if defined(MK61_OLED1602_WS0010)
    , reinitialization_count(0),
    initialization_phase(ws0010::InitializationPhase::IDLE),
    ws0010_graphics_active(false),
    oled_protection_state()
#endif
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
#if defined(MK61_OLED1602_WS0010)
  memset(ddram_home_shadow, ' ', sizeof(ddram_home_shadow));
#endif
}

#if defined(MK61_OLED1602_WS0010)
bool MK61Display::initializeWs0010Controller(bool cold_start,
                                             bool display_on_after_init) {
  initialization_phase = ws0010::InitializationPhase::GPIO_SAFE;
  noteWs0010InitializationPhase(initialization_phase);

  const LcdParallelBus bus = lcdParallelBus();
  if(!bus.validForWrite() || bus.rw == NC) {
    initialization_phase = ws0010::InitializationPhase::IDLE;
    noteWs0010InitializationPhase(initialization_phase);
    return false;
  }
  // Establish a completely inert 6800 bus before any line is allowed to
  // become an output. RW and E are always LOW in the qualified profile.
  LcdHardwareWriteSink hardware_sink = {bus};
  lcd_6800_4bit_bus::prepareWrite(hardware_sink);
#if MK61_LCD1602_BUSY_FLAG
  // Raw synchronization nibbles cannot be followed by a read, but every full
  // byte beginning with Function Set must complete with the WS0010 BF/AC read.
  busy_flag_state = LCD_BUSY_ACTIVE;
#endif

  initialization_phase = ws0010::InitializationPhase::POWER_WAIT;
  noteWs0010InitializationPhase(initialization_phase);
  delay(cold_start ? ws0010::POWER_STABILIZATION_MS
                   : ws0010::RECOVERY_STABILIZATION_MS);
  initialization_phase = ws0010::InitializationPhase::BUS_SYNC;
  noteWs0010InitializationPhase(initialization_phase);
  struct InitSink {
    const LcdParallelBus& bus;
    u8& busy_state;
    u32& timeouts;
    void nibble(u8 value) {
      lcdWriteNibble(bus, value);
      delayMicroseconds(ws0010::COMMAND_DELAY_US);
    }
    void delayMilliseconds(u8 duration) { ::delay(duration); }
    void command(u8 value) {
      if((busy_state & LCD_BUSY_FAULTED) != 0) return;
      lcdWriteByte(bus, value, false);
#if MK61_LCD1602_BUSY_FLAG
      const LcdReadyResult ready = lcdWaitReady(bus, 8000);
      if(ready == LcdReadyResult::TIMEOUT) {
        timeouts++;
        busy_state |= LCD_BUSY_FAULTED;
        return; // 8 ms already exceeds every documented execution time.
      }
      if(ready == LcdReadyResult::READY_AFTER_BUSY) {
        busy_state |= LCD_BUSY_OBSERVED;
        return;
      }
#endif
      // A tied-low or not-yet-driven BF must never shorten the conservative
      // timing. The full two-strobe read above is still performed.
      delayMicroseconds(value == ws0010::CLEAR_DISPLAY
                          ? ws0010::CLEAR_DELAY_US
                          : ws0010::COMMAND_DELAY_US);
    }
  } sink = {bus, busy_flag_state, busy_flag_timeouts};
  if(cold_start) {
    ws0010::emitFourBitInitialization(sink, display_on_after_init);
  } else {
    ws0010::emitFourBitRecovery(sink, display_on_after_init);
  }
  if((busy_flag_state & LCD_BUSY_FAULTED) != 0) {
    initialization_phase = ws0010::InitializationPhase::IDLE;
    noteWs0010InitializationPhase(initialization_phase);
    return false;
  }
  initialization_phase = ws0010::InitializationPhase::CONTROLLER_CONFIGURED;
  noteWs0010InitializationPhase(initialization_phase);
  return true;
}

void MK61Display::refreshWs0010VisibleShadow(
    const u8 cells[lcd_display::ROWS][lcd_display::DDRAM_COLS], u8 shift) {
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    for(u8 col = 0; col < lcd_display::COLS; col++) {
      ddram_shadow[row][col] = cells[row][
        ws0010_shifted_viewport::physicalAddress(shift, col)];
    }
  }
}

void MK61Display::restoreWs0010DdramAddress(void) {
  // In graphics mode 0x40/0x80 select GDRAM coordinates rather than character
  // address spaces.  The retained CGRAM catalogue will be restored when the
  // isolated graphics transaction returns through reinitialize().
  if(ws0010_graphics_active) return;
  const u8 hardware_x = shifted_viewport_active
                      ? lcdHardwareColumn(shifted_viewport_shift,
                                          shadow_cursor_x)
                      : shadow_cursor_x;
  sendCommand(ws0010::characterDdramAddressCommand(shadow_cursor_y,
                                                    hardware_x));
}
#endif

void MK61Display::begin(u8 cols, u8 rows) {
  (void) cols;
  (void) rows;
  busy_flag_state = 0;
  busy_flag_timeouts = 0;
#if defined(MK61_OLED1602_WS0010)
  // A real power-on/brown-out resets both chips, so the exact manufacturer
  // sequence is sufficient. Every other MCU reset must assume the separately
  // powered OLED stopped in an arbitrary 4-bit transfer phase.
  bool cold_start = false;
#if defined(RCC_CSR_PORRSTF) && defined(RCC_CSR_BORRSTF)
  const u32 reset_flags = crash_dump::boot_reset_flags();
  cold_start = (reset_flags & (RCC_CSR_PORRSTF | RCC_CSR_BORRSTF)) != 0;
#endif
  const bool controller_ready =
    initializeWs0010Controller(cold_start, false);
#else
  #if MK61_LCD1602_BUSY_FLAG
  // RW должен быть прижат к записи ещё до стандартной последовательности
  // инициализации LiquidCrystal.
  digitalWrite(PIN_LCD_RW, LOW);
  pinMode(PIN_LCD_RW, OUTPUT);
  #endif
  lcd.begin(lcd_display::COLS, lcd_display::ROWS);
  lcd.noCursor();
  lcd.noBlink();
#endif
  display_control = LCD_DISPLAYON | LCD_CURSOROFF | LCD_BLINKOFF;
#if !defined(MK61_OLED1602_WS0010)
  probeBusyFlag();
#endif
  memset(ddram_shadow, ' ', sizeof(ddram_shadow));
#if defined(MK61_OLED1602_WS0010)
  memset(ddram_home_shadow, ' ', sizeof(ddram_home_shadow));
#endif
  shadow_cursor_x = 0;
  shadow_cursor_y = 0;
  shifted_viewport_active = false;
  shifted_viewport_shift = 0;
#if defined(MK61_OLED1602_WS0010)
  ws0010_graphics_active = false;
  oled_protection_state.configure(oled_protection::Timeout::MINUTES_15,
                                  millis());
  if(controller_ready) {
    // Clear all controller CGRAM while D=0. Clear Display affects DDRAM only;
    // without this pass a warm reset could briefly expose a previous owner's
    // glyphs before the splash/default font is loaded.
    initialization_phase = ws0010::InitializationPhase::RESTORING_CGRAM;
    noteWs0010InitializationPhase(initialization_phase);
    sendCommand(LCD_SETCGRAMADDR);
    for(u8 address = 0; address < 64; address++) sendData(0);
    sendCommand(LCD_SETDDRAMADDR);
    sendDisplayControl();
    initialization_phase = busyFlagFaulted()
                         ? ws0010::InitializationPhase::IDLE
                         : ws0010::InitializationPhase::READY;
  } else {
    initialization_phase = ws0010::InitializationPhase::IDLE;
  }
  noteWs0010InitializationPhase(initialization_phase);
#endif
}

bool MK61Display::reinitialize(void) {
#if !defined(MK61_OLED1602_WS0010)
  return false;
#else
  const bool restore_shifted = shifted_viewport_active;
  const u8 restore_shift = shifted_viewport_shift;
  const u8 restore_cursor_x = shadow_cursor_x;
  const u8 restore_cursor_y = shadow_cursor_y;
  const u8 restore_control = display_control;

  // Keep D=0 until CGRAM and both retained windows are coherent. The final
  // sendDisplayControl() below restores the exact on/off/cursor/blink state in
  // one command and prevents a flash of half-restored contents.
  if(!initializeWs0010Controller(false, false)) return false;
  ws0010_graphics_active = false;

  initialization_phase = ws0010::InitializationPhase::RESTORING_CGRAM;
  noteWs0010InitializationPhase(initialization_phase);
  for(u8 slot = 0; slot < 8; slot++) {
    sendCommand((u8) (LCD_SETCGRAMADDR | (slot << 3)));
    for(u8 row = 0; row < 8; row++) {
      sendData(custom_valid[slot] ? custom_glyphs[slot][row] : 0);
    }
  }

  initialization_phase = ws0010::InitializationPhase::RESTORING_DDRAM;
  noteWs0010InitializationPhase(initialization_phase);
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    sendCommand((u8) (LCD_SETDDRAMADDR | (row == 0 ? 0x00u : 0x40u)));
    for(u8 col = 0; col < lcd_display::COLS; col++) {
      sendData(ddram_home_shadow[row][col]);
    }
  }

  shifted_viewport_active = false;
  shifted_viewport_shift = 0;
  if(restore_shifted) {
    // The owner deliberately retains the hidden 2x64 layout.  Recovery can
    // nevertheless reconstruct both compact windows immediately; the next
    // owner redraw replenishes the remaining hidden controller DDRAM.
    for(u8 row = 0; row < lcd_display::ROWS; row++) {
      for(u8 col = 0; col < lcd_display::COLS; col++) {
        const u8 address = ws0010_shifted_viewport::physicalAddress(
          restore_shift, col);
        sendCommand(ws0010_shifted_viewport::setDdramAddressCommand(row,
                                                                    address));
        sendData(ddram_shadow[row][col]);
      }
    }
    const auto emit = [this](ws0010_shifted_viewport::BusWrite write) {
      sendCommand(write.value, write.value ==
                  ws0010_shifted_viewport::COMMAND_RETURN_HOME
                    ? lcdReturnHomeDelayUs() : 0);
    };
    (void) ws0010_shifted_viewport::shiftTo(
      shifted_viewport_active, shifted_viewport_shift, restore_shift, emit);
  }

  // Restore the physical address counter directly. Calling the public
  // setCursor() here would redirect to usb_surface when recovery is requested
  // from the multiplexed terminal during an active USB Screen session. Keep
  // D=0 until AC is correct as well: otherwise cursor/blink can flash at the
  // last restored byte before moving to the logical cursor.
  shadow_cursor_x = restore_cursor_x < lcd_display::COLS
                  ? restore_cursor_x : (u8) (lcd_display::COLS - 1u);
  shadow_cursor_y = restore_cursor_y < lcd_display::ROWS
                  ? restore_cursor_y : (u8) (lcd_display::ROWS - 1u);
  restoreWs0010DdramAddress();
  display_control = restore_control;
  sendDisplayControl();
  if(busyFlagFaulted()) {
    initialization_phase = ws0010::InitializationPhase::IDLE;
    noteWs0010InitializationPhase(initialization_phase);
    return false;
  }
  reinitialization_count++;
  initialization_phase = ws0010::InitializationPhase::READY;
  noteWs0010InitializationPhase(initialization_phase);
  return true;
#endif
}

#if defined(MK61_OLED1602_WS0010)
bool MK61Display::beginWs0010Graphics(void) {
#if !MK61_WS0010_GRAPHICS_100X16
  return false;
#else
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) return false;
#endif
  if(ws0010_graphics_active) {
    // Every update transaction starts hidden as well; a second full frame
    // must not tear merely because graphics mode was already selected.
    sendCommand(ws0010::DISPLAY_OFF);
    return true;
  }
  // Cursor/blink are meaningless in graphics mode, but they are logical UI
  // state and must survive the experiment. Hide them on the controller
  // without mutating display_control; reinitialize() will restore the exact
  // character-mode value on return. WS0010 requires G/C to change while the
  // display is off, so keep it hidden until presentWs0010Graphics().
  ws0010::emitHiddenGraphicsMode(
    [this](u8 command) { sendCommand(command); });
  ws0010_graphics_active = true;
  return true;
#endif
}

bool MK61Display::writeWs0010GraphicsPage(u8 page, u8 first,
                                          const u8* data, usize count) {
#if !MK61_WS0010_GRAPHICS_100X16
  (void) page;
  (void) first;
  (void) data;
  (void) count;
  return false;
#else
  if(!ws0010_graphics_active) return false;
  const auto command = [this](u8 value) { sendCommand(value); };
  const auto write_data = [this](u8 value) { sendData(value); };
  return ws0010_graphics::streamPage(page, first, data, count,
                                     command, write_data);
#endif
}

bool MK61Display::presentWs0010Graphics(void) {
#if !MK61_WS0010_GRAPHICS_100X16
  return false;
#else
  if(!ws0010_graphics_active) return false;
  // sendDisplayControl() honours both the logical display state and OLED
  // protection; it cannot accidentally wake a deliberately sleeping panel.
  sendDisplayControl();
  return true;
#endif
}

bool MK61Display::showWs0010GraphicsFrame(const u8* frame, usize size) {
#if !MK61_WS0010_GRAPHICS_100X16
  (void) frame;
  (void) size;
  return false;
#else
  if(frame == NULL || size != ws0010_graphics::FRAME_BYTES ||
     !beginWs0010Graphics()) return false;
  for(u8 page = 0; page < ws0010_graphics::PAGES; page++) {
    if(!writeWs0010GraphicsPage(page, 0,
         frame + (usize) page * ws0010_graphics::WIDTH,
         ws0010_graphics::WIDTH)) return false;
  }
  return presentWs0010Graphics();
#endif
}

void MK61Display::endWs0010Graphics(void) {
  if(!ws0010_graphics_active) return;
  // A full recovery is intentional: it proves character mode, CGRAM, the two
  // compact windows and display-control are restored after every experiment.
  (void) reinitialize();
}

bool MK61Display::returnWs0010Home(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) return false;
#endif
  if(ws0010_graphics_active) return false;
  sendCommand(ws0010::RETURN_HOME, lcdReturnHomeDelayUs());
  shifted_viewport_active = false;
  shifted_viewport_shift = 0;
  memcpy(ddram_shadow, ddram_home_shadow, sizeof(ddram_shadow));
  shadow_cursor_x = 0;
  shadow_cursor_y = 0;
  return true;
}

bool MK61Display::shiftWs0010Cursor(bool right) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) return false;
#endif
  if(ws0010_graphics_active || shifted_viewport_active) return false;
  if((right && shadow_cursor_x >= lcd_display::COLS - 1u) ||
     (!right && shadow_cursor_x == 0)) return false;
  sendCommand(right ? ws0010::CURSOR_RIGHT : ws0010::CURSOR_LEFT);
  shadow_cursor_x = right ? (u8) (shadow_cursor_x + 1u)
                          : (u8) (shadow_cursor_x - 1u);
  return true;
}

bool MK61Display::showWs0010EntryModeTest(bool automatic_shift) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) return false;
#endif
  if(ws0010_graphics_active) return false;

  if(!automatic_shift) {
    clear();
    setCursor(0, 0);
    print("ENTRY DEC: CBA  ");
    sendCommand(ws0010::ENTRY_DECREMENT_NO_SHIFT);
    setCursor(7, 1);
    sendData('A');
    sendData('B');
    sendData('C');
    ddram_shadow[1][7] = ddram_home_shadow[1][7] = 'A';
    ddram_shadow[1][6] = ddram_home_shadow[1][6] = 'B';
    ddram_shadow[1][5] = ddram_home_shadow[1][5] = 'C';
    sendCommand(ws0010::ENTRY_INCREMENT_NO_SHIFT);
    setCursor(8, 1);
    cursorOn();
    return true;
  }

  u8 cells[lcd_display::ROWS][lcd_display::DDRAM_COLS];
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    for(u8 col = 0; col < lcd_display::DDRAM_COLS; col++) {
      cells[row][col] = (u8) ('A' + ((row * 7u + col) % 26u));
    }
  }
  renderShiftedViewport(cells, 0);
  sendCommand(ws0010::ENTRY_INCREMENT_WITH_SHIFT);
  sendCommand((u8) (LCD_SETDDRAMADDR | 15u));
  sendData('*');
  cells[0][15] = '*';
  sendCommand(ws0010::ENTRY_INCREMENT_NO_SHIFT);
  shifted_viewport_active = true;
  shifted_viewport_shift = 1;
  memcpy(ddram_home_shadow[0], cells[0], lcd_display::COLS);
  memcpy(ddram_home_shadow[1], cells[1], lcd_display::COLS);
  refreshWs0010VisibleShadow(cells, shifted_viewport_shift);
  shadow_cursor_x = 0;
  shadow_cursor_y = 0;
  return true;
}

bool MK61Display::showWs0010ZeroRunTest(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) return false;
#endif
  if(ws0010_graphics_active || busyFlagFaulted()) return false;

  // A field report reproduced 4-bit desynchronisation specifically on long
  // runs of zero data. Keep the OLED hidden, issue a much longer run than the
  // original reproducer, then prove command/data alignment with two markers.
  const u32 timeouts_before = busy_flag_timeouts;
  sendCommand(ws0010::DISPLAY_OFF);
  sendCommand(ws0010::characterDdramAddressCommand(0, 0));
  for(u16 index = 0; index < 256; index++) sendData(0x00);
  sendCommand(ws0010::CLEAR_DISPLAY, ws0010::CLEAR_DELAY_US);
  if(busyFlagFaulted() || busy_flag_timeouts != timeouts_before) {
    (void) reinitialize();
    return false;
  }

  static constexpr char row0[] = "ZERO/BF 256: OK ";
  static constexpr char row1[] = "4BIT SYNC: OK   ";
  static_assert(sizeof(row0) - 1u == lcd_display::COLS &&
                sizeof(row1) - 1u == lcd_display::COLS,
                "WS0010 zero-run markers must fill both visible rows");
  const char* rows[lcd_display::ROWS] = {row0, row1};
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    sendCommand(ws0010::characterDdramAddressCommand(row, 0));
    for(u8 col = 0; col < lcd_display::COLS; col++) {
      sendData((u8) rows[row][col]);
    }
  }
  if(busyFlagFaulted() || busy_flag_timeouts != timeouts_before) {
    (void) reinitialize();
    return false;
  }
  // Commit the software shadow only after the complete physical transaction
  // succeeds. A failed qualification test must never be restored as "OK".
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    memcpy(ddram_shadow[row], rows[row], lcd_display::COLS);
    memcpy(ddram_home_shadow[row], rows[row], lcd_display::COLS);
  }
  shadow_cursor_x = 0;
  shadow_cursor_y = 0;
  shifted_viewport_active = false;
  shifted_viewport_shift = 0;
  restoreWs0010DdramAddress();
  display_control |= LCD_DISPLAYON;
  oled_protection_state.force(true, millis());
  sendDisplayControl();
  if(busyFlagFaulted()) {
    (void) reinitialize();
    return false;
  }
  return true;
}

void MK61Display::configureOledProtection(oled_protection::Timeout timeout,
                                          u32 now) {
  oled_protection_state.configure(timeout, now);
}

void MK61Display::setDisplayEnabled(bool enabled, u32 now) {
  oled_protection_state.force(enabled, now);
  if(enabled) display_control |= LCD_DISPLAYON;
  else display_control &= (u8) ~LCD_DISPLAYON;
#if MK61_ENABLE_USB_SCREEN
  if(physical_screen_enabled)
#else
  if(true)
#endif
    sendDisplayControl();
}

void MK61Display::noteDisplayActivity(u32 now) {
  if(oled_protection_state.activity(now) ==
     oled_protection::Transition::DISPLAY_ON) {
    display_control |= LCD_DISPLAYON;
#if MK61_ENABLE_USB_SCREEN
    if(physical_screen_enabled)
#else
    if(true)
#endif
      sendDisplayControl();
  }
}

void MK61Display::pollOledProtection(u32 now) {
  if(oled_protection_state.poll(now) ==
     oled_protection::Transition::DISPLAY_OFF) {
    display_control &= (u8) ~LCD_DISPLAYON;
#if MK61_ENABLE_USB_SCREEN
    if(physical_screen_enabled)
#else
    if(true)
#endif
      sendDisplayControl();
  }
}
#endif

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
  sendCommand(LCD_CLEARDISPLAY, lcdClearDelayUs());
  memset(ddram_shadow, ' ', sizeof(ddram_shadow));
#if defined(MK61_OLED1602_WS0010)
  memset(ddram_home_shadow, ' ', sizeof(ddram_home_shadow));
#endif
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
  const u8 hardware_x = shifted_viewport_active
                      ? lcdHardwareColumn(shifted_viewport_shift,
                                          shadow_cursor_x)
                      : shadow_cursor_x;
  sendCommand((u8) (LCD_SETDDRAMADDR | (row_address + hardware_x)));
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
  for(u8 row = 0; row < 8; row++) {
#if defined(MK61_OLED1602_WS0010)
    custom_glyphs[nChar][row] = ws0010::normalizeCgramRow(row, glyph[row]);
#else
    custom_glyphs[nChar][row] = (u8) (glyph[row] & 0x1Fu);
#endif
  }
  custom_valid[nChar] = true;
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.createChar(nChar, custom_glyphs[nChar]);
    usb_surface.flush(millis());
    return;
  }
#endif
#if defined(MK61_OLED1602_WS0010)
  // CGRAM address commands become graphics-page commands in G/C=1. Retain the
  // catalogue only; endWs0010Graphics()/reinitialize() will install it safely
  // after returning to character mode.
  if(ws0010_graphics_active) return;
#endif
  sendCommand((u8) (LCD_SETCGRAMADDR | (nChar << 3)));
  for(u8 row = 0; row < 8; row++) sendData(custom_glyphs[nChar][row]);
#if defined(MK61_OLED1602_WS0010)
  restoreWs0010DdramAddress();
#endif
}

void MK61Display::clearCustomChars(void) {
  memset(custom_glyphs, 0, sizeof(custom_glyphs));
  memset(custom_valid, 0, sizeof(custom_valid));
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.clearCustomChars();
    usb_surface.flush(millis());
    return;
  }
#endif
#if defined(MK61_OLED1602_WS0010)
  if(ws0010_graphics_active) return;
#endif
  // Clearing the software catalogue must clear the controller as well; a
  // later reinitialize must not resurrect glyphs the current owner released.
  sendCommand(LCD_SETCGRAMADDR);
  for(u8 address = 0; address < 64; address++) sendData(0);
#if defined(MK61_OLED1602_WS0010)
  restoreWs0010DdramAddress();
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
#if defined(MK61_OLED1602_WS0010)
  // WS0010 keeps a compact snapshot of the window that is physically visible;
  // the remaining 96 hidden bytes live only in the controller's own DDRAM.
  value = ddram_shadow[y][x];
#else
  const u8 physical_x = shifted_viewport_active
                      ? lcdLogicalColumn(
                          shifted_viewport_shift, x) : x;
  value = ddram_shadow[y][physical_x];
#endif
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
  memset(custom_glyphs[nChar], 0, sizeof(custom_glyphs[nChar]));
  custom_valid[nChar] = false;
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.clearCustomChar(nChar);
    usb_surface.flush(millis());
    return;
  }
#endif
#if defined(MK61_OLED1602_WS0010)
  if(ws0010_graphics_active) return;
#endif
  sendCommand((u8) (LCD_SETCGRAMADDR | (nChar << 3)));
  for(u8 row = 0; row < 8; row++) sendData(0);
#if defined(MK61_OLED1602_WS0010)
  restoreWs0010DdramAddress();
#endif
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

#if defined(MK61_OLED1602_WS0010)
  const auto emit = [this](ws0010_shifted_viewport::BusWrite write) {
    if(write.data) {
      sendData(write.value);
    } else {
      const u32 delay_us = write.value ==
          ws0010_shifted_viewport::COMMAND_RETURN_HOME
            ? lcdReturnHomeDelayUs() : 0;
      sendCommand(write.value, delay_us);
    }
  };
  if(ws0010_shifted_viewport::render(
       shifted_viewport_active, shifted_viewport_shift, cells, shift, emit)) {
    for(u8 row = 0; row < lcd_display::ROWS; row++) {
      memcpy(ddram_home_shadow[row], cells[row], lcd_display::COLS);
    }
    refreshWs0010VisibleShadow(cells, shift);
    restoreWs0010DdramAddress();
  }
#else
  const auto emit = [this](lcd1602_shifted_viewport::BusWrite write) {
    if(write.data) {
      sendData(write.value);
    } else {
      const u32 delay_us = write.value ==
          lcd1602_shifted_viewport::COMMAND_RETURN_HOME
            ? lcdReturnHomeDelayUs() : 0;
      sendCommand(write.value, delay_us);
    }
  };
  (void) lcd1602_shifted_viewport::render(
      ddram_shadow, shifted_viewport_active, shifted_viewport_shift,
      cells, shift, emit);
#endif
}

bool MK61Display::shiftShiftedViewport(
    const u8 cells[lcd_display::ROWS][lcd_display::DDRAM_COLS], u8 shift) {
  if(cells == NULL || shift >= lcd_display::DDRAM_COLS) return false;
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
    return true;
  }
#endif

  if(!shifted_viewport_active) return false;
  if((display_control & (LCD_CURSORON | LCD_BLINKON)) != 0) {
    display_control &= (u8) ~(LCD_CURSORON | LCD_BLINKON);
    sendDisplayControl();
  }

#if defined(MK61_OLED1602_WS0010)
  const auto emit = [this](ws0010_shifted_viewport::BusWrite write) {
    sendCommand(write.value, write.value ==
                ws0010_shifted_viewport::COMMAND_RETURN_HOME
                  ? lcdReturnHomeDelayUs() : 0);
  };
  if(!ws0010_shifted_viewport::shiftTo(
       shifted_viewport_active, shifted_viewport_shift, shift, emit)) {
    return false;
  }
  refreshWs0010VisibleShadow(cells, shift);
  return true;
#else
  // The HD44780 renderer already compares against its complete 2x40 shadow;
  // for an unchanged owner layout this emits only the shortest shift command
  // sequence and therefore provides the same fast path.
  const auto emit = [this](lcd1602_shifted_viewport::BusWrite write) {
    if(write.data) sendData(write.value);
    else sendCommand(write.value, write.value ==
                     lcd1602_shifted_viewport::COMMAND_RETURN_HOME
                       ? lcdReturnHomeDelayUs() : 0);
  };
  return lcd1602_shifted_viewport::render(
    ddram_shadow, shifted_viewport_active, shifted_viewport_shift,
    cells, shift, emit);
#endif
}

#if defined(MK61_OLED1602_WS0010)
bool MK61Display::updateWs0010ShiftedViewportRow(
    const u8 cells[lcd_display::ROWS][lcd_display::DDRAM_COLS],
    u8 row, u8 shift) {
  if(cells == NULL || row >= lcd_display::ROWS ||
     shift >= lcd_display::DDRAM_COLS) return false;
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.beginUpdate();
    usb_surface.setCursor(0, row);
    for(u8 col = 0; col < lcd_display::COLS; col++) {
      usb_surface.writeCodepoint(canonicalLcdToken(
        cells[row][ws0010_shifted_viewport::physicalAddress(shift, col)]));
    }
    usb_surface.endUpdate();
    usb_surface.flush(millis());
    return true;
  }
#endif
  if(ws0010_graphics_active) return false;

  const auto emit = [this](ws0010_shifted_viewport::BusWrite write) {
    if(write.data) sendData(write.value);
    else sendCommand(write.value, write.value ==
                     ws0010_shifted_viewport::COMMAND_RETURN_HOME
                       ? lcdReturnHomeDelayUs() : 0);
  };
  if(!ws0010_shifted_viewport::writeRow(
       shifted_viewport_active, shifted_viewport_shift, cells, row, shift,
       emit)) return false;
  for(u8 col = 0; col < lcd_display::COLS; col++) {
    ddram_home_shadow[row][col] = cells[row][
      ws0010_shifted_viewport::independentSourceAddress(
        shifted_viewport_shift, shift, col)];
  }
  for(u8 col = 0; col < lcd_display::COLS; col++) {
    ddram_shadow[row][col] = cells[row][(u8) (
      (shift + col) % lcd_display::DDRAM_COLS)];
  }
  restoreWs0010DdramAddress();
  return true;
}
#endif

void MK61Display::endShiftedViewport(void) {
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) return;
#endif
  if(!shifted_viewport_active) return;
  cursorOff();
#if defined(MK61_OLED1602_WS0010)
  const auto emit = [this](ws0010_shifted_viewport::BusWrite write) {
    sendCommand(write.value, write.value ==
                ws0010_shifted_viewport::COMMAND_RETURN_HOME
                  ? lcdReturnHomeDelayUs() : 0);
  };
  ws0010_shifted_viewport::end(shifted_viewport_active,
                               shifted_viewport_shift, emit);
  memcpy(ddram_shadow, ddram_home_shadow, sizeof(ddram_shadow));
#else
  const auto emit = [this](lcd1602_shifted_viewport::BusWrite write) {
    sendCommand(write.value, write.value ==
                lcd1602_shifted_viewport::COMMAND_RETURN_HOME
                  ? lcdReturnHomeDelayUs() : 0);
  };
  lcd1602_shifted_viewport::end(shifted_viewport_active,
                                shifted_viewport_shift, emit);
#endif
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
#if defined(MK61_OLED1602_WS0010)
  u8 value = 0;
  write(ws0010_charset::unicodeToByte(codepoint, value) ? value : (u8) '?');
#else
  write(codepoint <= 0xFF ? (u8) codepoint : (u8) '?');
#endif
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
  sendCommand(LCD_CLEARDISPLAY, lcdClearDelayUs());
  memset(ddram_shadow, ' ', sizeof(ddram_shadow));
#if defined(MK61_OLED1602_WS0010)
  memset(ddram_home_shadow, ' ', sizeof(ddram_home_shadow));
#endif
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
#if defined(MK61_OLED1602_WS0010)
    memcpy(ddram_home_shadow[row], cells + row * lcd_display::COLS,
           lcd_display::COLS);
#endif
  }
  shadow_cursor_x = 0;
  shadow_cursor_y = 0;
#if defined(MK61_OLED1602_WS0010)
  restoreWs0010DdramAddress();
#endif
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
      const u8 desired =
#if defined(MK61_OLED1602_WS0010)
        ws0010::normalizeCgramRow(row, glyphs[slot][row]);
#else
        (u8) (glyphs[slot][row] & 0x1FU);
#endif
      if(!custom_valid[slot] || custom_glyphs[slot][row] != desired) {
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

  // Гасим экран только на время изменения видимой CGRAM. Основной драйвер сам
  // использует busy flag; HD44780 при аппаратной ошибке возвращается к
  // задержкам, а WS0010 продолжает обязательный BF/AC read и журналирует
  // timeout без опасной повторной записи байта.
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
      sendData(
#if defined(MK61_OLED1602_WS0010)
        ws0010::normalizeCgramRow(row, glyphs[slot][row])
#else
        (u8) (glyphs[slot][row] & 0x1FU)
#endif
      );
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

  shadow_cursor_x = 0;
  shadow_cursor_y = 0;
#if defined(MK61_OLED1602_WS0010)
  // A frame which changes glyph pixels but not cell bytes otherwise leaves AC
  // in CGRAM. Restore DDRAM while the OLED is still hidden, then present the
  // coherent frame.
  restoreWs0010DdramAddress();
#endif
  if(display_off) sendDisplayControl();

  for(usize slot = 0; slot < GLYPH_COUNT; slot++) {
    if((used_slots & ((u8) 1U << slot)) == 0) continue;
    for(usize row = 0; row < GLYPH_ROWS; row++) {
      custom_glyphs[slot][row] =
#if defined(MK61_OLED1602_WS0010)
        ws0010::normalizeCgramRow((u8) row, glyphs[slot][row]);
#else
        (u8) (glyphs[slot][row] & 0x1FU);
#endif
    }
    custom_valid[slot] = true;
  }
  for(u8 row = 0; row < lcd_display::ROWS; row++) {
    memcpy(ddram_shadow[row], cells + row * lcd_display::COLS,
           lcd_display::COLS);
#if defined(MK61_OLED1602_WS0010)
    memcpy(ddram_home_shadow[row], cells + row * lcd_display::COLS,
           lcd_display::COLS);
#endif
  }
  return true;
}

void MK61Display::endCellAnimation(void) {
  if(!animation_state.active) return;
  animation_state.active = false;
  clear();
}

lcd_display::BusyFlagStatus MK61Display::busyFlagStatus(void) const {
#if MK61_LCD1602_BUSY_FLAG
  return (busy_flag_state & LCD_BUSY_ACTIVE) != 0
       ? lcd_display::BusyFlagStatus::ACTIVE
       : lcd_display::BusyFlagStatus::FIXED_DELAYS;
#else
  return lcd_display::BusyFlagStatus::NOT_AVAILABLE;
#endif
}

bool MK61Display::busyFlagObserved(void) const {
#if MK61_LCD1602_BUSY_FLAG
  return (busy_flag_state & LCD_BUSY_OBSERVED) != 0;
#else
  return false;
#endif
}

bool MK61Display::busyFlagFaulted(void) const {
#if MK61_LCD1602_BUSY_FLAG
  return (busy_flag_state & LCD_BUSY_FAULTED) != 0;
#else
  return false;
#endif
}

u32 MK61Display::busyFlagTimeouts(void) const {
  return busy_flag_timeouts;
}

void MK61Display::probeBusyFlag(void) {
  busy_flag_state = 0;

#if MK61_LCD1602_BUSY_FLAG
  digitalWrite(PIN_LCD_RW, LOW);
  pinMode(PIN_LCD_RW, OUTPUT);

  const LcdParallelBus bus = lcdParallelBus();
  if(!bus.validForRead()) return;

#if defined(MK61_OLED1602_WS0010)
  // WS0010's 4-bit interface specification requires BF/AC to be read as one
  // complete byte after every write.  Do not conditionally "probe" it with a
  // Clear: even a controller which happens to answer 0 immediately still
  // needs both read strobes to close the transfer. The V3 pin profile is the
  // electrical qualification boundary for this path.
  busy_flag_state = LCD_BUSY_ACTIVE;
  return;
#else
  // Clear выполняется достаточно долго, чтобы надёжно увидеть переход BF
  // 1 -> 0.
  lcdWriteByte(bus, LCD_CLEARDISPLAY, false);
  const LcdReadyResult result = lcdWaitReady(bus, 3000);
  if(result == LcdReadyResult::READY_AFTER_BUSY) {
    busy_flag_state = LCD_BUSY_ACTIVE | LCD_BUSY_OBSERVED;
    return;
  }

  if(result == LcdReadyResult::TIMEOUT) {
    busy_flag_timeouts++;
  } else {
    // При неподключённом или прижатом к нулю DB7 чтение завершится сразу,
    // хотя только что отправленный Clear ещё может выполняться.
    delayMicroseconds(lcdClearDelayUs());
  }
#endif
#endif
}

void MK61Display::sendByte(u8 value, bool data, u32 fallback_delay_us) {
#if MK61_LCD1602_BUSY_FLAG
  if((busy_flag_state & LCD_BUSY_FAULTED) != 0) return;
  if((busy_flag_state & LCD_BUSY_ACTIVE) != 0) {
    const LcdParallelBus bus = lcdParallelBus();
    if(bus.validForRead()) {
      lcdWriteByte(bus, value, data);
      const LcdReadyResult ready = lcdWaitReady(bus,
#if defined(MK61_OLED1602_WS0010)
                       8000
#else
                       3000
#endif
                       );
      if(ready == LcdReadyResult::READY_AFTER_BUSY) {
        busy_flag_state |= LCD_BUSY_OBSERVED;
        return;
      }
      if(ready == LcdReadyResult::READY_WITHOUT_BUSY) {
        // Keep the fixed lower bound if BF is electrically tied low or the
        // instruction completed before the first sample. The WS0010 transfer
        // nevertheless included its mandatory two read strobes.
        delayMicroseconds(fallback_delay_us != 0 ? fallback_delay_us
#if defined(MK61_OLED1602_WS0010)
                                                 : ws0010::COMMAND_DELAY_US);
#else
                                                 : 50);
#endif
        return;
      }
      busy_flag_timeouts++;
#if !defined(MK61_OLED1602_WS0010)
      busy_flag_state &= (u8) ~LCD_BUSY_ACTIVE;
#else
      // A still-high BF means the just-written byte may not have completed;
      // stop the caller from continuing into a half-known controller state.
      // Latch the fault so callers cannot write another byte into a still-busy
      // controller. Explicit reinitialize() performs the documented five-zero
      // resynchronisation before more UI traffic.
      busy_flag_state |= LCD_BUSY_FAULTED;
#endif
      // После тайм-аута повторять уже принятый байт нельзя. WS0010 продолжает
      // выполнять полный BF/AC read после следующих байтов; уход в write-only
      // снова сделал бы 4-битный обмен непаспортным.
      return;
    }
#if !defined(MK61_OLED1602_WS0010)
    busy_flag_state &= (u8) ~LCD_BUSY_ACTIVE;
#endif
  }
#endif

  // Не вызываем LiquidCrystal::command/write: в Arduino LiquidCrystal 1.0.7
  // эти методы ошибочно определены как inline только в .cpp. При -O2 их
  // внешние символы исчезают, и прошивка не линкуется. Стандартная
  // инициализация HD44780 остаётся за библиотекой; WS0010 инициализируется
  // выше явной последовательностью. Последующий обмен обоих контроллеров идёт
  // через тот же четырёхбитный интерфейс напрямую.
  const LcdParallelBus bus = lcdParallelBus();
  if(!bus.validForWrite()) return;
  lcdWriteByte(bus, value, data);
  delayMicroseconds(fallback_delay_us != 0 ? fallback_delay_us
#if defined(MK61_OLED1602_WS0010)
                                           : ws0010::COMMAND_DELAY_US);
#else
                                           : 50);
#endif
}

void MK61Display::sendCommand(u8 value, u32 fallback_delay_us) {
  sendByte(value, false, fallback_delay_us);
}

void MK61Display::sendData(u8 value) {
  sendByte(value, true);
}

void MK61Display::sendDisplayControl(void) {
  u8 control = display_control;
#if defined(MK61_OLED1602_WS0010)
  // In G/C=1 only D is meaningful. Keep cursor/blink in the logical state so
  // character recovery is lossless, but never send those bits to graphics.
  if(ws0010_graphics_active) {
    control &= (u8) ~(LCD_CURSORON | LCD_BLINKON);
  }
#endif
  sendCommand((u8) (LCD_DISPLAYCONTROL | control));
}

void MK61Display::writeCharacterCell(u8 value) {
  const u8 row = shadow_cursor_y;
  const u8 visible_x = shadow_cursor_x;
#if defined(MK61_OLED1602_WS0010)
  const u8 hardware_x = shifted_viewport_active
                      ? lcdHardwareColumn(shifted_viewport_shift, visible_x)
                      : visible_x;
#else
  const u8 logical_x = shifted_viewport_active
                     ? lcdLogicalColumn(shifted_viewport_shift, visible_x)
                     : visible_x;
#endif

  sendData(value);

#if defined(MK61_OLED1602_WS0010)
  ddram_shadow[row][visible_x] = value;
  if(hardware_x < lcd_display::COLS) {
    ddram_home_shadow[row][hardware_x] = value;
  }
#else
  ddram_shadow[row][logical_x] = value;
#endif
  shadow_cursor_x++;
  if(shadow_cursor_x >= lcd_display::COLS) {
    shadow_cursor_x = 0;
    shadow_cursor_y = (u8) ((shadow_cursor_y + 1) % lcd_display::ROWS);
  }

#if defined(MK61_OLED1602_WS0010)
  if(shifted_viewport_active || visible_x == lcd_display::COLS - 1u) {
    // A logical 16-column row wrap never matches WS0010's native 64-byte AC
    // progression. Re-arm AC for both normal and shifted text so a Print
    // crossing column 15 continues at column 0 of the other logical row.
    const u8 next_row_address = shadow_cursor_y == 0 ? 0x00u : 0x40u;
    const u8 next_hardware_x = lcdHardwareColumn(
      shifted_viewport_shift, shadow_cursor_x);
    sendCommand((u8) (LCD_SETDDRAMADDR | next_row_address |
                      next_hardware_x));
  }
#endif
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
  writeCharacterCell(value);
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
  writeCharacterCell(value);
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
    render_width(lcd_display::PIXEL_WIDTH),
    grid(),
    custom_glyphs{{0}},
    custom_valid{false},
    active_font(),
    preview_font(),
    active_font_state(ActiveFontState::BUILTIN),
    initialized(false),
#if MK61_ANY_FULLSCREEN_FILE
    fullscreen_bitmap_active(false),
#endif
    screen_dirty(false),
    dirty(false),
    extra_dirty_page_cols{0},
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
#if MK61_ANY_FULLSCREEN_FILE
  if(fullscreen_bitmap_active) return;
#endif
  updateCursorBlink();
  if(!dirty && !screen_dirty && !grid.anyDirty()) return;

  u16 page_masks[RENDER_PAGE_COUNT];
  memcpy(page_masks, extra_dirty_page_cols, sizeof(page_masks));
  page_damage::clear(extra_dirty_page_cols, RENDER_PAGE_COUNT);

  // Ячейка повреждает только те 8-пиксельные страницы UC1609, с которыми
  // пересекается её строка. Маски объединяются до начала передачи.
  for(u8 row = 0; row < grid.rows(); row++) {
    const u16 mask = grid.dirtyMask(row);
    if(mask != 0) {
      page_damage::markSpan(page_masks, RENDER_PAGE_COUNT,
                            RENDER_PAGE_HEIGHT, rowTop(row), rowPitch(row),
                            mask);
    }
    grid.clearDirty(row);
  }

  if(screen_dirty) {
    // Полная очистка и новое содержимое уходят одним итоговым кадром.
    page_damage::markAll(page_masks, RENDER_PAGE_COUNT);
    screen_dirty = false;
  }

  for(u8 page = 0; page < RENDER_PAGE_COUNT; page++) {
    const u16 mask = page_masks[page];
    for(u8 col = 0; col < lcd_display::COLS;) {
      if((mask & ((u16) 1U << col)) == 0) {
        col++;
        continue;
      }

      const u8 first_col = col;
      do {
        col++;
      } while(col < lcd_display::COLS &&
              (mask & ((u16) 1U << col)) != 0);
      renderPageRun(page, first_col, col - first_col);
    }
  }

  dirty = grid.anyDirty() ||
          page_damage::any(extra_dirty_page_cols, RENDER_PAGE_COUNT);
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
  if(custom_valid[nChar] &&
     memcmp(custom_glyphs[nChar], glyph,
            sizeof(custom_glyphs[nChar])) == 0) return;
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
    if(!custom_valid[i]) continue;
    grid.markCustomSlot(i);
    memset(custom_glyphs[i], 0, sizeof(custom_glyphs[i]));
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

void MK61Display::clearCustomChar(u8 nChar) {
  if(nChar >= CUSTOM_GLYPHS || !custom_valid[nChar]) return;
  grid.markCustomSlot(nChar);
  memset(custom_glyphs[nChar], 0, sizeof(custom_glyphs[nChar]));
  custom_valid[nChar] = false;
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) {
    usb_surface.clearCustomChar(nChar);
    usb_surface.flush(millis());
    return;
  }
#endif
  dirty = dirty || grid.anyDirty();
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
                             top_right_overlay_height,
                             top_right_overlay_clear_border);
  }
  memset(top_right_overlay_rows, 0, sizeof(top_right_overlay_rows));
  for(u8 y = 0; y < height; y++) top_right_overlay_rows[y] = rows[y] & row_mask;
  top_right_overlay_width = width;
  top_right_overlay_height = height;
  top_right_overlay_clear_border = clear_border;
  top_right_overlay_visible = true;
  markTopRightOverlayDirty(width, height, clear_border);
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
  const u8 old_height = top_right_overlay_height;
  const u8 old_border = top_right_overlay_clear_border;
  top_right_overlay_visible = false;
  top_right_overlay_width = 0;
  top_right_overlay_height = 0;
  top_right_overlay_clear_border = 0;
  memset(top_right_overlay_rows, 0, sizeof(top_right_overlay_rows));
  markTopRightOverlayDirty(old_width, old_height, old_border);
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
  if(font_data == NULL) {
    exclusive_buffer::release(exclusive_buffer::Owner::DISPLAY_FONT);
    return false;
  }

  // Ни flush(), ни фоновый клиент не должны увидеть Face, пока его backing
  // storage заменяется. Сначала делаем старые представления недостижимыми,
  // затем копируем и только после полной повторной валидации публикуем новое.
  MK61DisplayUpdate update(*this);
  active_font_state = ActiveFontState::BUILTIN;
  active_font.reset();
  preview_font.reset();
  preview_profile_active = false;
  memmove(font_data, data, size);
  if(!active_font.open(font_data, size)) {
    active_font_state = ActiveFontState::BUILTIN;
    exclusive_buffer::release(exclusive_buffer::Owner::DISPLAY_FONT);
    applyTextProfile(lcd_display::defaultTextProfileForRows(
        lcd_display::DEFAULT_ROWS));
    markAllDirty();
    return false;
  }

  active_font_state = ActiveFontState::READY;
  applyTextProfile(recommendedProfile(active_font.metrics()), true);
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) usb_surface.setFont(&active_font);
#endif
  markAllDirty();
  return true;
}

bool MK61Display::setFontPreview(const u8* data, u16 size) {
  if(data == NULL || size == 0 || size > fmk::MAX_FILE_SIZE) return false;
  // preview_font не владеет копией: этот контракт должен быть подкреплён
  // живой арендой проводника, а не только комментарием у вызывающего кода.
  if(shared_scratch::current_owner() !=
         shared_scratch::Owner::EXPLORER_VIEW ||
     !shared_memory::contains(shared_memory::Arena::SCRATCH,
                              data, size)) return false;
  fmk::Face candidate;
  if(!candidate.open(data, size)) return false;
  MK61DisplayUpdate update(*this);
  // Проводник удерживает аренду shared-scratch до clearFontPreview().
  // Сохраняем представление этих байтов, чтобы не делать вторую копию на 1536 байт.
  if(!preview_font.open(data, size)) return false;
  if(!preview_profile_active) {
    preview_saved_profile = active_profile;
    preview_profile_active = true;
  }
  applyTextProfile(recommendedProfile(preview_font.metrics()), true);
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) usb_surface.setFont(&preview_font);
#endif
  markAllDirty();
  return true;
}

void MK61Display::clearFontPreview(void) {
  if(!preview_font.valid() && !preview_profile_active) return;
  MK61DisplayUpdate update(*this);
  const bool restore_profile = preview_profile_active;
  const lcd_display::TextProfile saved_profile = preview_saved_profile;
  preview_profile_active = false;
  preview_font.reset();
  if(restore_profile) applyTextProfile(saved_profile, true);
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) usb_surface.setFont(selectedFont());
#endif
  markAllDirty();
}

void MK61Display::useBuiltinFont(void) {
  MK61DisplayUpdate update(*this);
  const bool restore_profile = preview_profile_active;
  const lcd_display::TextProfile saved_profile = preview_saved_profile;
  const ActiveFontState previous_state = active_font_state;
  const bool had_active_font = previous_state != ActiveFontState::BUILTIN;
  const bool changed = had_active_font || preview_font.valid() ||
                       preview_profile_active;

  // Сначала запрещаем выбор Face и обнуляем его указатель. Только после этого
  // backing arena может перейти USB-кэшу, swap или компрессору.
  active_font_state = ActiveFontState::BUILTIN;
  preview_profile_active = false;
  active_font.reset();
  preview_font.reset();
#if MK61_ENABLE_USB_SCREEN
  if(usb_screen_active) usb_surface.setFont(NULL);
#endif
  if(previous_state == ActiveFontState::READY &&
     exclusive_buffer::current_owner() ==
         exclusive_buffer::Owner::DISPLAY_FONT) {
    exclusive_buffer::release(exclusive_buffer::Owner::DISPLAY_FONT);
  }
  if(had_active_font) applyTextProfile(lcd_display::defaultTextProfileForRows(lcd_display::DEFAULT_ROWS));
  else if(restore_profile) applyTextProfile(saved_profile, true);
  if(changed) markAllDirty();
}

bool MK61Display::externalFontActive(void) const {
  return active_font_state == ActiveFontState::READY &&
         active_font.valid() &&
         exclusive_buffer::current_owner() ==
             exclusive_buffer::Owner::DISPLAY_FONT &&
         shared_memory::contains(shared_memory::Arena::BULK,
                                 active_font.data(), active_font.size());
}

bool MK61Display::suspendExternalFontForUsb(void) {
  if(preview_font.valid() || preview_profile_active) return false;
  if(active_font_state == ActiveFontState::SUSPENDED) return true;
  if(active_font_state == ActiveFontState::BUILTIN) return true;
  active_font_state = ActiveFontState::SUSPENDED;
  active_font.reset();
  if(exclusive_buffer::current_owner() ==
     exclusive_buffer::Owner::DISPLAY_FONT) {
    exclusive_buffer::release(exclusive_buffer::Owner::DISPLAY_FONT);
  }
  return true;
}

const fmk::Face* MK61Display::selectedFont(void) const {
  if(preview_font.valid() &&
     shared_scratch::current_owner() ==
         shared_scratch::Owner::EXPLORER_VIEW &&
     shared_memory::contains(shared_memory::Arena::SCRATCH,
                             preview_font.data(), preview_font.size())) {
    return &preview_font;
  }
  return externalFontActive() ? &active_font : NULL;
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
  bool content_changed = false;
  if(codepoint == '\n') grid.newline();
  else content_changed = grid.writeCodepoint(codepoint);
  if(cursorOverlayVisible()) markCursorCellDirty();
  dirty = dirty || content_changed;
  if(update_depth == 0) flush();
}

void MK61Display::clearShadow(void) {
  grid.reset(active_profile.rows);
}

void MK61Display::clearPhysicalScreen(void) {
  memset(render_buffer, 0x00, lcd_display::PIXEL_WIDTH);
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
#if MK61_ANY_FULLSCREEN_FILE
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
#if MK61_ANY_FULLSCREEN_FILE
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

bool MK61Display::busyFlagObserved(void) const {
  return false;
}

bool MK61Display::busyFlagFaulted(void) const {
  return false;
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
  if(update_depth == 0 && initialized) flush();
}

void MK61Display::markAllDirty(void) {
  grid.markAll();
  dirty = true;
  if(update_depth == 0 && initialized) flush();
}

void MK61Display::markTopRightOverlayDirty(u8 width, u8 height,
                                           u8 clear_border) {
  const u16 total_width = (u16) width + (u16) clear_border * 2U;
  const u16 total_height = (u16) height + (u16) clear_border * 2U;
  if(total_width == 0 || total_width > lcd_display::PIXEL_WIDTH ||
     total_height == 0) return;
  const u8 left = (u8) (lcd_display::PIXEL_WIDTH - total_width);
  const u8 first_col = left / lcd_display::CELL_WIDTH;
  const u16 columns = (u16) (0xFFFFU << first_col);
  page_damage::markSpan(extra_dirty_page_cols, RENDER_PAGE_COUNT,
                        RENDER_PAGE_HEIGHT, 0, total_height, columns);
  dirty = true;
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
    fillRenderRect(clear_left - run_left, clear_top - page_y,
                   clear_right - clear_left, clear_bottom - clear_top, false);
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
      setRenderPixel(absolute_x - run_left, absolute_y - page_y);
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

void MK61Display::setRenderPixel(i16 x, i16 y) {
  if(x < 0 || x >= render_width ||
     y < 0 || y >= RENDER_PAGE_HEIGHT) return;
  render_buffer[x] |= (u8) 1U << y;
}

void MK61Display::fillRenderRect(i16 x, i16 y, i16 width, i16 height,
                                 bool foreground) {
  if(width <= 0 || height <= 0) return;
  const i16 left = x < 0 ? 0 : x;
  const i16 top = y < 0 ? 0 : y;
  const i16 right = x + width > render_width
                  ? render_width : x + width;
  const i16 bottom = y + height > RENDER_PAGE_HEIGHT
                   ? RENDER_PAGE_HEIGHT : y + height;
  if(left >= right || top >= bottom) return;

  const u16 below_bottom = ((u16) 1U << bottom) - 1U;
  const u16 below_top = ((u16) 1U << top) - 1U;
  const u8 mask = (u8) (below_bottom & ~below_top);
  for(i16 px = left; px < right; px++) {
    if(foreground) render_buffer[px] |= mask;
    else render_buffer[px] &= (u8) ~mask;
  }
}

void MK61Display::drawGlyph(u8 x, i16 row_y, u8 row, const uint8_t* bitmap,
                            u8 source_width, u8 source_height) {
  const u8 height = glyphHeight(row);
  const u8 max_width = glyphWidth();
  const u8 width = source_width < max_width ? source_width : max_width;
  const u8 glyph_x = x + (u8) ((lcd_display::CELL_WIDTH - width) / 2);
  const i16 glyph_y = row_y + glyphTop(row);
  if(bitmap == NULL || source_width == 0 || source_height == 0 || width == 0 || height == 0) return;

  for(u8 dest_y = 0; dest_y < height; dest_y++) {
    const u8 source_y = (u8) (((u16) dest_y * source_height) / height);
    for(u8 dest_x = 0; dest_x < width; dest_x++) {
      const u8 source_x = (u8) (((u16) dest_x * source_width) / width);
      if(fmk::bitmapPixel(bitmap, source_width, source_x, source_y)) {
        setRenderPixel(glyph_x + dest_x, glyph_y + dest_y);
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
  if(block) fillRenderRect(cursor_x, glyph_y, cursor_width, height, true);
  else fillRenderRect(cursor_x, glyph_y + height - underline_height,
                      cursor_width, underline_height, true);
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

void MK61Display::renderPageRun(u8 page, u8 first_col, u8 count) {
  if(page >= RENDER_PAGE_COUNT || count == 0 ||
     first_col >= lcd_display::COLS ||
     count > lcd_display::COLS - first_col) return;

  const u8 run_width = count * lcd_display::CELL_WIDTH;
  const u8 page_y = page * RENDER_PAGE_HEIGHT;
  const u8 saved_width = render_width;
  render_width = run_width;

  memset(render_buffer, 0x00, run_width);
  for(u8 render_row = 0; render_row < grid.rows(); render_row++) {
    const u8 absolute_row_y = rowTop(render_row);
    const u8 absolute_row_bottom = absolute_row_y + rowPitch(render_row);
    if(absolute_row_bottom <= page_y ||
       absolute_row_y >= page_y + RENDER_PAGE_HEIGHT) continue;
    const i16 row_y = (i16) absolute_row_y - page_y;
    for(u8 i = 0; i < count; i++) {
      const u8 col = first_col + i;
      const u8 x = i * lcd_display::CELL_WIDTH;
      drawToken(x, row_y, render_row, grid.cell(col, render_row),
                grid.cellIsCustom(col, render_row));
      if(render_row == grid.cursorY() && col == grid.cursorX()) {
        if(cursor_blink && cursor_blink_phase) {
          drawCursor(x, row_y, render_row, true);
        } else if(cursor_underline) {
          drawCursor(x, row_y, render_row, false);
        }
      }
    }
  }
  drawTopRightOverlay(first_col, count, page_y);
  lcd.LCDBuffer(first_col * lcd_display::CELL_WIDTH, page_y,
                run_width, RENDER_PAGE_HEIGHT, render_buffer);
  render_width = saved_width;
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
  bool content_changed = false;
  if(value == '\n') grid.newline();
  else if(value < CUSTOM_GLYPHS && custom_valid[value]) {
    content_changed = grid.writeByte(value);
  } else {
    content_changed = grid.writeCodepoint(value);
  }
  if(cursorOverlayVisible()) markCursorCellDirty();
  dirty = dirty || content_changed;
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

#if defined(MK61_OLED1602_WS0010)
  // USB Screen owns a character-oriented canonical surface. Never seed it
  // from, or later restore it into, an experimental G/C session. The same
  // idempotent recovery used by diagnostics reconstructs character DDRAM,
  // CGRAM, cursor/blink and the compact viewport before ownership changes.
  if(ws0010_graphics_active) endWs0010Graphics();
  if(ws0010_graphics_active) return false;
#endif

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
  if(enabled
#if defined(MK61_OLED1602_WS0010)
     && oled_protection_state.awake()
#endif
     ) display_control |= LCD_DISPLAYON;
  else display_control &= (u8) ~LCD_DISPLAYON;
  sendDisplayControl();
#else
  if(initialized) lcd.LCDEnable(enabled ? 1 : 0);
#endif
}

#endif // MK61_ENABLE_USB_SCREEN
