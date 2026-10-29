#include "m61_text.hpp"
#include "m61_keys.hpp"
#include "mk61emu_core.h"
#include "program_store.hpp"
#include "program_load.hpp"
#include "terminal_core.hpp"
#include "terminal_script.hpp"
#include "shared_memory.hpp"

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
  program_store::ProgramType type = program_store::ProgramType::MK61;
};

static std::vector<StoredScript> scripts;
static int range_reads = 0;
static u32 media_revision_value=1;
static int executed_commands = 0;
static int clear_count = 0;
static u8 loaded_program[10000] = {};
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
static int program_start_count = 0;
static std::vector<u8> program_start_addresses;
static u32 program_started_at = 0;
static std::vector<std::string> executed_lines;
static std::vector<bool> executed_in_trap;
struct HostFontRule {
  std::string name;
  u16 directory;
  i32 result;
};
struct HostFontAttempt {
  std::string name;
  u16 directory;
};
static std::vector<HostFontRule> font_rules;
static std::vector<HostFontAttempt> font_attempts;
static bool font_session_active = false;
static int font_begin_count = 0;
static int font_restore_count = 0;
static int font_end_count = 0;
static bool stop_nested_open = false;
static int calculator_redraw_count = 0;
static int manual_open_count = 0;
static u16 manual_directory = program_store::INVALID_ID;
static bool manual_paused = false;
static bool manual_available = true;
static int open_resolutions = 0, entry_reads = 0;
static int prepared_attempts = 0, condition_reads = 0;
static i16 condition_value = 0;
static std::vector<u16> basic_targets;
static void (*nested_open_hook)(u16) = nullptr;
static u16 failed_entry = program_store::INVALID_ID;
static int failed_entry_reads = 0, failed_relative_lookups = 0;
static int coerced_directory_reads = 0;
struct HostPath { u16 directory; std::string path; u16 target; };
static std::vector<HostPath> host_paths;
static unsigned loading_entry_reads = 0, loading_source_reads = 0, loading_font_calls = 0;

namespace program_store {

u32 media_revision() { return media_revision_value; }

bool entry_by_id(u16 id, Entry& out) {
  if(m61_text::loading_program()) ++loading_entry_reads;
  ++entry_reads;
  if(id == failed_entry && failed_entry_reads) { --failed_entry_reads; return false; }
  if(id>=scripts.size()) return false;
  out={}; out.type=scripts[id].type;
  std::strncpy(out.name,scripts[id].name.c_str(),NAME_SIZE-1);
  out.data_len=scripts[id].source.size(); out.id=id;
  out.parent_id=scripts[id].parent_id; out.kind=NodeKind::FILE;
  return true;
}
int count(ProgramType type) {
  int n=0; for(const auto& f:scripts) if(f.type==type) ++n; return n;
}
bool entry(ProgramType type, int index, Entry& out) {
  if(index<0) return false;
  for(usize i=0;i<scripts.size();++i)
    if(scripts[i].type==type && index--==0) return entry_by_id(i,out);
  return false;
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
    if(index-- == 0) return entry_by_id(i, out);
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
  if(m61_text::loading_program()) ++loading_source_reads;
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

bool read_absolute_program(u16 address, u8& value) {
  if(address>=sizeof(loaded_program)) return false;
  value=loaded_program[address]; return true;
}
bool write_absolute_program(u16 address, u8 value) {
  if(address>=sizeof(loaded_program)) return false;
  loaded_program[address]=value; return true;
}

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

void hidden_start_loaded_program(u8 address) {
  program_start_addresses.push_back(address);
  core_61::set_IP(address);
  m_IK1302.comma = core_61::COMMA_RUN_POSITION;
}

void mk61_program_started(void) {
  program_start_count++;
  program_started_at = fake_millis;
}

void MK61Emu_ClearCodePage(void) {
  clear_count++;
  std::memset(loaded_program,0,sizeof(loaded_program));
}

void reinit_mk61_calculator_state(void) {
  reinit_count++;
  std::memset(loaded_program,0,sizeof(loaded_program));
  m_IK1302.comma = 0;
}

u32 m61_text_host_millis(void) {
  return fake_millis;
}

i32 program_store_text_font_begin(void) {
  font_begin_count++;
  if(font_session_active) return -3;
  font_session_active = true;
  return 1;
}

i32 program_store_text_font_load_from(const char* name,
                                      u16 preferred_directory) {
  if(m61_text::loading_program()) ++loading_font_calls;
  if(!font_session_active || name == nullptr || name[0] == 0) return -3;
  font_attempts.push_back({name, preferred_directory});
  for(const HostFontRule& rule : font_rules) {
    if(rule.name == name && rule.directory == preferred_directory) {
      return rule.result;
    }
  }
  return 0;
}

i32 program_store_text_font_restore(void) {
  if(!font_session_active) return -3;
  font_restore_count++;
  return 1;
}

i32 program_store_text_font_end(void) {
  if(!font_session_active) return -3;
  font_restore_count++;
  font_end_count++;
  font_session_active = false;
  return 1;
}

bool OpenStoredFile(const char* name) {
  return m61_text::open_program(name);
}

u8 m61_text_host_open_file(const char* name, u16 directory) {
  if(std::strcmp(name, "manual.md") == 0) {
    manual_open_count++;
    manual_directory = directory;
    manual_paused = m61_text::calculator_suspended();
    // A viewer owns its OK/ESC keys; a bind must not reenter even if called.
    assert(!m61_text::handle_key_event(m61_keys::OK, true));
    return manual_available ? 0 : 2;
  }
  if(stop_nested_open && std::strcmp(name, "STOPPED") == 0) return 1;
  if(std::strcmp(name, "UNAVAILABLE") == 0) return 2;
  return OpenStoredFile(name) ? 0 : 2;
}

bool m61_text_host_resolve_file(u16 directory, const char* name,
                               program_store::Entry& out) {
  ++open_resolutions;
  if(directory != program_store::ROOT_ID && failed_relative_lookups) {
    --failed_relative_lookups;
    return false;
  }
  if(directory != program_store::ROOT_ID && coerced_directory_reads) {
    --coerced_directory_reads;
    // storage_path's legacy invalid-cwd recovery can succeed at root after
    // a failed directory-inode read. Its positive result is not a neighbour.
    directory = program_store::ROOT_ID;
  }
  for(const auto& rule : host_paths) {
    if(rule.directory == directory && rule.path == name)
      return program_store::entry_by_id(rule.target, out);
  }
  for(usize i = 0; i < scripts.size(); ++i) {
    if(scripts[i].parent_id == directory && scripts[i].name == name)
      return program_store::entry_by_id((u16)i, out);
  }
  // Legacy nested-M61 fixtures intentionally use an abstract global namespace
  // (their parent ids exist only to exercise binary/font directory context).
  for(usize i = 0; i < scripts.size(); ++i) {
    if(scripts[i].type == program_store::ProgramType::MK61 && scripts[i].name == name)
      return program_store::entry_by_id((u16)i, out);
  }
  if(std::strcmp(name, "manual.md") && std::strcmp(name, "STOPPED") &&
     std::strcmp(name, "UNAVAILABLE")) return false;
  out = {};
  out.id = program_store::INVALID_ID;
  out.parent_id = directory;
  out.type = program_store::ProgramType::MARKDOWN;
  std::strncpy(out.name, name, program_store::NAME_SIZE - 1);
  return true;
}

u8 m61_text_host_open_entry(const program_store::Entry& entry) {
  if(entry.type == program_store::ProgramType::TINYBASIC) {
    basic_targets.push_back(entry.id);
    if(nested_open_hook) nested_open_hook(entry.id);
    return 0;
  }
  if(entry.id != program_store::INVALID_ID)
    return m61_text::open_program(entry.id) ? 0 : 2;
  return m61_text_host_open_file(entry.name, entry.parent_id);
}

void lcd_std_display_redraw(void) {
  calculator_redraw_count++;
}

namespace terminal_script {

void reset(void) {}

// The terminal suite exercises the actual grammar and side effects. This
// seam supplies a tiny deterministic condition language to test M61's cache,
// line positions, storage revisions and nested-runtime lifetimes separately.
bool prepare_if(const char* line, PreparedIf& out, u8& tail) {
  ++prepared_attempts;
  int value = 0, offset = 0;
  if(std::sscanf(line, "if re==%d %n", &value, &offset) != 1 ||
     !offset || !line[offset] || value < -32768 || value > 32767) return false;
  out = {(i16)value, 15, 5}; tail = (u8)offset;
  return true;
}

IfResult evaluate_if(const PreparedIf& condition, bool) {
  ++condition_reads;
  return condition_value == condition.literal ? IfResult::TRUE : IfResult::FALSE;
}

terminal_protocol::Result execute(const char* line, bool trap_mode) {
  executed_commands++;
  executed_lines.emplace_back(line);
  executed_in_trap.push_back(trap_mode);
  if(std::strncmp(line, "if ", 3) == 0) {
    PreparedIf condition = {}; u8 tail = 0;
    if(!prepare_if(line, condition, tail)) return terminal_protocol::Result::error();
    return evaluate_if(condition, trap_mode) == IfResult::TRUE
        ? execute(line + tail, trap_mode) : terminal_protocol::Result::ok();
  }
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
  if(std::strncmp(line, "timer ", 6) == 0) {
    const char* args = line + 6;
    i32 value = 0;
    if(std::strcmp(args, "pause") == 0) value = -2;
    else if(std::strcmp(args, "resume") == 0) value = -3;
    else {
      usize duration = 0;
      if(!terminal_core::parse_single_unsigned(args, 10, 60000, duration))
        return terminal_protocol::Result::error();
      value = duration;
    }
    return {terminal_protocol::ResultKind::TIMER, value, ""};
  }
  if(std::strcmp(line, "bad") == 0) return terminal_protocol::Result::error();
  if(std::strncmp(line,"load ",5)==0) {
    program_load::Request request={};
    if(program_load::parse(line+5,request)!=program_load::Syntax::LEGACY)
      return terminal_protocol::Result::action(terminal_protocol::ResultKind::LOAD_BINARY,line+5);
  }
  if(std::strcmp(line, "run") == 0) return terminal_protocol::Result::action(terminal_protocol::ResultKind::RUN_PROGRAM, "");
  if(std::strncmp(line, "run :", 5) == 0) {
    return terminal_protocol::Result::action(terminal_protocol::ResultKind::GOTO_LABEL, line + 5);
  }
  if(std::strncmp(line, "run ", 4) == 0) {
    u8 address = 0;
    const auto parsed = terminal_core::parse_run_address(line + 4, core_61::program_steps(), address);
    if(parsed == terminal_core::RunAddressParse::VALID)
      return terminal_protocol::Result::run_program(address);
    if(parsed == terminal_core::RunAddressParse::INVALID)
      return terminal_protocol::Result::error();
    return terminal_protocol::Result::action(terminal_protocol::ResultKind::OPEN_FILE, line + 4);
  }
  if(std::strcmp(line, "invalid-run-result") == 0)
    return terminal_protocol::Result::run_program(200);
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
  program_load::reset();
  assert((u8) core_61::context_buffer_owner == 0);
  scripts.clear();
  ++media_revision_value;
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
  program_start_count = 0;
  program_start_addresses.clear();
  program_started_at = 0;
  executed_lines.clear();
  executed_in_trap.clear();
  font_rules.clear();
  font_attempts.clear();
  font_session_active = false;
  font_begin_count = 0;
  font_restore_count = 0;
  font_end_count = 0;
  stop_nested_open = false;
  calculator_redraw_count = 0;
  manual_open_count = 0;
  manual_directory = program_store::INVALID_ID;
  manual_paused = false;
  manual_available = true;
  open_resolutions = entry_reads = prepared_attempts = condition_reads = 0;
  condition_value = 0;
  basic_targets.clear();
  nested_open_hook = nullptr;
  failed_entry = program_store::INVALID_ID;
  failed_entry_reads = failed_relative_lookups = 0;
  coerced_directory_reads = 0;
  host_paths.clear();
  m_IK1302.comma = 0;
}

static void add_script(
    const char* name, const std::string& source,
    u16 parent_id = program_store::ROOT_ID);

static void test_nested_interpreter_esc_cancels_scenario_silently(void) {
  reset_host();
  font_rules.push_back({"HighNoon", program_store::ROOT_ID, 1});
  stop_nested_open = true;
  add_script("GAME",
             "loadfont HighNoon\n"
             "open STOPPED\n"
             "bad\n");

  assert(m61_text::load_program("GAME"));
  assert(!m61_text::active());
  assert(!font_session_active);
  assert(font_begin_count == 1);
  assert(font_end_count == 1);
  assert(font_restore_count == 1);
  assert(calculator_redraw_count == 1);
  assert(executed_lines.size() == 1);
  assert(executed_lines[0] == "open STOPPED");
  m61_text::Error error = {};
  assert(!m61_text::last_error(error));
}

static void test_optional_open_skips_missing_content_but_keeps_strict_open(void) {
  reset_host();
  add_script("OPTIONAL", "open? UNAVAILABLE\nok\nret\n");
  assert(m61_text::load_program("OPTIONAL"));
  assert(!m61_text::active());
  m61_text::Error error = {};
  assert(!m61_text::last_error(error));
  assert(executed_lines.size() == 2);
  assert(executed_lines[0] == "ok");
  assert(executed_lines[1] == "ret");

  reset_host();
  add_script("STRICT", "open UNAVAILABLE\nok\n");
  assert(!m61_text::load_program("STRICT"));
  assert(m61_text::last_error(error));
  assert(error.line == 1);
  assert(std::strcmp(error.message, "cannot open referenced file") == 0);

  reset_host();
  add_script("INVALID", "open?\nok\n");
  assert(!m61_text::load_program("INVALID"));
  assert(m61_text::last_error(error));
  assert(error.line == 1);
  assert(std::strcmp(error.message, "optional open needs a path") == 0);

  reset_host();
  add_script("TRAPOPTIONAL",
             "trap 10 run :handler\n"
             "run\n"
             "ret\n"
             ":handler\n"
             "open? UNAVAILABLE\n"
             "ret\n");
  assert(m61_text::load_program("TRAPOPTIONAL"));
  assert(boundary_hook != nullptr);
  const core_61::Mk61ProgramBoundaryContext boundary = {10, 0};
  assert(boundary_hook(boundary, boundary_user_data));
  m61_text::service();
  assert(m61_text::last_error(error));
  assert(error.line == 5);
  assert(std::strcmp(error.message,
                     "open? is not allowed in a trap handler") == 0);
}

static void add_script(const char* name, const std::string& source,
                       u16 parent_id) {
  scripts.push_back({name, source, parent_id});
}

static void test_loading_scope_covers_source_and_initial_font_but_not_idle(void) {
  reset_host();
  assert(!m61_text::loading_program());
  loading_entry_reads = loading_source_reads = loading_font_calls = 0;
  font_rules.push_back({"TEST", program_store::ROOT_ID, 1});
  add_script("START", "loadfont TEST\nwait 500\nret\n");
  assert(m61_text::load_program("START"));
  assert(loading_entry_reads && loading_source_reads && loading_font_calls == 1);
  assert(!m61_text::loading_program());
  m61_text::service();
  assert(!m61_text::loading_program());
  m61_text::cancel();
  assert(!m61_text::load_program((u16)0xffff));
  assert(!m61_text::loading_program());
  add_script("BAD", ":same\n:same\nret\n");
  assert(!m61_text::load_program((u16)1));
  assert(!m61_text::loading_program());
  assert(!m61_text::load_program("ABSENT"));
  assert(!m61_text::loading_program());
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

static void test_loadfont_is_m61_scoped_and_uses_script_directory(void) {
  reset_host();
  font_rules.push_back({"HighNoon", 17, 1});
  add_script("FONT", "loadfont Missing HighNoon\nok\n", 17);

  assert(m61_text::load_program("FONT"));
  assert(!m61_text::active());
  assert(font_begin_count == 1);
  assert(font_attempts.size() == 2);
  assert(font_attempts[0].name == "Missing" &&
         font_attempts[0].directory == 17);
  assert(font_attempts[1].name == "HighNoon" &&
         font_attempts[1].directory == 17);
  assert(font_end_count == 1);
  assert(font_restore_count == 1);
  assert(!font_session_active);
  assert(executed_lines.size() == 1 && executed_lines[0] == "ok");
}

static void test_loadfont_default_and_all_exit_paths_restore(void) {
  reset_host();
  font_rules.push_back({"High Noon", program_store::ROOT_ID, 1});
  add_script("DEFAULT",
             "loadfont \"High Noon\"\n"
             "loadfont\n"
             "bad\n");
  assert(!m61_text::load_program("DEFAULT"));
  assert(font_begin_count == 1);
  assert(font_restore_count == 2); // explicit default plus final END
  assert(font_end_count == 1);
  assert(!font_session_active);

  reset_host();
  font_rules.push_back({"Loop", program_store::ROOT_ID, 1});
  add_script("CANCEL", "loadfont Loop\n:again\nrun :again\n");
  assert(m61_text::load_program("CANCEL"));
  assert(m61_text::active());
  m61_text::cancel();
  assert(font_end_count == 1);
  assert(!font_session_active);
}

static void test_loadfont_failures_are_reported_by_m61(void) {
  reset_host();
  add_script("MISSING", "loadfont Missing AlsoMissing\n");
  assert(!m61_text::load_program("MISSING"));
  m61_text::Error error = require_error();
  assert(error.line == 1);
  assert(std::strcmp(error.message, "font not found") == 0);
  assert(font_end_count == 1);

  reset_host();
  add_script("SYNTAX", "loadfont \"unterminated\n");
  assert(!m61_text::load_program("SYNTAX"));
  error = require_error();
  assert(std::strstr(error.message, "invalid loadfont syntax") != nullptr);
  assert(font_end_count == 1);
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

static void test_line_reader_handles_window_edges_and_mixed_endings(void) {
  for(unsigned edge : {0U, 1U, 61U, 62U, 63U, 64U, 65U, 1021U, 1022U, 1023U, 1024U}) {
    reset_host();
    std::string source(edge, '\n');
    source += "ok\r\nok\rok\n";
    source += std::string("ok\0ok", 5); // NUL is an M61 line delimiter, not EOF.
    add_script("EDGES", source);
    assert(m61_text::load_program("EDGES"));
    for(unsigned i = 0; i < 150 && m61_text::active(); ++i) m61_text::service();
    assert(!m61_text::active());
    m61_text::Error error = {};
    assert(!m61_text::last_error(error));
    assert((executed_lines == std::vector<std::string>{"ok", "ok", "ok", "ok", "ok"}));
  }
  for(const char* ending : {"", "\r", "\n", "\r\n"}) {
    reset_host();
    const std::string line(terminal_core::MAX_INPUT_TEXT, 'x');
    add_script("MAX", line + ending);
    assert(m61_text::load_program("MAX"));
    while(m61_text::active()) m61_text::service();
    m61_text::Error error = {};
    assert(!m61_text::last_error(error));
    assert((executed_lines == std::vector<std::string>{line}));
  }
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

static void test_read_window_survives_goto_but_observes_writes(void) {
  reset_host();
  std::string source(300,'\n');source+=":loop\nok\nrun :loop\n";
  add_script("CACHE",source);
  assert(m61_text::load_program("CACHE"));
  for(int i=0;i<64;++i)m61_text::service();
  const int before=range_reads;
  for(int i=0;i<32;++i)m61_text::service();
  // Both commands and indexed label names share the verified window.
  assert(range_reads==before);
  scripts[0].source.replace(scripts[0].source.find("ok\n"),2,"bad");
  ++media_revision_value;
  for(int i=0;i<4 && m61_text::active();++i)m61_text::service();
  assert(!m61_text::active());
  const auto error=require_error();assert(error.line==302);
}

static void test_prepared_if_is_live_budgeted_and_lazy(void) {
  reset_host();
  add_script("CACHE", ":loop\r\n \tif re==1 open piece.tbi\r\n"
                      "  if re==2 bad\r\nrun :loop\r\n");
  scripts.push_back({"piece.tbi", "", program_store::ROOT_ID,
                     program_store::ProgramType::TINYBASIC});
  assert(m61_text::load_program("CACHE"));
  for(int i = 0; i < 32; ++i) {
    const int before = condition_reads;
    m61_text::service();
    assert(condition_reads - before <= 8);
  }
  assert(basic_targets.empty() && open_resolutions == 0);
  condition_value = 1;
  m61_text::service();
  assert(!basic_targets.empty());
  const int before = open_resolutions, metadata_before = entry_reads;
  for(int i = 0; i < 32; ++i) m61_text::service();
  assert(basic_targets.size() > 32);
  for(u16 id : basic_targets) assert(id == 1);
#if MK61_M61_PREPARED_CACHE
  assert(open_resolutions == before && entry_reads == metadata_before);
#else
  (void)before; (void)metadata_before;
#endif
  condition_value = 2;
  for(int i = 0; i < 4 && m61_text::active(); ++i) m61_text::service();
  assert(!m61_text::active());
  assert(require_error().line == 3);
}

static void test_prepared_open_observes_rename_id_reuse_parent_and_source(void) {
  reset_host();
  add_script("CACHE", ":loop\nif re==1 open piece.tbi\nrun :loop\n");
  scripts.push_back({"piece.tbi", "", program_store::ROOT_ID,
                     program_store::ProgramType::TINYBASIC});
  condition_value = 1;
  assert(m61_text::load_program("CACHE"));
  for(int i = 0; i < 8; ++i) m61_text::service();
  assert(!basic_targets.empty() && basic_targets.back() == 1);
  // The old id can now name a completely different file. Never reuse it.
  scripts[1].name = "other.tbi";
  scripts.push_back({"piece.tbi", "", program_store::ROOT_ID,
                     program_store::ProgramType::TINYBASIC});
  ++media_revision_value;
  basic_targets.clear();
  for(int i = 0; i < 8; ++i) m61_text::service();
  assert(!basic_targets.empty());
  for(u16 id : basic_targets) assert(id == 2);
  // A same-named neighbour takes precedence after moving the caller.
  scripts[0].parent_id = 100;
  scripts.push_back({"piece.tbi", "", 100, program_store::ProgramType::TINYBASIC});
  ++media_revision_value;
  basic_targets.clear();
  for(int i = 0; i < 8; ++i) m61_text::service();
  assert(!basic_targets.empty());
  for(u16 id : basic_targets) assert(id == 3);
  scripts[0].parent_id = 200; // no local target: retain the root fallback
  ++media_revision_value;
  basic_targets.clear();
  for(int i = 0; i < 8; ++i) m61_text::service();
  for(u16 id : basic_targets) assert(id == 2);
  assert(!basic_targets.empty());
  scripts[0].source.replace(scripts[0].source.find("==1"), 3, "==9");
  ++media_revision_value;
  basic_targets.clear();
  for(int i = 0; i < 8; ++i) m61_text::service();
  assert(basic_targets.empty());
  condition_value = 9;
  m61_text::service();
  assert(!basic_targets.empty());
  // Deletion/type change invalidates a successful OPEN, too; do not cache
  // negative resolutions and accidentally conceal a mandatory missing file.
  scripts[2].name = "deleted.tbi";
  ++media_revision_value;
  for(int i = 0; i < 8 && m61_text::active(); ++i) m61_text::service();
  assert(!m61_text::active());
  assert(require_error().line == 2);
}

static void test_prepared_line_endings_capacity_and_nested_runtime(void) {
  for(const std::string& ending : {std::string("\n"), std::string("\r"),
       std::string("\r\n"), std::string("\0", 1), std::string()}) {
    reset_host();
    add_script("END", ":loop\nif re==1 run :loop" + ending);
    condition_value = 1;
    assert(m61_text::load_program("END"));
    for(int i = 0; i < 16; ++i) m61_text::service();
    condition_value = 0;
    for(int i = 0; i < 4 && m61_text::active(); ++i) m61_text::service();
    assert(!m61_text::active());
    m61_text::Error error = {}; assert(!m61_text::last_error(error));
  }
  reset_host();
  std::string source = ":loop\n";
  for(int i = 1; i <= 50; ++i) source += "if re==" + std::to_string(i) + " bad\n";
  source += "if re==99 ret\nrun :loop\n";
  add_script("FULL", source); // fits a window, not its complete prepared table
  assert(m61_text::load_program("FULL"));
  for(int i = 0; i < 128; ++i) m61_text::service();
  condition_value = 99;
  for(int i = 0; i < 16 && m61_text::active(); ++i) m61_text::service();
  assert(!m61_text::active());
  m61_text::Error error = {}; assert(!m61_text::last_error(error));

  reset_host();
  add_script("PARENT", ":loop\nif re==1 open CHILD\nrun :loop\n");
  add_script("CHILD", "wait 500\nret\n");
  condition_value = 1;
  assert(m61_text::load_program("PARENT"));
  for(int i = 0; i < 128; ++i) { fake_millis += 500; m61_text::service(); }
  assert(m61_text::active() && !m61_text::last_error(error));
  m61_text::cancel();
}

static void test_prepared_table_borrows_only_unused_label_slots(void) {
  struct Scenario { int labels, false_conditions; bool cached; };
  for(const auto& scenario : {Scenario{1, 30, true}, Scenario{16, 30, true},
       Scenario{63, 1, true}, Scenario{63, 30, false},
       Scenario{64, 0, true}, Scenario{64, 30, false}}) {
    const int label_slots = scenario.labels;
    reset_host();
    std::string source = ":loop\n";
    for(int i = 1; i < label_slots; ++i)
      source += ":L" + std::to_string(i) + "\n";
    for(int i = 1; i <= scenario.false_conditions; ++i)
      source += "if re==" + std::to_string(i) + " bad\n";
    source += "if re==99 open piece.tbi\nrun :loop\n";
    // Occupy almost all of the source window without adding executed work.
    assert(source.size() <= 1000);
    source.append(1000 - source.size(), '\n');
    add_script("DENSE", source);
    scripts.push_back({"piece.tbi", "", program_store::ROOT_ID,
                       program_store::ProgramType::TINYBASIC});
    condition_value = 99;
    assert(m61_text::load_program("DENSE"));
    for(int i = 0; i < 128; ++i) {
      const int conditions_before = condition_reads;
      m61_text::service();
      assert(condition_reads - conditions_before <= 8);
    }
    const int resolves_before = open_resolutions, metadata_before = entry_reads;
    const usize calls_before = basic_targets.size();
    for(int i = 0; i < 64; ++i) m61_text::service();
    assert(basic_targets.size() > calls_before);
#if MK61_M61_PREPARED_CACHE && MK61_M61_READ_CACHE_BYTES >= 1023
    if(scenario.cached) {
      assert(open_resolutions == resolves_before && entry_reads == metadata_before);
    } else {
      // A genuinely full table falls back; it must never overwrite a label.
      assert(open_resolutions > resolves_before);
    }
#else
    assert(open_resolutions > resolves_before);
    (void)metadata_before;
#endif
    const usize live_calls = basic_targets.size();
    condition_value = 98;
    for(int i = 0; i < 64; ++i) m61_text::service();
    assert(basic_targets.size() == live_calls);
    const auto position = scripts[0].source.find("if re==99 open");
    assert(position != std::string::npos);
    scripts[0].source.replace(position, 9, "if re==98");
    ++media_revision_value;
    for(int i = 0; i < 64; ++i) m61_text::service();
    assert(basic_targets.size() > live_calls);
    m61_text::Error error = {};
    assert(m61_text::active() && !m61_text::last_error(error));
    m61_text::cancel();
  }
}

static void test_prepared_label_storage_survives_nested_rebuilds(void) {
  reset_host();
  std::string parent = ":loop\nif re==1 open CHILD\nrun :loop\n";
  parent.append(1000 - parent.size(), '\n');
  std::string child = "run :child63\n";
  for(int i = 0; i < 64; ++i)
    child += ":child" + std::to_string(i) + "\n";
  child += "wait 500\nret\n";
  add_script("PARENT", parent);
  add_script("CHILD", child);
  condition_value = 1;
  assert(m61_text::load_program("PARENT"));
  for(int i = 0; i < 128; ++i) {
    fake_millis += 500;
    m61_text::service();
  }
  m61_text::Error error = {};
  assert(m61_text::active() && !m61_text::last_error(error));
  m61_text::cancel();
}

static void cancel_during_open(u16) { m61_text::cancel(); }

static void rewrite_during_open(u16) {
  nested_open_hook = nullptr;
  scripts[0].source.replace(scripts[0].source.find("==1"), 3, "==2");
  ++media_revision_value;
}

static void test_prepared_open_does_not_reuse_runtime_after_call(void) {
  for(bool cancel : {false, true}) {
    reset_host();
    add_script("CALL", ":loop\nif re==1 open piece.tbi\nrun :loop\n");
    scripts.push_back({"piece.tbi", "", program_store::ROOT_ID,
                       program_store::ProgramType::TINYBASIC});
    condition_value = 1;
    assert(m61_text::load_program("CALL"));
    for(int i = 0; i < 8; ++i) m61_text::service();
    const usize count = basic_targets.size();
    nested_open_hook = cancel ? cancel_during_open : rewrite_during_open;
    for(int i = 0; i < 16; ++i) m61_text::service();
    assert(basic_targets.size() == count + 1);
    assert(m61_text::active() != cancel);
    m61_text::Error error = {}; assert(!m61_text::last_error(error));
    m61_text::cancel();
  }
}

static void test_prepared_open_does_not_cache_failed_directory_or_lookup(void) {
  for(int failure = 0; failure < 3; ++failure) {
    reset_host();
    add_script("FAULT", ":loop\nif re==1 open piece.tbi\nrun :loop\n", 100);
    scripts.push_back({"piece.tbi", "", 100, program_store::ProgramType::TINYBASIC});
    scripts.push_back({"piece.tbi", "", program_store::ROOT_ID,
                       program_store::ProgramType::TINYBASIC});
    assert(m61_text::load_program("FAULT"));
    for(int i = 0; i < 8; ++i) m61_text::service();
    assert(basic_targets.empty());
    if(failure == 0) { failed_entry = 0; failed_entry_reads = 1; }
    else if(failure == 1) failed_relative_lookups = 1;
    else coerced_directory_reads = 1;
    condition_value = 1;
    for(int i = 0; i < 16; ++i) m61_text::service();
    // The existing permissive lookup can use root for this single failed
    // read. Without a filesystem mutation, the next call must prefer local.
    assert(basic_targets.size() > 16 && basic_targets.front() == 2);
    for(usize i = 1; i < basic_targets.size(); ++i) assert(basic_targets[i] == 1);
    assert(failed_entry_reads == 0 && failed_relative_lookups == 0 && coerced_directory_reads == 0);
    m61_text::cancel();
  }
}

static void test_prepared_open_keeps_complex_relative_paths_uncached(void) {
  reset_host();
  add_script("PATH", ":loop\nif re==1 open folder/piece.tbi\nrun :loop\n", 100);
  scripts.push_back({"piece.tbi", "", 200, program_store::ProgramType::TINYBASIC});
  scripts.push_back({"piece.tbi", "", 100, program_store::ProgramType::TINYBASIC});
  // Relative lookup from /folder normally reaches /folder/folder/piece.
  // A transient invalid-cwd recovery can instead reach /folder/piece: its
  // parent even equals the caller's directory, so that check alone is unsafe.
  host_paths = {{100, "folder/piece.tbi", 1},
                {program_store::ROOT_ID, "folder/piece.tbi", 2}};
  assert(m61_text::load_program("PATH"));
  for(int i = 0; i < 8; ++i) m61_text::service();
  coerced_directory_reads = 1;
  condition_value = 1;
  for(int i = 0; i < 16; ++i) m61_text::service();
  assert(basic_targets.size() > 16 && basic_targets.front() == 2);
  for(usize i = 1; i < basic_targets.size(); ++i) assert(basic_targets[i] == 1);
  const int before = open_resolutions;
  m61_text::service();
  assert(open_resolutions > before);
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

static void test_run_address_waits_and_preserves_default_start(void) {
  reset_host();
  add_script("ENTRY", "run 08\nok\nrun\nret\n");
  assert(m61_text::load_program("ENTRY"));
  assert(core_61::get_IP() == 8);
  assert((program_start_addresses == std::vector<u8>{8}));
  assert(program_start_count == 1 && executed_commands == 1);
  m61_text::service();
  assert(executed_commands == 1);
  m_IK1302.comma = 0;
  m61_text::service();
  assert(core_61::get_IP() == 0);
  assert((program_start_addresses == std::vector<u8>{8, 0}));
  assert(program_start_count == 2 && m61_text::active());
  m_IK1302.comma = 0;
  m61_text::service();
  assert(!m61_text::active());
}

static void test_run_address_limits_and_named_file(void) {
  for(const auto address : {104, 111}) {
    reset_host();
    active_program_steps = address == 104 ? 105 : 112;
    add_script("LIMIT", "run " + std::to_string(address) + "\nret\n");
    assert(m61_text::load_program("LIMIT"));
    assert(core_61::get_IP() == address && program_start_count == 1);
    m_IK1302.comma = 0;
    m61_text::service();
    assert(!m61_text::active());
  }
  for(const char* command : {"run 105", "run -1", "run +8", "run 99999999999999", "invalid-run-result"}) {
    reset_host();
    add_script("INVALID", std::string(command) + "\nret\n");
    assert(!m61_text::load_program("INVALID"));
    assert(require_error().line == 1);
    assert(program_start_count == 0 && !core_61::is_RUN());
  }
  reset_host();
  add_script("PARENT", "run 8.m61\nok\nret\n");
  add_script("8.m61", "ok\nret\n");
  assert(m61_text::load_program("PARENT"));
  assert(!m61_text::active() && program_start_count == 0);
  assert(executed_lines[0] == "run 8.m61");
  assert(executed_lines.size() == 5);
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

static void test_m61_run_uses_common_program_start_hook(void) {
  reset_host();
  fake_millis = 1371932U;
  add_script("TIMED", "run\nret\n");

  assert(m61_text::load_program("TIMED"));
  assert(program_start_count == 1);
  assert(program_started_at == 1371932U);

  m_IK1302.comma = 0;
  m61_text::service();
  assert(!m61_text::active());
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

static void drain_keys(unsigned limit = 512) {
  for(unsigned i=0;i<limit;++i) m61_text::service();
  m61_text::Error error{};
  assert(!m61_text::last_error(error));
}

static unsigned occurrences(const char* line) {
  unsigned n=0;
  for(const auto& value:executed_lines) if(value==line) ++n;
  return n;
}

static void test_key_bind_run_boundary_and_edges(void) {
  reset_host();
  add_script("GAME", "bind key 04 down run :down\nbind key 04 up run :up\n"
      "run\nok\nret\n:down\nleft_down\nret\n:up\nleft_up\nret\n");
  assert(m61_text::load_program("GAME"));
  assert(core_61::is_RUN() && !core_61::registered_mk61_command_hook_count());
  const auto cpu=m_IK1302;
  assert(m61_text::handle_key_event(4,true));
  assert(m61_text::handle_key_event(4,true)); // held DOWN is not a repeat
  assert(m61_text::handle_key_event(4,false)); // tap finishes before core polls
  assert(!m61_text::calculator_suspended());
  m61_text::service();
  assert(!occurrences("left_down"));
  assert(fire_program_boundary(0));
  assert(m61_text::calculator_suspended());
  drain_keys();
  assert(occurrences("left_down")==1 && occurrences("left_up")==1);
  assert(!occurrences("ok") && !m61_text::calculator_suspended());
  assert(core_61::is_RUN() && program_start_count==1);
  assert(std::memcmp(&cpu,&m_IK1302,sizeof(cpu))==0);
  assert(context_saves==0 && context_restores==0);
  assert(!m61_text::handle_key_event(6,true));
}

static void test_key_bind_queue_while_handler_waits(void) {
  reset_host();
  add_script("GAME", "bind key 04 down run :left\nbind key 04 up run :left_up\n"
      "bind key 06 down run :right\nbind key 06 up run :right_up\nret\n"
      ":left\nleft_down\nwait 500\nret\n:left_up\nleft_up\nret\n"
      ":right\nright_down\nret\n:right_up\nright_up\nret\n");
  assert(m61_text::load_program("GAME"));
  assert(m61_text::handle_key_event(4,true));
  m61_text::service();
  assert(m61_text::calculator_suspended() && occurrences("left_down")==1);
  assert(m61_text::handle_key_event(6,true));
  assert(m61_text::handle_key_event(4,false));
  assert(m61_text::handle_key_event(6,false));
  drain_keys(4);
  assert(!occurrences("right_down") && !occurrences("left_up"));
  fake_millis=500;
  drain_keys();
  std::vector<std::string> events;
  for(const auto& line:executed_lines)
    if(line=="left_down" || line=="right_down" || line=="left_up" || line=="right_up")
      events.push_back(line);
  assert((events==std::vector<std::string>{"left_down","right_down","left_up","right_up"}));
  assert(!m61_text::calculator_suspended());
}

static void test_key_bind_preempts_wait_and_preserves_deadline(void) {
  for(u32 start : {0U, 0xFFFFFF00U}) {
    reset_host();
    fake_millis = start;
    add_script("WAITKEY", "bind key 04 down run :key\nwait 500\nresumed\nret\n"
        ":key\npressed\nret\n");
    assert(m61_text::load_program("WAITKEY"));
    fake_millis = start+100;
    assert(m61_text::handle_key_event(4,true));
    drain_keys();
    assert(occurrences("pressed")==1 && !occurrences("resumed"));
    fake_millis = start+499; drain_keys();
    assert(!occurrences("resumed"));
    fake_millis = start+500; drain_keys();
    assert(occurrences("resumed")==1);
  }
  reset_host();
  add_script("WAITKEY", "bind key 04 down run :key\nwait 500\nresumed\nret\n"
      ":key\npressed\nwait 500\nfinished\nret\n");
  assert(m61_text::load_program("WAITKEY"));
  fake_millis=100;
  assert(m61_text::handle_key_event(4,true)); drain_keys();
  assert(occurrences("pressed")==1 && !occurrences("finished"));
  fake_millis=599; drain_keys(); assert(!occurrences("finished"));
  fake_millis=600; drain_keys();
  assert(occurrences("finished")==1 && occurrences("resumed")==1);
}

static void test_monotonic_timer(void) {
  for(u32 start : {0U, 0xFFFFFF00U}) {
    reset_host(); fake_millis = start;
    add_script("TIMER", "timer 4000\nwait 500\nret\n");
    assert(m61_text::load_program("TIMER"));
    assert(m61_text::timer_remaining_ms() == 4000);
    fake_millis = start + 3999;
    assert(m61_text::timer_remaining_ms() == 1);
    fake_millis = start + 4000;
    assert(m61_text::timer_remaining_ms() == 0);
    m61_text::cancel();
    assert(m61_text::timer_remaining_ms() == 0);
  }
  reset_host();
  add_script("TIMER", "bind key 04 down run :pause\nbind key 06 down run :resume\n"
      "bind key 08 down run :reset\ntimer 4000\nret\n"
      ":pause\ntimer pause\ntimer pause\nret\n"
      ":resume\ntimer resume\ntimer resume\nret\n"
      ":reset\ntimer 3000\nret\n");
  assert(m61_text::load_program("TIMER")); drain_keys();
  fake_millis = 1000;
  assert(m61_text::handle_key_event(4, true)); drain_keys();
  assert(m61_text::timer_remaining_ms() == 3000);
  fake_millis = 11000;
  assert(m61_text::timer_remaining_ms() == 3000);
  assert(m61_text::handle_key_event(6, true)); drain_keys();
  fake_millis = 13999;
  assert(m61_text::timer_remaining_ms() == 1);
  fake_millis = 14000;
  assert(m61_text::timer_remaining_ms() == 0);
  assert(m61_text::handle_key_event(8, true)); drain_keys();
  assert(m61_text::timer_remaining_ms() == 3000); // A bind changes its script's timer.
  m61_text::cancel();
  assert(m61_text::timer_remaining_ms() == 0);

  reset_host();
  add_script("PARENT", "timer 4000\nrun CHILD\nwait 500\nret\n");
  add_script("CHILD", "timer 1000\nwait 500\nret\n");
  assert(m61_text::load_program("PARENT")); drain_keys();
  assert(m61_text::timer_remaining_ms() == 1000);
  fake_millis = 600; drain_keys();
  assert(m61_text::timer_remaining_ms() == 3400); // Parent time includes the child.
  m61_text::cancel();
}

static void test_timer_bind_dispatch_and_validation(void) {
  for(u32 start : {0U, 0xFFFFFF00U}) {
    reset_host(); fake_millis = start;
    add_script("TIMER", "bind timer run :tick\ntimer 100\nret\n:tick\nfired\nret\n");
    assert(m61_text::load_program("TIMER")); drain_keys();
    assert(m61_text::active() && !occurrences("fired"));
    fake_millis = start + 99; drain_keys(); assert(!occurrences("fired"));
    fake_millis = start + 100; drain_keys(); assert(occurrences("fired") == 1);
    fake_millis = start + 5000; drain_keys(); assert(occurrences("fired") == 1);
    assert(context_saves == 0 && context_restores == 0);
  }
  for(const char* declaration : {"bind timer", "bind timer 100 run :tick",
      "bind timer run :tick junk", "bind timer run :missing",
      "bind timer run :tick\nbind timer run :tick"}) {
    reset_host();
    add_script("BAD", std::string(declaration)+"\nret\n:tick\nret\n");
    assert(!m61_text::load_program("BAD"));
    assert(!m61_text::active());
  }
  reset_host();
  add_script("SKIP", "run :done\nbind timer run :tick\n:done\ntimer 100\nwait 500\nret\n:tick\nfired\nret\n");
  assert(m61_text::load_program("SKIP"));
  fake_millis=100; drain_keys(); assert(!occurrences("fired"));

  // A busy script can receive the event between service slices, without IF polling.
  reset_host();
  add_script("BUSY", "bind timer run :tick\ntimer 100\n:loop\nok\nrun :loop\n:tick\nfired\nret\n");
  assert(m61_text::load_program("BUSY"));
  fake_millis=100; drain_keys(); assert(occurrences("fired")==1);
}

static void test_timer_bind_boundaries_and_serialization(void) {
  reset_host();
  add_script("RUN", "bind timer run :tick\ntimer 100\nrun\nret\n:tick\nfired\nret\n");
  assert(m61_text::load_program("RUN"));
  const auto cpu = m_IK1302;
  fake_millis=100; m61_text::service();
  assert(!occurrences("fired") && !m61_text::calculator_suspended());
  assert(fire_program_boundary(37));
  assert(m61_text::calculator_suspended());
  drain_keys();
  assert(occurrences("fired")==1 && !m61_text::calculator_suspended());
  assert(std::memcmp(&cpu,&m_IK1302,sizeof(cpu))==0);
  assert(!fire_program_boundary(37));
  assert(context_saves==0 && context_restores==0);

  // A timer callback's WAIT keeps the parent's original deadline.
  reset_host();
  add_script("WAIT", "bind timer run :tick\ntimer 100\nwait 500\nparent_done\nret\n"
      ":tick\nfired\nwait 500\nret\n");
  assert(m61_text::load_program("WAIT"));
  fake_millis=100; drain_keys(); assert(occurrences("fired")==1);
  fake_millis=599; drain_keys(); assert(!occurrences("parent_done"));
  fake_millis=600; drain_keys(); assert(occurrences("parent_done")==1);

  // Physical bindings and timer bindings never enter each other.
  reset_host();
  add_script("KEY", "bind timer run :tick\nbind key 04 down run :key\ntimer 100\nret\n"
      ":key\npressed\nwait 500\nret\n:tick\nfired\nret\n");
  assert(m61_text::load_program("KEY")); drain_keys();
  fake_millis=50; assert(m61_text::handle_key_event(4,true)); drain_keys();
  fake_millis=100; drain_keys(); assert(!occurrences("fired"));
  fake_millis=550; drain_keys(); assert(occurrences("fired")==1);

  reset_host();
  add_script("TRAP", "bind timer run :tick\ntrap 10 run :frame\ntimer 100\nrun\nret\n"
      ":frame\nwait 500\nret\n:tick\nfired\nret\n");
  assert(m61_text::load_program("TRAP")); assert(fire_program_boundary(10));
  drain_keys(); fake_millis=100; drain_keys(); assert(!occurrences("fired"));
  fake_millis=500; drain_keys(); assert(context_restores==1);
  assert(fire_program_boundary(11)); drain_keys();
  assert(occurrences("fired")==1 && !executed_in_trap[executed_lines.size()-2]);
}

static void test_timer_bind_scope_rearm_and_clear(void) {
  reset_host();
  add_script("REARM", "bind timer run :tick\ntimer 100\nret\n"
      ":tick\nfired\ntimer 100\nret\n");
  assert(m61_text::load_program("REARM")); drain_keys();
  fake_millis=100; drain_keys(); assert(occurrences("fired")==1);
  fake_millis=199; drain_keys(); assert(occurrences("fired")==1);
  fake_millis=200; drain_keys(); assert(occurrences("fired")==2);
  assert(m61_text::clear_bindings_and_traps());
  assert(!m61_text::active() && !m61_text::timer_remaining_ms());
  fake_millis=1000; drain_keys(); assert(occurrences("fired")==2);

  reset_host();
  add_script("PARENT", "bind timer run :parent\ntimer 100\nopen CHILD\nwait 500\nret\n:parent\nparent_fired\nret\n");
  add_script("CHILD", "bind timer run :child\ntimer 200\nwait 500\nret\n:child\nchild_fired\nret\n");
  assert(m61_text::load_program("PARENT")); drain_keys();
  fake_millis=100; drain_keys(); assert(!occurrences("parent_fired"));
  fake_millis=200; drain_keys(); assert(occurrences("child_fired")==1);
  fake_millis=500; drain_keys(); assert(occurrences("parent_fired")==1);

  // The long-Cx reset cancels a boundary event before its callback enters.
  reset_host();
  add_script("CLEAR", "bind timer run :tick\ntimer 100\nrun\nret\n:tick\nfired\nret\n");
  assert(m61_text::load_program("CLEAR"));
  fake_millis=100; assert(fire_program_boundary(3));
  assert(m61_text::calculator_suspended());
  assert(m61_text::clear_bindings_and_traps());
  assert(!m61_text::calculator_suspended() && !m61_text::timer_remaining_ms());
  drain_keys(); assert(!occurrences("fired"));

  // Clear all kinds of binding in a child and in the saved parent frame.
  reset_host();
  add_script("PARENT", "bind AE run :key\nbind key 04 down run :key\ntrap 10 run :key\n"
      "bind timer run :tick\ntimer 100\nopen CHILD\nret\n:key\nret\n:tick\nparent_fired\nret\n");
  add_script("CHILD", "bind timer run :tick\ntimer 100\nwait 500\nret\n:tick\nchild_fired\nret\n");
  assert(m61_text::load_program("PARENT")); drain_keys();
  assert(m61_text::clear_bindings_and_traps());
  assert(!m61_text::captures_key(4) && !m61_text::timer_remaining_ms());
  fake_millis=500; drain_keys();
  assert(!m61_text::active() && !occurrences("parent_fired") && !occurrences("child_fired"));
  assert(core_61::registered_mk61_command_hook_count()==0 && boundary_hook==nullptr);

  // Returning from an already running handler must not restore the binding.
  reset_host();
  add_script("HANDLER", "bind timer run :tick\ntimer 100\nret\n:tick\nfired\nwait 500\nret\n");
  assert(m61_text::load_program("HANDLER")); drain_keys();
  fake_millis=100; drain_keys(); assert(occurrences("fired")==1);
  assert(m61_text::clear_bindings_and_traps());
  fake_millis=600; drain_keys(); assert(!m61_text::active());
  assert(!m61_text::timer_remaining_ms() && occurrences("fired")==1);
}

static void test_key_bind_release_reserved_under_pressure(void) {
  reset_host();
  add_script("GAME", "bind key 04 down run :left\nbind key 04 up run :left_up\n"
      "bind key 06 down run :right\nbind key 06 up run :right_up\nret\n"
      ":left\nwait 500\nret\n:left_up\nleft_up\nret\n"
      ":right\nright_down\nret\n:right_up\nright_up\nret\n");
  assert(m61_text::load_program("GAME"));
  assert(m61_text::handle_key_event(4,true));
  m61_text::service();
  for(unsigned i=0;i<256;++i) {
    assert(m61_text::handle_key_event(6,true));
    assert(m61_text::handle_key_event(6,false));
  }
  assert(m61_text::handle_key_event(4,false));
  fake_millis=500;
  drain_keys(1024);
  assert(occurrences("left_up")==1);
  assert(occurrences("right_down")==occurrences("right_up"));
  assert(occurrences("right_down")>0 && occurrences("right_down")<256);
  assert(!m61_text::calculator_suspended());
}

static void test_key_bind_trap_defers_events(void) {
  reset_host();
  add_script("GAME", "bind key 04 down run :down\nbind key 04 up run :up\n"
      "trap 10 run :frame\nrun\nret\n:frame\nwait 500\nret\n"
      ":down\nleft_down\nret\n:up\nleft_up\nret\n");
  assert(m61_text::load_program("GAME") && fire_program_boundary(10));
  m61_text::service();
  assert(context_saves==1);
  assert(m61_text::handle_key_event(4,true));
  assert(m61_text::handle_key_event(4,false));
  m61_text::service();
  assert(!occurrences("left_down"));
  fake_millis=500;
  drain_keys();
  assert(context_restores==1);
  assert(occurrences("left_down")==1 && occurrences("left_up")==1);
  assert(core_61::is_RUN() && !m61_text::calculator_suspended());
  assert(!fire_program_boundary(10)); // original trap bypassed once
  assert(fire_program_boundary(10));
}

static void test_key_bind_validation_and_capacity(void) {
  reset_host();
  add_script("UP", "bind key 04 up run :up\nret\n:up\nreleased\nret\n");
  assert(m61_text::load_program("UP"));
  assert(m61_text::handle_key_event(4,true));
  drain_keys();
  assert(!occurrences("released"));
  assert(m61_text::handle_key_event(4,false));
  assert(m61_text::handle_key_event(4,false));
  drain_keys();
  assert(occurrences("released")==1);
  for(const char* invalid:{"bind OK run :h", "bind key 04 run :h",
      "bind key 04 press run :h", "bind key 04 release run :h",
      "bind key 04 DOWN run :h", "bind key 4 down run :h",
      "bind key 2A down run :h", "bind key 1F down run :h",
      "bind key 20 down run :h", "bind key FF down run :h"}) {
    reset_host();
    add_script("BAD",std::string(invalid)+"\nret\n:h\nret\n");
    assert(!m61_text::load_program("BAD"));
    assert(std::strstr(require_error().message,"invalid bind"));
  }
  reset_host();
  add_script("DUP","bind key 04 down run :h\nbind key 04 down run :h\nret\n:h\nret\n");
  assert(!m61_text::load_program("DUP"));
  assert(std::strstr(require_error().message,"duplicate bind key event"));
  add_script("MISSING","bind key 04 up run :missing\nret\n");
  assert(!m61_text::load_program("MISSING"));
  assert(std::strstr(require_error().message,"label not found"));
  std::string all;
  for(unsigned code=0;code<m61_keys::COUNT;++code) if(m61_keys::valid(code)) {
    char line[80];
    std::snprintf(line,sizeof(line),"bind key %02X down run :h\nbind key %02X up run :h\n",code,code);
    all+=line;
  }
  for(unsigned code=0;code<8;++code) {
    char line[40];std::snprintf(line,sizeof(line),"bind %02X run :h\n",code);all+=line;
  }
  add_script("ALL",all+"bind timer run :h\nret\n:h\nret\n");
  assert(m61_text::load_program("ALL"));
  drain_keys();
  assert(core_61::registered_mk61_command_hook_count()==16);
  for(unsigned code=0;code<m61_keys::COUNT;++code)
    assert(m61_text::captures_key((u8)code)==m61_keys::valid(code));
}

static void test_key_bind_lifecycle_and_viewer(void) {
  reset_host();
  add_script("GAME","bind key 13 down run :help\nrun\nret\n:help\nopen? manual.md\nret\n");
  add_script("OTHER","ret\n");
  assert(m61_text::load_program("GAME"));
  const auto cpu=m_IK1302;
  for(unsigned i=0;i<2;++i) {
    assert(m61_text::handle_key_event(m61_keys::OK,true));
    assert(m61_text::handle_key_event(m61_keys::OK,false));
    assert(fire_program_boundary(0));
    drain_keys();
    assert(manual_open_count==int(i+1) && manual_paused);
    assert(std::memcmp(&cpu,&m_IK1302,sizeof(cpu))==0);
  }
  assert(m61_text::handle_key_event(m61_keys::OK,true));
  assert(m61_text::clear_bindings_and_traps());
  assert(!m61_text::captures_key(m61_keys::OK) && !m61_text::calculator_suspended());
  assert(m61_text::load_program("GAME"));
  assert(m61_text::handle_key_event(m61_keys::OK,true));
  assert(m61_text::load_program("OTHER"));
  assert(!m61_text::captures_key(m61_keys::OK));
  assert(!m61_text::calculator_suspended());
  add_script("SKIP","run :done\nbind key 04 down run :h\n:done\nret\n:h\nret\n");
  assert(m61_text::load_program("SKIP"));
  assert(!m61_text::captures_key(4));
  add_script("NORET","bind key 04 down run :h\nret\n:h\nok\n");
  assert(m61_text::load_program("NORET"));
  assert(m61_text::handle_key_event(4,true));
  if(core_61::is_RUN()) assert(fire_program_boundary(0));
  m61_text::service();
  assert(std::strstr(require_error().message,"without ret"));
  assert(!m61_text::calculator_suspended());
}

static void test_key_bind_can_run_without_event_deadlock(void) {
  reset_host();
  add_script("GAME","bind key 04 down run :h\nbind key 04 up run :u\nret\n"
      ":h\nrun\nprint off\nret\n:u\nreleased\nret\n");
  assert(m61_text::load_program("GAME"));
  assert(m61_text::handle_key_event(4,true));
  m61_text::service();
  assert(core_61::is_RUN() && !m61_text::calculator_suspended());
  assert(m61_text::handle_key_event(4,false));
  assert(!fire_program_boundary(0) && !m61_text::calculator_suspended());
  m_IK1302.comma=0;
  drain_keys();
  assert(m61_text::display_owned() && occurrences("released")==1);
  assert(calculator_redraw_count==0);
}

static void test_key_bind_nested_input_and_opcode_priority(void) {
  reset_host();
  add_script("GAME", "bind key 04 down run :left\nbind key 04 up run :up\nret\n"
      ":left\nheld\nopen CHILD\nret\n:up\nreleased\nret\n");
  add_script("CHILD", "wait 500\nret\n");
  assert(m61_text::load_program("GAME"));
  assert(m61_text::handle_key_event(4,true));
  m61_text::service();
  assert(occurrences("held")==1 && !m61_text::captures_key(4));
  assert(!m61_text::handle_key_event(4,false));
  fake_millis=500;
  drain_keys();
  assert(occurrences("released")==1 && m61_text::captures_key(4));
  assert(!m61_text::calculator_suspended());

  reset_host();
  add_script("GAME", "bind AE run :first\nbind key 04 down run :second\nret\n"
      ":first\nfirst\nret\n:second\nsecond\nret\n");
  assert(m61_text::load_program("GAME"));
  assert(fire_mk61_command(0xAE)==(u8)MK61_NOP);
  assert(m61_text::handle_key_event(4,true));
  drain_keys();
  auto first=executed_lines.end(),second=executed_lines.end();
  for(auto it=executed_lines.begin();it!=executed_lines.end();++it) {
    if(*it=="first")first=it;
    if(*it=="second")second=it;
  }
  assert(first!=executed_lines.end() && second!=executed_lines.end() && first<second);
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

static void test_nested_open_preserves_program_and_root_still_clears(void) {
  reset_host();
  add_script("ROOT", "open FIRST\nopen SECOND\nret\n");
  add_script("FIRST", "ok\n");
  add_script("SECOND", "open LEAF\nret\n");
  add_script("LEAF", "ok\n");
  assert(m61_text::load_program("ROOT"));
  for(int i=0; i<10 && m61_text::active(); ++i) m61_text::service();
  assert(!m61_text::active());
  m61_text::Error error={};
  assert(!m61_text::last_error(error));
  // Three nested calls must not erase their caller's loaded program.
  assert(clear_count==1);
  assert(m61_text::open_program((u16) 1));
  assert(!m61_text::active());
  assert(clear_count==2); // A fresh launch still starts with empty memory.
}

static std::vector<u16> binary_directories;
bool load_binary_program(u16 directory, const char* args) {
  binary_directories.push_back(directory);
  program_load::Request request={};
  if(program_load::parse(args,request)!=program_load::Syntax::BINARY)
    return program_load::reject("Invalid binary load syntax");
  for(usize i=0;i<scripts.size();++i)
    if(scripts[i].parent_id==directory && scripts[i].name==request.path)
      return program_load::load(i,request.address,10000);
  return program_load::reject("Cannot open binary program");
}

static void test_binary_load_uses_script_directory_and_reports_failure() {
  const u8 expected[]={1,2,3,4,5,1,2,3,4,5,0x50};
  // Independent desktop optimal ZX0 fixture, with little-endian CRC32.
  const u8 encoded[]={0xcf,0x81,0x3f,0xf3,0x1e,0x01,0x02,0x03,0x04,0x05,0xf6,0x2d,0x50,0x55,0x56};
  const std::string binary(reinterpret_cast<const char*>(encoded),sizeof(encoded));
  reset_host(); binary_directories.clear();
  add_script("ROOT","load 0109 payload.bin\nopen CHILD\nload 0500 payload.bin\nret\n",17);
  add_script("CHILD","load 0224 payload.bin\nret\n",88);
  scripts.push_back({"payload.bin",binary,17,program_store::ProgramType::MK61_BINARY});
  scripts.push_back({"payload.bin",binary,88,program_store::ProgramType::MK61_BINARY});
  assert(m61_text::load_program("ROOT"));
  for(int i=0;i<20 && m61_text::active();++i) m61_text::service();
  assert(!m61_text::active() && !program_load::blocked());
  for(unsigned address:{109,224,500})
    assert(std::memcmp(loaded_program+address,expected,sizeof(expected))==0);
  assert(clear_count==1 && loaded_program[108]==0 && loaded_program[520]==0);
  assert((binary_directories==std::vector<u16>{17,88,17}));
  m61_text::Error error;
  assert(!m61_text::last_error(error));

  for(unsigned mode=0;mode<4;++mode) {
    reset_host();
    std::string bad=binary;
    if(mode==0) bad[0]^=1;
    if(mode==1) bad.pop_back();
    if(mode==2) bad.push_back(0);
    add_script("BAD","ok\nload 0000 payload.bin\nrun\n");
    if(mode!=3) scripts.push_back({"payload.bin",bad,program_store::ROOT_ID,program_store::ProgramType::MK61_BINARY});
    assert(!m61_text::load_program("BAD"));
    assert(m61_text::last_error(error) && error.line==2);
    assert(!core_61::is_RUN());
    assert(executed_lines.back()=="load 0000 payload.bin");
    if(mode==0) assert(std::strstr(error.message,"CRC32"));
    if(mode<3) assert(program_load::blocked());
    // A fresh root resets the failed load along with the calculator memory.
    add_script("FRESH","ret\n");
    assert(m61_text::load_program("FRESH") && !program_load::blocked());
  }
  reset_host();
  add_script("REINIT","reinit\nload 0000 payload.bin\nret\n");
  scripts.push_back({"payload.bin",binary,program_store::ROOT_ID,program_store::ProgramType::MK61_BINARY});
  assert(m61_text::load_program("REINIT") && !program_load::blocked());
  assert(reinit_count==1 && std::memcmp(loaded_program,expected,sizeof(expected))==0);
}

#if MK61_SCOPED_RESIDENT_BUFFERS
static void test_scoped_runtime_lifetime_and_oom() {
  using namespace shared_memory;
  reset_host();
  const usize total=capacity(Arena::OVERLAY);
  add_script("WATCH", "bind key 13 down run :help\nret\n:help\nret\n");
  for(unsigned order=0;order<2;++order) {
    Lease app;
    if(order==0) assert(app.acquire(Arena::APP,Owner::LOADABLE_MODULE,APP_MAX_SIZE));
    assert(m61_text::load_program("WATCH") && m61_text::active());
    if(order==1) assert(app.acquire(Arena::APP,Owner::LOADABLE_MODULE,APP_MAX_SIZE));
    auto* const address=app.data();
    std::memset(address,0x9A,app.size());
    const usize active_capacity=capacity(Arena::OVERLAY);
    assert(m61_text::handle_key_event(m61_keys::OK, true));m61_text::service();
    assert(m61_text::active() && capacity(Arena::OVERLAY)==active_capacity);
    assert(m61_text::clear_bindings_and_traps());
    assert(!m61_text::active() && app.ok() && app.data()==address);
    for(usize i=0;i<app.size();++i) assert(address[i]==0x9A);
    assert(validate_invariants());app.reset();
    assert(capacity(Arena::OVERLAY)==total);
  }
  Lease full;
  assert(full.acquire(Arena::OVERLAY,Owner::VFAT_STAGE,total));
  std::memset(full.data(),0x65,total);
  assert(!m61_text::load_program("WATCH") && !m61_text::active());
  const auto error=require_error();
  assert(std::strcmp(error.message,"not enough RAM for script runtime")==0);
  for(usize i=0;i<total;++i) assert(full.data()[i]==0x65);
  assert(validate_invariants());full.reset();
  assert(m61_text::load_program("WATCH"));m61_text::cancel();
  assert(capacity(Arena::OVERLAY)==total && validate_invariants());
}
#endif

int main(void) {
  test_loading_scope_covers_source_and_initial_font_but_not_idle();
  test_binary_load_uses_script_directory_and_reports_failure();
  test_nested_open_preserves_program_and_root_still_clears();
  test_nested_interpreter_esc_cancels_scenario_silently();
  test_optional_open_skips_missing_content_but_keeps_strict_open();
  test_loadfont_is_m61_scoped_and_uses_script_directory();
  test_loadfont_default_and_all_exit_paths_restore();
  test_loadfont_failures_are_reported_by_m61();
  test_command_failure_reports_script_and_line();
  test_long_missing_name_is_truncated_to_error_capacity();
  test_duplicate_and_oversized_labels_fail_before_execution();
  test_line_limit_is_enforced_during_indexing();
  test_line_reader_handles_window_edges_and_mixed_endings();
  test_indexed_loop_is_budgeted_and_uses_block_reads();
  test_read_window_survives_goto_but_observes_writes();
  test_prepared_if_is_live_budgeted_and_lazy();
  test_prepared_open_observes_rename_id_reuse_parent_and_source();
  test_prepared_line_endings_capacity_and_nested_runtime();
  test_prepared_table_borrows_only_unused_label_slots();
  test_prepared_label_storage_survives_nested_rebuilds();
  test_prepared_open_does_not_reuse_runtime_after_call();
  test_prepared_open_does_not_cache_failed_directory_or_lookup();
  test_prepared_open_keeps_complex_relative_paths_uncached();
  test_label_reference_rejects_trailing_tokens();
  test_run_waits_and_reports_later_failure();
  test_run_address_waits_and_preserves_default_start();
  test_run_address_limits_and_named_file();
  test_m61_run_uses_common_program_start_hook();
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
  test_key_bind_run_boundary_and_edges();
  test_key_bind_preempts_wait_and_preserves_deadline();
  test_monotonic_timer();
  test_timer_bind_dispatch_and_validation();
  test_timer_bind_boundaries_and_serialization();
  test_timer_bind_scope_rearm_and_clear();
  test_key_bind_queue_while_handler_waits();
  test_key_bind_release_reserved_under_pressure();
  test_key_bind_trap_defers_events();
  test_key_bind_validation_and_capacity();
  test_key_bind_lifecycle_and_viewer();
  test_key_bind_can_run_without_event_deadlock();
  test_key_bind_nested_input_and_opcode_priority();
  test_bind_limit_and_non_reentrant_handler();
  test_reinit_continues_script_and_clears_handlers();
  test_manual_clear_stops_bind_and_trap_watcher();
  test_bind_and_trap_survive_program_stop();
  test_manual_clear_preserves_running_script();
  test_manual_clear_inside_trap_restores_context();
  test_ret_returns_from_nested_script_and_ends_root();
#if MK61_SCOPED_RESIDENT_BUFFERS
  test_scoped_runtime_lifetime_and_oom();
#endif
  std::printf("m61_text_self_test: ok\n");
  return 0;
}
