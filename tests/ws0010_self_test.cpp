#define MK61_OLED1602_WS0010

#include "character_display_geometry.hpp"
#include "cgram_window_plan.hpp"
#include "lcd_6800_4bit_bus.hpp"
#include "lcd1602_editor_viewport.hpp"
#include "oled_protection.hpp"
#include "startup_splash.hpp"
#include "utf8_view.hpp"
#include "ws0010_charset.hpp"
#include "ws0010_controller.hpp"
#include "ws0010_graphics.hpp"
#include "ws0010_shifted_viewport.hpp"
#include "oled_settings.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

namespace {

enum class TransferKind : u8 {
  NIBBLE,
  COMMAND,
};

struct Transfer {
  TransferKind kind;
  u8 value;
};

struct TraceSink {
  Transfer transfers[24] = {};
  u8 count = 0;

  void append(TransferKind kind, u8 value) {
    assert(count < sizeof(transfers) / sizeof(transfers[0]));
    transfers[count++] = {kind, value};
  }

  void nibble(u8 value) { append(TransferKind::NIBBLE, value); }
  void command(u8 value) { append(TransferKind::COMMAND, value); }
};

enum class BusEventKind : u8 {
  PRELOAD_LOW,
  OUTPUT,
  WRITE,
  DELAY,
};

enum class BusSignal : u8 {
  RW,
  RS,
  ENABLE,
  DB4,
  DB5,
  DB6,
  DB7,
  TIME,
};

struct BusEvent {
  BusEventKind kind;
  BusSignal signal;
  u8 value;
};

struct BusTrace {
  BusEvent events[512] = {};
  usize count = 0;

  void append(BusEventKind kind, BusSignal signal, u8 value) {
    assert(count < sizeof(events) / sizeof(events[0]));
    events[count++] = {kind, signal, value};
  }

  void outputLow(BusSignal signal) {
    append(BusEventKind::PRELOAD_LOW, signal, 0);
    append(BusEventKind::OUTPUT, signal, 1);
  }
  void setRwOutputLow(void) { outputLow(BusSignal::RW); }
  void setRsOutputLow(void) { outputLow(BusSignal::RS); }
  void setEnableOutputLow(void) { outputLow(BusSignal::ENABLE); }
  void setDataOutputLow(u8 bit) {
    outputLow((BusSignal) ((u8) BusSignal::DB4 + bit));
  }
  void rw(bool high) {
    append(BusEventKind::WRITE, BusSignal::RW, high ? 1 : 0);
  }
  void rs(bool high) {
    append(BusEventKind::WRITE, BusSignal::RS, high ? 1 : 0);
  }
  void enable(bool high) {
    append(BusEventKind::WRITE, BusSignal::ENABLE, high ? 1 : 0);
  }
  void data(u8 bit, bool high) {
    append(BusEventKind::WRITE,
           (BusSignal) ((u8) BusSignal::DB4 + bit), high ? 1 : 0);
  }
  void delayMicroseconds(u8 duration) {
    append(BusEventKind::DELAY, BusSignal::TIME, duration);
  }
};

void test_low_level_6800_write_trace(void) {
  BusTrace trace;
  lcd_6800_4bit_bus::prepareWrite(trace);
  assert(trace.count == 14);
  for(usize index = 0; index < trace.count; index += 2) {
    assert(trace.events[index].kind == BusEventKind::PRELOAD_LOW);
    assert(trace.events[index].value == 0);
    assert(trace.events[index + 1].kind == BusEventKind::OUTPUT);
  }
  assert(trace.events[0].signal == BusSignal::RW);
  assert(trace.events[2].signal == BusSignal::RS);
  assert(trace.events[4].signal == BusSignal::ENABLE);
  assert(trace.events[6].signal == BusSignal::DB4);
  assert(trace.events[12].signal == BusSignal::DB7);

  trace.count = 0;
  lcd_6800_4bit_bus::writeByte(trace, 0xA5, false);
  assert(trace.events[0].kind == BusEventKind::WRITE &&
         trace.events[0].signal == BusSignal::RW &&
         trace.events[0].value == 0);
  assert(trace.events[1].signal == BusSignal::RS &&
         trace.events[1].value == 0);

  u8 rising_edges = 0;
  u8 falling_edges = 0;
  u8 nibble = 0;
  for(usize index = 0; index < trace.count; index++) {
    const BusEvent& event = trace.events[index];
    if(event.signal == BusSignal::RW) assert(event.value == 0);
    if(event.kind == BusEventKind::WRITE &&
       event.signal == BusSignal::ENABLE) {
      if(event.value != 0) rising_edges++;
      else falling_edges++;
    }
    if(event.kind == BusEventKind::WRITE &&
       event.signal >= BusSignal::DB4 && event.signal <= BusSignal::DB7) {
      const u8 bit = (u8) event.signal - (u8) BusSignal::DB4;
      if(event.value != 0) nibble |= (u8) 1u << bit;
      if(bit == 3) {
        assert(nibble == (rising_edges == 0 ? 0x0A : 0x05));
        nibble = 0;
      }
    }
  }
  assert(rising_edges == 2 && falling_edges == 4);

  trace.count = 0;
  lcd_6800_4bit_bus::writeByte(trace, 0x5A, true);
  assert(trace.events[0].signal == BusSignal::RW &&
         trace.events[0].value == 0);
  assert(trace.events[1].signal == BusSignal::RS &&
         trace.events[1].value == 1);
}

struct ControllerBusSink {
  BusTrace& trace;
  void nibble(u8 value) {
    lcd_6800_4bit_bus::writeNibble(trace, value);
  }
  void command(u8 value) {
    lcd_6800_4bit_bus::writeByte(trace, value, false);
  }
};

void test_controller_init_expands_to_safe_bus_trace(void) {
  BusTrace trace;
  ControllerBusSink sink = {trace};
  ws0010::emitFourBitInitialization(sink);
  u8 rising_edges = 0;
  for(usize index = 0; index < trace.count; index++) {
    const BusEvent& event = trace.events[index];
    if(event.signal == BusSignal::RW) assert(event.value == 0);
    if(event.kind == BusEventKind::WRITE &&
       event.signal == BusSignal::ENABLE && event.value != 0) rising_edges++;
  }
  // Six raw synchronization nibbles plus six complete command bytes.
  assert(rising_edges == 18);
}

void test_initialization_trace(void) {
  TraceSink trace;
  ws0010::emitFourBitInitialization(trace);

  assert(trace.count == 12);
  for(u8 i = 0; i < ws0010::BUS_SYNCHRONIZATION_WRITES; i++) {
    assert(trace.transfers[i].kind == TransferKind::NIBBLE);
    assert(trace.transfers[i].value == 0x00);
  }
  assert(trace.transfers[5].kind == TransferKind::NIBBLE);
  assert(trace.transfers[5].value == 0x02);

  static constexpr u8 commands[] = {
    0x2A, // 4-bit, 2-line, 5x8, English/Russian FT=10
    0x17, // character mode, internal power on
    0x08, // display/cursor/blink off while RAM is initialized
    0x01, // clear DDRAM
    0x06, // increment, no automatic display shift
    0x0C, // display on, cursor and blink off
  };
  for(u8 i = 0; i < sizeof(commands); i++) {
    const Transfer& transfer = trace.transfers[6 + i];
    assert(transfer.kind == TransferKind::COMMAND);
    assert(transfer.value == commands[i]);
  }

  assert(ws0010::POWER_STABILIZATION_MS == 500);
  assert(ws0010::CLEAR_DELAY_US >= 6200);
  assert(ws0010::COMMAND_DELAY_US >= 50);
}

void test_hidden_initialization_trace(void) {
  TraceSink trace;
  ws0010::emitFourBitInitialization(trace, false);
  assert(trace.count == 12);
  assert(trace.transfers[11].kind == TransferKind::COMMAND);
  assert(trace.transfers[11].value == ws0010::DISPLAY_OFF);
}

void test_recovery_trace_and_nibble_convergence(void) {
  TraceSink trace;
  ws0010::emitFourBitRecovery(trace);
  assert(trace.count == 12);
  for(u8 i = 0; i < ws0010::BUS_SYNCHRONIZATION_WRITES; i++) {
    assert(trace.transfers[i].kind == TransferKind::NIBBLE);
    assert(trace.transfers[i].value == 0x00);
  }
  assert(trace.transfers[5].kind == TransferKind::NIBBLE);
  assert(trace.transfers[5].value == 0x02);
  assert(trace.transfers[6].kind == TransferKind::COMMAND);
  assert(trace.transfers[6].value == 0x2A);

  // WS0010 defines five consecutive 0000 transfers as a controller-level
  // synchronization operation: regardless of the interrupted half-byte, the
  // following transfer is consumed as the lower nibble. Raw 0010 completes
  // that phase, leaving a normal high-nibble boundary for command(0x2A).
  enum class BusPhase : u8 { EIGHT_BIT, FOUR_HIGH, FOUR_LOW };
  for(u8 initial = 0; initial < 3; initial++) {
    BusPhase phase = (BusPhase) initial;
    u8 consecutive_zeroes = 0;
    for(u8 i = 0; i < ws0010::BUS_SYNCHRONIZATION_WRITES; i++) {
      consecutive_zeroes++;
      if(consecutive_zeroes == ws0010::BUS_SYNCHRONIZATION_WRITES) {
        phase = BusPhase::FOUR_LOW;
      }
    }
    assert(phase == BusPhase::FOUR_LOW);
    phase = BusPhase::FOUR_HIGH; // lower-nibble 0010 transfer
    assert(phase == BusPhase::FOUR_HIGH);
  }

  TraceSink hidden;
  ws0010::emitFourBitRecovery(hidden, false);
  assert(hidden.count == trace.count);
  assert(hidden.transfers[hidden.count - 1].kind == TransferKind::COMMAND);
  assert(hidden.transfers[hidden.count - 1].value == ws0010::DISPLAY_OFF);
}

void test_cgram_cursor_row_policy(void) {
  for(u8 value = 0; value <= 0x1F; value++) {
    for(u8 row = 0; row < ws0010::CGRAM_ROWS_5X8; row++) {
      const u8 expected = row == ws0010::CGRAM_CURSOR_ROW ? 0 : value;
      assert(ws0010::normalizeCgramRow(row, value) == expected);
    }
  }
  assert(ws0010_charset::INVERSE_MARKER_FALLBACK == '-');
  assert(ws0010_charset::INVERSE_MARKER_FALLBACK !=
         ws0010_charset::CYR_SMALL_SHORT_I);
  static_assert(ws0010_charset::cgram::GREATER_OR_EQUAL == 0 &&
                ws0010_charset::cgram::POWER_Y == 1 &&
                ws0010_charset::cgram::XOR == 2 &&
                ws0010_charset::cgram::NOT_EQUAL == 3 &&
                ws0010_charset::cgram::SQUARE_ROOT == 4 &&
                ws0010_charset::cgram::CYCLE_ARROW == 5 &&
                ws0010_charset::cgram::POWER_X == 6 &&
                ws0010_charset::cgram::POWER_2 == 7,
                "default WS0010 CGRAM route regression");
}

void test_cgram_window_plan_reserves_fixed_symbols(void) {
  cgram_window_plan::Plan plan = {};
  assert(cgram_window_plan::add(plan, 0x0406));
  assert(cgram_window_plan::slotFor(plan, 0x0406) == 0);
  cgram_window_plan::reserve(plan, 0);
  assert(cgram_window_plan::slotFor(plan, 0x0406) == 1);
  assert(plan.reserved_mask == 0x01);

  assert(cgram_window_plan::add(plan, 0x0407));
  assert(cgram_window_plan::slotFor(plan, 0x0407) == 2);
  cgram_window_plan::reserve(plan, 2);
  assert(cgram_window_plan::slotFor(plan, 0x0407) == 3);
  assert(cgram_window_plan::slotFor(plan, 0x0406) == 1);

  for(u8 slot = 0; slot < cgram_window_plan::SLOT_COUNT; slot++) {
    cgram_window_plan::reserve(plan, slot);
  }
  assert(plan.reserved_mask == 0xFF);
  assert(plan.count == 0);
  assert(plan.overflow);
  assert(!cgram_window_plan::add(plan, 0x040E));
}

void expect_mapping(u16 codepoint, u8 expected) {
  u8 value = 0;
  assert(ws0010_charset::unicodeToByte(codepoint, value));
  assert(value == expected);
}

void test_english_russian_ft10(void) {
  expect_mapping('A', 'A');
  expect_mapping('z', 'z');
  expect_mapping(0x0410, 'A');       // Cyrillic А
  expect_mapping(0x0411, 0xA0);      // Б
  expect_mapping(0x0413, 0xA1);      // Г
  expect_mapping(0x0415, 'E');       // Cyrillic Е
  expect_mapping(0x0401, 0xA2);      // Ё
  expect_mapping(0x0424, 0xAA);      // Ф
  expect_mapping(0x042F, 0xB1);      // Я
  expect_mapping(0x0431, 0xB2);      // б: real FT=10 lowercase glyph
  expect_mapping(0x0451, 0xB5);      // ё

  // One FT=10 table handles both languages; no state change separates these
  // codepoints in the same string.
  static constexpr u16 mixed[] = {
    'U', 'S', 'B', '-', 0x0434, 0x0438, 0x0441, 0x043A, ':', ' ',
    0x0424, 0x0430, 0x0439, 0x043B, ' ', 'A', '1',
  };
  static constexpr u8 expected[] = {
    'U', 'S', 'B', '-', 0xE3, 0xB8, 'c', 0xBA, ':', ' ',
    0xAA, 'a', 0xB9, 0xBB, ' ', 'A', '1',
  };
  static_assert(sizeof(mixed) / sizeof(mixed[0]) == sizeof(expected),
                "mixed FT=10 fixture size mismatch");
  for(usize i = 0; i < sizeof(expected); i++) {
    expect_mapping(mixed[i], expected[i]);
  }

  u8 value = 0;
  assert(!ws0010_charset::unicodeToByte(0x20AC, value));
}

void test_complete_russian_alphabet_and_mixed_width(void) {
  static constexpr u16 upper[] = {
    0x0410, 0x0411, 0x0412, 0x0413, 0x0414, 0x0415, 0x0401,
    0x0416, 0x0417, 0x0418, 0x0419, 0x041A, 0x041B, 0x041C,
    0x041D, 0x041E, 0x041F, 0x0420, 0x0421, 0x0422, 0x0423,
    0x0424, 0x0425, 0x0426, 0x0427, 0x0428, 0x0429, 0x042A,
    0x042B, 0x042C, 0x042D, 0x042E, 0x042F,
  };
  static constexpr u16 lower[] = {
    0x0430, 0x0431, 0x0432, 0x0433, 0x0434, 0x0435, 0x0451,
    0x0436, 0x0437, 0x0438, 0x0439, 0x043A, 0x043B, 0x043C,
    0x043D, 0x043E, 0x043F, 0x0440, 0x0441, 0x0442, 0x0443,
    0x0444, 0x0445, 0x0446, 0x0447, 0x0448, 0x0449, 0x044A,
    0x044B, 0x044C, 0x044D, 0x044E, 0x044F,
  };
  static_assert(sizeof(upper) == sizeof(lower),
                "Russian alphabet fixtures must have matching case pairs");
  for(usize i = 0; i < sizeof(upper) / sizeof(upper[0]); i++) {
    assert(ws0010_charset::russianAlphabetCodepoint(false, (u8) i) ==
           upper[i]);
    assert(ws0010_charset::russianAlphabetCodepoint(true, (u8) i) ==
           lower[i]);
    u8 upper_byte = 0;
    u8 lower_byte = 0;
    assert(ws0010_charset::unicodeToByte(upper[i], upper_byte));
    assert(ws0010_charset::unicodeToByte(lower[i], lower_byte));
    assert(ws0010_charset::canonicalToByte(
      ws0010_charset::canonicalForByte(upper_byte), upper_byte));
    assert(ws0010_charset::canonicalToByte(
      ws0010_charset::canonicalForByte(lower_byte), lower_byte));
  }
  assert(ws0010_charset::RUSSIAN_ALPHABET_SIZE == 33);
  assert(ws0010_charset::russianAlphabetCodepoint(false, 33) == 0);
  assert(ws0010_charset::russianAlphabetCodepoint(true, 33) == 0);

  // UTF-8 is variable-width, but a display page is always clipped after 16
  // decoded codepoints. This fixture alternates one- and two-byte characters
  // and places the final Cyrillic glyph exactly in cell 15.
  const char text[] = "AБCДEЁGЖIЗKИMЙOПtail";
  const u16 clipped = utf8_view::byte_offset(
    text, ws0010::CHARACTER_VISIBLE_COLS);
  assert(clipped == 24);
  assert(text[clipped] == 't');
  assert(utf8_view::codepoint_count(text, clipped) ==
         ws0010::CHARACTER_VISIBLE_COLS);
}

void test_reverse_distinct_cyrillic_mapping(void) {
  static constexpr u8 bytes[] = {
    0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7,
    0xA8, 0xA9, 0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF,
    0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7,
    0xB8, 0xB9, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF,
    0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7,
    0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6,
  };
  for(u8 value : bytes) {
    u16 codepoint = 0;
    assert(ws0010_charset::byteToUnicode(value, codepoint));
    u8 roundtrip = 0;
    assert(ws0010_charset::unicodeToByte(codepoint, roundtrip));
    assert(roundtrip == value);
  }

  u16 codepoint = 0;
  assert(!ws0010_charset::byteToUnicode('A', codepoint));
}

void test_complete_canonical_byte_map(void) {
  for(u16 raw = 0; raw <= 0xFF; raw++) {
    const u8 value = (u8) raw;
    const u16 canonical = ws0010_charset::canonicalForByte(value);
    u8 restored = 0;
    assert(ws0010_charset::canonicalToByte(canonical, restored));
    assert(restored == value);
  }

  // Confusable physical ASCII remains Latin in the reverse map.
  assert(ws0010_charset::canonicalForByte('A') == 0x0041);
  assert(ws0010_charset::canonicalForByte('B') == 0x0042);
  assert(ws0010_charset::canonicalForByte('C') == 0x0043);
  assert(ws0010_charset::canonicalForByte('E') == 0x0045);
  assert(ws0010_charset::canonicalForByte('H') == 0x0048);
  assert(ws0010_charset::canonicalForByte('K') == 0x004B);
  assert(ws0010_charset::canonicalForByte('M') == 0x004D);
  assert(ws0010_charset::canonicalForByte('O') == 0x004F);
  assert(ws0010_charset::canonicalForByte('P') == 0x0050);
  assert(ws0010_charset::canonicalForByte('T') == 0x0054);
  assert(ws0010_charset::canonicalForByte('X') == 0x0058);

  expect_mapping(0x2192, ws0010_charset::RIGHT_ARROW);
  expect_mapping(0x2190, ws0010_charset::LEFT_ARROW);
  expect_mapping(0x2191, ws0010_charset::UP_ARROW_FALLBACK);
  expect_mapping(0x03C0, ws0010_charset::PI_SYMBOL);
  expect_mapping(0x00B0, ws0010_charset::DEGREE);
  expect_mapping(0x00F7, ws0010_charset::DIVIDE);
  expect_mapping(0x00D7, ws0010_charset::MULTIPLY_FALLBACK);
  expect_mapping(0x2265, ws0010_charset::cgram::GREATER_OR_EQUAL);
  expect_mapping(0x02B8, ws0010_charset::cgram::POWER_Y);
  expect_mapping(0x22BB, ws0010_charset::cgram::XOR);
  expect_mapping(0x2260, ws0010_charset::cgram::NOT_EQUAL);
  expect_mapping(0x221A, ws0010_charset::cgram::SQUARE_ROOT);
  expect_mapping(0x21BB, ws0010_charset::cgram::CYCLE_ARROW);
  expect_mapping(0x02E3, ws0010_charset::cgram::POWER_X);
  expect_mapping(0x00B2, ws0010_charset::cgram::POWER_2);
}

void test_graphics_address_policy(void) {
  assert(ws0010::CHARACTER_VISIBLE_COLS == 16);
  assert(ws0010::CHARACTER_DDRAM_COLS == 64);
  assert(ws0010::CHARACTER_DDRAM_BYTES == 128);
  assert(ws0010::GRAPHICS_WIDTH == 100);
  assert(ws0010::GRAPHICS_HEIGHT == 16);
  assert(ws0010::GRAPHICS_FRAME_BYTES == 200);
  assert(ws0010::graphicsXAddress(0) == 0x80);
  assert(ws0010::graphicsXAddress(99) == 0xE3);
  assert(ws0010::graphicsPageAddress(0) == 0x40);
  assert(ws0010::graphicsPageAddress(1) == 0x41);
  assert(ws0010::MODE_GRAPHICS_POWER_ON == 0x1F);
  assert(ws0010::MODE_CHARACTER_POWER_ON == 0x17);
}

void test_character_control_state_model(void) {
  ws0010::CharacterState state;
  ws0010::applyCharacterCommand(state, ws0010::MODE_CHARACTER_POWER_ON);
  assert(!state.graphics && state.power_on);
  ws0010::applyCharacterCommand(state, 0x0F);
  assert(state.display_on && state.cursor_on && state.blink_on);

  ws0010::applyCharacterCommand(state, 0xBF); // DDRAM 0x3f
  ws0010::applyCharacterDataWrite(state);
  assert(state.space == ws0010::AddressSpace::DDRAM);
  assert(state.address == 0x40);
  ws0010::applyCharacterCommand(state, 0xFF); // DDRAM 0x7f
  ws0010::applyCharacterDataWrite(state);
  assert(state.address == 0x00);

  ws0010::applyCharacterCommand(state,
                                 ws0010::ENTRY_DECREMENT_NO_SHIFT);
  ws0010::applyCharacterDataWrite(state);
  assert(state.address == 0x7F);
  const u8 address_before_shift = state.address;
  ws0010::applyCharacterCommand(state, ws0010::DISPLAY_SHIFT_LEFT);
  assert(state.address == address_before_shift && state.display_shift == 1);
  ws0010::applyCharacterCommand(state, ws0010::DISPLAY_SHIFT_RIGHT);
  assert(state.address == address_before_shift && state.display_shift == 0);
  ws0010::applyCharacterCommand(state, ws0010::CURSOR_RIGHT);
  assert(state.address == 0);
  ws0010::applyCharacterCommand(state, ws0010::CURSOR_LEFT);
  assert(state.address == 0x7F);

  ws0010::applyCharacterCommand(state,
                                 ws0010::ENTRY_INCREMENT_WITH_SHIFT);
  ws0010::applyCharacterDataWrite(state);
  assert(state.address == 0 && state.display_shift == 1);
  ws0010::applyCharacterCommand(state,
                                 ws0010::ENTRY_DECREMENT_WITH_SHIFT);
  ws0010::applyCharacterDataWrite(state);
  assert(state.address == 0x7F && state.display_shift == 0);

  ws0010::applyCharacterCommand(state, 0x7F); // CGRAM 0x3f
  assert(state.space == ws0010::AddressSpace::CGRAM &&
         state.address == 0x3F);
  ws0010::applyCharacterCommand(state,
                                 ws0010::ENTRY_INCREMENT_NO_SHIFT);
  ws0010::applyCharacterDataWrite(state);
  assert(state.address == 0);

  state.display_shift = 17;
  ws0010::applyCharacterCommand(state, ws0010::RETURN_HOME);
  assert(state.space == ws0010::AddressSpace::DDRAM && state.address == 0 &&
         state.display_shift == 0);
  state.display_shift = 23;
  state.increment = false;
  state.automatic_shift = true;
  ws0010::applyCharacterCommand(state, ws0010::CLEAR_DISPLAY);
  assert(state.address == 0 && state.display_shift == 0 && state.increment &&
         state.automatic_shift);

  ws0010::applyCharacterCommand(state, ws0010::MODE_GRAPHICS_POWER_ON);
  assert(state.graphics && state.power_on);
  ws0010::applyCharacterCommand(state, ws0010::MODE_CHARACTER_POWER_OFF);
  assert(!state.graphics && !state.power_on);
}

void test_graphics_pack_clip_stream_and_damage(void) {
  u8 frame[ws0010_graphics::FRAME_BYTES];
  ws0010_graphics::clear(frame, sizeof(frame));
  for(u8 y = 0; y < ws0010_graphics::HEIGHT; y++) {
    for(u8 x = 0; x < ws0010_graphics::WIDTH; x++) {
      assert(!ws0010_graphics::pixel(frame, sizeof(frame), x, y));
    }
  }

  assert(ws0010_graphics::setPixel(frame, sizeof(frame), 0, 0));
  assert(ws0010_graphics::setPixel(frame, sizeof(frame), 99, 15));
  assert(ws0010_graphics::pixel(frame, sizeof(frame), 0, 0));
  assert(ws0010_graphics::pixel(frame, sizeof(frame), 99, 15));
  assert(frame[0] == 0x01);
  assert(frame[ws0010_graphics::FRAME_BYTES - 1] == 0x80);
  assert(!ws0010_graphics::setPixel(frame, sizeof(frame), -1, 0));
  assert(!ws0010_graphics::setPixel(frame, sizeof(frame), 100, 0));
  assert(!ws0010_graphics::setPixel(frame, sizeof(frame), 0, 16));

  u8 before[ws0010_graphics::FRAME_BYTES] = {};
  ws0010_graphics::DirtySpan span =
    ws0010_graphics::changedSpan(before, frame, 0);
  assert(span.valid && span.first == 0 && span.last == 0);
  span = ws0010_graphics::changedSpan(before, frame, 1);
  assert(span.valid && span.first == 99 && span.last == 99);
  span = ws0010_graphics::changedSpan(frame, frame, 0);
  assert(!span.valid);

  struct GraphicsTrace {
    u8 commands[2] = {};
    u8 bytes[4] = {};
    u8 command_count = 0;
    u8 byte_count = 0;
  } trace;
  const u8 payload[] = {0x11, 0x22, 0x44, 0x88};
  assert(ws0010_graphics::streamPage(
    1, 96, payload, sizeof(payload),
    [&trace](u8 value) { trace.commands[trace.command_count++] = value; },
    [&trace](u8 value) { trace.bytes[trace.byte_count++] = value; }));
  assert(trace.command_count == 2);
  assert(trace.commands[0] == ws0010::graphicsXAddress(96));
  assert(trace.commands[1] == ws0010::graphicsPageAddress(1));
  assert(trace.byte_count == sizeof(payload));
  for(u8 i = 0; i < sizeof(payload); i++) assert(trace.bytes[i] == payload[i]);
  assert(!ws0010_graphics::streamPage(
    2, 0, payload, 1, [](u8) {}, [](u8) {}));
  assert(!ws0010_graphics::streamPage(
    0, 99, payload, 2, [](u8) {}, [](u8) {}));

  for(u8 pattern = 0; pattern < 8; pattern++) {
    ws0010_graphics::makeQualificationPattern(frame, sizeof(frame), pattern);
    bool any = false;
    for(u8 value : frame) any |= value != 0;
    assert(any == (pattern != 7));
  }

  ws0010_graphics::makeQualificationPattern(frame, sizeof(frame), 0);
  assert(ws0010_graphics::pixel(frame, sizeof(frame), 0, 0));
  assert(ws0010_graphics::pixel(frame, sizeof(frame), 99, 15));
  assert(ws0010_graphics::pixel(frame, sizeof(frame), 49, 7));
  assert(ws0010_graphics::pixel(frame, sizeof(frame), 50, 8));
  assert(!ws0010_graphics::pixel(frame, sizeof(frame), 1, 1));

  ws0010_graphics::makeQualificationPattern(frame, sizeof(frame), 6);
  for(u8 value : frame) assert(value == 0xFF);
  ws0010_graphics::makeQualificationPattern(frame, sizeof(frame), 7);
  for(u8 value : frame) assert(value == 0x00);
}

void test_oled_protection_state_machine(void) {
  oled_protection::State state;
  state.configure(oled_protection::Timeout::MINUTES_5, 100);
  assert(state.awake());
  assert(state.poll(100 + 5UL * 60UL * 1000UL - 1) ==
         oled_protection::Transition::NONE);
  assert(state.poll(100 + 5UL * 60UL * 1000UL) ==
         oled_protection::Transition::DISPLAY_OFF);
  assert(!state.awake());
  assert(state.poll(0xFFFFFFFFu) == oled_protection::Transition::NONE);
  assert(state.activity(0xFFFFFFF0u) ==
         oled_protection::Transition::DISPLAY_ON);
  assert(state.awake());
  // Unsigned subtraction makes the inactivity deadline safe across wrap.
  assert(state.poll(0x00000010u) == oled_protection::Transition::NONE);
  state.configure(oled_protection::Timeout::OFF, 123);
  assert(state.poll(0xFFFFFFFFu) == oled_protection::Transition::NONE);
}

void test_oled_settings_reserve_unqualified_brightness_bits(void) {
  const OledSettings defaults = normalize_oled_settings(0xFF);
  assert(defaults.timeout() == DEFAULT_OLED_TIMEOUT);
  assert((defaults.raw & (u8) ~OledSettings::KNOWN_MASK) == 0);

  assert(defaults.raw == (u8) (DEFAULT_OLED_TIMEOUT << 4));
  const OledSettings scrubbed = normalize_oled_settings(0xCFu);
  assert(scrubbed.timeout() == 0);
  assert((scrubbed.raw & (u8) ~OledSettings::KNOWN_MASK) == 0);

  OledSettings changed = defaults;
  changed.setTimeout(3);
  assert(changed.raw == 0x30 && changed.timeout() == 3);
}

void test_editor_uses_complete_native_ring(void) {
  static_assert(character_display_geometry::DDRAM_COLS == 64,
                "WS0010 geometry must not inherit the HD44780 limit");
  static_assert(lcd1602_editor_viewport::DDRAM_COLS == 64,
                "Editor must expose the complete WS0010 DDRAM row");

  char first[65] = {};
  char second[65] = {};
  for(u8 index = 0; index < 64; index++) {
    first[index] = (char) ('A' + index % 26);
    second[index] = (char) ('a' + index % 26);
  }
  const lcd1602_editor_viewport::RowSpan rows[] = {
    {first, 64},
    {second, 64},
  };
  lcd1602_editor_viewport::Layout layout = {};
  lcd1602_editor_viewport::build(rows, 0, 0, layout);
  assert(layout.shift == 0);
  assert(layout.cells[0][0] == '>');
  assert(layout.cells[0][40] == (u8) first[39]);
  assert(layout.cells[0][63] == (u8) first[62]);

  lcd1602_editor_viewport::build(rows, 0, 64, layout);
  assert(layout.shift == 50);
  assert(layout.cells[0][50] == '>');
  for(u8 visible = 1; visible < lcd1602_editor_viewport::VISIBLE_COLS;
      visible++) {
    const u8 address = (u8) ((layout.shift + visible) % 64u);
    const u8 source = (u8) (50u + visible - 1u);
    const u8 expected = source < 64 ? (u8) first[source] : (u8) ' ';
    assert(layout.cells[0][address] == expected);
  }

  const character_display_geometry::ShiftPlan wrap =
      character_display_geometry::shortestShift(0, 63);
  assert(wrap.steps == 1 && !wrap.left);
}

void test_startup_splash_uses_64_column_ring(void) {
  static constexpr char text[] = "0123456789ABCDEF";
  static constexpr u8 logo[startup_splash::COLS] = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
  };
  static_assert(startup_splash::LCD1602_TEXT_START == 48,
                "WS0010 splash text must occupy native addresses 48..63");

  u8 ddram[character_display_geometry::DDRAM_COLS] = {};
  startup_splash::composeLcd1602DdramRow(text, logo, ddram);
  for(u8 frame = 0; frame <= startup_splash::FINAL_FRAME; frame++) {
    u8 expected[startup_splash::COLS] = {};
    startup_splash::composeRow(text, logo, frame, expected);
    const u8 shift = startup_splash::lcd1602ShiftForFrame(frame);
    for(u8 col = 0; col < startup_splash::COLS; col++) {
      assert(ddram[character_display_geometry::physicalAddress(shift, col)] ==
             expected[col]);
    }
  }
}

struct ViewportModel {
  u8 ddram[ws0010_shifted_viewport::ROWS]
          [ws0010_shifted_viewport::DDRAM_COLS] = {};
  u8 address = 0;
  u8 shift = 0;
  u32 commands = 0;
  u32 data_writes = 0;

  ViewportModel(void) {
    for(u8 row = 0; row < ws0010_shifted_viewport::ROWS; row++) {
      for(u8 col = 0; col < ws0010_shifted_viewport::DDRAM_COLS; col++) {
        ddram[row][col] = ' ';
      }
    }
  }

  void resetCounters(void) {
    commands = 0;
    data_writes = 0;
  }

  void apply(ws0010_shifted_viewport::BusWrite write) {
    if(write.data) {
      const u8 row = (address & 0x40u) != 0 ? 1 : 0;
      const u8 col = (u8) (address & 0x3Fu);
      assert(col < ws0010_shifted_viewport::DDRAM_COLS);
      ddram[row][col] = write.value;
      address = (u8) ((address & 0x40u) | ((col + 1u) & 0x3Fu));
      data_writes++;
      return;
    }
    commands++;
    if(write.value == ws0010_shifted_viewport::COMMAND_RETURN_HOME) {
      address = 0;
      shift = 0;
      return;
    }
    if(write.value == ws0010_shifted_viewport::COMMAND_SHIFT_LEFT) {
      shift = (u8) ((shift + 1u) %
                    ws0010_shifted_viewport::DDRAM_COLS);
      return;
    }
    if(write.value == ws0010_shifted_viewport::COMMAND_SHIFT_RIGHT) {
      shift = shift == 0
            ? (u8) (ws0010_shifted_viewport::DDRAM_COLS - 1u)
            : (u8) (shift - 1u);
      return;
    }
    assert((write.value & ws0010_shifted_viewport::COMMAND_SET_DDRAM) != 0);
    address = (u8) (write.value & 0x7Fu);
  }

  u8 visible(u8 row, u8 column) const {
    return ddram[row][(u8) ((shift + column) %
                            ws0010_shifted_viewport::DDRAM_COLS)];
  }
};

void fill_viewport(u8 desired[ws0010_shifted_viewport::ROWS]
                             [ws0010_shifted_viewport::DDRAM_COLS]) {
  for(u8 row = 0; row < ws0010_shifted_viewport::ROWS; row++) {
    for(u8 col = 0; col < ws0010_shifted_viewport::DDRAM_COLS; col++) {
      desired[row][col] = (u8) ('!' + ((row * 11u + col) % 90u));
    }
  }
}

void assert_viewport(const ViewportModel& model,
                     const u8 desired[ws0010_shifted_viewport::ROWS]
                                     [ws0010_shifted_viewport::DDRAM_COLS],
                     u8 target) {
  assert(model.shift == target);
  for(u8 row = 0; row < ws0010_shifted_viewport::ROWS; row++) {
    for(u8 col = 0; col < ws0010_shifted_viewport::VISIBLE_COLS; col++) {
      assert(model.visible(row, col) ==
             desired[row][(u8) ((target + col) %
                                ws0010_shifted_viewport::DDRAM_COLS)]);
    }
  }
}

void test_ws0010_native_64_column_viewport(void) {
  static_assert(ws0010_shifted_viewport::DDRAM_COLS == 64,
                "WS0010 test must cover its complete native DDRAM row");
  assert(ws0010_shifted_viewport::setDdramAddressCommand(0, 63) == 0xBF);
  assert(ws0010_shifted_viewport::setDdramAddressCommand(1, 63) == 0xFF);

  for(u8 shift = 0; shift < ws0010_shifted_viewport::DDRAM_COLS; shift++) {
    for(u8 visible = 0; visible < ws0010_shifted_viewport::VISIBLE_COLS;
        visible++) {
      assert(ws0010_shifted_viewport::physicalAddress(shift, visible) ==
             (u8) ((shift + visible) %
                    ws0010_shifted_viewport::DDRAM_COLS));
    }
  }

  for(u8 initial = 0; initial < ws0010_shifted_viewport::DDRAM_COLS;
      initial++) {
    for(u8 target = 0; target < ws0010_shifted_viewport::DDRAM_COLS;
        target++) {
      u8 desired[ws0010_shifted_viewport::ROWS]
                [ws0010_shifted_viewport::DDRAM_COLS];
      fill_viewport(desired);
      ViewportModel model;
      bool active = false;
      u8 current = 0;
      const auto emit = [&model](ws0010_shifted_viewport::BusWrite write) {
        model.apply(write);
      };
      assert(ws0010_shifted_viewport::render(
        active, current, desired, initial, emit));
      assert(model.data_writes == 2u * ws0010_shifted_viewport::DDRAM_COLS);
      assert_viewport(model, desired, initial);

      // All hidden positions, including the old HD44780 boundary 39/40 and
      // the native endpoint 63, must be real controller content—not mirrors.
      for(u8 row = 0; row < ws0010_shifted_viewport::ROWS; row++) {
        for(u8 col = 0; col < ws0010_shifted_viewport::DDRAM_COLS; col++) {
          assert(model.ddram[row][col] == desired[row][col]);
        }
      }

      model.resetCounters();
      assert(ws0010_shifted_viewport::shiftTo(
        active, current, target, emit));
      assert_viewport(model, desired, target);
      const ws0010_shifted_viewport::ShiftPlan expected =
          ws0010_shifted_viewport::shortestShift(initial, target);
      assert(model.data_writes == 0);
      assert(model.commands == expected.steps);

      desired[0][40] ^= 0x20u;
      desired[1][63] ^= 0x20u;
      model.resetCounters();
      assert(ws0010_shifted_viewport::render(
        active, current, desired, target, emit));
      assert_viewport(model, desired, target);
      assert(model.ddram[0][40] == desired[0][40]);
      assert(model.ddram[1][63] == desired[1][63]);

      // Independent scrolling must rewrite exactly one rotated native row.
      // The common hardware shift and therefore the other row's visible
      // window must remain unchanged.
      u8 untouched[ws0010_shifted_viewport::DDRAM_COLS] = {};
      memcpy(untouched, model.ddram[1], sizeof(untouched));
      desired[0][0] ^= 0x01u;
      desired[0][63] ^= 0x01u;
      const u8 independent_target = (u8) ((target + 17u) %
        ws0010_shifted_viewport::DDRAM_COLS);
      model.resetCounters();
      assert(ws0010_shifted_viewport::writeRow(
        active, current, desired, 0, independent_target, emit));
      assert(model.data_writes == ws0010_shifted_viewport::DDRAM_COLS);
      assert(memcmp(model.ddram[1], untouched, sizeof(untouched)) == 0);
      assert(model.shift == target);
      assert(current == target);
      for(u8 physical = 0;
          physical < ws0010_shifted_viewport::DDRAM_COLS; physical++) {
        assert(model.ddram[0][physical] == desired[0][
          ws0010_shifted_viewport::independentSourceAddress(
            target, independent_target, physical)]);
      }
      for(u8 col = 0; col < ws0010_shifted_viewport::VISIBLE_COLS; col++) {
        assert(model.visible(0, col) == desired[0][
          ws0010_shifted_viewport::physicalAddress(independent_target, col)]);
        assert(model.visible(1, col) == untouched[
          ws0010_shifted_viewport::physicalAddress(target, col)]);
      }

      ws0010_shifted_viewport::end(active, current, emit);
      assert(!active);
      assert(current == 0);
      assert(model.shift == 0);
    }
  }

  u8 desired[ws0010_shifted_viewport::ROWS]
            [ws0010_shifted_viewport::DDRAM_COLS] = {};
  bool active = false;
  u8 current = 17;
  u32 writes = 0;
  const auto discard = [&writes](ws0010_shifted_viewport::BusWrite) {
    writes++;
  };
  assert(!ws0010_shifted_viewport::render(
    active, current, desired, ws0010_shifted_viewport::DDRAM_COLS, discard));
  assert(!active && current == 17 && writes == 0);

  assert(!ws0010_shifted_viewport::shiftTo(
    active, current, ws0010_shifted_viewport::DDRAM_COLS, discard));
  assert(!active && current == 17 && writes == 0);

  assert(!ws0010_shifted_viewport::writeRow(
    active, current, desired, ws0010_shifted_viewport::ROWS, 0, discard));
  assert(!ws0010_shifted_viewport::writeRow(
    active, current, desired, 0,
    ws0010_shifted_viewport::DDRAM_COLS, discard));
  assert(!active && current == 17 && writes == 0);
}

} // namespace

int main(void) {
  test_low_level_6800_write_trace();
  test_controller_init_expands_to_safe_bus_trace();
  test_initialization_trace();
  test_hidden_initialization_trace();
  test_recovery_trace_and_nibble_convergence();
  test_cgram_cursor_row_policy();
  test_cgram_window_plan_reserves_fixed_symbols();
  test_english_russian_ft10();
  test_complete_russian_alphabet_and_mixed_width();
  test_reverse_distinct_cyrillic_mapping();
  test_complete_canonical_byte_map();
  test_graphics_address_policy();
  test_character_control_state_model();
  test_graphics_pack_clip_stream_and_damage();
  test_oled_protection_state_machine();
  test_oled_settings_reserve_unqualified_brightness_bits();
  test_editor_uses_complete_native_ring();
  test_startup_splash_uses_64_column_ring();
  test_ws0010_native_64_column_viewport();
  puts("ws0010_self_test: ok");
  return 0;
}
