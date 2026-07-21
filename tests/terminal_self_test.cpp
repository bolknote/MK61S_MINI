#include "terminal_command_ids.hpp"
#include "terminal_core.hpp"
#include "rtc_clock_core.hpp"
#include "rtc_idle_clock_core.hpp"
#include "rtc_settings_core.hpp"

#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>

static void test_input_capacity_reserves_terminator(void) {
  assert(terminal_core::input_can_append(0));
  assert(terminal_core::input_can_append(terminal_core::MAX_INPUT_TEXT - 1));
  assert(!terminal_core::input_can_append(terminal_core::MAX_INPUT_TEXT));
  assert(terminal_core::MAX_INPUT_TEXT + 1 == terminal_core::INPUT_CAPACITY);
}

static void test_bounded_unsigned_parser(void) {
  usize value = 0;
  assert(terminal_core::parse_single_unsigned("EF", 16, 0xEF, value));
  assert(value == 0xEF);
  assert(!terminal_core::parse_single_unsigned("F0", 16, 0xEF, value));
  assert(!terminal_core::parse_single_unsigned("garbage", 16, 0xEF, value));
  assert(!terminal_core::parse_single_unsigned("10 trailing", 16, 0xEF, value));
  assert(!terminal_core::parse_single_unsigned("999999999999999999", 10, 99, value));
}

static void test_confirmation_is_a_complete_token(void) {
  assert(terminal_core::exact_confirmation("y", 'y'));
  assert(terminal_core::exact_confirmation("  Y  ", 'y'));
  assert(!terminal_core::exact_confirmation("yes", 'y'));
  assert(!terminal_core::exact_confirmation("yesterday", 'y'));
  assert(!terminal_core::exact_confirmation("n", 'y'));
}

static void test_quoted_path_tokens(void) {
  const char* input = "  \"/My Files/a.m61\"  '../Other Folder'  ";
  char first[64];
  char second[64];
  assert(terminal_core::parse_token(input, first, sizeof(first)));
  assert(std::strcmp(first, "/My Files/a.m61") == 0);
  assert(terminal_core::parse_token(input, second, sizeof(second)));
  assert(std::strcmp(second, "../Other Folder") == 0);
  assert(terminal_core::at_end(input));

  input = "\"unterminated";
  assert(!terminal_core::parse_token(input, first, sizeof(first)));
  input = "\"ok\"junk";
  assert(!terminal_core::parse_token(input, first, sizeof(first)));
}

static void test_decimal_parser_is_finite_and_bounded(void) {
  double value = 0.0;
  assert(terminal_core::parse_single_decimal("-1.25e+02", value));
  assert(std::fabs(value + 125.0) < 0.000001);
  assert(terminal_core::parse_single_decimal("3.14", value));
  assert(!terminal_core::parse_single_decimal("1e100", value));
  assert(!terminal_core::parse_single_decimal("1e", value));
  assert(!terminal_core::parse_single_decimal("1234567890123456789", value));
  assert(!terminal_core::parse_single_decimal("2.0 junk", value));
}

static void test_assembler_accepts_final_mnemonic_and_is_atomic_input(void) {
  const char isa[] = "0,1,add,jnz[E]";
  terminal_core::Assembly assembly = terminal_core::parse_assembly("0007  1\tadd  jnz[E]", 0, isa, 112);
  assert(assembly.error == terminal_core::AssemblyError::NONE);
  assert(assembly.address == 7);
  assert(assembly.count == 3);
  assert(assembly.opcodes[0] == 1);
  assert(assembly.opcodes[1] == 2);
  assert(assembly.opcodes[2] == 3);

  assembly = terminal_core::parse_assembly("0007 1 broken", 0, isa, 112);
  assert(assembly.error == terminal_core::AssemblyError::UNKNOWN_MNEMONIC);
  assert(assembly.count == 1); // caller commits only when error == NONE

  assembly = terminal_core::parse_assembly("0111 1 1", 0, isa, 112);
  assert(assembly.error == terminal_core::AssemblyError::TOO_LONG);
}

static void test_script_allowlist_is_explicit(void) {
  assert(terminal_command_allowed_in_script(CMD_HIN));
  assert(terminal_command_allowed_in_script(CMD_ASM));
  assert(terminal_command_allowed_in_script(CMD_RUN));
  assert(terminal_command_allowed_in_script(CMD_IF));
  assert(!terminal_command_allowed_in_script(CMD_DFU));
  assert(!terminal_command_allowed_in_script(CMD_RESET));
  assert(!terminal_command_allowed_in_script(CMD_FS_REMOVE));
  assert(!terminal_command_allowed_in_script(CMD_FS_CLEAN));
  assert(!terminal_command_allowed_in_script(CMD_FS_PWD));
  assert(!terminal_command_allowed_in_script(CMD_FS_CD));
  assert(!terminal_command_allowed_in_script(CMD_FS_MKDIR));
  assert(!terminal_command_allowed_in_script(CMD_FS_MOVE));
  assert(!terminal_command_allowed_in_script(CMD_FS_RMDIR));
  assert(!terminal_command_allowed_in_script(CMD_FS_STAT));
  assert(!terminal_command_allowed_in_script(CMD_ERASE_STORAGE));
  assert(!terminal_command_allowed_in_script(CMD_DATE));
  assert(!terminal_command_allowed_in_script(CMD_UNKNOWN));
}

static void test_rtc_datetime_parser_and_formatter(void) {
  assert(rtc_clock::select_clock_source(false, false) ==
         rtc_clock::ClockSource::LSI);
  assert(rtc_clock::select_clock_source(false, true) ==
         rtc_clock::ClockSource::LSI);
  assert(rtc_clock::select_clock_source(true, false) ==
         rtc_clock::ClockSource::LSI);
  assert(rtc_clock::select_clock_source(true, true) ==
         rtc_clock::ClockSource::LSE);
  assert(!rtc_clock::retained_lse_must_be_disabled(false, false));
  assert(rtc_clock::retained_lse_must_be_disabled(false, true));
  assert(!rtc_clock::retained_lse_must_be_disabled(true, false));
  assert(!rtc_clock::retained_lse_must_be_disabled(true, true));

  rtc_clock::DateTime value = {};
  assert(rtc_clock::parse_datetime("2026-07-19 14:35:00", value));
  assert(value.year == 2026 && value.month == 7 && value.day == 19);
  assert(value.hour == 14 && value.minute == 35 && value.second == 0);
  assert(rtc_clock::weekday(value) == 7); // Sunday

  char text[rtc_clock::DATETIME_TEXT_SIZE];
  assert(rtc_clock::format_datetime(value, text));
  assert(std::strcmp(text, "2026-07-19 14:35:00") == 0);

  assert(rtc_clock::parse_datetime("  2000-02-29 00:00:00  ", value));
  assert(rtc_clock::weekday(value) == 2); // Tuesday
  assert(!rtc_clock::parse_datetime("2023-02-29 00:00:00", value));
  assert(!rtc_clock::parse_datetime("2100-01-01 00:00:00", value));
  assert(!rtc_clock::parse_datetime("2026-04-31 00:00:00", value));
  assert(!rtc_clock::parse_datetime("2026-07-19T14:35:00", value));
  assert(!rtc_clock::parse_datetime("2026-07-19 24:00:00", value));
  assert(!rtc_clock::parse_datetime("2026-07-19 14:35:60", value));
  assert(!rtc_clock::parse_datetime("2026-07-19 14:35:00 junk", value));
}

static void test_rtc_startup_material(void) {
  const rtc_clock::StartupSnapshot base = {
    {2026, 7, 19, 14, 35, 0},
    255,
    255,
    true
  };
  assert(rtc_clock::is_valid(base));

  rtc_clock::StartupSnapshot changed = base;
  changed.subsecond = 254;
  assert(rtc_clock::startup_phase_material(changed)
      != rtc_clock::startup_phase_material(base));
  assert(rtc_clock::startup_calendar_material(changed)
      == rtc_clock::startup_calendar_material(base));

  changed = base;
  changed.date_time.second = 1;
  assert(rtc_clock::startup_calendar_material(changed)
      != rtc_clock::startup_calendar_material(base));

  changed = base;
  changed.time_set = false;
  assert(rtc_clock::startup_calendar_material(changed)
      != rtc_clock::startup_calendar_material(base));

  changed = base;
  changed.subsecond = 256;
  assert(!rtc_clock::is_valid(changed));
}

static void test_date_terminal_request(void) {
  rtc_clock::TerminalRequest request = rtc_clock::parse_date_request("");
  assert(request.action == rtc_clock::TerminalAction::SHOW);
  request = rtc_clock::parse_date_request("  \t");
  assert(request.action == rtc_clock::TerminalAction::SHOW);

  request = rtc_clock::parse_date_request("2024-02-29 23:59:59");
  assert(request.action == rtc_clock::TerminalAction::SET);
  assert(request.date_time.year == 2024 && request.date_time.second == 59);

  assert(rtc_clock::parse_date_request("set 2024-02-29 23:59:59").action == rtc_clock::TerminalAction::INVALID);
  assert(rtc_clock::parse_date_request("2026-2-3 9:5:7").action == rtc_clock::TerminalAction::INVALID);
  assert(rtc_clock::parse_date_request("2023-02-29 00:00:00").action == rtc_clock::TerminalAction::INVALID);
  assert(rtc_clock::parse_date_request("status").action == rtc_clock::TerminalAction::INVALID);
}

static void test_rtc_build_datetime_parser(void) {
  rtc_clock::DateTime value = {};
  assert(rtc_clock::parse_build_datetime("Jul 19 2026", "14:35:00", value));
  assert(value.year == 2026 && value.month == 7 && value.day == 19);
  assert(value.hour == 14 && value.minute == 35 && value.second == 0);

  assert(rtc_clock::parse_build_datetime("Feb  9 2024", "01:02:03", value));
  assert(value.year == 2024 && value.month == 2 && value.day == 9);
  assert(!rtc_clock::parse_build_datetime("Feb 29 2023", "01:02:03", value));
  assert(!rtc_clock::parse_build_datetime("Foo 19 2026", "01:02:03", value));
  assert(!rtc_clock::parse_build_datetime("Jul 19 2026", "24:00:00", value));
  assert(!rtc_clock::parse_build_datetime("Jul 19 2100", "00:00:00", value));
  assert(!rtc_clock::parse_build_datetime("short", "00:00:00", value));
}

static void test_rtc_settings_editor(void) {
  rtc_settings::Editor editor = {};
  const rtc_clock::DateTime initial = {2026, 7, 19, 14, 35, 0};
  assert(rtc_settings::begin(editor, initial));
  assert(std::strcmp(editor.text, "2026-07-19 14:35:00") == 0);
  assert(rtc_settings::active_text_position(editor) == 0);

  const char digits[] = "20240229235958";
  for(u8 i = 0; i < rtc_settings::EDITABLE_DIGIT_COUNT; i++) {
    assert(rtc_settings::enter_digit(editor, digits[i] - '0'));
  }
  assert(std::strcmp(editor.text, "2024-02-29 23:59:58") == 0);
  assert(rtc_settings::active_text_position(editor) == 18);
  rtc_settings::move_right(editor);
  assert(rtc_settings::active_text_position(editor) == 18);
  rtc_settings::move_left(editor);
  assert(rtc_settings::active_text_position(editor) == 17);

  rtc_clock::DateTime value = {};
  assert(rtc_settings::value(editor, value));
  assert(value.year == 2024 && value.month == 2 && value.day == 29);
  assert(value.hour == 23 && value.minute == 59 && value.second == 58);
  assert(!rtc_settings::enter_digit(editor, -1));
  assert(!rtc_settings::enter_digit(editor, 10));

  assert(rtc_settings::begin(editor, initial));
  const char invalid_digits[] = "20230229235958";
  for(u8 i = 0; i < rtc_settings::EDITABLE_DIGIT_COUNT; i++) {
    assert(rtc_settings::enter_digit(editor, invalid_digits[i] - '0'));
  }
  assert(!rtc_settings::value(editor, value));
}

static void test_rtc_idle_clock_glyphs_and_slots(void) {
  u8 glyph[rtc_idle_clock::GLYPH_ROWS] = {};
  assert(rtc_idle_clock::build_hour_tens_glyph(12, glyph));
  assert(glyph[0] == 0b00000);
  assert(glyph[1] == 0b00001);
  assert(glyph[2] == 0b00001);
  assert(glyph[3] == 0b00001);
  assert(glyph[4] == 0b00001);
  assert(glyph[5] == 0b00001);
  assert(glyph[6] == 0b00000);
  assert(glyph[7] == 0b00000);
  assert(!rtc_idle_clock::build_hour_tens_glyph(24, glyph));

  assert(rtc_idle_clock::build_hour_units_colon_glyph(12, glyph));
  assert(glyph[0] == 0b00000);
  assert(glyph[1] == 0b11000);
  assert(glyph[2] == 0b01001);
  assert(glyph[3] == 0b01000);
  assert(glyph[4] == 0b10001);
  assert(glyph[5] == 0b11000);
  assert(glyph[6] == 0b00000);
  assert(glyph[7] == 0b00000);
  assert(!rtc_idle_clock::build_hour_units_colon_glyph(24, glyph));

  assert(rtc_idle_clock::build_pair_glyph(12, glyph));
  assert(glyph[0] == 0b00000);
  assert(glyph[1] == 0b01011);
  assert(glyph[2] == 0b01001);
  assert(glyph[3] == 0b01001);
  assert(glyph[4] == 0b01010);
  assert(glyph[5] == 0b01011);
  assert(glyph[6] == 0b00000);
  assert(glyph[7] == 0b00000);
  assert(!rtc_idle_clock::build_pair_glyph(100, glyph));

  assert(rtc_idle_clock::slot_for_character(0) == 0);
  assert(rtc_idle_clock::slot_for_character(8) == 0);
  assert(rtc_idle_clock::slot_for_character(15) == 7);
  assert(rtc_idle_clock::slot_for_character(' ') == rtc_idle_clock::INVALID_SLOT);

  rtc_idle_clock::Slots slots = {};
  assert(rtc_idle_clock::select_slots(0b00011111, slots));
  assert(slots.count == rtc_idle_clock::CLOCK_GLYPH_COUNT);
  assert(slots.hour_tens == 7 && slots.hour_units_colon == 6 && slots.minute == 5);
  assert(!rtc_idle_clock::select_slots(0b00111111, slots));
  assert(!rtc_idle_clock::select_slots(0xFF, slots));

  u32 graphic[rtc_idle_clock::GRAPHIC_CLOCK_HEIGHT] = {};
  assert(rtc_idle_clock::build_graphic_clock(0, 0, graphic));
  const u32 digits =
    ((u32) 0x0F << rtc_idle_clock::GRAPHIC_CLOCK_HOUR_TENS_X) |
    ((u32) 0x0F << rtc_idle_clock::GRAPHIC_CLOCK_HOUR_UNITS_X) |
    ((u32) 0x0F << rtc_idle_clock::GRAPHIC_CLOCK_MINUTE_TENS_X) |
    ((u32) 0x0F << rtc_idle_clock::GRAPHIC_CLOCK_MINUTE_UNITS_X);
  const u32 colon = (u32) 0x03 << rtc_idle_clock::GRAPHIC_CLOCK_COLON_X;
  for(u8 y = 0; y < rtc_idle_clock::GRAPHIC_CLOCK_HEIGHT; y++) {
    const bool colon_row = y == 2 || y == 3 || y == 6 || y == 7;
    assert(graphic[y] == (digits | (colon_row ? colon : 0)));
    assert((graphic[y] >> rtc_idle_clock::GRAPHIC_CLOCK_WIDTH) == 0);
  }
  assert(!rtc_idle_clock::build_graphic_clock(24, 0, graphic));
  assert(!rtc_idle_clock::build_graphic_clock(0, 60, graphic));
}

int main(void) {
  test_input_capacity_reserves_terminator();
  test_bounded_unsigned_parser();
  test_confirmation_is_a_complete_token();
  test_quoted_path_tokens();
  test_decimal_parser_is_finite_and_bounded();
  test_assembler_accepts_final_mnemonic_and_is_atomic_input();
  test_script_allowlist_is_explicit();
  test_rtc_datetime_parser_and_formatter();
  test_rtc_startup_material();
  test_date_terminal_request();
  test_rtc_build_datetime_parser();
  test_rtc_settings_editor();
  test_rtc_idle_clock_glyphs_and_slots();
  std::printf("terminal_self_test: ok\n");
  return 0;
}
