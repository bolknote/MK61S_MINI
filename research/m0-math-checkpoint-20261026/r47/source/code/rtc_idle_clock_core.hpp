#ifndef MK61_RTC_IDLE_CLOCK_CORE_HPP
#define MK61_RTC_IDLE_CLOCK_CORE_HPP

#include "rust_types.h"

namespace rtc_idle_clock {

static constexpr u8 DIGIT_ROWS = 5;
static constexpr u8 GLYPH_ROWS = 8;
static constexpr u8 CUSTOM_SLOT_COUNT = 8;
static constexpr u8 CLOCK_GLYPH_COUNT = 3;
static constexpr u8 INVALID_SLOT = 0xFF;
static constexpr u8 GRAPHIC_CLOCK_DIGIT_WIDTH = 5;
static constexpr u8 GRAPHIC_CLOCK_HEIGHT = 7;
static constexpr u8 GRAPHIC_CLOCK_GAP = 1;
static constexpr u8 GRAPHIC_CLOCK_HOUR_TENS_X = 0;
static constexpr u8 GRAPHIC_CLOCK_HOUR_UNITS_X =
  GRAPHIC_CLOCK_HOUR_TENS_X + GRAPHIC_CLOCK_DIGIT_WIDTH + GRAPHIC_CLOCK_GAP;
static constexpr u8 GRAPHIC_CLOCK_COLON_X =
  GRAPHIC_CLOCK_HOUR_UNITS_X + GRAPHIC_CLOCK_DIGIT_WIDTH + GRAPHIC_CLOCK_GAP;
static constexpr u8 GRAPHIC_CLOCK_MINUTE_TENS_X =
  GRAPHIC_CLOCK_COLON_X + 1 + GRAPHIC_CLOCK_GAP;
static constexpr u8 GRAPHIC_CLOCK_MINUTE_UNITS_X =
  GRAPHIC_CLOCK_MINUTE_TENS_X + GRAPHIC_CLOCK_DIGIT_WIDTH + GRAPHIC_CLOCK_GAP;
static constexpr u8 GRAPHIC_CLOCK_WIDTH =
  GRAPHIC_CLOCK_MINUTE_UNITS_X + GRAPHIC_CLOCK_DIGIT_WIDTH;
static constexpr u8 GRAPHIC_CLOCK_CLEAR_BORDER = 2;

static_assert(GRAPHIC_CLOCK_WIDTH <= 32,
              "Graphic clock rows must fit a 32-bit bitmap");

// Маски перенесены без изменений из нарисованного для проекта макета digits.png.
static constexpr u8 DIGITS[10][DIGIT_ROWS] = {
  {0b11, 0b11, 0b11, 0b11, 0b11}, // 0
  {0b01, 0b01, 0b01, 0b01, 0b01}, // 1
  {0b11, 0b01, 0b01, 0b10, 0b11}, // 2
  {0b11, 0b01, 0b11, 0b01, 0b11}, // 3
  {0b10, 0b10, 0b11, 0b01, 0b01}, // 4
  {0b11, 0b10, 0b11, 0b01, 0b11}, // 5
  {0b11, 0b10, 0b11, 0b11, 0b11}, // 6
  {0b11, 0b01, 0b01, 0b01, 0b01}, // 7
  {0b11, 0b11, 0b00, 0b11, 0b11}, // 8
  {0b11, 0b11, 0b01, 0b01, 0b11}  // 9
};

// Тонкие цифры совпадают с растром штатного шрифта 5x8 графического экрана.
// Последняя строка того шрифта пустая, поэтому часы занимают ровно 5x7 и
// аккуратно помещаются над разделительной линией поля текущей команды.
static constexpr u8 GRAPHIC_DIGIT_COLUMNS[10][GRAPHIC_CLOCK_DIGIT_WIDTH] = {
  {0x3E, 0x51, 0x49, 0x45, 0x3E}, // 0
  {0x00, 0x42, 0x7F, 0x40, 0x00}, // 1
  {0x72, 0x49, 0x49, 0x49, 0x46}, // 2
  {0x21, 0x41, 0x49, 0x4D, 0x33}, // 3
  {0x18, 0x14, 0x12, 0x7F, 0x10}, // 4
  {0x27, 0x45, 0x45, 0x45, 0x39}, // 5
  {0x3C, 0x4A, 0x49, 0x49, 0x31}, // 6
  {0x41, 0x21, 0x11, 0x09, 0x07}, // 7
  {0x36, 0x49, 0x49, 0x49, 0x36}, // 8
  {0x46, 0x49, 0x49, 0x29, 0x1E}  // 9
};

struct Slots {
  u8 hour_tens;
  u8 hour_units_colon;
  u8 minute;
  u8 count;
};

inline void clear_glyph(u8 out[GLYPH_ROWS]) {
  for(u8 row = 0; row < GLYPH_ROWS; row++) out[row] = 0;
}

inline bool build_hour_tens_glyph(u8 hour, u8 out[GLYPH_ROWS]) {
  if(out == 0 || hour > 23) return false;
  clear_glyph(out);
  const u8 digit = hour / 10;
  for(u8 row = 0; row < DIGIT_ROWS; row++) {
    // Первый разряд прижат к правому краю знакоместа.
    out[row + 1] = DIGITS[digit][row];
  }
  return true;
}

inline bool build_hour_units_colon_glyph(u8 hour, u8 out[GLYPH_ROWS]) {
  if(out == 0 || hour > 23) return false;
  clear_glyph(out);
  const u8 digit = hour % 10;
  for(u8 row = 0; row < DIGIT_ROWS; row++) {
    // Второй разряд расположен слева, точки двоеточия — справа.
    const u8 colon = (row == 1 || row == 3) ? 0b00001 : 0;
    out[row + 1] = (u8) ((DIGITS[digit][row] << 3) | colon);
  }
  return true;
}

inline bool build_pair_glyph(u8 value, u8 out[GLYPH_ROWS]) {
  if(out == 0 || value > 99) return false;
  const u8 tens = value / 10;
  const u8 units = value % 10;
  out[0] = 0;
  for(u8 row = 0; row < DIGIT_ROWS; row++) {
    // Две цифры 2x5 разделены пустой средней колонкой матрицы 5x8.
    out[row + 1] = (u8) ((DIGITS[tens][row] << 3) | DIGITS[units][row]);
  }
  out[6] = 0;
  out[7] = 0;
  return true;
}

inline void draw_graphic_digit(u8 digit, u8 left,
                               u32 out[GRAPHIC_CLOCK_HEIGHT]) {
  for(u8 x = 0; x < GRAPHIC_CLOCK_DIGIT_WIDTH; x++) {
    const u8 column = GRAPHIC_DIGIT_COLUMNS[digit][x];
    for(u8 y = 0; y < GRAPHIC_CLOCK_HEIGHT; y++) {
      if((column & ((u8) 1U << y)) != 0) {
        out[y] |= (u32) 1U << (left + x);
      }
    }
  }
}

inline bool build_graphic_clock(u8 hour, u8 minute,
                                u32 out[GRAPHIC_CLOCK_HEIGHT]) {
  if(out == 0 || hour > 23 || minute > 59) return false;
  for(u8 y = 0; y < GRAPHIC_CLOCK_HEIGHT; y++) out[y] = 0;

  draw_graphic_digit(hour / 10, GRAPHIC_CLOCK_HOUR_TENS_X, out);
  draw_graphic_digit(hour % 10, GRAPHIC_CLOCK_HOUR_UNITS_X, out);
  draw_graphic_digit(minute / 10, GRAPHIC_CLOCK_MINUTE_TENS_X, out);
  draw_graphic_digit(minute % 10, GRAPHIC_CLOCK_MINUTE_UNITS_X, out);

  out[2] |= (u32) 1U << GRAPHIC_CLOCK_COLON_X;
  out[4] |= (u32) 1U << GRAPHIC_CLOCK_COLON_X;
  return true;
}

inline u8 slot_for_character(u8 value) {
  // В режиме 5x8 контроллеры семейства HD44780 отображают 00..07 и
  // их зеркальные коды 08..0F через одни и те же восемь ячеек CGRAM.
  return value < 0x10 ? (u8) (value & 0x07) : INVALID_SLOT;
}

inline bool select_slots(u8 used_mask, Slots& out) {
  out = {INVALID_SLOT, INVALID_SLOT, INVALID_SLOT, 0};
  for(i8 slot = CUSTOM_SLOT_COUNT - 1; slot >= 0; slot--) {
    if((used_mask & ((u8) 1 << slot)) != 0) continue;
    if(out.count == 0) {
      out.hour_tens = (u8) slot;
      out.count = 1;
    } else if(out.count == 1) {
      out.hour_units_colon = (u8) slot;
      out.count = 2;
    } else {
      out.minute = (u8) slot;
      out.count = CLOCK_GLYPH_COUNT;
      return true;
    }
  }
  return false;
}

} // пространство имён rtc_idle_clock

#endif
