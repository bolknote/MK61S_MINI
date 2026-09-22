#include "lcd_ru.hpp"
#include "mk8_codec.hpp"
#include "mk8_literal.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void check_system_window(const char* top, const char* bottom,
                                u8 width) {
  assert(strlen(top) <= width && strlen(bottom) <= width);
  lcd_ru::font_map_t map = {};
  lcd_ru::scan_text(map, top, width);
  lcd_ru::scan_text(map, bottom, width);
  assert(!map.overflow);
}

int main() {
  // The character LCD shows two adjacent menu items at once. Both lines must
  // fit alongside the selection marker without exhausting its eight CGRAM
  // slots on either the A00 or A02 controller.
  check_system_window(M8("Разработка"), M8("Система"), 15);
  check_system_window(M8("Перезагрузка"), M8("Информация"), 15);
  check_system_window(M8("Информация"), M8("Плата"), 15);
  check_system_window(M8("Плата"), M8("Формат диска"), 15);
  check_system_window(M8("Формат диска"), M8("Полный сброс"), 15);
  check_system_window(M8("USB-диск уйдёт"),
                      M8("OK далее ESC нет"), 16);
  check_system_window(M8("Формат диска?"), M8("OK да ESC нет"), 16);
  check_system_window(M8("Файлы+настройки"), M8("OK да ESC нет"), 16);
  check_system_window(M8("Сброс настроек"), M8("Подождите"), 16);
  check_system_window(M8("Ошибка настроек"), M8("Любая клавиша"), 16);
  check_system_window(M8("USB-диск"), M8("сохранение..."), 16);

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
    u8 fallback = '?';
    assert(lcd_ru::fallback_char(codepoint, fallback));
    assert(fallback >= 0x20 && fallback <= 0x7E && fallback != '?');
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
