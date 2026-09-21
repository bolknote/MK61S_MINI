#include "lcd_ru.hpp"
#include "mk8_codec.hpp"

#include <assert.h>
#include <stdio.h>

int main() {
  for(u8 byte = mk8::BYTE_LEFT_ARROW; byte <= mk8::BYTE_RETURN_ARROW;
      ++byte) {
    const char single[] = {(char) byte, 0};
    lcd_ru::font_map_t single_map = {};
    lcd_ru::scan_text(single_map, single, 1);
    const u16 codepoint = mk8::codepoint(byte);
    u8 rom = 0;
    const bool in_rom = lcd_ru::rom_char(codepoint, rom);
    u8 fixed_slot = 0;
    const bool fixed = lcd_ru::fixed_cgram_char(codepoint, fixed_slot);
    assert(in_rom || fixed || lcd_ru::slot_for(single_map, codepoint) >= 0);
    assert(!single_map.overflow);
  }

  const char text[] = {
      (char) mk8::BYTE_CYCLE_ARROW,
      (char) mk8::BYTE_LESS_EQUAL,
      (char) mk8::BYTE_RETURN_ARROW,
      0};
  lcd_ru::font_map_t map = {};
  lcd_ru::scan_text(map, text, 3);

#if defined(MK61_OLED1602_WS0010)
  assert((map.reserved_mask &
          ((u8) 1U << ws0010_charset::cgram::CYCLE_ARROW)) != 0);
#else
  assert(lcd_ru::slot_for(map, 0x21BB) >= 0);
#endif
  assert(lcd_ru::slot_for(map, 0x2264) >= 0);
  assert(lcd_ru::slot_for(map, 0x21B5) >= 0);
  assert(!map.overflow);
  puts("lcd_ru_m8_self_test: ok");
}
