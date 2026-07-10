#include "m61_text.hpp"

#include "library_pmk.hpp"
#include "mk61emu_core.h"
#include "program_store.hpp"
#include "terminal.hpp"
#include "tools.hpp"

#include <stdio.h>
#include <string.h>

namespace m61_text {

static constexpr u16 MAX_LINE_SIZE = 240;
static constexpr u8 HIN_BYTES_PER_LINE = 24;

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
  runner_state = RunnerState::IDLE;
  clear_current_script();
  script_stack_depth = 0;
  script_error = false;
}

static void finish_script(void) {
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
  char label[32];
  usize label_len = 0;
  while(args[label_len] != 0 && !is_space(args[label_len]) && label_len + 1 < sizeof(label)) {
    label[label_len] = args[label_len];
    label_len++;
  }
  label[label_len] = 0;
  if(label_len == 0) return false;

  const u16 saved_pos = script_pos;
  script_pos = 0;
  char line[MAX_LINE_SIZE + 1];
  while(script_pos < script_len) {
    if(!read_next_line(line, sizeof(line))) break;
    const char* p = skip_spaces(line);
    if(*p != ':') continue;
    p = skip_spaces(p + 1);
    if(strncmp(p, label, label_len) == 0 && token_ends(p + label_len)) {
      return true; // script_pos уже указывает на строку после метки
    }
  }
  script_pos = saved_pos;
  return false;
}

// Вся грамматика команд разбирается терминалом (единый диспетчер интерактивного
// и скриптового режимов). Сценарию терминал возвращает только действия,
// влияющие на поток выполнения: run, open, load, переходы по меткам.
static bool execute_script_line(const char* raw_line) {
  const char* line = skip_spaces(raw_line);
  if(is_line_end(*line)) return true;
  if(*line == ':') return true; // метка - точка перехода, сама по себе no-op

  switch(script_terminal.execute_script_line(line)) {
    case class_terminal::SCRIPT_RESULT_OK:
      return true;
    case class_terminal::SCRIPT_RUN_PROGRAM:
      start_current_program();
      return true;
    case class_terminal::SCRIPT_OPEN_FILE:
      return OpenStoredFile(script_terminal.script_args());
    case class_terminal::SCRIPT_LOAD_SLOT:
      return open_slot(script_terminal.script_args());
    case class_terminal::SCRIPT_GOTO_LABEL:
      return goto_label(script_terminal.script_args());
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
  usize budget = 64;
  while(runner_state == RunnerState::EXECUTING) {
    if(budget-- == 0) return;
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
