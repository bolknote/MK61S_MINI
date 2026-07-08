#include "m61_text.hpp"

#include "basic.hpp"
#include "cross_hal.h"
#include "focal.hpp"
#include "keyboard.h"
#include "mk61emu_core.h"
#include "program_store.hpp"
#include "shared_scratch.hpp"
#include "terminal.hpp"
#include "tinybasic.hpp"

#include <string.h>

namespace m61_text {

static constexpr u16 MAX_LINE_SIZE = 240;
static constexpr u8 HIN_BYTES_PER_LINE = 24;

enum class RunnerState : u8 {
  IDLE,
  EXECUTING,
  WAIT_RUN_START,
  WAIT_RUN_STOP,
  PAUSED_AFTER_RUN
};

static RunnerState runner_state = RunnerState::IDLE;
static u16 script_len = 0;
static u16 script_pos = 0;
static bool script_error = false;
static class_terminal script_terminal;

static bool is_line_end(char c) {
  return c == 0 || c == '\r' || c == '\n';
}

static bool is_space(char c) {
  return c == ' ' || c == '\t';
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

static u8* script_buffer(void) {
  return shared_scratch::data(shared_scratch::Owner::M61_SCRIPT);
}

bool active(void) {
  return runner_state != RunnerState::IDLE;
}

void cancel(void) {
  runner_state = RunnerState::IDLE;
  script_len = 0;
  script_pos = 0;
  script_error = false;
  shared_scratch::release(shared_scratch::Owner::M61_SCRIPT);
}

static void finish_script(void) {
  cancel();
}

static void fail_script(void) {
  cancel();
  script_error = true;
}

static bool read_next_line(char* line, u16 capacity) {
  if(line == NULL || capacity == 0) return false;
  u8* buffer = script_buffer();
  if(buffer == NULL) return false;

  u16 line_len = 0;
  while(script_pos <= script_len) {
    const char c = (script_pos < script_len) ? (char) buffer[script_pos++] : '\n';
    if(c == '\r') continue;
    if(c == '\n' || c == 0) {
      line[line_len] = 0;
      return true;
    }
    if(line_len + 1 >= capacity) return false;
    line[line_len++] = c;
  }

  line[0] = 0;
  return true;
}

static bool copy_run_name(const char* args, char* name, usize capacity) {
  args = skip_spaces(args);
  usize len = 0;
  while(!is_line_end(args[len])) len++;
  while(len > 0 && is_space(args[len - 1])) len--;
  if(len == 0 || len >= capacity) return false;
  for(usize i = 0; i < len; i++) name[i] = args[i];
  name[len] = 0;

  char* dot = strrchr(name, '.');
  if(dot != NULL) *dot = 0;
  return name[0] != 0;
}

static bool run_named_program(const char* args) {
  char name[program_store::NAME_SIZE];
  if(!copy_run_name(args, name, sizeof(name))) return false;

#if MK61_ENABLE_BASIC
  if(program_store::exists(program_store::ProgramType::BASIC, name)) return RunBasicProgram(name);
#endif
#if MK61_ENABLE_FOCAL
  if(program_store::exists(program_store::ProgramType::FOCAL, name)) return RunFocalProgram(name);
#endif
#if MK61_ENABLE_TINYBASIC
  if(program_store::exists(program_store::ProgramType::TINYBASIC, name)) return RunTinyBasicProgram(name);
#endif
  return false;
}

static void queue_current_program_run(void) {
  kbd::push((i8) sw::F);
  kbd::push((i8) sw::NEG);
  kbd::push((i8) sw::RET);
  kbd::push((i8) sw::RUN);
}

static bool execute_script_line(const char* raw_line) {
  const char* line = skip_spaces(raw_line);
  if(is_line_end(*line)) return true;

  if(starts_with(line, "run") && (token_ends(line + 3) || is_space(line[3]))) {
    const char* args = skip_spaces(line + 3);
    if(!is_line_end(*args)) return run_named_program(args);
    queue_current_program_run();
    runner_state = RunnerState::WAIT_RUN_START;
    return true;
  }

  const i32 result = script_terminal.execute_script_line(line);
  if(result >= 0) {
    kbd::push((i8) result);
    return true;
  }
  return result == -1;
}

void service(void) {
  if(runner_state == RunnerState::WAIT_RUN_START) {
    if(core_61::is_RUN()) runner_state = RunnerState::WAIT_RUN_STOP;
    return;
  }

  if(runner_state == RunnerState::WAIT_RUN_STOP) {
    if(core_61::is_CALC()) {
      core_61::clear_displayed();
      runner_state = RunnerState::PAUSED_AFTER_RUN;
    }
    return;
  }

  while(runner_state == RunnerState::EXECUTING) {
    if(script_pos >= script_len) {
      finish_script();
      return;
    }

    char line[MAX_LINE_SIZE + 1];
    if(!read_next_line(line, sizeof(line))) {
      fail_script();
      return;
    }
    if(!execute_script_line(line)) {
      fail_script();
      return;
    }
  }
}

bool handle_key(i32 key) {
  if(runner_state != RunnerState::PAUSED_AFTER_RUN) return false;

  // C/P stays available to the MK program; OK means "return to the script".
  if(key == KEY_OK || key == KEY_OK_PRESS) {
    kbd::get_key();
    runner_state = RunnerState::EXECUTING;
    service();
    return true;
  }

  if(key == KEY_ESC || key == KEY_ESC_PRESS) {
    kbd::get_key();
    cancel();
    return true;
  }

  return false;
}

bool start(const u8* text, u16 len) {
  if(text == NULL && len != 0) return false;
  if(len > program_store::MAX_MK61_TEXT_SIZE) return false;
  if(active()) cancel();

  u8* buffer = shared_scratch::acquire(shared_scratch::Owner::M61_SCRIPT, program_store::MAX_MK61_TEXT_SIZE);
  if(buffer == NULL) return false;
  if(len != 0) memcpy(buffer, text, len);

  script_len = len;
  script_pos = 0;
  script_error = false;
  script_terminal.init_script();
  MK61Emu_ClearCodePage();
  runner_state = RunnerState::EXECUTING;
  service();
  return !script_error;
}

bool load_program(const char* name) {
  if(name == NULL || name[0] == 0) return false;
  if(active()) cancel();

  u8* buffer = shared_scratch::acquire(shared_scratch::Owner::M61_SCRIPT, program_store::MAX_MK61_TEXT_SIZE);
  if(buffer == NULL) return false;

  u16 len = 0;
  if(!program_store::read_mk61(name, buffer, program_store::MAX_MK61_TEXT_SIZE, &len)) {
    shared_scratch::release(shared_scratch::Owner::M61_SCRIPT);
    return false;
  }

  script_len = len;
  script_pos = 0;
  script_error = false;
  script_terminal.init_script();
  MK61Emu_ClearCodePage();
  runner_state = RunnerState::EXECUTING;
  service();
  return !script_error;
}

bool execute(const u8* text, u16 len) {
  return start(text, len);
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
