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
static int context_saves = 0;
static int context_restores = 0;
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

} // namespace program_store

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

bool save_context(ContextBuffer& out) {
  std::memset(out.bytes, 0xA5, sizeof(out.bytes));
  context_saves++;
  return true;
}

bool restore_context(const ContextBuffer& saved) {
  assert(saved.bytes[0] == 0xA5);
  context_restores++;
  return true;
}

} // namespace core_61

void hidden_start_loaded_program(void) {
  m_IK1302.comma = core_61::COMMA_RUN_POSITION;
}

void MK61Emu_ClearCodePage(void) {
  clear_count++;
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
  if(std::strncmp(line, "print ", 6) == 0) {
    m61_text::claim_display();
    return terminal_protocol::Result::ok();
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
  return terminal_protocol::Result::ok();
}

} // namespace terminal_script

static void reset_host(void) {
  m61_text::cancel();
  scripts.clear();
  range_reads = 0;
  executed_commands = 0;
  clear_count = 0;
  active_program_steps = core_61::CLASSIC_PROGRAM_STEP;
  boundary_hook = nullptr;
  boundary_user_data = nullptr;
  context_saves = 0;
  context_restores = 0;
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
  assert(range_reads < 200); // old runner needed thousands of one-byte reads here
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
  assert(executed_commands == 1); // calculator is still running
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

  // Restoring the exact pre-command context encounters address 10 again.
  // The first encounter is the one-shot resume; a later loop can trap again.
  assert(!fire_program_boundary(10, 0x02));
  assert(fire_program_boundary(10, 0x02));
  m61_text::service();
  assert(context_saves == 2 && context_restores == 2);
  assert(!fire_program_boundary(10, 0x02));

  m_IK1302.comma = 0;
  m61_text::service();
  assert(!m61_text::active());
  assert(boundary_hook == nullptr);
  m61_text::Error error = {};
  assert(!m61_text::last_error(error));
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
  assert(!m61_text::active());
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
  assert(!m61_text::active());
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
  test_nested_script_returns_to_parent_and_depth_is_bounded();
  test_explicit_id_disambiguates_directory_names();
  test_trap_saves_runs_and_restores_at_exact_address();
  test_trap_is_activated_only_when_its_line_executes();
  test_invalid_traps_fail_before_or_at_run();
  test_trap_handler_requires_ret_and_restores_on_error();
  test_ret_returns_from_nested_script_and_ends_root();
  std::printf("m61_text_self_test: ok\n");
  return 0;
}
