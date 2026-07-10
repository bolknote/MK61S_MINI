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
};

static std::vector<StoredScript> scripts;
static int range_reads = 0;
static int executed_commands = 0;
static int clear_count = 0;

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
  return true;
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

} // namespace program_store

namespace core_61 {

usize program_steps(void) { return CLASSIC_PROGRAM_STEP; }

void get_code_page(uint8_t* page) {
  std::memset(page, 0, CODE_PAGE_BUFFER_SIZE);
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

terminal_protocol::Result execute(const char* line) {
  executed_commands++;
  if(std::strcmp(line, "bad") == 0) return terminal_protocol::Result::error();
  if(std::strcmp(line, "run") == 0) return terminal_protocol::Result::action(terminal_protocol::ResultKind::RUN_PROGRAM, "");
  if(std::strncmp(line, "run :", 5) == 0) {
    return terminal_protocol::Result::action(terminal_protocol::ResultKind::GOTO_LABEL, line + 5);
  }
  if(std::strncmp(line, "open ", 5) == 0) {
    return terminal_protocol::Result::action(terminal_protocol::ResultKind::OPEN_FILE, line + 5);
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
  m_IK1302.comma = 0;
}

static void add_script(const char* name, const std::string& source) {
  scripts.push_back({name, source});
}

static m61_text::Error require_error(void) {
  m61_text::Error error = {};
  assert(m61_text::last_error(error));
  return error;
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

int main(void) {
  test_command_failure_reports_script_and_line();
  test_duplicate_and_oversized_labels_fail_before_execution();
  test_line_limit_is_enforced_during_indexing();
  test_indexed_loop_is_budgeted_and_uses_block_reads();
  test_label_reference_rejects_trailing_tokens();
  test_run_waits_and_reports_later_failure();
  test_nested_script_returns_to_parent_and_depth_is_bounded();
  std::printf("m61_text_self_test: ok\n");
  return 0;
}
