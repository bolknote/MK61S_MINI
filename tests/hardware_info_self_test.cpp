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

static void test_device_identity(void) {
  const hardware_info::DeviceIdentity f401xb =
    hardware_info::decode_device_identity(0x10000423U, 128);
  assert(f401xb.device_id == 0x423);
  assert(f401xb.revision_id == 0x1000);
  assert(f401xb.flash_kb == 128);
  assert(f401xb.ram_kb == 64);
  assert(std::strcmp(f401xb.family, "STM32F401") == 0);
  assert(f401xb.pin_count_code == 'x');
  assert(f401xb.flash_size_code == 'B');

  const hardware_info::DeviceIdentity f401xc =
    hardware_info::decode_device_identity(0x20010423U, 256, 'C');
  assert(f401xc.revision_id == 0x2001);
  assert(std::strcmp(f401xc.family, "STM32F401") == 0);
  assert(f401xc.pin_count_code == 'C');
  assert(f401xc.flash_size_code == 'C');

  const hardware_info::DeviceIdentity f401xd =
    hardware_info::decode_device_identity(0x10000433U, 384);
  assert(f401xd.ram_kb == 96);
  assert(f401xd.flash_size_code == 'D');

  const hardware_info::DeviceIdentity f401xe =
    hardware_info::decode_device_identity(0x10000433U, 512);
  assert(f401xe.flash_size_code == 'E');

  const hardware_info::DeviceIdentity f411xc =
    hardware_info::decode_device_identity(0x10000431U, 256);
  assert(f411xc.ram_kb == 128);
  assert(std::strcmp(f411xc.family, "STM32F411") == 0);
  assert(f411xc.flash_size_code == 'C');

  const hardware_info::DeviceIdentity f411xe =
    hardware_info::decode_device_identity(0x10000431U, 512);
  assert(f411xe.flash_size_code == 'E');

  const hardware_info::DeviceIdentity unexpected_density =
    hardware_info::decode_device_identity(0x10000431U, 384);
  assert(unexpected_density.flash_size_code == '?');
  assert(unexpected_density.flash_kb == 384);

  const hardware_info::DeviceIdentity invalid_signature =
    hardware_info::decode_device_identity(0x10000423U, 0xFFFF);
  assert(invalid_signature.flash_size_code == '?');
  assert(invalid_signature.flash_kb == 0);

  const hardware_info::DeviceIdentity unknown =
    hardware_info::decode_device_identity(0xABCD0999U, 1024);
  assert(unknown.device_id == 0x999);
  assert(unknown.revision_id == 0xABCD);
  assert(unknown.flash_kb == 1024);
  assert(unknown.ram_kb == 0);
  assert(unknown.family == NULL);
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
  const hardware_info::DeviceIdentity f401xc =
    hardware_info::decode_device_identity(0x10000423U, 256, 'C');
  assert(hardware_info::format_device_line(
    line, sizeof(line), true, f401xc));
  assert(std::strcmp(line, "ЧИП:STM32F401CC") == 0);
  assert(utf8_width(line) == 15);

  const hardware_info::DeviceIdentity unspecified_package =
    hardware_info::decode_device_identity(0x10000423U, 256);
  assert(hardware_info::format_device_line(
    line, sizeof(line), false, unspecified_package));
  assert(std::strcmp(line, "Chip:STM32F401xC") == 0);

  assert(hardware_info::format_memory_line(
    line, sizeof(line), false, f401xc));
  assert(std::strcmp(line, "RAM:64 ROM:256") == 0);

  const hardware_info::DeviceIdentity unknown =
    hardware_info::decode_device_identity(0x10000999U, 512);
  assert(hardware_info::format_device_line(
    line, sizeof(line), false, unknown));
  assert(std::strcmp(line, "Chip:ID 0x999") == 0);
  assert(hardware_info::format_memory_line(
    line, sizeof(line), true, unknown));
  assert(std::strcmp(line, "ОЗУ:? ПЗУ:512") == 0);

  const hardware_info::DeviceIdentity missing_flash =
    hardware_info::decode_device_identity(0x10000431U, 0);
  assert(hardware_info::format_memory_line(
    line, sizeof(line), false, missing_flash));
  assert(std::strcmp(line, "RAM:128 ROM:?") == 0);

  assert(hardware_info::format_vbat_line(
    line, sizeof(line), true, {true, 3020}));
  assert(std::strcmp(line, "VBAT вход:3,02 В") == 0);

  assert(hardware_info::format_vbat_line(
    line, sizeof(line), false, {true, 3025}));
  assert(std::strcmp(line, "VBAT pin:3.03 V") == 0);

  assert(hardware_info::format_vbat_line(
    line, sizeof(line), true, {false, 0}));
  assert(std::strcmp(line, "VBAT вход:--,-- В") == 0);

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
  test_device_identity();
  test_vbat_conversion();
  test_line_formatting();
  test_scroll_bounds();
  std::cout << "hardware_info_self_test: ok\n";
  return 0;
}
