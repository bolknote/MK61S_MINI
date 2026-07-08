#include "m61_text.hpp"

#include "basic.hpp"
#include "cross_hal.h"
#include "development.hpp"
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

enum class ScriptSource : u8 {
  NONE,
  BUFFER,
  STORE
};

struct ScriptFrame {
  ScriptSource source;
  char name[program_store::NAME_SIZE];
  u16 len;
  u16 pos;
};

static constexpr u8 SCRIPT_STACK_DEPTH = 8;

static RunnerState runner_state = RunnerState::IDLE;
static ScriptSource script_source = ScriptSource::NONE;
static char script_name[program_store::NAME_SIZE] = {};
static u16 script_len = 0;
static u16 script_pos = 0;
static bool script_error = false;
static class_terminal script_terminal;
static ScriptFrame script_stack[SCRIPT_STACK_DEPTH];
static u8 script_stack_depth = 0;

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

static void copy_script_name(char* out, const char* name) {
  if(out == NULL) return;
  out[0] = 0;
  if(name == NULL) return;
  strncpy(out, name, program_store::NAME_SIZE - 1);
  out[program_store::NAME_SIZE - 1] = 0;
}

static void clear_current_script(void) {
  script_source = ScriptSource::NONE;
  script_name[0] = 0;
  script_len = 0;
  script_pos = 0;
}

static bool stack_uses_script_buffer(void) {
  for(u8 i = 0; i < script_stack_depth; i++) {
    if(script_stack[i].source == ScriptSource::BUFFER) return true;
  }
  return false;
}

static void release_script_buffer_if_owned(void) {
  if(script_source == ScriptSource::BUFFER || stack_uses_script_buffer()) {
    shared_scratch::release(shared_scratch::Owner::M61_SCRIPT);
  }
}

static bool find_entry_by_type_name(program_store::ProgramType type, const char* name, program_store::Entry& out) {
  if(name == NULL || name[0] == 0) return false;
  const int count = program_store::count(type);
  for(int i = 0; i < count; i++) {
    program_store::Entry entry;
    if(!program_store::entry(type, i, entry)) continue;
    if(strncmp(entry.name, name, program_store::NAME_SIZE) == 0) {
      out = entry;
      return true;
    }
  }
  return false;
}

static void store_current_frame(ScriptFrame& frame) {
  frame.source = script_source;
  copy_script_name(frame.name, script_name);
  frame.len = script_len;
  frame.pos = script_pos;
}

static void restore_frame(const ScriptFrame& frame) {
  script_source = frame.source;
  copy_script_name(script_name, frame.name);
  script_len = frame.len;
  script_pos = frame.pos;
}

static bool make_store_frame(const char* name, ScriptFrame& frame) {
  program_store::Entry entry;
  if(!find_entry_by_type_name(program_store::ProgramType::MK61, name, entry)) return false;
  frame.source = ScriptSource::STORE;
  copy_script_name(frame.name, entry.name);
  frame.len = entry.data_len;
  frame.pos = 0;
  return true;
}

static bool push_current_script(void) {
  if(script_stack_depth >= SCRIPT_STACK_DEPTH || script_source == ScriptSource::NONE) return false;
  store_current_frame(script_stack[script_stack_depth++]);
  return true;
}

bool active(void) {
  return runner_state != RunnerState::IDLE;
}

void cancel(void) {
  release_script_buffer_if_owned();
  runner_state = RunnerState::IDLE;
  clear_current_script();
  script_stack_depth = 0;
  script_error = false;
}

static void finish_script(void) {
  if(script_source == ScriptSource::BUFFER) shared_scratch::release(shared_scratch::Owner::M61_SCRIPT);

  if(script_stack_depth > 0) {
    restore_frame(script_stack[--script_stack_depth]);
    script_terminal.init_script();
    runner_state = RunnerState::EXECUTING;
    return;
  }

  runner_state = RunnerState::IDLE;
  clear_current_script();
  script_error = false;
}

static void fail_script(void) {
  cancel();
  script_error = true;
}

static bool read_script_byte(u8& value, bool& eof) {
  eof = false;
  if(script_pos >= script_len) {
    eof = true;
    return true;
  }

  if(script_source == ScriptSource::BUFFER) {
    u8* buffer = script_buffer();
    if(buffer == NULL) return false;
    value = buffer[script_pos++];
    return true;
  }

  if(script_source == ScriptSource::STORE) {
    u16 got = 0;
    if(!program_store::read_range(program_store::ProgramType::MK61, script_name, script_pos, &value, 1, &got)) {
      return false;
    }
    if(got != 1) return false;
    script_pos++;
    return true;
  }

  return false;
}

static bool read_next_line(char* line, u16 capacity) {
  if(line == NULL || capacity == 0) return false;

  u16 line_len = 0;
  while(true) {
    u8 value = 0;
    bool eof = false;
    if(!read_script_byte(value, eof)) return false;
    if(eof) {
      line[line_len] = 0;
      return line_len > 0;
    }

    const char c = (char) value;
    if(c == '\r') continue;
    if(c == '\n' || c == 0) {
      line[line_len] = 0;
      return true;
    }
    if(line_len + 1 >= capacity) return false;
    line[line_len++] = c;
  }
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

static bool open_store_script(const char* name) {
  ScriptFrame child;
  if(!make_store_frame(name, child)) return false;
  if(!push_current_script()) return false;

  restore_frame(child);
  script_terminal.init_script();
  MK61Emu_ClearCodePage();
  runner_state = RunnerState::EXECUTING;
  return true;
}

static bool open_entry(const program_store::Entry& entry) {
  switch(entry.type) {
    case program_store::ProgramType::MK61:
      return open_store_script(entry.name);
#if MK61_ENABLE_BASIC
    case program_store::ProgramType::BASIC:
      return RunBasicProgram(entry.name);
#endif
#if MK61_ENABLE_FOCAL
    case program_store::ProgramType::FOCAL:
      return RunFocalProgram(entry.name);
#endif
#if MK61_ENABLE_TINYBASIC
    case program_store::ProgramType::TINYBASIC:
      return RunTinyBasicProgram(entry.name);
#endif
    case program_store::ProgramType::TEXT:
    case program_store::ProgramType::MK61_STATE:
      return program_store_view_entry(entry.type, entry.name);
  }
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

  if(starts_with(line, "open") && (token_ends(line + 4) || is_space(line[4]))) {
    program_store::Entry entry;
    if(!ResolveStoredFile(skip_spaces(line + 4), entry)) return false;
    return open_entry(entry);
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

  script_source = ScriptSource::BUFFER;
  script_name[0] = 0;
  script_len = len;
  script_pos = 0;
  script_stack_depth = 0;
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

  ScriptFrame frame;
  if(!make_store_frame(name, frame)) return false;

  restore_frame(frame);
  script_stack_depth = 0;
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
