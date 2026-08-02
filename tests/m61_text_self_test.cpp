#include "m61_text.hpp"
#include "mk61emu_core.h"
#include "program_store.hpp"
#include "terminal_core.hpp"
#include "terminal_script.hpp"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

IK1302 m_IK1302 = {};
u8 ringM[SIZE_RING_M] = {};

struct StoredScript {
  std::string name;
  std::string source;
  u16 parent_id;
};

static std::vector<StoredScript> scripts;
static int range_reads = 0;
static int executed_commands = 0;
static int clear_count = 0;
static usize active_program_steps = core_61::CLASSIC_PROGRAM_STEP;
static core_61::Mk61ProgramBoundaryHook boundary_hook = nullptr;
static void* boundary_user_data = nullptr;
struct HostCommandHook {
  core_61::Mk61CommandHookHandle handle;
  u8 opcode;
  core_61::Mk61CommandHookPhase phase;
  core_61::Mk61CommandHook callback;
  void* user_data;
};
static std::vector<HostCommandHook> command_hooks;
static core_61::Mk61CommandHookHandle next_command_hook = 1;
static u32 command_sequence = 0;
static int context_saves = 0;
static int context_restores = 0;
static int reinit_count = 0;
static AngleUnit host_angle_unit = DEGREE;
static AngleUnit saved_context_angle = DEGREE;
static u32 fake_millis = 0;
static std::vector<std::string> executed_lines;
static std::vector<bool> executed_in_trap;

namespace program_store {

int count(ProgramType type) {
  return type == ProgramType::MK61 ? (int) scripts.size() : 0;
}

bool entry(ProgramType type, int index, Entry& out) {
  if(type != ProgramType::MK61 || index < 0 || index >= (int) scripts.size()) return false;
  out.type = type;
  std::strncpy(out.name, scripts[(usize) index].name.c_str(), NAME_SIZE - 1);
  out.name[NAME_SIZE - 1] = 0;
  out.data_len = (u16) scripts[(usize) index].source.size();
  out.id = (u16) index;
  out.parent_id = scripts[(usize) index].parent_id;
  out.kind = NodeKind::FILE;
  return true;
}

bool entry_by_id(u16 id, Entry& out) {
  return entry(ProgramType::MK61, id, out);
}

int child_count(u16 parent_id) {
  int result = 0;
  for(const StoredScript& script : scripts) {
    if(script.parent_id == parent_id) result++;
  }
  return result;
}

bool child(u16 parent_id, int index, Entry& out) {
  for(usize i = 0; i < scripts.size(); i++) {
    if(scripts[i].parent_id != parent_id) continue;
    if(index-- == 0) return entry(ProgramType::MK61, (int) i, out);
  }
  return false;
}

bool read_range(ProgramType type, const char* name, u16 offset, u8* data, u16 len, u16* out_len) {
  range_reads++;
  if(out_len != nullptr) *out_len = 0;
  if(type != ProgramType::MK61) return false;
  for(const StoredScript& script : scripts) {
    if(script.name != name) continue;
    if(offset >= script.source.size()) return true;
    usize available = script.source.size() - offset;
    if(available > len) available = len;
    std::memcpy(data, script.source.data() + offset, available);
    if(out_len != nullptr) *out_len = (u16) available;
    return true;
  }
  return false;
}

bool read_range_id(u16 id, u16 offset, u8* data, u16 len, u16* out_len) {
  range_reads++;
  if(out_len != nullptr) *out_len = 0;
  if(id >= scripts.size()) return false;
  const StoredScript& script = scripts[id];
  if(offset >= script.source.size()) return true;
  usize available = script.source.size() - offset;
  if(available > len) available = len;
  std::memcpy(data, script.source.data() + offset, available);
  if(out_len != nullptr) *out_len = (u16) available;
  return true;
}

} // пространство имён program_store

namespace core_61 {

usize program_steps(void) { return active_program_steps; }

void get_code_page(uint8_t* page) {
  std::memset(page, 0, CODE_PAGE_BUFFER_SIZE);
}

bool set_mk61_program_boundary_hook(Mk61ProgramBoundaryHook callback,
                                    void* user_data) {
  if(callback == nullptr || boundary_hook != nullptr) return false;
  boundary_hook = callback;
  boundary_user_data = user_data;
  return true;
}

void clear_mk61_program_boundary_hook(void) {
  boundary_hook = nullptr;
  boundary_user_data = nullptr;
}

bool program_boundary_yielded(void) { return false; }

Mk61CommandHookHandle register_mk61_command_hook(
    u8 opcode, Mk61CommandHookPhase phase, Mk61CommandHook callback,
    void* user_data) {
  if(callback == nullptr ||
     command_hooks.size() >= MK61_COMMAND_HOOK_CAPACITY) {
    return INVALID_MK61_COMMAND_HOOK;
  }
  const Mk61CommandHookHandle handle = next_command_hook++;
  command_hooks.push_back({handle, opcode, phase, callback, user_data});
  return handle;
}

bool unregister_mk61_command_hook(Mk61CommandHookHandle handle) {
  for(usize i = 0; i < command_hooks.size(); i++) {
    if(command_hooks[i].handle != handle) continue;
    command_hooks.erase(command_hooks.begin() + (isize) i);
    return true;
  }
  return false;
}

usize registered_mk61_command_hook_count(void) {
  return command_hooks.size();
}

static ContextBuffer context_buffer = {};
static ContextBufferOwner context_buffer_owner = (ContextBufferOwner) 0;

ContextBuffer* acquire_context_buffer(ContextBufferOwner owner) {
  if((u8) owner == 0 || (u8) context_buffer_owner != 0) return nullptr;
  context_buffer_owner = owner;
  return &context_buffer;
}

ContextBuffer* owned_context_buffer(ContextBufferOwner owner) {
  return (u8) owner != 0 && context_buffer_owner == owner
      ? &context_buffer : nullptr;
}

bool release_context_buffer(ContextBufferOwner owner) {
  if((u8) owner == 0 || context_buffer_owner != owner) return false;
  context_buffer_owner = (ContextBufferOwner) 0;
  return true;
}

bool save_context(ContextBuffer& out) {
  std::memset(out.bytes, 0xA5, sizeof(out.bytes));
  saved_context_angle = host_angle_unit;
  context_saves++;
  return true;
}

bool restore_context(const ContextBuffer& saved) {
  assert(saved.bytes[0] == 0xA5);
  host_angle_unit = saved_context_angle;
  context_restores++;
  return true;
}

} // пространство имён core_61

void MK61Emu_SetAngleUnit(AngleUnit angle) {
  host_angle_unit = angle;
}

AngleUnit MK61Emu_GetAngleUnit(void) {
  return host_angle_unit;
}

void hidden_start_loaded_program(void) {
  m_IK1302.comma = core_61::COMMA_RUN_POSITION;
}

void MK61Emu_ClearCodePage(void) {
  clear_count++;
}

void reinit_mk61_calculator_state(void) {
  reinit_count++;
  m_IK1302.comma = 0;
}

u32 m61_text_host_millis(void) {
  return fake_millis;
}

bool OpenStoredFile(const char* name) {
  return m61_text::open_program(name);
}

namespace terminal_script {

void reset(void) {}

terminal_protocol::Result execute(const char* line, bool trap_mode) {
  executed_commands++;
  executed_lines.emplace_back(line);
  executed_in_trap.push_back(trap_mode);
  if(std::strcmp(line, "print on") == 0) {
    m61_text::release_display();
    return terminal_protocol::Result::ok();
  }
  if(std::strncmp(line, "print ", 6) == 0) {
    m61_text::claim_display();
    return terminal_protocol::Result::ok();
  }
  if(std::strcmp(line, "wait 500") == 0) {
    return terminal_protocol::Result::wait(500);
  }
  if(std::strcmp(line, "bad") == 0) return terminal_protocol::Result::error();
  if(std::strcmp(line, "run") == 0) return terminal_protocol::Result::action(terminal_protocol::ResultKind::RUN_PROGRAM, "");
  if(std::strncmp(line, "run :", 5) == 0) {
    return terminal_protocol::Result::action(terminal_protocol::ResultKind::GOTO_LABEL, line + 5);
  }
  if(std::strncmp(line, "open ", 5) == 0) {
    return terminal_protocol::Result::action(terminal_protocol::ResultKind::OPEN_FILE, line + 5);
  }
  if(std::strcmp(line, "ret") == 0) {
    return terminal_protocol::Result::action(
        terminal_protocol::ResultKind::RETURN_SCRIPT, "");
  }
  if(std::strcmp(line, "reinit") == 0) {
    return terminal_protocol::Result::action(
        terminal_protocol::ResultKind::REINIT_CALCULATOR, "");
  }
  return terminal_protocol::Result::ok();
}

} // пространство имён terminal_script

static void reset_host(void) {
  m61_text::cancel();
  assert((u8) core_61::context_buffer_owner == 0);
  scripts.clear();
  range_reads = 0;
  executed_commands = 0;
  clear_count = 0;
  active_program_steps = core_61::CLASSIC_PROGRAM_STEP;
  boundary_hook = nullptr;
  boundary_user_data = nullptr;
  command_hooks.clear();
  next_command_hook = 1;
  command_sequence = 0;
  context_saves = 0;
  context_restores = 0;
  reinit_count = 0;
  host_angle_unit = DEGREE;
  saved_context_angle = DEGREE;
  fake_millis = 0;
  executed_lines.clear();
  executed_in_trap.clear();
  m_IK1302.comma = 0;
}

static void add_script(const char* name, const std::string& source,
                       u16 parent_id = program_store::ROOT_ID) {
  scripts.push_back({name, source, parent_id});
}

static m61_text::Error require_error(void) {
  m61_text::Error error = {};
  assert(m61_text::last_error(error));
  return error;
}

static bool fire_program_boundary(u8 address, u8 opcode = 0) {
  assert(boundary_hook != nullptr);
  const core_61::Mk61ProgramBoundaryContext context = {address, opcode};
  return boundary_hook(context, boundary_user_data);
}

static u8 fire_mk61_command(
    u8 opcode,
    core_61::Mk61CommandSource source =
        core_61::Mk61CommandSource::KEYBOARD) {
  command_sequence++;
  core_61::Mk61CommandHookContext before = {
    core_61::Mk61CommandHookPhase::BEFORE_EXECUTE,
    source,
    opcode,
    opcode,
    command_sequence
  };
  for(HostCommandHook& hook : command_hooks) {
    if(hook.opcode == opcode &&
       hook.phase == core_61::Mk61CommandHookPhase::BEFORE_EXECUTE) {
      hook.callback(before, hook.user_data);
    }
  }

  core_61::Mk61CommandHookContext after = {
    core_61::Mk61CommandHookPhase::AFTER_EXECUTE,
    source,
    opcode,
    before.replacement_opcode,
    command_sequence
  };
  for(HostCommandHook& hook : command_hooks) {
    if(hook.opcode == opcode &&
       hook.phase == core_61::Mk61CommandHookPhase::AFTER_EXECUTE) {
      hook.callback(after, hook.user_data);
    }
  }
  return before.replacement_opcode;
}

static void test_command_failure_reports_script_and_line(void) {
  reset_host();
  add_script("FAIL", "ok\nbad\nok\n");
  assert(!m61_text::load_program("FAIL"));
  const m61_text::Error error = require_error();
  assert(std::strcmp(error.script, "FAIL") == 0);
  assert(error.line == 2);
  assert(std::strcmp(error.message, "terminal command failed") == 0);
  assert(!m61_text::active());
  assert(executed_commands == 2);
}

static void test_long_missing_name_is_truncated_to_error_capacity(void) {
  reset_host();
  const char* name = "1234567890123456789012345678901";
  assert(std::strlen(name) == program_store::NAME_SIZE - 1);
  assert(!m61_text::load_program(name));
  const m61_text::Error error = require_error();
  assert(std::strcmp(error.script, "123456789012345") == 0);
  assert(error.line == 0);
  assert(std::strcmp(error.message, "script not found") == 0);
}

static void test_duplicate_and_oversized_labels_fail_before_execution(void) {
  reset_host();
  add_script("DUP", ":same\n:same\nok\n");
  assert(!m61_text::load_program("DUP"));
  m61_text::Error error = require_error();
  assert(error.line == 2);
  assert(std::strcmp(error.message, "duplicate label") == 0);
  assert(executed_commands == 0);

  reset_host();
  add_script("LONG", ":abcdefghijklmnopqrstuvwxyz123456\nok\n");
  assert(!m61_text::load_program("LONG"));
  error = require_error();
  assert(error.line == 1);
  assert(std::strstr(error.message, "invalid label") != nullptr);
}

static void test_line_limit_is_enforced_during_indexing(void) {
  reset_host();
  add_script("LINE", std::string(terminal_core::MAX_INPUT_TEXT + 1, 'x') + "\n");
  assert(!m61_text::load_program("LINE"));
  const m61_text::Error error = require_error();
  assert(error.line == 1);
  assert(std::strstr(error.message, "line is too long") != nullptr);
}

static void test_indexed_loop_is_budgeted_and_uses_block_reads(void) {
  reset_host();
  std::string source;
  for(int i = 0; i < 200; i++) source += "\n";
  source += ":loop\nrun :loop\n";
  add_script("LOOP", source);

  assert(m61_text::load_program("LOOP"));
  assert(m61_text::active());
  for(int i = 0; i < 32; i++) {
    const int before = executed_commands;
    m61_text::service();
    assert(executed_commands - before <= 8);
  }
  assert(executed_commands > 8);
  assert(range_reads < 200); // старому исполнителю здесь требовались тысячи однобайтовых чтений
  m61_text::cancel();
}

static void test_label_reference_rejects_trailing_tokens(void) {
  reset_host();
  add_script("ARGS", ":loop\nrun :loop extra\n");
  assert(!m61_text::load_program("ARGS"));
  const m61_text::Error error = require_error();
  assert(error.line == 2);
}

static void test_run_waits_and_reports_later_failure(void) {
  reset_host();
  add_script("WAIT", "run\nbad\n");
  assert(m61_text::load_program("WAIT"));
  assert(m61_text::active());
  assert(executed_commands == 1);

  m61_text::service();
  assert(executed_commands == 1); // калькулятор всё ещё работает
  m_IK1302.comma = 0;
  m61_text::service();
  const m61_text::Error error = require_error();
  assert(std::strcmp(error.script, "WAIT") == 0);
  assert(error.line == 2);
}

static void test_print_owns_display_until_root_script_finishes(void) {
  reset_host();
  add_script("DISPLAY", "print \"frame\"\nrun\nret\n");
  assert(m61_text::load_program("DISPLAY"));
  assert(m61_text::active());
  assert(m61_text::display_owned());

  m_IK1302.comma = 0;
  m61_text::service();
  assert(!m61_text::active());
  assert(!m61_text::display_owned());
}

static void test_print_off_and_on_control_display_ownership(void) {
  reset_host();
  add_script("DISPLAY", "print off\nrun\nprint on\nrun\nret\n");
  assert(m61_text::load_program("DISPLAY"));
  assert(m61_text::active());
  assert(m61_text::display_owned());

  m_IK1302.comma = 0;
  m61_text::service();
  assert(m61_text::active());
  assert(!m61_text::display_owned());

  m_IK1302.comma = 0;
  m61_text::service();
  assert(!m61_text::active());
  assert(!m61_text::display_owned());
}

static void test_trap_wait_holds_snapshot_and_resumes_at_deadline(void) {
  reset_host();
  add_script("WAIT", "trap 10 run :frame\nrun\nret\n:frame\nprint \"frame\"\nwait 500\nret\n");
  assert(m61_text::load_program("WAIT"));
  assert(fire_program_boundary(10, 0x02));

  m61_text::service();
  assert(m61_text::calculator_suspended());
  assert(m61_text::display_owned());
  assert(context_saves == 1);
  assert(context_restores == 0);

  fake_millis = 499;
  m61_text::service();
  assert(m61_text::calculator_suspended());
  assert(context_restores == 0);

  fake_millis = 500;
  m61_text::service();
  assert(!m61_text::calculator_suspended());
  assert(context_restores == 1);
  assert(m61_text::active());
  m61_text::cancel();
}

static void test_trap_ret_preserves_user_angle_change(void) {
  reset_host();
  add_script("ANGLE",
             "trap 10 run :frame\n"
             "run\n"
             "ret\n"
             ":frame\n"
             "wait 500\n"
             "ret\n");
  MK61Emu_SetAngleUnit(DEGREE);
  assert(m61_text::load_program("ANGLE"));
  assert(fire_program_boundary(10));

  m61_text::service();
  assert(m61_text::calculator_suspended());
  assert(MK61Emu_GetAngleUnit() == DEGREE);

  // Имитируем Р, нажатую на физической клавиатуре во время показа кадра.
  MK61Emu_SetAngleUnit(RADIAN);
  fake_millis = 500;
  m61_text::service();

  assert(!m61_text::calculator_suspended());
  assert(context_restores == 1);
  assert(MK61Emu_GetAngleUnit() == RADIAN);
  m61_text::cancel();
}

static void test_trap_handler_can_call_a_common_label(void) {
  reset_host();
  add_script("CALL",
             "trap 10 run :frame\n"
             "run\n"
             "ret\n"
             ":frame\n"
             "run :common\n"
             "print \"bee\"\n"
             "ret\n"
             ":common\n"
             "print \"ansi\"\n"
             "ret\n");
  assert(m61_text::load_program("CALL"));
  assert(fire_program_boundary(10));

  m61_text::service();
  assert(context_saves == 1 && context_restores == 1);
  assert(executed_lines.size() == 6);
  assert(executed_lines[1] == "run :common");
  assert(executed_lines[2] == "print \"ansi\"");
  assert(executed_lines[3] == "ret");
  assert(executed_lines[4] == "print \"bee\"");
  assert(executed_lines[5] == "ret");
  assert(m61_text::active());
  m61_text::cancel();
}

static void test_nested_script_returns_to_parent_and_depth_is_bounded(void) {
  reset_host();
  add_script("PARENT", "open CHILD\nbad\n");
  add_script("CHILD", "ok\n");
  assert(m61_text::load_program("PARENT"));
  assert(m61_text::active());
  m61_text::service();
  const m61_text::Error error = require_error();
  assert(std::strcmp(error.script, "PARENT") == 0);
  assert(error.line == 2);

  reset_host();
  add_script("RECURSE", "open RECURSE\n");
  assert(m61_text::load_program("RECURSE"));
  assert(m61_text::active());
  m61_text::service();
  const m61_text::Error depth_error = require_error();
  assert(std::strcmp(depth_error.script, "RECURSE") == 0);
  assert(depth_error.line == 1);
  assert(!m61_text::active());
}

static void test_explicit_id_disambiguates_directory_names(void) {
  reset_host();
  add_script("SAME", "bad\n", 10);
  add_script("SAME", "ok\n", 20);
  assert(m61_text::load_program((u16) 1));
  assert(executed_commands == 1);
  assert(!m61_text::active());
  m61_text::Error error = {};
  assert(!m61_text::last_error(error));
}

static void test_trap_saves_runs_and_restores_at_exact_address(void) {
  reset_host();
  add_script(
      "TRAP",
      "trap 10 run :message\n"
      "run\n"
      "ret\n"
      ":message\n"
      "print \"AT 10: X={X}\\r\\n\"\n"
      "ret\n");

  assert(m61_text::load_program("TRAP"));
  assert(m61_text::active());
  assert(m_IK1302.comma == core_61::COMMA_RUN_POSITION);
  assert(!fire_program_boundary(9, 0x01));
  assert(fire_program_boundary(10, 0x02));
  assert(m61_text::calculator_suspended());

  m61_text::service();
  assert(context_saves == 1);
  assert(context_restores == 1);
  assert(!m61_text::calculator_suspended());
  assert(executed_lines.size() == 3);
  assert(executed_lines[0] == "run");
  assert(executed_lines[1].rfind("print ", 0) == 0);
  assert(executed_lines[2] == "ret");
  assert(!executed_in_trap[0]);
  assert(executed_in_trap[1] && executed_in_trap[2]);

  // Восстановление точного контекста до команды снова встречает адрес 10.
  // Первая встреча — однократное продолжение; последующий цикл может снова
  // попасть в ловушку.
  assert(!fire_program_boundary(10, 0x02));
  assert(fire_program_boundary(10, 0x02));
  m61_text::service();
  assert(context_saves == 2 && context_restores == 2);
  assert(!fire_program_boundary(10, 0x02));

  m_IK1302.comma = 0;
  m61_text::service();
  assert(m61_text::active());
  assert(boundary_hook != nullptr);

  // После ручного В/О → С/П наблюдатель остаётся привязан к программе.
  m_IK1302.comma = core_61::COMMA_RUN_POSITION;
  assert(fire_program_boundary(10, 0x02));
  m61_text::service();
  assert(context_saves == 3 && context_restores == 3);
  assert(m61_text::active());
  m61_text::Error error = {};
  assert(!m61_text::last_error(error));
  m61_text::cancel();
}

static void test_trap_is_activated_only_when_its_line_executes(void) {
  reset_host();
  add_script(
      "LATE",
      "run\n"
      "trap 10 run :message\n"
      "run\n"
      "ret\n"
      ":message\n"
      "ret\n");
  assert(m61_text::load_program("LATE"));
  assert(!fire_program_boundary(10));

  m_IK1302.comma = 0;
  m61_text::service();
  assert(m_IK1302.comma == core_61::COMMA_RUN_POSITION);
  assert(fire_program_boundary(10));
  m61_text::service();
  assert(context_saves == 1 && context_restores == 1);
  assert(!fire_program_boundary(10));
  m_IK1302.comma = 0;
  m61_text::service();
  assert(m61_text::active());
  m61_text::cancel();
}

static void test_restarting_same_root_preserves_active_traps(void) {
  reset_host();
  add_script(
      "RESTART",
      "run\n"
      "trap 10 run :message\n"
      "ret\n"
      ":message\n"
      "ret\n");

  // Первый запуск доходит до `run` раньше объявления и пока не перехватывает
  // адрес. После останова строка trap исполняется, а корневой ret оставляет
  // наблюдатель активным.
  assert(m61_text::load_program("RESTART"));
  assert(!fire_program_boundary(10));
  m_IK1302.comma = 0;
  m61_text::service();
  assert(m61_text::active());

  // Повторная загрузка того же корневого файла не должна создавать пустую
  // карту: самый первый run уже использует ловушку предыдущего запуска.
  assert(m61_text::load_program("RESTART"));
  assert(fire_program_boundary(10));
  m61_text::service();
  assert(context_saves == 1 && context_restores == 1);

  // Если тот же inode переписали и объявление удалили, старый активный бит
  // не должен пережить повторную индексацию.
  m_IK1302.comma = 0;
  m61_text::service();
  assert(m61_text::active());
  scripts[0].source = "run\nret\n";
  assert(m61_text::load_program((u16) 0));
  assert(!fire_program_boundary(10));
  m61_text::cancel();

  // Активные адреса всё ещё изолированы по корневому файлу.
  reset_host();
  add_script(
      "FIRST",
      "trap 10 run :message\n"
      "ret\n"
      ":message\n"
      "ret\n");
  add_script(
      "SECOND",
      "run\n"
      "trap 10 run :message\n"
      "ret\n"
      ":message\n"
      "ret\n");
  assert(m61_text::load_program("FIRST"));
  assert(m61_text::active());
  assert(m61_text::load_program("SECOND"));
  assert(!fire_program_boundary(10));
  m61_text::cancel();
}

static void test_invalid_traps_fail_before_or_at_run(void) {
  reset_host();
  add_script("MISSING", "trap 10 run :missing\nrun\n");
  assert(!m61_text::load_program("MISSING"));
  m61_text::Error error = require_error();
  assert(error.line == 1);
  assert(std::strcmp(error.message, "trap label not found") == 0);
  assert(executed_commands == 0);

  reset_host();
  add_script("DUPTRAP",
             "trap 10 run :one\ntrap 10 run :two\n:one\nret\n:two\nret\n");
  assert(!m61_text::load_program("DUPTRAP"));
  error = require_error();
  assert(error.line == 2);
  assert(std::strcmp(error.message, "duplicate trap address") == 0);

  reset_host();
  add_script("RANGE", "trap 999999999999999999999 run :x\n:x\nret\n");
  assert(!m61_text::load_program("RANGE"));
  error = require_error();
  assert(error.line == 1);
  assert(std::strstr(error.message, "invalid trap") != nullptr);

  reset_host();
  add_script("CLASSIC", "trap 105 run :x\nrun\n:x\nret\n");
  assert(!m61_text::load_program("CLASSIC"));
  error = require_error();
  assert(error.line == 2);
  assert(std::strstr(error.message, "outside current program memory") != nullptr);

  reset_host();
  active_program_steps = core_61::MAX_PROGRAM_STEP;
  add_script("EXPANDED", "trap 105 run :x\nrun\nret\n:x\nret\n");
  assert(m61_text::load_program("EXPANDED"));
  assert(fire_program_boundary(105));
  m61_text::service();
  assert(context_saves == 1 && context_restores == 1);
  assert(!fire_program_boundary(105));
  m_IK1302.comma = 0;
  m61_text::service();
  assert(m61_text::active());
  m61_text::cancel();
}

static void test_trap_handler_requires_ret_and_restores_on_error(void) {
  reset_host();
  add_script(
      "NORET",
      "trap 10 run :message\n"
      "run\n"
      "ret\n"
      ":message\n"
      "ok\n");
  assert(m61_text::load_program("NORET"));
  assert(fire_program_boundary(10));
  m61_text::service();
  const m61_text::Error error = require_error();
  assert(std::strstr(error.message, "without ret") != nullptr);
  assert(context_saves == 1 && context_restores == 1);
  assert(!m61_text::calculator_suspended());
  assert(boundary_hook == nullptr);
}

static void test_bind_consumes_keyboard_opcode_and_calls_handler(void) {
  reset_host();
  add_script(
      "BIND",
      "bind AE run :pressed\n"
      "ret\n"
      ":pressed\n"
      "ok\n"
      "ret\n");
  assert(m61_text::load_program("BIND"));
  assert(m61_text::active());
  assert(core_61::registered_mk61_command_hook_count() == 2);

  assert(fire_mk61_command(
             0xAE, core_61::Mk61CommandSource::PROGRAM) == 0xAE);
  m61_text::service();
  assert(executed_lines.size() == 1);

  assert(fire_mk61_command(0xAD) == 0xAD);
  m61_text::service();
  assert(executed_lines.size() == 1);

  assert(fire_mk61_command(0xAE) == (u8) MK61_NOP);
  m61_text::service();
  assert(m61_text::active());
  assert(executed_lines.size() == 3);
  assert(executed_lines[1] == "ok");
  assert(executed_lines[2] == "ret");
  assert(core_61::registered_mk61_command_hook_count() == 2);

  assert(fire_mk61_command(0xAE) == (u8) MK61_NOP);
  m61_text::service();
  assert(executed_lines.size() == 5);
  m61_text::cancel();
  assert(core_61::registered_mk61_command_hook_count() == 0);
}

static void test_bind_is_validated_and_activated_only_when_executed(void) {
  reset_host();
  add_script("MISSING", "bind AE run :missing\nret\n");
  assert(!m61_text::load_program("MISSING"));
  m61_text::Error error = require_error();
  assert(std::strcmp(error.message, "bind label not found") == 0);

  reset_host();
  add_script(
      "DUPLICATE",
      "bind AE run :one\n"
      "bind AE run :two\n"
      ":one\nret\n"
      ":two\nret\n");
  assert(!m61_text::load_program("DUPLICATE"));
  error = require_error();
  assert(std::strcmp(error.message, "duplicate bind opcode") == 0);

  reset_host();
  add_script("RANGE", "bind F0 run :key\n:key\nret\n");
  assert(!m61_text::load_program("RANGE"));
  error = require_error();
  assert(std::strstr(error.message, "invalid bind") != nullptr);

  reset_host();
  add_script(
      "SKIPPED",
      "run :done\n"
      "bind AE run :pressed\n"
      ":done\n"
      "ret\n"
      ":pressed\n"
      "ret\n");
  assert(m61_text::load_program("SKIPPED"));
  assert(!m61_text::active());
  assert(core_61::registered_mk61_command_hook_count() == 0);
  assert(fire_mk61_command(0xAE) == 0xAE);
}

static void test_bind_handler_requires_ret(void) {
  reset_host();
  add_script(
      "BINDEND",
      "bind AE run :pressed\n"
      "ret\n"
      ":pressed\n"
      "ok\n");
  assert(m61_text::load_program("BINDEND"));
  assert(fire_mk61_command(0xAE) == (u8) MK61_NOP);
  m61_text::service();
  const m61_text::Error error = require_error();
  assert(std::strstr(error.message, "bind handler") != nullptr);
  assert(std::strstr(error.message, "without ret") != nullptr);
  assert(!m61_text::active());
  assert(core_61::registered_mk61_command_hook_count() == 0);
}

static void test_bind_limit_and_non_reentrant_handler(void) {
  reset_host();
  add_script(
      "EIGHT",
      "bind 00 run :pressed\n"
      "bind 01 run :pressed\n"
      "bind 02 run :pressed\n"
      "bind 03 run :pressed\n"
      "bind 04 run :pressed\n"
      "bind 05 run :pressed\n"
      "bind 06 run :pressed\n"
      "bind EF run :pressed\n"
      "ret\n"
      ":pressed\n"
      "wait 500\n"
      "ok\n"
      "ret\n");
  assert(m61_text::load_program("EIGHT"));
  m61_text::service(); // восьмая строка исчерпала бюджет первого прохода
  assert(core_61::registered_mk61_command_hook_count() == 16);
  assert(fire_mk61_command(0xEF) == (u8) MK61_NOP);
  m61_text::service();
  // Пока обработчик bind ждёт, новое нажатие не поглощается и не входит
  // в тот же обработчик повторно.
  assert(fire_mk61_command(0xEF) == 0xEF);
  fake_millis = 500;
  m61_text::service();
  assert(executed_lines.back() == "ret");

  reset_host();
  add_script(
      "NINE",
      "bind 00 run :pressed\n"
      "bind 01 run :pressed\n"
      "bind 02 run :pressed\n"
      "bind 03 run :pressed\n"
      "bind 04 run :pressed\n"
      "bind 05 run :pressed\n"
      "bind 06 run :pressed\n"
      "bind 07 run :pressed\n"
      "bind 08 run :pressed\n"
      ":pressed\n"
      "ret\n");
  assert(!m61_text::load_program("NINE"));
  const m61_text::Error error = require_error();
  assert(std::strcmp(error.message, "too many binds (maximum 8)") == 0);
}

static void test_reinit_continues_script_and_clears_handlers(void) {
  reset_host();
  add_script(
      "REINIT",
      "bind AE run :pressed\n"
      "trap 10 run :trapped\n"
      "reinit\n"
      "ok\n"
      "ret\n"
      ":pressed\n"
      "ret\n"
      ":trapped\n"
      "ret\n");
  assert(m61_text::load_program("REINIT"));
  assert(reinit_count == 1);
  assert(!m61_text::active());
  assert(core_61::registered_mk61_command_hook_count() == 0);
  assert(executed_lines.size() == 3);
  assert(executed_lines[0] == "reinit");
  assert(executed_lines[1] == "ok");
  assert(executed_lines[2] == "ret");
}

static void test_manual_clear_stops_bind_and_trap_watcher(void) {
  reset_host();
  add_script(
      "CLEAR",
      "bind AE run :pressed\n"
      "trap 10 run :trapped\n"
      "ret\n"
      ":pressed\n"
      "ret\n"
      ":trapped\n"
      "ret\n");
  assert(m61_text::load_program("CLEAR"));
  assert(m61_text::active());
  assert(boundary_hook != nullptr);
  assert(core_61::registered_mk61_command_hook_count() == 2);

  assert(m61_text::clear_bindings_and_traps());
  assert(!m61_text::active());
  assert(!m61_text::calculator_suspended());
  assert(boundary_hook == nullptr);
  assert(core_61::registered_mk61_command_hook_count() == 0);
  assert(fire_mk61_command(0xAE) == 0xAE);
  assert(!m61_text::clear_bindings_and_traps());
}

static void test_bind_and_trap_survive_program_stop(void) {
  reset_host();
  add_script(
      "PERSIST",
      "bind AE run :pressed\n"
      "trap 10 run :trapped\n"
      "run\n"
      "ret\n"
      ":pressed\n"
      "ret\n"
      ":trapped\n"
      "ret\n");
  assert(m61_text::load_program("PERSIST"));
  assert(m61_text::active());
  assert(m_IK1302.comma == core_61::COMMA_RUN_POSITION);
  assert(core_61::registered_mk61_command_hook_count() == 2);

  // Штатный останов программы только продолжает сценарий до корневого ret.
  // Активные обработчики переводят его в WATCH_EVENTS, а не очищаются.
  m_IK1302.comma = 0;
  m61_text::service();
  assert(m61_text::active());
  assert(boundary_hook != nullptr);
  assert(core_61::registered_mk61_command_hook_count() == 2);

  assert(fire_mk61_command(0xAE) == (u8) MK61_NOP);
  m61_text::service();
  assert(m61_text::active());

  m_IK1302.comma = core_61::COMMA_RUN_POSITION;
  assert(fire_program_boundary(10));
  m61_text::service();
  assert(context_saves == 1 && context_restores == 1);
  assert(m61_text::active());
  m61_text::cancel();
}

static void test_manual_clear_preserves_running_script(void) {
  reset_host();
  add_script(
      "CONTINUE",
      "bind AE run :pressed\n"
      "trap 10 run :trapped\n"
      "wait 500\n"
      "ok\n"
      "ret\n"
      ":pressed\n"
      "ret\n"
      ":trapped\n"
      "ret\n");
  assert(m61_text::load_program("CONTINUE"));
  assert(m61_text::active());
  assert(core_61::registered_mk61_command_hook_count() == 2);

  assert(m61_text::clear_bindings_and_traps());
  assert(m61_text::active());
  assert(core_61::registered_mk61_command_hook_count() == 0);
  assert(!fire_program_boundary(10));

  fake_millis = 500;
  m61_text::service();
  assert(!m61_text::active());
  assert(boundary_hook == nullptr);
  assert(executed_lines.back() == "ret");
}

static void test_manual_clear_inside_trap_restores_context(void) {
  reset_host();
  add_script(
      "TRAPCLEAR",
      "trap 10 run :trapped\n"
      "ret\n"
      ":trapped\n"
      "wait 500\n"
      "ret\n");
  assert(m61_text::load_program("TRAPCLEAR"));
  m_IK1302.comma = core_61::COMMA_RUN_POSITION;
  assert(fire_program_boundary(10));
  m61_text::service();
  assert(m61_text::calculator_suspended());
  assert(context_saves == 1);

  assert(m61_text::clear_bindings_and_traps());
  assert(m61_text::calculator_suspended());
  fake_millis = 500;
  m61_text::service();
  assert(context_restores == 1);
  assert(!m61_text::calculator_suspended());
  assert(!m61_text::active());
  assert(boundary_hook == nullptr);
}

static void test_ret_returns_from_nested_script_and_ends_root(void) {
  reset_host();
  add_script("PARENT", "open CHILD\nbad\n");
  add_script("CHILD", "ret\nbad\n");
  assert(!m61_text::load_program("PARENT"));
  const m61_text::Error error = require_error();
  assert(std::strcmp(error.script, "PARENT") == 0);
  assert(error.line == 2);

  reset_host();
  add_script("ROOTRET", "ret\nbad\n");
  assert(m61_text::load_program("ROOTRET"));
  assert(!m61_text::active());
  assert(executed_commands == 1);
  m61_text::Error no_error = {};
  assert(!m61_text::last_error(no_error));
}

int main(void) {
  test_command_failure_reports_script_and_line();
  test_long_missing_name_is_truncated_to_error_capacity();
  test_duplicate_and_oversized_labels_fail_before_execution();
  test_line_limit_is_enforced_during_indexing();
  test_indexed_loop_is_budgeted_and_uses_block_reads();
  test_label_reference_rejects_trailing_tokens();
  test_run_waits_and_reports_later_failure();
  test_print_owns_display_until_root_script_finishes();
  test_print_off_and_on_control_display_ownership();
  test_trap_wait_holds_snapshot_and_resumes_at_deadline();
  test_trap_ret_preserves_user_angle_change();
  test_trap_handler_can_call_a_common_label();
  test_nested_script_returns_to_parent_and_depth_is_bounded();
  test_explicit_id_disambiguates_directory_names();
  test_trap_saves_runs_and_restores_at_exact_address();
  test_trap_is_activated_only_when_its_line_executes();
  test_restarting_same_root_preserves_active_traps();
  test_invalid_traps_fail_before_or_at_run();
  test_trap_handler_requires_ret_and_restores_on_error();
  test_bind_consumes_keyboard_opcode_and_calls_handler();
  test_bind_is_validated_and_activated_only_when_executed();
  test_bind_handler_requires_ret();
  test_bind_limit_and_non_reentrant_handler();
  test_reinit_continues_script_and_clears_handlers();
  test_manual_clear_stops_bind_and_trap_watcher();
  test_bind_and_trap_survive_program_stop();
  test_manual_clear_preserves_running_script();
  test_manual_clear_inside_trap_restores_context();
  test_ret_returns_from_nested_script_and_ends_root();
  std::printf("m61_text_self_test: ok\n");
  return 0;
}
