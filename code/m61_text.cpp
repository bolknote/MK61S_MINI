#include "m61_text.hpp"

#include "cross_hal.h"
#include "library_pmk.hpp"
#include "mk61emu_core.h"
#include "tools.hpp"

namespace m61_text {

static constexpr u16 MAX_LINE_SIZE = 240;
static constexpr usize SCRIPT_KEY_HOLD_STEPS = 4;
static constexpr usize SCRIPT_KEY_SETTLE_STEPS = 64;
static constexpr u8 HIN_BYTES_PER_LINE = 24;

static bool is_space(char c) {
  return c == ' ' || c == '\t';
}

static bool is_line_end(char c) {
  return c == 0 || c == '\r' || c == '\n';
}

static const char* skip_spaces(const char* p) {
  while(is_space(*p)) p++;
  return p;
}

static bool token_ends(const char* p) {
  p = skip_spaces(p);
  return is_line_end(*p);
}

static bool starts_with(const char* line, const char* token) {
  while(*token != 0) {
    if(*line++ != *token++) return false;
  }
  return true;
}

static bool parse_decimal4(const char* p, u16& out) {
  u16 value = 0;
  for(u8 i = 0; i < 4; i++) {
    if(p[i] < '0' || p[i] > '9') return false;
    value = (u16) (value * 10 + (u16) (p[i] - '0'));
  }
  out = value;
  return true;
}

static bool parse_hex_digit(char c, u8& out) {
  if(c >= '0' && c <= '9') {
    out = (u8) (c - '0');
    return true;
  }
  if(c >= 'A' && c <= 'F') {
    out = (u8) (c - 'A' + 10);
    return true;
  }
  if(c >= 'a' && c <= 'f') {
    out = (u8) (c - 'a' + 10);
    return true;
  }
  return false;
}

static bool parse_hex_number(const char* p, u16& out) {
  p = skip_spaces(p);
  u16 value = 0;
  bool any = false;
  while(!is_line_end(*p) && !is_space(*p)) {
    u8 digit = 0;
    if(!parse_hex_digit(*p++, digit)) return false;
    value = (u16) ((value << 4) | digit);
    any = true;
  }
  if(!any) return false;
  out = value;
  return token_ends(p);
}

static bool press_scan_code(u16 keycode) {
  if(keycode == KEY_DEGREE) {
    MK61Emu_SetAngleUnit(DEGREE);
    return true;
  }
  if(keycode == KEY_GRADE) {
    MK61Emu_SetAngleUnit(GRADE);
    return true;
  }
  if(keycode == KEY_RADIAN) {
    MK61Emu_SetAngleUnit(RADIAN);
    return true;
  }
  if(keycode >= 40) return false;

  const TMK61_cross_key cross_key = KeyPairs[keycode];
  if(cross_key.as_u16() == NON.as_u16()) return false;

  core_61::clear_displayed();
  for(usize i = 0; i < SCRIPT_KEY_HOLD_STEPS; i++) {
    MK61Emu_SetKeyPress(cross_key.x, cross_key.y);
    core_61::step();
    if(core_61::is_RUN()) break;
  }

  for(usize i = 0; i < SCRIPT_KEY_SETTLE_STEPS; i++) {
    core_61::step();
    if(core_61::is_RUN() || core_61::is_displayed()) break;
  }

  core_61::clear_displayed();
  return true;
}

static bool execute_hin(const char* line) {
  u16 address = 0;
  if(!parse_decimal4(line + 4, address)) return false;
  if(address >= core_61::MAX_PROGRAM_STEP) return false;

  const char* p = line + 8;
  if(!is_space(*p)) return false;
  p = skip_spaces(p);

  u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
  core_61::get_code_page(&code_page[0]);

  u16 linear_addr = address;
  while(!is_line_end(*p)) {
    if(is_space(*p)) {
      p++;
      continue;
    }

    if(linear_addr >= core_61::MAX_PROGRAM_STEP) return false;
    u8 hi = 0;
    u8 lo = 0;
    if(!parse_hex_digit(*p++, hi)) return false;
    if(!parse_hex_digit(*p++, lo)) return false;
    code_page[linear_addr++] = (u8) ((hi << 4) | lo);
  }

  const bool force_expanded = linear_addr > core_61::CLASSIC_PROGRAM_STEP;
  apply_program_memory_auto(&code_page[0], linear_addr, false, force_expanded);
  core_61::set_code_page(&code_page[0]);
  return true;
}

static bool execute_kbd(const char* line) {
  u16 keycode = 0;
  if(!parse_hex_number(line + 4, keycode)) return false;
  return press_scan_code(keycode);
}

static bool execute_line(const char* line) {
  line = skip_spaces(line);
  if(is_line_end(*line)) return true;
  if(starts_with(line, "hin ")) return execute_hin(line);
  if(starts_with(line, "kbd ")) return execute_kbd(line);
  if(starts_with(line, "run") && token_ends(line + 3)) return run_loaded_setup_program();
  return false;
}

bool execute(const u8* text, u16 len) {
  if(text == NULL && len != 0) return false;

  MK61Emu_ClearCodePage();

  char line[MAX_LINE_SIZE + 1];
  u16 line_len = 0;
  for(u16 i = 0; i <= len; i++) {
    const char c = (i < len) ? (char) text[i] : '\n';
    if(c == '\r') continue;
    if(c == '\n' || c == 0) {
      line[line_len] = 0;
      if(!execute_line(line)) return false;
      line_len = 0;
      continue;
    }
    if(line_len >= MAX_LINE_SIZE) return false;
    line[line_len++] = c;
  }
  return true;
}

static bool append_char(u8* out, u16 capacity, u16& pos, char c) {
  if(pos >= capacity) return false;
  out[pos++] = (u8) c;
  return true;
}

static bool append_text(u8* out, u16 capacity, u16& pos, const char* text) {
  while(*text != 0) {
    if(!append_char(out, capacity, pos, *text++)) return false;
  }
  return true;
}

static char hex_digit(u8 value) {
  value &= 0x0F;
  return (value < 10) ? (char) ('0' + value) : (char) ('A' + value - 10);
}

static bool append_decimal4(u8* out, u16 capacity, u16& pos, u16 value) {
  if(value > 9999) return false;
  if(!append_char(out, capacity, pos, (char) ('0' + (value / 1000) % 10))) return false;
  if(!append_char(out, capacity, pos, (char) ('0' + (value / 100) % 10))) return false;
  if(!append_char(out, capacity, pos, (char) ('0' + (value / 10) % 10))) return false;
  return append_char(out, capacity, pos, (char) ('0' + value % 10));
}

static bool append_hex_byte(u8* out, u16 capacity, u16& pos, u8 value) {
  if(!append_char(out, capacity, pos, hex_digit((u8) (value >> 4)))) return false;
  return append_char(out, capacity, pos, hex_digit(value));
}

bool format_current_program(u8* out, u16 capacity, u16* out_len) {
  if(out_len != NULL) *out_len = 0;
  if(out == NULL && capacity != 0) return false;

  u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
  core_61::get_code_page(&code_page[0]);

  const u16 program_steps = (u16) core_61::program_steps();
  u16 pos = 0;
  for(u16 offset = 0; offset < program_steps; offset = (u16) (offset + HIN_BYTES_PER_LINE)) {
    const u16 remaining = (u16) (program_steps - offset);
    const u8 line_len = (remaining > HIN_BYTES_PER_LINE) ? HIN_BYTES_PER_LINE : (u8) remaining;
    if(!append_text(out, capacity, pos, "hin ")) return false;
    if(!append_decimal4(out, capacity, pos, offset)) return false;
    if(!append_char(out, capacity, pos, ' ')) return false;
    for(u8 i = 0; i < line_len; i++) {
      if(!append_hex_byte(out, capacity, pos, code_page[offset + i])) return false;
    }
    if(!append_char(out, capacity, pos, '\n')) return false;
  }

  if(out_len != NULL) *out_len = pos;
  return true;
}

} // namespace m61_text
