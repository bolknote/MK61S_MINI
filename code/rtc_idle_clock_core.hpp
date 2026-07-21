#ifndef MK61_RTC_IDLE_CLOCK_CORE_HPP
#define MK61_RTC_IDLE_CLOCK_CORE_HPP

#include "rust_types.h"

namespace rtc_idle_clock {

static constexpr u8 DIGIT_ROWS = 5;
static constexpr u8 GLYPH_ROWS = 8;
static constexpr u8 CUSTOM_SLOT_COUNT = 8;
static constexpr u8 CLOCK_GLYPH_COUNT = 3;
static constexpr u8 INVALID_SLOT = 0xFF;
static constexpr u8 GRAPHIC_CLOCK_SCALE = 2;
static constexpr u8 GRAPHIC_CLOCK_DIGIT_WIDTH = 2 * GRAPHIC_CLOCK_SCALE;
static constexpr u8 GRAPHIC_CLOCK_HEIGHT = DIGIT_ROWS * GRAPHIC_CLOCK_SCALE;
static constexpr u8 GRAPHIC_CLOCK_GAP = GRAPHIC_CLOCK_SCALE;
static constexpr u8 GRAPHIC_CLOCK_HOUR_TENS_X = 0;
static constexpr u8 GRAPHIC_CLOCK_HOUR_UNITS_X =
  GRAPHIC_CLOCK_HOUR_TENS_X + GRAPHIC_CLOCK_DIGIT_WIDTH + GRAPHIC_CLOCK_GAP;
static constexpr u8 GRAPHIC_CLOCK_COLON_X =
  GRAPHIC_CLOCK_HOUR_UNITS_X + GRAPHIC_CLOCK_DIGIT_WIDTH + GRAPHIC_CLOCK_GAP;
static constexpr u8 GRAPHIC_CLOCK_MINUTE_TENS_X =
  GRAPHIC_CLOCK_COLON_X + GRAPHIC_CLOCK_SCALE + GRAPHIC_CLOCK_GAP;
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
  for(u8 source_y = 0; source_y < DIGIT_ROWS; source_y++) {
    for(u8 source_x = 0; source_x < 2; source_x++) {
      const u8 source_mask = (u8) 1U << (1U - source_x);
      if((DIGITS[digit][source_y] & source_mask) == 0) continue;
      for(u8 scale_y = 0; scale_y < GRAPHIC_CLOCK_SCALE; scale_y++) {
        const u8 y = source_y * GRAPHIC_CLOCK_SCALE + scale_y;
        for(u8 scale_x = 0; scale_x < GRAPHIC_CLOCK_SCALE; scale_x++) {
          const u8 x = left + source_x * GRAPHIC_CLOCK_SCALE + scale_x;
          out[y] |= (u32) 1U << x;
        }
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

  for(u8 dot = 0; dot < 2; dot++) {
    const u8 top = (u8) ((dot == 0 ? 1 : 3) * GRAPHIC_CLOCK_SCALE);
    for(u8 y = 0; y < GRAPHIC_CLOCK_SCALE; y++) {
      for(u8 x = 0; x < GRAPHIC_CLOCK_SCALE; x++) {
        out[top + y] |= (u32) 1U << (GRAPHIC_CLOCK_COLON_X + x);
      }
    }
  }
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
