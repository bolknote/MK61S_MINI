#include <cassert>
#include <cstring>
#include <iostream>

#include "hardware_info.hpp"

static usize utf8_width(const char* text) {
  usize width = 0;
  for(const unsigned char* cursor =
        reinterpret_cast<const unsigned char*>(text);
      *cursor != 0; cursor++) {
    if((*cursor & 0xC0U) != 0x80U) width++;
  }
  return width;
}

static void test_vbat_conversion(void) {
  const hardware_info::VbatReading nominal =
    hardware_info::calculate_vbat_millivolts(931, 1500, 1500);
  assert(nominal.valid);
  assert(nominal.millivolts >= 2999);
  assert(nominal.millivolts <= 3002);

  const hardware_info::VbatReading empty =
    hardware_info::calculate_vbat_millivolts(0, 1500, 1500);
  assert(empty.valid);
  assert(empty.millivolts == 0);

  assert(!hardware_info::calculate_vbat_millivolts(931, 0, 1500).valid);
  assert(!hardware_info::calculate_vbat_millivolts(931, 1500, 0).valid);
  assert(!hardware_info::calculate_vbat_millivolts(4096, 1500, 1500).valid);
}

static void test_line_formatting(void) {
  char line[32];
  assert(hardware_info::format_vbat_line(
    line, sizeof(line), true, {true, 3020}));
  assert(std::strcmp(line, "VBAT:3,02 В") == 0);

  assert(hardware_info::format_vbat_line(
    line, sizeof(line), false, {true, 3025}));
  assert(std::strcmp(line, "VBAT:3.03 V") == 0);

  assert(hardware_info::format_vbat_line(
    line, sizeof(line), true, {false, 0}));
  assert(std::strcmp(line, "VBAT:--,-- В") == 0);

  assert(hardware_info::format_display_line(
    line, sizeof(line), true, "LCD1602A00"));
  assert(std::strcmp(line, "Экран:LCD1602A00") == 0);
  assert(utf8_width(line) == 16);

  assert(hardware_info::format_display_line(
    line, sizeof(line), false, "LCD1602A02"));
  assert(std::strcmp(line, "Disp:LCD1602A02") == 0);
  assert(utf8_width(line) == 15);

  assert(hardware_info::format_display_line(
    line, sizeof(line), true, "UC1609"));
  assert(std::strcmp(line, "Экран:UC1609") == 0);
  assert(utf8_width(line) == 12);

  assert(hardware_info::format_generator_line(
    line, sizeof(line), true, "LSE"));
  assert(std::strcmp(line, "Генератор:LSE") == 0);
  assert(utf8_width(line) == 13);

  assert(hardware_info::format_generator_line(
    line, sizeof(line), false, "LSI"));
  assert(std::strcmp(line, "Generator:LSI") == 0);
  assert(utf8_width(line) == 13);

  char short_line[8];
  assert(!hardware_info::format_display_line(
    short_line, sizeof(short_line), false, "LCD1602A00"));
  assert(!hardware_info::format_generator_line(
    short_line, sizeof(short_line), false, "LSE"));
}

static void test_scroll_bounds(void) {
  assert(hardware_info::max_scroll_offset(2) == 3);
  assert(hardware_info::step_scroll_offset(0, 2, -1) == 0);
  assert(hardware_info::step_scroll_offset(0, 2, 1) == 1);
  assert(hardware_info::step_scroll_offset(1, 2, 1) == 2);
  assert(hardware_info::step_scroll_offset(2, 2, 1) == 3);
  assert(hardware_info::step_scroll_offset(3, 2, 1) == 3);
  assert(hardware_info::step_scroll_offset(3, 2, -1) == 2);
  assert(hardware_info::step_scroll_offset(2, 2, -1) == 1);

  assert(hardware_info::max_scroll_offset(4) == 1);
  assert(hardware_info::step_scroll_offset(0, 4, 1) == 1);
  assert(hardware_info::step_scroll_offset(1, 4, 1) == 1);
  assert(hardware_info::max_scroll_offset(5) == 0);
  assert(hardware_info::max_scroll_offset(6) == 0);
}

int main(void) {
  test_vbat_conversion();
  test_line_formatting();
  test_scroll_bounds();
  std::cout << "hardware_info_self_test: ok\n";
  return 0;
}
