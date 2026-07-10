#include "m61_text.hpp"

#include "program_store.hpp"
#include "terminal_core.hpp"
#include "terminal_script.hpp"

#ifndef M61_TEXT_HOST_TEST
#include "Arduino.h"
#include "library_pmk.hpp"
#include "mk61emu_core.h"
#include "tools.hpp"
#else
bool OpenStoredFile(const char* args);
void hidden_start_loaded_program(void);
void MK61Emu_ClearCodePage(void);
#endif

#include <stdio.h>
#include <string.h>

namespace m61_text {

static constexpr u16 MAX_LINE_SIZE = (u16) terminal_core::MAX_INPUT_TEXT;
static constexpr u8 HIN_BYTES_PER_LINE = 24;
static constexpr u8 SCRIPT_STACK_DEPTH = 8;
static constexpr u8 SCRIPT_LINE_BUDGET = 8;
static constexpr u8 READ_CACHE_SIZE = 64;
static constexpr u8 MAX_LABELS = 64;
static constexpr u8 MAX_LABEL_SIZE = 31;

enum class RunnerState : u8 {
  IDLE,
  EXECUTING,
  WAIT_RUN_STOP
};

enum class ScriptSource : u8 {
  NONE,
  STORE
};

struct ScriptFrame {
  ScriptSource source;
  char name[program_store::NAME_SIZE];
  u16 len;
  u16 pos;
  u16 line;
};

struct LabelEntry {
  u32 hash;
  u16 name_pos;
  u16 target_pos;
  u16 target_line;
  u8 len;
};

static RunnerState runner_state = RunnerState::IDLE;
static ScriptSource script_source = ScriptSource::NONE;
static char script_name[program_store::NAME_SIZE] = {};
static u16 script_len = 0;
static u16 script_pos = 0;
static u16 script_line = 1;
static ScriptFrame script_stack[SCRIPT_STACK_DEPTH];
static u8 script_stack_depth = 0;
static u8 read_cache[READ_CACHE_SIZE];
static u16 read_cache_start = 0;
static u8 read_cache_len = 0;
static LabelEntry labels[MAX_LABELS];
static u8 label_count = 0;
static bool has_error = false;
static Error last_error_info = {};
static const char* line_error_message = NULL;

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

static void clear_error(void) {
  has_error = false;
  memset(&last_error_info, 0, sizeof(last_error_info));
}

static void invalidate_read_cache(void) {
  read_cache_start = 0;
  read_cache_len = 0;
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
  script_line = 1;
  invalidate_read_cache();
  label_count = 0;
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
  frame.line = script_line;
}

static void restore_frame(const ScriptFrame& frame) {
  script_source = frame.source;
  copy_script_name(script_name, frame.name);
  script_len = frame.len;
  script_pos = frame.pos;
  script_line = frame.line;
  invalidate_read_cache();
}

static bool make_store_frame(const char* name, ScriptFrame& frame) {
  program_store::Entry entry;
  if(!find_entry_by_type_name(program_store::ProgramType::MK61, name, entry)) return false;
  frame.source = ScriptSource::STORE;
  copy_script_name(frame.name, entry.name);
  frame.len = entry.data_len;
  frame.pos = 0;
  frame.line = 1;
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

static void stop_runner(void) {
  runner_state = RunnerState::IDLE;
  clear_current_script();
  script_stack_depth = 0;
}

void cancel(void) {
  stop_runner();
  clear_error();
}

bool last_error(Error& out) {
  out = last_error_info;
  return has_error;
}

static void fail_script(const char* message, u16 line) {
  copy_script_name(last_error_info.script, script_name);
  last_error_info.line = line;
  strncpy(last_error_info.message, message == NULL ? "unknown error" : message, sizeof(last_error_info.message) - 1);
  last_error_info.message[sizeof(last_error_info.message) - 1] = 0;
  stop_runner();
  has_error = true;
#ifndef M61_TEXT_HOST_TEST
  Serial.print("M61 error in ");
  Serial.print(last_error_info.script);
  if(line != 0) {
    Serial.print(" at line ");
    Serial.print(line);
  }
  Serial.print(": ");
  Serial.println(last_error_info.message);
#endif
}

static bool read_script_byte(u8& value, bool& eof) {
  eof = false;
  if(script_pos >= script_len) {
    eof = true;
    return true;
  }

  if(script_source == ScriptSource::STORE) {
    if(script_pos < read_cache_start || script_pos >= (u16) (read_cache_start + read_cache_len)) {
      read_cache_start = script_pos;
      const u16 remaining = (u16) (script_len - script_pos);
      const u16 wanted = remaining < READ_CACHE_SIZE ? remaining : READ_CACHE_SIZE;
      u16 got = 0;
      if(!program_store::read_range(program_store::ProgramType::MK61, script_name,
                                    read_cache_start, read_cache, wanted, &got) || got == 0) {
        read_cache_len = 0;
        return false;
      }
      read_cache_len = (u8) got;
    }
    value = read_cache[script_pos - read_cache_start];
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
    if(c == '\r') {
      // Accept CR and CRLF without leaking the paired LF as an empty line.
      if(script_pos < script_len) {
        u8 next = 0;
        bool next_eof = false;
        const u16 saved_pos = script_pos;
        if(!read_script_byte(next, next_eof)) return false;
        if(next_eof || next != '\n') script_pos = saved_pos;
      }
      line[line_len] = 0;
      script_line++;
      return true;
    }
    if(c == '\n' || c == 0) {
      line[line_len] = 0;
      script_line++;
      return true;
    }
    if(line_len + 1 >= capacity) return false;
    line[line_len++] = c;
  }
}

static u32 label_hash(const char* name, usize len) {
  u32 hash = 2166136261UL;
  for(usize i = 0; i < len; i++) {
    hash ^= (u8) name[i];
    hash *= 16777619UL;
  }
  return hash;
}

enum class LabelParse : u8 { NONE, VALID, INVALID };

static LabelParse parse_label(const char* line, const char*& name, usize& len) {
  const char* p = skip_spaces(line);
  if(*p != ':') return LabelParse::NONE;
  p = skip_spaces(p + 1);
  name = p;
  len = 0;
  while(!is_space(p[len]) && !is_line_end(p[len])) len++;
  if(len == 0 || len > MAX_LABEL_SIZE || !token_ends(p + len)) return LabelParse::INVALID;
  return LabelParse::VALID;
}

static bool stored_label_equals(const LabelEntry& entry, const char* name, usize len) {
  if(entry.len != len || entry.hash != label_hash(name, len)) return false;
  char stored[MAX_LABEL_SIZE + 1];
  u16 got = 0;
  if(!program_store::read_range(program_store::ProgramType::MK61, script_name,
                                entry.name_pos, (u8*) stored, entry.len, &got) || got != entry.len) return false;
  return memcmp(stored, name, len) == 0;
}

static bool build_label_index(const char*& error_message, u16& error_line) {
  const u16 resume_pos = script_pos;
  const u16 resume_line = script_line;
  script_pos = 0;
  script_line = 1;
  label_count = 0;
  invalidate_read_cache();

  char line[MAX_LINE_SIZE + 1];
  while(script_pos < script_len) {
    const u16 line_start = script_pos;
    const u16 line_number = script_line;
    if(!read_next_line(line, sizeof(line))) {
      error_message = "cannot read script or line is too long";
      error_line = line_number;
      return false;
    }
    const char* name = NULL;
    usize len = 0;
    const LabelParse parsed = parse_label(line, name, len);
    if(parsed == LabelParse::NONE) continue;
    if(parsed == LabelParse::INVALID) {
      error_message = "invalid label (use 1..31 non-space characters)";
      error_line = line_number;
      return false;
    }
    if(label_count >= MAX_LABELS) {
      error_message = "too many labels (maximum 64)";
      error_line = line_number;
      return false;
    }
    for(u8 i = 0; i < label_count; i++) {
      if(stored_label_equals(labels[i], name, len)) {
        error_message = "duplicate label";
        error_line = line_number;
        return false;
      }
    }

    LabelEntry& entry = labels[label_count++];
    entry.hash = label_hash(name, len);
    entry.name_pos = (u16) (line_start + (u16) (name - line));
    entry.target_pos = script_pos;
    entry.target_line = script_line;
    entry.len = (u8) len;
  }

  script_pos = resume_pos;
  script_line = resume_line;
  invalidate_read_cache();
  return true;
}

static bool activate_frame(const ScriptFrame& frame, const char*& error_message, u16& error_line) {
  restore_frame(frame);
  return build_label_index(error_message, error_line);
}

static void finish_script(void) {
  if(script_stack_depth > 0) {
    const ScriptFrame parent = script_stack[--script_stack_depth];
    const char* error_message = NULL;
    u16 error_line = 0;
    if(!activate_frame(parent, error_message, error_line)) {
      fail_script(error_message, error_line);
      return;
    }
    terminal_script::reset();
    runner_state = RunnerState::EXECUTING;
    return;
  }

  runner_state = RunnerState::IDLE;
  clear_current_script();
}

static bool open_store_script(const char* name) {
  ScriptFrame child;
  if(!make_store_frame(name, child)) return false;
  if(!push_current_script()) return false;

  const char* error_message = NULL;
  u16 error_line = 0;
  if(!activate_frame(child, error_message, error_line)) {
    restore_frame(script_stack[--script_stack_depth]);
    return false;
  }
  terminal_script::reset();
  MK61Emu_ClearCodePage();
  runner_state = RunnerState::EXECUTING;
  return true;
}

// Запуск загруженной программы прямо на ядре, ожидание останова — асинхронно
// из service(). Клавиши через буфер клавиатуры терялись бы при выходе из меню.
static void start_current_program(void) {
  hidden_start_loaded_program();
  runner_state = RunnerState::WAIT_RUN_STOP;
}

// "load N" внутри сценария: слот выполняется как вложенный скрипт с возвратом
// на следующую строку (Load() терминала отменил бы текущий сценарий).
static bool open_slot(const char* args) {
  args = skip_spaces(args);
  usize slot = 0;
  usize digits = 0;
  while(args[digits] >= '0' && args[digits] <= '9') {
    slot = slot * 10 + (usize) (args[digits] - '0');
    digits++;
  }
  if(digits == 0 || slot > 99 || !token_ends(args + digits)) return false;

  char name[8];
  snprintf(name, sizeof(name), "%u", (unsigned) slot);
  return open_store_script(name);
}

// "run :метка" - переход на строку ":метка" текущего скрипта. Поиск ведётся
// с начала, поэтому переходы возможны и назад (циклы), и вперёд.
static bool goto_label(const char* args) {
  args = skip_spaces(args);
  usize label_len = 0;
  while(!is_line_end(args[label_len]) && !is_space(args[label_len])) label_len++;
  if(label_len == 0 || label_len > MAX_LABEL_SIZE || !token_ends(args + label_len)) return false;

  const u32 hash = label_hash(args, label_len);
  for(u8 i = 0; i < label_count; i++) {
    const LabelEntry& entry = labels[i];
    if(entry.hash == hash && stored_label_equals(entry, args, label_len)) {
      script_pos = entry.target_pos;
      script_line = entry.target_line;
      invalidate_read_cache();
      return true;
    }
  }
  return false;
}

// Вся грамматика команд разбирается терминалом (единый диспетчер интерактивного
// и скриптового режимов). Сценарию терминал возвращает только действия,
// влияющие на поток выполнения: run, open, load, переходы по меткам.
static bool execute_script_line(const char* raw_line) {
  line_error_message = NULL;
  const char* line = skip_spaces(raw_line);
  if(is_line_end(*line)) return true;
  if(*line == ':') return true; // метка - точка перехода, сама по себе no-op

  const terminal_protocol::Result result = terminal_script::execute(line);
  switch(result.kind) {
    case terminal_protocol::ResultKind::OK:
      return true;
    case terminal_protocol::ResultKind::RUN_PROGRAM:
      start_current_program();
      return true;
    case terminal_protocol::ResultKind::OPEN_FILE:
      if(OpenStoredFile(result.args)) return true;
      line_error_message = "cannot open referenced file";
      return false;
    case terminal_protocol::ResultKind::LOAD_SLOT:
      if(open_slot(result.args)) return true;
      line_error_message = "cannot load nested slot";
      return false;
    case terminal_protocol::ResultKind::GOTO_LABEL:
      if(goto_label(result.args)) return true;
      line_error_message = "label not found or invalid";
      return false;
    case terminal_protocol::ResultKind::ERROR:
    case terminal_protocol::ResultKind::KEY:
      line_error_message = "terminal command failed";
      return false;
  }
  return false;
}

void service(void) {
  if(runner_state == RunnerState::WAIT_RUN_STOP) {
    if(!core_61::is_CALC()) return;
    // The MK program has stopped: control returns to the next script line.
    core_61::clear_displayed();
    runner_state = RunnerState::EXECUTING;
  }

  // Бюджет строк на вызов: бесконечный цикл по меткам (run :метка) не должен
  // блокировать основной loop() - продолжение в следующей итерации.
  usize budget = SCRIPT_LINE_BUDGET;
  while(runner_state == RunnerState::EXECUTING) {
    if(budget-- == 0) return;
    if(script_pos >= script_len) {
      finish_script();
      return;
    }

    const u16 line_number = script_line;
    char line[MAX_LINE_SIZE + 1];
    if(!read_next_line(line, sizeof(line))) {
      fail_script("cannot read script or line is too long", line_number);
      return;
    }
    if(!execute_script_line(line)) {
      fail_script(line_error_message == NULL ? "command failed" : line_error_message, line_number);
      return;
    }
  }
}

bool load_program(const char* name) {
  if(name == NULL || name[0] == 0) return false;
  if(active()) stop_runner();
  clear_error();

  ScriptFrame frame;
  if(!make_store_frame(name, frame)) {
    copy_script_name(script_name, name);
    fail_script("script not found", 0);
    return false;
  }

  const char* error_message = NULL;
  u16 error_line = 0;
  if(!activate_frame(frame, error_message, error_line)) {
    fail_script(error_message, error_line);
    return false;
  }
  script_stack_depth = 0;
  terminal_script::reset();
  MK61Emu_ClearCodePage();
  runner_state = RunnerState::EXECUTING;
  service();
  return !has_error;
}

// Единственная точка открытия МК61-скрипта по имени (через OpenStoredEntry):
// изнутри выполняющегося сценария — вложенный вызов с возвратом на следующую
// строку, извне (терминал, проводник, меню) — свежая загрузка.
bool open_program(const char* name) {
  if(runner_state == RunnerState::EXECUTING) return open_store_script(name);
  return load_program(name);
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
