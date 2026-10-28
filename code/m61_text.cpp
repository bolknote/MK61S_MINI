#include "m61_text.hpp"
#include "m61_keys.hpp"

#include "bounded_string.hpp"
#include "mk61emu_core.h"
#include "program_store.hpp"
#include "program_load.hpp"
#include "program_execution.hpp"
#include "stm32_sram_bit_band.hpp"
#include "terminal_core.hpp"
#include "terminal_script.hpp"
#include "terminal_catalog.hpp"
#include "shared_memory.hpp"
#if defined(MK61_LINKED_VM_POC) && MK61_LINKED_VM_POC
#include "language_vm_resident.hpp"
#endif

#if defined(MK61_CORE_STANDALONE)
#include "m61_platform.hpp"
#elif !defined(M61_TEXT_HOST_TEST)
#include "Arduino.h"
#include "calculator_control.hpp"
#include "development.hpp"
#include "storage_path.hpp"
#include "dwt_profiler.hpp"
#include "loadable_module_runtime.hpp"
#include "tinybasic.hpp"
#include "tools.hpp"
#else
bool OpenStoredFile(const char* args);
// Test seam for all three outcomes of a synchronous nested file launch:
// 0 = opened, 1 = stopped by ESC, 2 = failed.
u8 m61_text_host_open_file(const char* args, u16 directory);
bool m61_text_host_resolve_file(u16 directory, const char* path,
                               program_store::Entry& out);
u8 m61_text_host_open_entry(const program_store::Entry& entry);
void hidden_start_loaded_program(u8 address);
void MK61Emu_ClearCodePage(void);
void reinit_mk61_calculator_state(void);
bool load_binary_program(u16 directory, const char* args);
u32 m61_text_host_millis(void);
i32 program_store_text_font_begin(void);
i32 program_store_text_font_load_from(const char* name,
                                      u16 preferred_directory);
i32 program_store_text_font_restore(void);
i32 program_store_text_font_end(void);
#endif

void lcd_std_display_redraw(void);

#include <new>
#include <stdio.h>
#include <string.h>

#if defined(M61_TEXT_HOST_TEST) || defined(MK61_DISPLAY_UC1609) || defined(MK61_CORE_STANDALONE)
  #define M61_TEXT_FONT_COMMAND 1
#else
  #define M61_TEXT_FONT_COMMAND 0
#endif

namespace m61_text {

static constexpr u16 MAX_LINE_SIZE = (u16) terminal_core::MAX_INPUT_TEXT;
static constexpr u8 HIN_BYTES_PER_LINE = 24;
static constexpr u8 SCRIPT_STACK_DEPTH = 8;
static constexpr u8 SCRIPT_LINE_BUDGET = 8;
#ifndef MK61_M61_READ_CACHE_BYTES
  #if defined(STM32F411xE)
    #define MK61_M61_READ_CACHE_BYTES 1024
  #else
    #define MK61_M61_READ_CACHE_BYTES 64
  #endif
#endif
static constexpr u16 READ_CACHE_SIZE = MK61_M61_READ_CACHE_BYTES;
static_assert(READ_CACHE_SIZE > 0 && READ_CACHE_SIZE <= 4096, "M61 read cache size is invalid");
// Small-window targets keep the original path and do not link this optional
// accelerator. The cache borrows slack, never reduces the source read window.
#ifndef MK61_M61_PREPARED_CACHE
#define MK61_M61_PREPARED_CACHE (MK61_M61_READ_CACHE_BYTES >= 256)
#endif
static constexpr u8 MAX_LABELS = 64;
static constexpr u8 MAX_LABEL_SIZE = 31;
static constexpr u8 TRAP_ADDRESS_COUNT = (u8) core_61::MAX_PROGRAM_STEP;
static constexpr u8 TRAP_BITMAP_SIZE =
    (u8) ((core_61::MAX_PROGRAM_STEP + 7U) / 8U);
static constexpr u8 INVALID_TRAP_TARGET = 0xFF;
static constexpr u8 MAX_BINDS = 8;
static constexpr u8 INVALID_BIND_OPCODE = 0xFF;
static constexpr u8 INVALID_BIND_TARGET = 0xFF;
static constexpr u8 RETURN_STACK_DEPTH = SCRIPT_STACK_DEPTH + 1;

enum class RunnerState : u8 {
  IDLE,
  EXECUTING,
  WAIT_RUN_STOP,
  WAIT_TIME,
  WATCH_EVENTS
};

enum class ScriptSource : u8 {
  NONE,
  STORE
};

struct ScriptFrame {
  ScriptSource source;
  u16 id;
  u16 len;
  u16 pos;
  u16 line;
  u8 active_traps[TRAP_BITMAP_SIZE];
  u8 active_bind_opcodes[MAX_BINDS];
  u8 active_keys[2][m61_keys::MASK_BYTES];
  u8 held_keys[m61_keys::MASK_BYTES];
};

enum class ReturnKind : u8 {
  SCRIPT,
  LABEL,
  TRAP,
  BIND
};

struct ReturnFrame {
  ReturnKind kind;
  RunnerState runner_state;
  ScriptFrame script;
};

struct LabelEntry {
  u32 hash;
  u16 name_pos;
  u16 target_pos;
  u16 target_line;
  u8 len;
};

struct BindEntry {
  u8 opcode;
  u8 target;
};

struct RuntimeBuffers {
  // Label count is fixed after indexing. Unused slots can hold prepared
  // commands without reducing the source window or the 64-label limit.
  alignas(LabelEntry) u8 label_bytes[sizeof(LabelEntry) * MAX_LABELS];
  u8 cache_bytes[READ_CACHE_SIZE];
  ReturnFrame frames[RETURN_STACK_DEPTH];
};
#if MK61_SCOPED_RESIDENT_BUFFERS
static shared_memory::LifetimeBuffer runtime_storage;
static RuntimeBuffers& runtime_buffers() {
  return *std::launder(reinterpret_cast<RuntimeBuffers*>(runtime_storage.data()));
}
static bool prepare_runtime() {
  if(runtime_storage.ok()) return true;
#if MK61_APP_RUNTIME_AVAILABLE && !defined(M61_TEXT_HOST_TEST)
  // Place a new root script above the APP gap, rather than below an idle
  // editor image. Otherwise that image fragments RAM and a larger VM cannot
  // load later. Active/pinned native calls refuse this cache eviction.
  (void)loadable_module::evict_cached();
#endif
  if(!runtime_storage.acquire(shared_memory::Owner::M61_RUNTIME,
                              sizeof(RuntimeBuffers))) return false;
  new(runtime_storage.data()) RuntimeBuffers{};
  return true;
}
static void release_runtime() { runtime_storage.reset(); }
#if defined(ARDUINO_ARCH_STM32)
// Keep the full live-script cost in APP qualification after removing its BSS.
static_assert(sizeof(RuntimeBuffers) == READ_CACHE_SIZE + 1236U,
              "update the scoped M61 ELF reserve when runtime shapes change");
#define MK61_M61_STRING_IMPL(x) #x
#define MK61_M61_STRING(x) MK61_M61_STRING_IMPL(x)
__asm__(".global mk61_m61_runtime_bytes\n.set mk61_m61_runtime_bytes, (("
        MK61_M61_STRING(MK61_M61_READ_CACHE_BYTES) "+1236+31)&-32)");
#undef MK61_M61_STRING
#undef MK61_M61_STRING_IMPL
#endif
#else
static RuntimeBuffers runtime_storage;
static RuntimeBuffers& runtime_buffers() { return runtime_storage; }
static bool prepare_runtime() { return true; }
static void release_runtime() {}
#endif
static auto& read_cache() { return runtime_buffers().cache_bytes; }
static u8* label_storage(u8 index) {
  return runtime_buffers().label_bytes + sizeof(LabelEntry) * index;
}
static LabelEntry& label(u8 index) {
  return *std::launder(reinterpret_cast<LabelEntry*>(label_storage(index)));
}
static auto& return_stack() { return runtime_buffers().frames; }

struct PreparedLine {
  u16 start, next, target;
  terminal_script::PreparedIf condition;
  u8 tail_offset, flags;
};
static_assert(sizeof(PreparedLine) == 12, "M61 prepared cache entry changed");
static_assert(sizeof(PreparedLine) == sizeof(LabelEntry),
              "prepared commands must fit an unused label slot");
#if MK61_M61_PREPARED_CACHE
struct PreparedHeader { u16 count, directory; };
static constexpr u16 PREPARED_END = READ_CACHE_SIZE & ~1U;
static constexpr u16 DIRECTORY_READY = 0x8000;
static constexpr u8 LINE_TERMINATED = 0x10;
// The low nibble is the resolved file type. No hash is used as identity: an
// entry belongs to an exact source position in a revision-checked window.
static_assert((u8)program_store::ProgramType::SHEET < LINE_TERMINATED,
              "prepared OPEN type no longer fits");
#endif

static RunnerState runner_state = RunnerState::IDLE;
static ScriptSource script_source = ScriptSource::NONE;
static char script_name[program_store::NAME_SIZE] = {};
static u16 script_id = program_store::INVALID_ID;
static u16 script_len = 0;
static u16 script_pos = 0;
static u16 script_line = 1;
#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
static volatile u8 active_traps[TRAP_BITMAP_SIZE] = {};
#else
static u8 active_traps[TRAP_BITMAP_SIZE] = {};
#endif
static u8 return_stack_depth = 0;
static u8 script_stack_depth = 0;
static u16 read_cache_start = 0;
static u16 read_cache_len = 0;
static u32 read_cache_revision;
static u8 label_count = 0;
static u8 trap_targets[TRAP_ADDRESS_COUNT];
static BindEntry binds[MAX_BINDS];
static u8 bind_count = 0;
static u8 active_bind_opcodes[MAX_BINDS];
static core_61::Mk61CommandHookHandle bind_before_hooks[MAX_BINDS];
static core_61::Mk61CommandHookHandle bind_after_hooks[MAX_BINDS];
static bool trap_pending = false;
static u8 pending_trap_address = 0;
static u8 pending_trap_target = INVALID_TRAP_TARGET;
static u8 suspended_trap_address = 0;
static bool bypass_trap_once = false;
static u8 bypass_trap_address = 0;
static bool bind_pending = false;
static bool bind_ready = false;
static u8 pending_bind_target = INVALID_BIND_TARGET;
static u32 pending_bind_sequence = 0;
static bool bind_handler_active = false;
static bool key_bind_active = false;
static u8 key_targets[2][m61_keys::COUNT];
static u8 active_keys[2][m61_keys::MASK_BYTES];
static constexpr u8 KEY_QUEUE_CAPACITY = 128;
static u8 key_queue[KEY_QUEUE_CAPACITY];
static u8 key_queue_head = 0, key_queue_count = 0;
static u8 key_reserved_count = 0;
static u64 key_pressed = 0, key_ignored = 0, key_reserved = 0;
static bool key_boundary_ready = false;
static u8 key_input_blocked = 0;

static void clear_key_runtime() {
  key_queue_head = key_queue_count = 0;
  key_reserved_count = 0;
  key_pressed = key_ignored = key_reserved = 0;
  key_boundary_ready = false;
}
static bool key_event_active(u8 code, u8 event) {
  return m61_keys::valid(code) &&
      (active_keys[event][code / 8U] & (1U << (code % 8U))) != 0;
}
static void set_key_active(u8 code, u8 event, bool on) {
  const u8 bit = (u8)(1U << (code % 8U));
  if(on) active_keys[event][code / 8U] |= bit;
  else active_keys[event][code / 8U] &= (u8)~bit;
}
static void queue_key(u8 code, u8 event) {
  key_queue[(key_queue_head + key_queue_count) % KEY_QUEUE_CAPACITY] =
      (u8)(code | (event ? 0x40U : 0U));
  ++key_queue_count;
}
static bool boundary_hook_installed = false;
static bool display_claimed = false;
#if M61_TEXT_FONT_COMMAND
static bool text_font_session_active = false;
#endif
static u32 wait_until_ms = 0;
static bool has_error = false;
static Error last_error_info = {};
static const char* line_error_message = NULL;
static bool loading = false;

struct LoadScope {
  const bool previous = loading;
  LoadScope() { loading = true; }
  ~LoadScope() { loading = previous; }
};

bool loading_program(void) { return loading; }

static void bind_command_hook(
    core_61::Mk61CommandHookContext& context, void* user_data);

#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
static volatile u32* active_trap_bit_alias_base(void) {
  return stm32_sram_bit_band::alias_base(&active_traps[0]);
}

static void* active_trap_boundary_hook_data(void) {
  return reinterpret_cast<void*>(
      const_cast<u32*>(active_trap_bit_alias_base()));
}
#else
static void* active_trap_boundary_hook_data(void) {
  return NULL;
}
#endif

static void clear_active_traps(void) {
  for(u8 i = 0; i < TRAP_BITMAP_SIZE; i++) active_traps[i] = 0;
}

static void clear_active_binds(void) {
  memset(active_keys, 0, sizeof(active_keys));
  for(u8 i = 0; i < MAX_BINDS; i++) {
    active_bind_opcodes[i] = INVALID_BIND_OPCODE;
  }
}

static void save_active_traps(u8 (&out)[TRAP_BITMAP_SIZE]) {
  for(u8 i = 0; i < TRAP_BITMAP_SIZE; i++) out[i] = active_traps[i];
}

static void save_active_binds(u8 (&out)[MAX_BINDS]) {
  for(u8 i = 0; i < MAX_BINDS; i++) out[i] = active_bind_opcodes[i];
}

static void restore_active_traps(const u8 (&saved)[TRAP_BITMAP_SIZE]) {
  for(u8 i = 0; i < TRAP_BITMAP_SIZE; i++) active_traps[i] = saved[i];
}

static void restore_active_binds(const u8 (&saved)[MAX_BINDS]) {
  for(u8 i = 0; i < MAX_BINDS; i++) active_bind_opcodes[i] = saved[i];
}

static bool bind_is_active(u8 opcode) {
  for(u8 i = 0; i < MAX_BINDS; i++) {
    if(active_bind_opcodes[i] == opcode) return true;
  }
  return false;
}

bool key_bindings_active(void) {
  for(u8 event = 0; event < 2; ++event)
    for(u8 bits : active_keys[event]) if(bits) return true;
  return false;
}

static bool any_bind_is_active(void) {
  if(key_bindings_active()) return true;
  for(u8 i = 0; i < MAX_BINDS; i++) {
    if(active_bind_opcodes[i] != INVALID_BIND_OPCODE) return true;
  }
  return false;
}

static i16 find_bind_index(u8 opcode) {
  for(u8 i = 0; i < bind_count; i++) {
    if(binds[i].opcode == opcode) return (i16) i;
  }
  return -1;
}

static void clear_bind_hooks(void) {
  for(u8 i = 0; i < MAX_BINDS; i++) {
    if(bind_before_hooks[i] != core_61::INVALID_MK61_COMMAND_HOOK) {
      (void) core_61::unregister_mk61_command_hook(bind_before_hooks[i]);
      bind_before_hooks[i] = core_61::INVALID_MK61_COMMAND_HOOK;
    }
    if(bind_after_hooks[i] != core_61::INVALID_MK61_COMMAND_HOOK) {
      (void) core_61::unregister_mk61_command_hook(bind_after_hooks[i]);
      bind_after_hooks[i] = core_61::INVALID_MK61_COMMAND_HOOK;
    }
  }
}

static bool sync_bind_hooks(void) {
  clear_bind_hooks();
  u8 hook_index = 0;
  for(u8 i = 0; i < MAX_BINDS; i++) {
    const u8 opcode = active_bind_opcodes[i];
    if(opcode == INVALID_BIND_OPCODE) continue;
    if(find_bind_index(opcode) < 0 || hook_index >= MAX_BINDS) {
      clear_bind_hooks();
      return false;
    }

    bind_before_hooks[hook_index] = core_61::register_mk61_command_hook(
        opcode, core_61::Mk61CommandHookPhase::BEFORE_EXECUTE,
        &bind_command_hook, NULL);
    bind_after_hooks[hook_index] = core_61::register_mk61_command_hook(
        opcode, core_61::Mk61CommandHookPhase::AFTER_EXECUTE,
        &bind_command_hook, NULL);
    if(bind_before_hooks[hook_index] ==
           core_61::INVALID_MK61_COMMAND_HOOK ||
       bind_after_hooks[hook_index] ==
           core_61::INVALID_MK61_COMMAND_HOOK) {
      clear_bind_hooks();
      return false;
    }
    hook_index++;
  }
  return true;
}

// Снимок ловушки фиксирует всё состояние ядра, включая единицу угла. Однако
// Р/Г/ГРД на корпусе играют роль внешнего переключателя: изменение, сделанное
// пользователем, пока обработчик ловушки держит кадр, должно пережить `ret`.
static core_61::ContextBuffer* trap_context(void) {
  return core_61::owned_context_buffer(
      core_61::ContextBufferOwner::M61_TRAP);
}

static bool trap_context_valid(void) {
  return trap_context() != nullptr;
}

static bool restore_trap_context(void) {
  core_61::ContextBuffer* saved = trap_context();
  if(saved == nullptr) return false;
  const AngleUnit selected_angle = MK61Emu_GetAngleUnit();
  if(!core_61::restore_context(*saved)) return false;
  MK61Emu_SetAngleUnit(selected_angle);
  return true;
}

static void release_trap_context(void) {
  if(trap_context_valid()) {
    (void) core_61::release_context_buffer(
        core_61::ContextBufferOwner::M61_TRAP);
  }
}

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

static u32 runner_millis(void) {
#ifndef M61_TEXT_HOST_TEST
  return millis();
#else
  return m61_text_host_millis();
#endif
}

static bool time_reached(u32 now, u32 deadline) {
  return (i32) (now - deadline) >= 0;
}

static void clear_error(void) {
  has_error = false;
  memset(&last_error_info, 0, sizeof(last_error_info));
}

static void invalidate_read_cache(void) {
  read_cache_start = 0;
  read_cache_len = 0;
}

template<usize N>
static void copy_script_name(char (&out)[N], const char* name) {
  bounded_string::copy(out, name);
}

static void clear_current_script(void) {
  script_source = ScriptSource::NONE;
  script_name[0] = 0;
  script_id = program_store::INVALID_ID;
  script_len = 0;
  script_pos = 0;
  script_line = 1;
  invalidate_read_cache();
  label_count = 0;
  bind_count = 0;
  clear_active_traps();
  clear_active_binds();
  memset(trap_targets, INVALID_TRAP_TARGET, sizeof(trap_targets));
}

#ifdef M61_TEXT_HOST_TEST
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
#endif

static void store_current_frame(ScriptFrame& frame) {
  frame.source = script_source;
  frame.id = script_id;
  frame.len = script_len;
  frame.pos = script_pos;
  frame.line = script_line;
  save_active_traps(frame.active_traps);
  save_active_binds(frame.active_bind_opcodes);
  memcpy(frame.active_keys, active_keys, sizeof(active_keys));
  for(u8 i=0;i<m61_keys::MASK_BYTES;++i)
    frame.held_keys[i]=(u8)((key_pressed & ~key_ignored) >> (8U*i));
}

static bool restore_frame(const ScriptFrame& frame) {
  program_store::Entry entry;
  if(frame.source != ScriptSource::STORE ||
     !program_store::entry_by_id(frame.id, entry) ||
     entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::MK61) return false;
  script_source = frame.source;
  copy_script_name(script_name, entry.name);
  script_id = frame.id;
  script_len = frame.len;
  script_pos = frame.pos;
  script_line = frame.line;
  restore_active_traps(frame.active_traps);
  restore_active_binds(frame.active_bind_opcodes);
  memcpy(active_keys, frame.active_keys, sizeof(active_keys));
  invalidate_read_cache();
  return true;
}

static bool make_store_frame(u16 id, ScriptFrame& frame) {
  program_store::Entry entry;
  if(!program_store::entry_by_id(id, entry) ||
     entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::MK61) return false;
  frame.source = ScriptSource::STORE;
  frame.id = entry.id;
  frame.len = entry.data_len;
  frame.pos = 0;
  frame.line = 1;
  memset(frame.active_traps, 0, sizeof(frame.active_traps));
  memset(frame.active_bind_opcodes, INVALID_BIND_OPCODE,
         sizeof(frame.active_bind_opcodes));
  memset(frame.active_keys, 0, sizeof(frame.active_keys));
  memset(frame.held_keys, 0, sizeof(frame.held_keys));
  return true;
}

static bool make_store_frame(const char* name, ScriptFrame& frame) {
  if(name == NULL || name[0] == 0) return false;

#ifndef M61_TEXT_HOST_TEST
  // Имена вложенных сценариев сначала разрешаются в каталоге вызывающего
  // сценария. Это изолирует одноимённые сценарии в независимых деревьях
  // каталогов и позволяет использовать обычные относительные пути
  // (../lib/tool.m61).
  u16 cwd = program_store::ROOT_ID;
  if(script_id != program_store::INVALID_ID) {
    program_store::Entry current;
    if(program_store::entry_by_id(script_id, current)) cwd = current.parent_id;
  }

  program_store::Entry entry;
  if(storage_path::resolve_file(cwd, name,
      program_store::ProgramType::MK61, entry) == storage_path::Status::OK) {
    return make_store_frame(entry.id, frame);
  }

  // Раньше простые имена без пути считались глобальными. Сохраняем этот
  // запасной вариант, но не превращаем явно относительный путь в поиск
  // несвязанного файла в корневом каталоге.
  if(cwd != program_store::ROOT_ID && strchr(name, '/') == NULL &&
     strchr(name, '\\') == NULL &&
     storage_path::resolve_file(program_store::ROOT_ID, name,
       program_store::ProgramType::MK61, entry) == storage_path::Status::OK) {
    return make_store_frame(entry.id, frame);
  }
  return false;
#else
  program_store::Entry entry;
  if(script_id != program_store::INVALID_ID) {
    program_store::Entry current;
    if(program_store::entry_by_id(script_id, current)) {
      const int count = program_store::child_count(current.parent_id);
      for(int i = 0; i < count; i++) {
        program_store::Entry candidate;
        if(program_store::child(current.parent_id, i, candidate) &&
           candidate.kind == program_store::NodeKind::FILE &&
           candidate.type == program_store::ProgramType::MK61 &&
           strncmp(candidate.name, name, program_store::NAME_SIZE) == 0) {
          return make_store_frame(candidate.id, frame);
        }
      }
    }
  }

  return find_entry_by_type_name(program_store::ProgramType::MK61, name, entry) &&
         make_store_frame(entry.id, frame);
#endif
}

static bool push_current_frame(ReturnKind kind) {
  if(return_stack_depth >= RETURN_STACK_DEPTH ||
     script_source == ScriptSource::NONE) return false;
  if(kind == ReturnKind::SCRIPT && script_stack_depth >= SCRIPT_STACK_DEPTH) {
    return false;
  }
  ReturnFrame& frame = return_stack()[return_stack_depth++];
  frame.kind = kind;
  frame.runner_state = runner_state;
  store_current_frame(frame.script);
  if(kind == ReturnKind::SCRIPT) script_stack_depth++;
  return true;
}

bool active(void) {
  return runner_state != RunnerState::IDLE;
}

bool calculator_suspended(void) {
  return trap_pending || trap_context_valid() ||
      (key_bind_active && runner_state != RunnerState::WAIT_RUN_STOP) ||
      (!bind_handler_active && !bind_pending && key_queue_count && key_boundary_ready);
}

bool trap_handler_active(void) { return trap_pending || trap_context_valid(); }

bool captures_key(u8 code) {
  return active() && !key_input_blocked &&
      (key_event_active(code, 0) || key_event_active(code, 1));
}

bool keyboard_available(void) { return active() && !key_input_blocked; }

bool handle_key_event(u8 code, bool down) {
  if(!captures_key(code)) return false;
  const u64 bit = (u64)1U << code;
  if(down) {
    if(key_pressed & bit) return true; // one DOWN for the whole gesture
    key_pressed |= bit;
    const bool press = key_event_active(code, 0);
    const bool release = key_event_active(code, 1);
    // Reserve release capacity before accepting a gesture. Under pressure
    // ignore a NEW complete gesture; never lose UP for an accepted DOWN.
    if(KEY_QUEUE_CAPACITY - key_queue_count < key_reserved_count + press + release) {
      key_ignored |= bit;
      return true;
    }
    if(release) { key_reserved |= bit; ++key_reserved_count; }
    if(press) queue_key(code, 0);
  } else {
    if(!(key_pressed & bit)) return true;
    key_pressed &= ~bit;
    if(key_ignored & bit) { key_ignored &= ~bit; return true; }
    if(key_reserved & bit) {
      key_reserved &= ~bit;
      --key_reserved_count;
      queue_key(code, 1);
    }
  }
  if(!core_61::is_RUN() || trap_pending || trap_context_valid())
    key_boundary_ready = true;
  return true;
}

bool display_owned(void) {
  return active() && display_claimed;
}

void claim_display(void) {
  if(active()) display_claimed = true;
}

void release_display(void) {
  display_claimed = false;
}

static void clear_trap_runtime(bool restore_calculator) {
  if(restore_calculator && trap_context_valid()) {
    (void) restore_trap_context();
  }
  release_trap_context();
  trap_pending = false;
  pending_trap_address = 0;
  pending_trap_target = INVALID_TRAP_TARGET;
  suspended_trap_address = 0;
  bypass_trap_once = false;
  bypass_trap_address = 0;
}

static void clear_bind_runtime(void) {
  bind_pending = false;
  bind_ready = false;
  pending_bind_target = INVALID_BIND_TARGET;
  pending_bind_sequence = 0;
  bind_handler_active = false;
  key_bind_active = false;
  key_input_blocked = 0;
  clear_key_runtime();
}

static void close_text_font_session(void) {
#if M61_TEXT_FONT_COMMAND
  if(!text_font_session_active) return;
  (void) program_store_text_font_end();
  text_font_session_active = false;
#endif
}

static void stop_runner(void) {
  close_text_font_session();
  clear_trap_runtime(true);
  clear_bind_runtime();
  clear_bind_hooks();
  if(boundary_hook_installed) {
    core_61::clear_mk61_program_boundary_hook();
    boundary_hook_installed = false;
  }
  runner_state = RunnerState::IDLE;
  display_claimed = false;
  wait_until_ms = 0;
  clear_current_script();
  return_stack_depth = 0;
  script_stack_depth = 0;
  release_runtime();
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
  bounded_string::copy(last_error_info.message,
                       message == NULL ? "unknown error" : message);
  stop_runner();
  has_error = true;
#if defined(MK61_CORE_STANDALONE)
  picocalc::script::report_error(last_error_info);
#elif !defined(M61_TEXT_HOST_TEST)
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

#if MK61_M61_PREPARED_CACHE
static bool prepared_space_available() {
  return read_cache_len && !read_cache_start && read_cache_len == script_len &&
      read_cache_len + sizeof(PreparedHeader) + sizeof(PreparedLine) <= PREPARED_END;
}

static PreparedHeader* prepared_header() {
  if(!prepared_space_available() ||
     read_cache_revision != program_store::media_revision()) return nullptr;
  return std::launder(reinterpret_cast<PreparedHeader*>(
      read_cache() + PREPARED_END - sizeof(PreparedHeader)));
}

static u8* prepared_slot_storage(u16 index) {
  const u16 spare_labels = MAX_LABELS - label_count;
  if(index < spare_labels) return label_storage((u8)(MAX_LABELS - index - 1U));
  index -= spare_labels;
  return read_cache() + PREPARED_END - sizeof(PreparedHeader) -
      (index + 1U) * sizeof(PreparedLine);
}

static PreparedLine* prepared_slot(u16 index) {
  return std::launder(reinterpret_cast<PreparedLine*>(prepared_slot_storage(index)));
}

static PreparedLine* find_prepared_line() {
  const PreparedHeader* header = prepared_header();
  if(header) {
    const u16 count = header->count & ~DIRECTORY_READY;
    for(u16 i = 0; i < count; ++i) {
      PreparedLine* entry = prepared_slot(i);
      if(entry->start == script_pos) return entry;
    }
  }
  return nullptr;
}
#endif

// Caller checks EOF before asking for a verified window.
static bool prepare_read_window(void) {
  if(script_source == ScriptSource::STORE) {
    const u32 revision=program_store::media_revision();
    if(read_cache_revision!=revision || script_pos < read_cache_start ||
       script_pos >= (u16) (read_cache_start + read_cache_len)) {
      read_cache_start = (u16)(script_pos / READ_CACHE_SIZE * READ_CACHE_SIZE);
      const u16 remaining = (u16) (script_len - read_cache_start);
      const u16 wanted = remaining < READ_CACHE_SIZE ? remaining : READ_CACHE_SIZE;
      u16 got = 0;
      if(!program_store::read_range_id(script_id, read_cache_start, read_cache(),
                                       wanted, &got) || got == 0) {
        read_cache_len = 0;
        return false;
      }
      read_cache_len = got;
      read_cache_revision = revision;
#if MK61_M61_PREPARED_CACHE
      if(prepared_space_available())
        new(read_cache() + PREPARED_END - sizeof(PreparedHeader)) PreparedHeader{};
#endif
    }
    return true;
  }

  return false;
}

static bool read_next_line(char* line, u16 capacity) {
#if !defined(M61_TEXT_HOST_TEST) && !defined(MK61_CORE_STANDALONE)
  MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::M61_READ_LINE);
#endif
  if(line == NULL || capacity == 0) return false;

  u16 line_len = 0;
  while(script_pos < script_len) {
    if(!prepare_read_window()) return false;
    const u8* cursor = read_cache() + (script_pos - read_cache_start);
    const u8* end = read_cache() + read_cache_len;
    // No storage writes or event service occur while consuming this window.
    // Refills and the next command recheck its revision.
    do {
      const char c = (char) *cursor++;
      if(c == '\r' || c == '\n' || c == 0) {
        script_pos = (u16) (read_cache_start + (cursor - read_cache()));
        // Принимаем CR и CRLF, не выдавая парный LF за пустую строку.
        if(c == '\r' && script_pos < script_len) {
          if(cursor == end && !prepare_read_window()) return false;
          if(read_cache()[script_pos - read_cache_start] == '\n') ++script_pos;
        }
        line[line_len] = 0;
        script_line++;
        return true;
      }
      if(line_len + 1 >= capacity) {
        script_pos = (u16) (read_cache_start + (cursor - read_cache()));
        return false;
      }
      line[line_len++] = c;
    } while(cursor < end);
    script_pos = (u16) (read_cache_start + read_cache_len);
  }
  line[line_len] = 0;
  return line_len > 0;
}

#if MK61_M61_PREPARED_CACHE
static PreparedLine* remember_prepared_line(const char* line, u16 start,
                                           bool terminated) {
  PreparedHeader* header = prepared_header();
  if(!header) return nullptr;
  const u16 count = header->count & ~DIRECTORY_READY;
  const u16 spare_labels = MAX_LABELS - label_count;
  const u16 source_slots = count < spare_labels ? 0 : count - spare_labels + 1U;
  if(sizeof(PreparedHeader) + source_slots * sizeof(PreparedLine) >
     (usize)(PREPARED_END - read_cache_len)) return nullptr;
  PreparedLine prepared = {};
  const char* command = skip_spaces(line);
  if(terminal_script::prepare_if(command, prepared.condition, prepared.tail_offset)) {
    prepared.tail_offset += (u8)(command - line);
  } else {
    const char* args = terminal_catalog::open_arguments(command);
    if(!args || terminal_core::at_end(args)) return nullptr;
  }
  prepared.start = start;
  prepared.next = script_pos;
  prepared.target = program_store::INVALID_ID;
  prepared.flags = terminated ? LINE_TERMINATED : 0;
  PreparedLine* slot = new(prepared_slot_storage(count)) PreparedLine(prepared);
  ++header->count;
  return slot;
}

static void copy_prepared_line(const PreparedLine& entry, u8 offset, char* line) {
  u16 len = entry.next - entry.start;
  const u8* source = read_cache() + entry.start;
  if(entry.flags & LINE_TERMINATED) {
    --len;
    if(source[len] == '\n' && len && source[len - 1] == '\r') --len;
  }
  len -= offset;
  memcpy(line, source + offset, len);
  line[len] = 0;
}
#endif

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
  if(read_cache_revision==program_store::media_revision() &&
     entry.name_pos>=read_cache_start &&
     (u32)entry.name_pos+entry.len<=(u32)read_cache_start+read_cache_len)
    return memcmp(read_cache()+(entry.name_pos-read_cache_start),name,len)==0;
  char stored[MAX_LABEL_SIZE + 1];
  u16 got = 0;
  if(!program_store::read_range_id(script_id, entry.name_pos, (u8*) stored,
                                   entry.len, &got) || got != entry.len) return false;
  return memcmp(stored, name, len) == 0;
}

static i16 find_label_index(const char* name, usize len) {
  const u32 hash = label_hash(name, len);
  for(u8 i = 0; i < label_count; i++) {
    if(label(i).hash == hash && stored_label_equals(label(i), name, len)) {
      return (i16) i;
    }
  }
  return -1;
}

enum class TrapParse : u8 { NONE, VALID, INVALID };

struct ParsedTrap {
  u8 address;
  const char* label;
  usize label_len;
};

static const char* keyword_end(const char* line, const char* keyword, usize length) {
  const char* p = skip_spaces(line);
  if(strncmp(p, keyword, length) != 0 ||
     (!is_space(p[length]) && !is_line_end(p[length]))) return NULL;
  return p + length;
}

static bool parse_handler_target(const char* p, const char*& label, usize& length) {
  if(strncmp(p, "run", 3) != 0 || !is_space(p[3])) return false;
  return parse_label(skip_spaces(p + 3), label, length) == LabelParse::VALID;
}

static TrapParse parse_trap(const char* line, ParsedTrap& out) {
  const char* p = keyword_end(line, "trap", 4);
  if(p == NULL) return TrapParse::NONE;
  if(!is_space(*p)) return TrapParse::INVALID;
  p = skip_spaces(p);

  usize address = 0;
  usize digits = 0;
  while(p[digits] >= '0' && p[digits] <= '9') {
    const usize digit = (usize) (p[digits] - '0');
    if(address > (core_61::MAX_PROGRAM_STEP - 1U - digit) / 10U) {
      return TrapParse::INVALID;
    }
    address = address * 10U + digit;
    digits++;
  }
  if(digits == 0 || !is_space(p[digits])) return TrapParse::INVALID;
  p = skip_spaces(p + digits);

  if(!parse_handler_target(p, out.label, out.label_len)) {
    return TrapParse::INVALID;
  }
  out.address = (u8) address;
  return TrapParse::VALID;
}

enum class BindParse : u8 { NONE, VALID, INVALID };

struct ParsedBind {
  bool key;
  u8 event;
  u8 opcode;
  const char* label;
  usize label_len;
};

static i8 hex_value(char value) {
  if(value >= '0' && value <= '9') return (i8) (value - '0');
  if(value >= 'A' && value <= 'F') return (i8) (value - 'A' + 10);
  if(value >= 'a' && value <= 'f') return (i8) (value - 'a' + 10);
  return -1;
}

static BindParse parse_bind(const char* line, ParsedBind& out) {
  const char* p = keyword_end(line, "bind", 4);
  if(p == NULL) return BindParse::NONE;
  if(!is_space(*p)) return BindParse::INVALID;
  p = skip_spaces(p);

  if(is_line_end(*p)) return BindParse::INVALID;
  out.key = strncmp(p, "key", 3) == 0 && is_space(p[3]);
  out.event = 0;
  if(out.key) p = skip_spaces(p + 3);
  const i8 high = hex_value(*p++);
  if(is_line_end(*p)) return BindParse::INVALID;
  const i8 low = hex_value(*p++);
  if(high < 0 || low < 0) return BindParse::INVALID;
  out.opcode = (u8)(((u8)high << 4) | (u8)low);
  if(!is_space(*p)) return BindParse::INVALID;
  p = skip_spaces(p);
  if(out.key) {
    if(!m61_keys::valid(out.opcode)) return BindParse::INVALID;
    if(strncmp(p, "down", 4) == 0 && is_space(p[4])) p += 4;
    else if(strncmp(p, "up", 2) == 0 && is_space(p[2])) {
      out.event = 1;
      p += 2;
    } else return BindParse::INVALID;
    p = skip_spaces(p);
  } else if(high > 0x0E) return BindParse::INVALID;

  if(!parse_handler_target(p, out.label, out.label_len)) {
    return BindParse::INVALID;
  }
  return BindParse::VALID;
}

static void set_trap_active(u8 address, bool active) {
#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
  active_trap_bit_alias_base()[address] = active ? 1U : 0U;
#else
  const u8 mask = (u8) (1U << (address & 7U));
  if(active) active_traps[address >> 3] |= mask;
  else active_traps[address >> 3] &= (u8) ~mask;
#endif
}

static bool trap_is_active(u8 address) {
#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
  return address < TRAP_ADDRESS_COUNT &&
         active_trap_bit_alias_base()[address] != 0;
#else
  return address < TRAP_ADDRESS_COUNT &&
         (active_traps[address >> 3] &
          (u8) (1U << (address & 7U))) != 0;
#endif
}

static bool any_trap_is_active(void) {
  for(u8 i = 0; i < TRAP_BITMAP_SIZE; i++) {
    if(active_traps[i] != 0) return true;
  }
  return false;
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
      if(stored_label_equals(label(i), name, len)) {
        error_message = "duplicate label";
        error_line = line_number;
        return false;
      }
    }

    // A previous frame may have used this slot for a prepared command.
    // Explicitly restart the label lifetime before writing its fields.
    LabelEntry& entry = *new(label_storage(label_count++)) LabelEntry;
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

static bool build_trap_index(const char*& error_message, u16& error_line) {
  const u16 resume_pos = script_pos;
  const u16 resume_line = script_line;
  script_pos = 0;
  script_line = 1;
  memset(trap_targets, INVALID_TRAP_TARGET, sizeof(trap_targets));
  invalidate_read_cache();

  char line[MAX_LINE_SIZE + 1];
  while(script_pos < script_len) {
    const u16 line_number = script_line;
    if(!read_next_line(line, sizeof(line))) {
      error_message = "cannot read script or line is too long";
      error_line = line_number;
      return false;
    }

    ParsedTrap parsed = {};
    const TrapParse result = parse_trap(line, parsed);
    if(result == TrapParse::NONE) continue;
    if(result == TrapParse::INVALID) {
      error_message = "invalid trap (use: trap <0..111> run :label)";
      error_line = line_number;
      return false;
    }
    if(trap_targets[parsed.address] != INVALID_TRAP_TARGET) {
      error_message = "duplicate trap address";
      error_line = line_number;
      return false;
    }
    const i16 target = find_label_index(parsed.label, parsed.label_len);
    if(target < 0) {
      error_message = "trap label not found";
      error_line = line_number;
      return false;
    }
    trap_targets[parsed.address] = (u8) target;
  }

  script_pos = resume_pos;
  script_line = resume_line;
  invalidate_read_cache();
  return true;
}

static bool build_bind_index(const char*& error_message, u16& error_line) {
  const u16 resume_pos = script_pos;
  const u16 resume_line = script_line;
  script_pos = 0;
  script_line = 1;
  bind_count = 0;
  memset(key_targets, INVALID_BIND_TARGET, sizeof(key_targets));
  invalidate_read_cache();

  char line[MAX_LINE_SIZE + 1];
  while(script_pos < script_len) {
    const u16 line_number = script_line;
    if(!read_next_line(line, sizeof(line))) {
      error_message = "cannot read script or line is too long";
      error_line = line_number;
      return false;
    }

    ParsedBind parsed = {};
    const BindParse result = parse_bind(line, parsed);
    if(result == BindParse::NONE) continue;
    if(result == BindParse::INVALID) {
      error_message = "invalid bind (use: bind key <code> down/up run :label)";
      error_line = line_number;
      return false;
    }
    if(parsed.key) {
      u8& target = key_targets[parsed.event][parsed.opcode];
      if(target != INVALID_BIND_TARGET) {
        error_message = "duplicate bind key event";
        error_line = line_number;
        return false;
      }
      const i16 found = find_label_index(parsed.label, parsed.label_len);
      if(found < 0) {
        error_message = "bind label not found";
        error_line = line_number;
        return false;
      }
      target = (u8)found;
      continue;
    }
    if(bind_count >= MAX_BINDS) {
      error_message = "too many binds (maximum 8)";
      error_line = line_number;
      return false;
    }
    if(find_bind_index(parsed.opcode) >= 0) {
      error_message = "duplicate bind opcode";
      error_line = line_number;
      return false;
    }
    const i16 target = find_label_index(parsed.label, parsed.label_len);
    if(target < 0) {
      error_message = "bind label not found";
      error_line = line_number;
      return false;
    }
    binds[bind_count++] = {parsed.opcode, (u8) target};
  }

  script_pos = resume_pos;
  script_line = resume_line;
  invalidate_read_cache();
  return true;
}

static void discard_undefined_active_traps(void) {
  for(u8 address = 0; address < TRAP_ADDRESS_COUNT; address++) {
    if(trap_targets[address] == INVALID_TRAP_TARGET) {
      set_trap_active(address, false);
    }
  }
}

static void discard_undefined_active_binds(void) {
  for(u8 event = 0; event < 2; ++event)
    for(u8 code = 0; code < m61_keys::COUNT; ++code)
      if(key_targets[event][code] == INVALID_BIND_TARGET)
        set_key_active(code, event, false);
  u8 next = 0;
  for(u8 i = 0; i < MAX_BINDS; i++) {
    const u8 opcode = active_bind_opcodes[i];
    if(opcode == INVALID_BIND_OPCODE || find_bind_index(opcode) < 0) continue;
    bool duplicate = false;
    for(u8 j = 0; j < next; j++) {
      if(active_bind_opcodes[j] == opcode) {
        duplicate = true;
        break;
      }
    }
    if(!duplicate) active_bind_opcodes[next++] = opcode;
  }
  while(next < MAX_BINDS) {
    active_bind_opcodes[next++] = INVALID_BIND_OPCODE;
  }
}

static bool activate_bind(u8 opcode) {
  if(bind_is_active(opcode)) return true;
  for(u8 i = 0; i < MAX_BINDS; i++) {
    if(active_bind_opcodes[i] != INVALID_BIND_OPCODE) continue;
    active_bind_opcodes[i] = opcode;
    if(sync_bind_hooks()) return true;
    active_bind_opcodes[i] = INVALID_BIND_OPCODE;
    (void) sync_bind_hooks();
    return false;
  }
  return false;
}

static bool activate_frame(const ScriptFrame& frame, const char*& error_message, u16& error_line) {
  clear_bind_hooks();
  if(frame.id != script_id) clear_key_runtime();
  if(!restore_frame(frame)) {
    error_message = "script file is unavailable";
    error_line = frame.line;
    return false;
  }
  if(!build_label_index(error_message, error_line) ||
     !build_trap_index(error_message, error_line) ||
     !build_bind_index(error_message, error_line)) {
    return false;
  }
  // Повторный запуск того же корневого файла может принести активные биты из
  // предыдущего запуска. Если файл успели переписать, не оставляем адреса,
  // для которых в новой версии уже нет объявления и обработчика.
  discard_undefined_active_traps();
  discard_undefined_active_binds();
  if(!sync_bind_hooks()) {
    error_message = "calculator command hook capacity is exhausted";
    error_line = 0;
    return false;
  }
  return true;
}

static bool restore_return_frame(const ReturnFrame& returned) {
  const char* error_message = NULL;
  u16 error_line = 0;
  if(!activate_frame(returned.script, error_message, error_line)) {
    fail_script(error_message, error_line);
    return false;
  }
  terminal_script::reset();
  return true;
}

static bool return_from_script(void) {
  if(return_stack_depth == 0) {
    if(program_load::blocked()) {
      fail_script(program_load::error(), script_line);
      return false;
    }
    if(any_trap_is_active() || any_bind_is_active()) {
      runner_state = RunnerState::WATCH_EVENTS;
      wait_until_ms = 0;
      return true;
    }
    stop_runner();
    return true;
  }

  const ReturnFrame returned = return_stack()[--return_stack_depth];
  if(returned.kind == ReturnKind::BIND) {
    if(!bind_handler_active) {
      fail_script("bind handler context is unavailable", script_line);
      return false;
    }
    if(!restore_return_frame(returned)) return false;
    bind_handler_active = false;
    const bool redraw = key_bind_active && !display_owned();
    key_bind_active = false;
    if(!key_queue_count) key_boundary_ready = false;
    runner_state = returned.runner_state;
    if(redraw) lcd_std_display_redraw();
    if(runner_state == RunnerState::WATCH_EVENTS &&
       !any_trap_is_active() && !any_bind_is_active()) {
      stop_runner();
    }
    return true;
  }

  if(returned.kind != ReturnKind::TRAP) {
    if(returned.kind == ReturnKind::SCRIPT && script_stack_depth > 0) {
      script_stack_depth--;
    }
    if(returned.kind == ReturnKind::SCRIPT) clear_key_runtime();
    if(!restore_return_frame(returned)) return false;
    runner_state = returned.runner_state;
    if(returned.kind == ReturnKind::SCRIPT) {
      // A nested program owned the input. End the parent's old gestures on
      // return, before its calculator can advance, rather than leave a flag
      // held forever when the physical UP was consumed by the child.
      for(u8 code=0;code<m61_keys::COUNT;++code)
        if((returned.script.held_keys[code/8U] & (1U << (code%8U))) &&
           key_event_active(code,1)) queue_key(code,1);
      if(key_queue_count) key_boundary_ready=true;
    }
    return true;
  }

  if(!trap_context_valid() || !restore_trap_context()) {
    fail_script("cannot restore calculator trap context", script_line);
    return false;
  }
  release_trap_context();
  bypass_trap_once = true;
  bypass_trap_address = suspended_trap_address;
  suspended_trap_address = 0;
  if(!restore_return_frame(returned)) return false;
  runner_state = returned.runner_state;
  if(runner_state == RunnerState::WATCH_EVENTS &&
     !any_trap_is_active() && !any_bind_is_active()) {
    stop_runner();
  }
  return true;
}

static void finish_script(void) {
  if(return_stack_depth > 0) {
    const ReturnKind kind = return_stack()[return_stack_depth - 1].kind;
    if(kind == ReturnKind::TRAP) {
      fail_script("trap handler reached end of script without ret", script_line);
      return;
    }
    if(kind == ReturnKind::BIND) {
      fail_script("bind handler reached end of script without ret", script_line);
      return;
    }
  }
  (void) return_from_script();
}

static bool open_store_script(const char* name) {
  ScriptFrame child;
  if(!make_store_frame(name, child)) return false;
  if(!push_current_frame(ReturnKind::SCRIPT)) return false;
  clear_key_runtime();

  const char* error_message = NULL;
  u16 error_line = 0;
  if(!activate_frame(child, error_message, error_line)) {
    const ReturnFrame parent = return_stack()[--return_stack_depth];
    if(script_stack_depth > 0) script_stack_depth--;
    restore_frame(parent.script);
    return false;
  }
  terminal_script::reset();
  // Nested scripts share the caller's program, just as they share registers.
  // Only a new root script or an explicit reinit starts with empty banks.
  runner_state = RunnerState::EXECUTING;
  return true;
}

static bool open_store_script(u16 id) {
  ScriptFrame child;
  if(!make_store_frame(id, child)) return false;
  if(!push_current_frame(ReturnKind::SCRIPT)) return false;
  clear_key_runtime();

  const char* error_message = NULL;
  u16 error_line = 0;
  if(!activate_frame(child, error_message, error_line)) {
    const ReturnFrame parent = return_stack()[--return_stack_depth];
    if(script_stack_depth > 0) script_stack_depth--;
    restore_frame(parent.script);
    return false;
  }
  terminal_script::reset();
  runner_state = RunnerState::EXECUTING;
  return true;
}

// Запуск загруженной программы прямо на ядре, ожидание останова — асинхронно
// из service(). Клавиши через буфер клавиатуры терялись бы при выходе из меню.
static bool start_current_program(u8 start_address) {
  if(trap_context_valid()) return false;
  const usize steps = core_61::program_steps();
  if(start_address >= steps) return false;
  for(u8 address = 0; address < TRAP_ADDRESS_COUNT; address++) {
    if(trap_is_active(address) && address >= steps) return false;
  }
  runner_state = RunnerState::WAIT_RUN_STOP;
  // Взводим исполнитель до последнего скрытого шага С/П: один шаг ядра может
  // дойти до первого кода программы, особенно в режиме MAXIMUM.
  hidden_start_loaded_program(start_address);
  if(!core_61::is_RUN()) {
    runner_state = RunnerState::EXECUTING;
    return false;
  }
  mk61_program_started();
  return true;
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

// В обычном сценарии "run :метка" остаётся переходом и поддерживает циклы.
// В обработчике trap или bind это локальный вызов: ret возвращает на строку
// после run, что позволяет вынести общий код кадра в одну метку.
static bool goto_label(const char* args) {
  args = skip_spaces(args);
  usize label_len = 0;
  while(!is_line_end(args[label_len]) && !is_space(args[label_len])) label_len++;
  if(label_len == 0 || label_len > MAX_LABEL_SIZE || !token_ends(args + label_len)) return false;

  const i16 target = find_label_index(args, label_len);
  if(target < 0) return false;
  if((trap_context_valid() || bind_handler_active) &&
     !push_current_frame(ReturnKind::LABEL)) {
    line_error_message = "label return stack is full";
    return false;
  }
  const LabelEntry& entry = label(target);
  script_pos = entry.target_pos;
  script_line = entry.target_line;
  // A same-script jump can reuse its verified read window. read_next_line
  // checks the media revision before consuming it.
  return true;
}

static void bind_command_hook(
    core_61::Mk61CommandHookContext& context, void* user_data) {
  (void) user_data;
  if(context.source != core_61::Mk61CommandSource::KEYBOARD) return;

  if(context.phase == core_61::Mk61CommandHookPhase::AFTER_EXECUTE) {
    if(bind_pending && context.sequence == pending_bind_sequence) {
      bind_ready = true;
    }
    return;
  }

  if(context.phase != core_61::Mk61CommandHookPhase::BEFORE_EXECUTE ||
     runner_state != RunnerState::WATCH_EVENTS ||
     bind_handler_active || bind_pending ||
     !bind_is_active(context.opcode)) {
    return;
  }

  const i16 bind_index = find_bind_index(context.opcode);
  if(bind_index < 0 || binds[bind_index].target >= label_count) return;

  pending_bind_target = binds[bind_index].target;
  pending_bind_sequence = context.sequence;
  bind_pending = true;
  bind_ready = false;
  // bind является горячей клавишей, а не наблюдателем: исходная операция
  // калькулятора поглощается, но завершает штатный клавиатурный цикл через NOP.
  context.replacement_opcode = (u8) MK61_NOP;
}

static bool enter_pending_bind(void) {
  if(!bind_pending || !bind_ready ||
     pending_bind_target >= label_count) {
    return false;
  }
  const u8 target = pending_bind_target;
  if(!push_current_frame(ReturnKind::BIND)) {
    line_error_message = "bind return stack is full";
    return false;
  }

  bind_pending = false;
  bind_ready = false;
  pending_bind_target = INVALID_BIND_TARGET;
  pending_bind_sequence = 0;
  bind_handler_active = true;

  const LabelEntry& entry = label(target);
  script_pos = entry.target_pos;
  script_line = entry.target_line;
  invalidate_read_cache();
  runner_state = RunnerState::EXECUTING;
  return true;
}

static bool program_boundary_hook(
    const core_61::Mk61ProgramBoundaryContext& context, void* user_data) {
  if((runner_state != RunnerState::WAIT_RUN_STOP &&
      runner_state != RunnerState::WATCH_EVENTS) ||
     !core_61::is_RUN()) {
    return false;
  }

  if(key_queue_count && !bind_handler_active && !bind_pending) {
    key_boundary_ready = true;
    return true;
  }

  if(bypass_trap_once) {
    const bool bypass = context.address == bypass_trap_address;
    bypass_trap_once = false;
    if(bypass) return false;
  }

#if MK61_STM32_SRAM_BIT_BAND_AVAILABLE
  const volatile u32* active_bits =
      reinterpret_cast<volatile u32*>(user_data);
  if(context.address >= TRAP_ADDRESS_COUNT ||
     active_bits[context.address] == 0) return false;
#else
  (void) user_data;
  if(!trap_is_active(context.address)) return false;
#endif
  const u8 target = trap_targets[context.address];
  if(target == INVALID_TRAP_TARGET || target >= label_count) return false;
  trap_pending = true;
  pending_trap_address = context.address;
  pending_trap_target = target;
  return true;
}

static bool enter_pending_trap(void) {
  if(!trap_pending || pending_trap_target >= label_count) return false;
  const u8 address = pending_trap_address;
  const u8 target = pending_trap_target;

  if(!push_current_frame(ReturnKind::TRAP)) {
    line_error_message = "trap return stack is full";
    return false;
  }
  core_61::ContextBuffer* saved = core_61::acquire_context_buffer(
      core_61::ContextBufferOwner::M61_TRAP);
  if(saved == nullptr || !core_61::save_context(*saved)) {
    release_trap_context();
    return_stack_depth--;
    line_error_message = "cannot save calculator trap context";
    return false;
  }

  trap_pending = false;
  pending_trap_address = 0;
  pending_trap_target = INVALID_TRAP_TARGET;
  suspended_trap_address = address;

  const LabelEntry& entry = label(target);
  script_pos = entry.target_pos;
  script_line = entry.target_line;
  invalidate_read_cache();
  runner_state = RunnerState::EXECUTING;
  return true;
}

enum class ReferencedOpenResult : u8 {
  OPENED = 0,
  STOPPED = 1,
  FAILED = 2
};

static ReferencedOpenResult open_referenced_entry(
    const program_store::Entry& entry) {
  struct InputScope {
    bool owns_input;
    explicit InputScope(bool owns) : owns_input(owns) {
      if(!owns_input) return;
      for(u8 code = 0; code < m61_keys::COUNT; ++code)
        if(key_pressed & ((u64)1U << code)) (void)handle_key_event(code, false);
      ++key_input_blocked;
    }
    ~InputScope() { if(owns_input && key_input_blocked) --key_input_blocked; }
  } input_scope(entry.type != program_store::ProgramType::MK61);
#if defined(MK61_CORE_STANDALONE)
  return (ReferencedOpenResult)picocalc::script::open_entry(entry);
#elif !defined(M61_TEXT_HOST_TEST)
  if(entry.type == program_store::ProgramType::TINYBASIC) {
    const TinyBasicRunStatus status = RunTinyBasicProgramStatus(
        entry.id, TinyBasicRunMode::M61_SCENARIO);
    if(status == TinyBasicRunStatus::COMPLETED) {
      return ReferencedOpenResult::OPENED;
    }
    if(status == TinyBasicRunStatus::STOPPED) {
      return ReferencedOpenResult::STOPPED;
    }
    switch(status) {
      case TinyBasicRunStatus::UNAVAILABLE:
        line_error_message = "TinyBASIC is unavailable";
        break;
      case TinyBasicRunStatus::COMPILE_ERROR:
        line_error_message = "TinyBASIC compile error";
        break;
      case TinyBasicRunStatus::RUNTIME_ERROR:
        line_error_message = "TinyBASIC runtime error";
        break;
      case TinyBasicRunStatus::NOT_FOUND:
        line_error_message = "TinyBASIC file not found";
        break;
      case TinyBasicRunStatus::COMPLETED:
      case TinyBasicRunStatus::STOPPED:
        break;
    }
    return ReferencedOpenResult::FAILED;
  }
  return OpenStoredEntry(entry) ? ReferencedOpenResult::OPENED
                                : ReferencedOpenResult::FAILED;
#else
  return (ReferencedOpenResult)m61_text_host_open_entry(entry);
#endif
}

static u16 current_script_directory(bool* resolved = nullptr) {
#if MK61_M61_PREPARED_CACHE
  PreparedHeader* header = prepared_header();
  if(header && (header->count & DIRECTORY_READY)) {
    if(resolved) *resolved = true;
    return header->directory;
  }
#endif
  program_store::Entry entry;
  const bool found = script_id != program_store::INVALID_ID &&
      program_store::entry_by_id(script_id, entry);
  if(resolved) *resolved = found;
  const u16 directory = found ? entry.parent_id : program_store::ROOT_ID;
#if MK61_M61_PREPARED_CACHE
  if(header && found) {
    header->directory = directory;
    header->count |= DIRECTORY_READY;
  }
#endif
  return directory;
}

static bool resolve_referenced_file(u16 cwd, const char* path,
                                    program_store::Entry& entry) {
#ifndef M61_TEXT_HOST_TEST
  return storage_path::resolve_file(cwd, path, entry) == storage_path::Status::OK;
#else
  return m61_text_host_resolve_file(cwd, path, entry);
#endif
}

static ReferencedOpenResult open_referenced_file(const char* path,
                                               PreparedLine* prepared = nullptr) {
#if !defined(M61_TEXT_HOST_TEST) && !defined(MK61_CORE_STANDALONE)
  MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::M61_OPEN);
#endif
  program_store::Entry entry;
#if MK61_M61_PREPARED_CACHE
  if(prepared && !prepared_header()) prepared = nullptr;
  if(prepared && prepared->target != program_store::INVALID_ID) {
    // BASIC consumes only id/type. Other viewers may need the full Entry.
    entry = {};
    entry.id = prepared->target;
    entry.type = (program_store::ProgramType)(prepared->flags & 0x0F);
    if(entry.type == program_store::ProgramType::TINYBASIC ||
       program_store::entry_by_id(entry.id, entry))
      return open_referenced_entry(entry);
  }
#else
  (void)prepared;
#endif
#if MK61_M61_PREPARED_CACHE
  bool directory_resolved = false;
  const u16 cwd = current_script_directory(&directory_resolved);
#else
  const u16 cwd = current_script_directory();
#endif
#if MK61_M61_PREPARED_CACHE
  const bool simple = strchr(path, '/') == NULL && strchr(path, '\\') == NULL;
#endif
  const bool direct = resolve_referenced_file(cwd, path, entry);
  // Совместимость со старыми сценариями без каталогов: простое имя, которого
  // нет рядом с вызывающим сценарием, всё ещё может обозначать файл в корне.
  // Для явно относительных путей переход к несвязанному объекту запрещён.
  if(!direct &&
     !(cwd != program_store::ROOT_ID &&
#if MK61_M61_PREPARED_CACHE
     simple &&
#else
     strchr(path, '/') == NULL && strchr(path, '\\') == NULL &&
#endif
     resolve_referenced_file(program_store::ROOT_ID, path, entry))) {
    return ReferencedOpenResult::FAILED;
  }
#if MK61_M61_PREPARED_CACHE
  // Cache only a positively identified neighbour. The path resolver also has
  // an invalid-cwd recovery at root: a transient directory read failure can
  // therefore produce OK for a different base, even without our fallback.
  // Complex paths and every uncertain/root-fallback result keep ordinary
  // resolution; never turn a single failed read into a persistent wrong file.
  if(prepared && directory_resolved && direct && simple && entry.parent_id == cwd) {
    prepared->target = entry.id;
    prepared->flags = (prepared->flags & LINE_TERMINATED) | (u8)entry.type;
  }
#endif
  // Do not touch the borrowed cache after launching: a nested script or an
  // interpreter can replace its window, mutate the FS, or cancel this runner.
  return open_referenced_entry(entry);
}

// `open?` is the optional counterpart of the strict `open` command.  It is
// intentionally handled by the M61 runner instead of the interactive terminal:
// launchers may offer a manual or another enhancement when its viewer exists,
// while every mandatory program part continues to use strict `open`.
static const char* optional_open_arguments(const char* line) {
  const char* p = keyword_end(line, "open?", 5);
  return p == NULL ? NULL : skip_spaces(p);
}

#if M61_TEXT_FONT_COMMAND
static bool loadfont_arguments(const char* line, const char*& args) {
  const char* p = keyword_end(line, "loadfont", 8);
  if(p == NULL) return false;
  args = skip_spaces(p);
  return true;
}

static bool execute_loadfont(const char* args) {
  if(token_ends(args)) {
    if(!text_font_session_active) return true;
    if(program_store_text_font_restore() == 1) return true;
    line_error_message = "cannot restore default font";
    return false;
  }

  if(!text_font_session_active) {
    const i32 begin = program_store_text_font_begin();
    if(begin != 1) {
      line_error_message = begin == -2
          ? "loadfont requires UC1609"
          : "font service is unavailable";
      return false;
    }
    text_font_session_active = true;
  }

  const u16 directory = current_script_directory();
  bool selected = false;
  bool stopped = false;
  i32 result = 0;
  const char* cursor = args;
  while(!terminal_core::at_end(cursor)) {
    char name[program_store::NAME_SIZE + 16U];
    if(!terminal_core::parse_token(cursor, name, sizeof(name))) {
      line_error_message =
          "invalid loadfont syntax (use names separated by spaces)";
      return false;
    }
    if(selected || stopped) continue;
    const i32 attempt = program_store_text_font_load_from(name, directory);
    if(attempt == 1) {
      selected = true;
    } else if(attempt == -1) {
      result = -1;
    } else if(attempt == -2 || attempt == -3) {
      result = attempt;
      stopped = true;
    } else if(attempt != 0) {
      result = -3;
      stopped = true;
    }
  }
  if(selected) return true;
  if(result == -1) line_error_message = "font file is invalid";
  else if(result == -2) line_error_message = "loadfont requires UC1609";
  else if(result == -3) line_error_message = "font service is unavailable";
  else line_error_message = "font not found";
  return false;
}
#endif

static void clear_frame_handlers(ScriptFrame& frame) {
  memset(frame.active_traps, 0, sizeof(frame.active_traps));
  memset(frame.active_bind_opcodes, INVALID_BIND_OPCODE,
         sizeof(frame.active_bind_opcodes));
  memset(frame.active_keys, 0, sizeof(frame.active_keys));
  memset(frame.held_keys, 0, sizeof(frame.held_keys));
}

static void clear_active_handlers(void) {
  clear_bind_hooks();
  clear_active_traps();
  clear_active_binds();
  for(u8 i = 0; i < return_stack_depth; i++) {
    clear_frame_handlers(return_stack()[i].script);
  }

  trap_pending = false;
  pending_trap_address = 0;
  pending_trap_target = INVALID_TRAP_TARGET;
  bypass_trap_once = false;
  bypass_trap_address = 0;
  bind_pending = false;
  bind_ready = false;
  pending_bind_target = INVALID_BIND_TARGET;
  pending_bind_sequence = 0;
  clear_key_runtime();
}

static bool frame_has_active_handlers(const ScriptFrame& frame) {
  for(const auto& events : frame.active_keys)
    for(u8 bits : events) if(bits) return true;
  for(u8 i = 0; i < TRAP_BITMAP_SIZE; i++) {
    if(frame.active_traps[i] != 0) return true;
  }
  for(u8 i = 0; i < MAX_BINDS; i++) {
    if(frame.active_bind_opcodes[i] != INVALID_BIND_OPCODE) return true;
  }
  return false;
}

bool clear_bindings_and_traps(void) {
  bool had_handlers =
      any_trap_is_active() || any_bind_is_active() ||
      trap_pending || trap_context_valid() ||
      bind_pending || bind_handler_active ||
      runner_state == RunnerState::WATCH_EVENTS;
  for(u8 i = 0; i < return_stack_depth && !had_handlers; i++) {
    had_handlers = frame_has_active_handlers(return_stack()[i].script);
  }
  if(!had_handlers) return false;

  clear_active_handlers();
  // После корневого ret выполнять больше нечего: освобождаем boundary hook,
  // дисплей и runner. Исполняющийся сценарий или текущий обработчик завершает
  // свой обычный путь; очищенные кадры не восстановят старые bind/trap.
  if(runner_state == RunnerState::WATCH_EVENTS) stop_runner();
  return true;
}

// Вся грамматика команд разбирается терминалом (единый диспетчер интерактивного
// и скриптового режимов). Сценарию терминал возвращает только действия,
// влияющие на поток выполнения: run, open, load, переходы по меткам и reinit.
static bool execute_script_result(const terminal_protocol::Result& result,
                                  PreparedLine* prepared);

static bool execute_script_line(const char* raw_line,
                               PreparedLine* prepared = nullptr) {
#if !defined(M61_TEXT_HOST_TEST) && !defined(MK61_CORE_STANDALONE)
  MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::M61_COMMAND);
#endif
  line_error_message = NULL;
  const char* line = skip_spaces(raw_line);
  if(is_line_end(*line)) return true;
  if(*line == ':') return true; // Метка — точка перехода, сама по себе ничего не делает
#if defined(MK61_LINKED_VM_POC) && MK61_LINKED_VM_POC
  // Explicit experimental command; never recognize/rewrite arbitrary OPEN
  // dispatch scripts. Package chunks are already installed beside the script.
  if(const char* args=keyword_end(line,"vm-linked",9)) {
    if(!is_line_end(*skip_spaces(args)) || trap_context_valid()) {
      line_error_message="invalid vm-linked context";return false;
    }
    if(language_vm::run_linked_program(current_script_directory()))return true;
    line_error_message="linked VM failed";return false;
  }
#endif

  const char* optional_path = optional_open_arguments(line);
  if(optional_path != NULL) {
    if(trap_context_valid()) {
      line_error_message = "open? is not allowed in a trap handler";
      return false;
    }
    if(is_line_end(*optional_path)) {
      line_error_message = "optional open needs a path";
      return false;
    }
    switch(open_referenced_file(optional_path)) {
      case ReferencedOpenResult::OPENED:
        return true;
      case ReferencedOpenResult::STOPPED:
        // ESC inside a nested interpreter still means that the user wants to
        // leave the whole scenario, exactly as it does for strict `open`.
        cancel();
        lcd_std_display_redraw();
        return true;
      case ReferencedOpenResult::FAILED:
        // Optional content must never poison a later strict command with its
        // diagnostic.  The script deliberately asked to continue silently.
        line_error_message = NULL;
        return true;
    }
  }

#if M61_TEXT_FONT_COMMAND
  const char* font_args = NULL;
  if(loadfont_arguments(line, font_args)) return execute_loadfont(font_args);
#endif

  ParsedTrap parsed_trap = {};
  const TrapParse trap_result = parse_trap(line, parsed_trap);
  if(trap_result == TrapParse::VALID) {
    set_trap_active(parsed_trap.address, true);
    return true;
  }
  if(trap_result == TrapParse::INVALID) {
    line_error_message = "invalid trap (use: trap <0..111> run :label)";
    return false;
  }

  ParsedBind parsed_bind = {};
  const BindParse bind_result = parse_bind(line, parsed_bind);
  if(bind_result == BindParse::VALID) {
    if(parsed_bind.key) {
      set_key_active(parsed_bind.opcode, parsed_bind.event, true);
      return true;
    }
    if(activate_bind(parsed_bind.opcode)) return true;
    line_error_message = "cannot activate bind command hooks";
    return false;
  }
  if(bind_result == BindParse::INVALID) {
    line_error_message = "invalid bind (use: bind key <code> down/up run :label)";
    return false;
  }

  const terminal_protocol::Result result =
      terminal_script::execute(line, trap_context_valid());
  return execute_script_result(result, prepared);
}

static bool execute_script_result(const terminal_protocol::Result& result,
                                  PreparedLine* prepared) {
  switch(result.kind) {
    case terminal_protocol::ResultKind::OK:
      return true;
    case terminal_protocol::ResultKind::RUN_PROGRAM: {
      if(program_load::blocked()) {
        line_error_message = program_load::error();
        return false;
      }
      // Older callers use action(RUN_PROGRAM, ""), whose key is -1.
      const i32 address = result.key == -1 ? 0 : result.key;
      if(address < 0 || (usize) address >= core_61::program_steps()) {
        line_error_message = "run address is outside current program memory";
        return false;
      }
      if(start_current_program((u8) address)) return true;
      line_error_message = trap_context_valid()
          ? "cannot run calculator from a trap handler"
          : "active trap address is outside current program memory";
      return false;
    }
    case terminal_protocol::ResultKind::OPEN_FILE:
      switch(open_referenced_file(result.args, prepared)) {
        case ReferencedOpenResult::OPENED:
          return true;
        case ReferencedOpenResult::STOPPED:
          // ESC inside a nested interpreter belongs to the M61 scenario as a
          // whole. stop_runner() closes the scoped font session first; only
          // then redraw the ordinary calculator face. This path deliberately
          // has no error overlay and no second acknowledgement wait.
          cancel();
          lcd_std_display_redraw();
          return true;
        case ReferencedOpenResult::FAILED:
          break;
      }
      if(line_error_message == NULL)
        line_error_message = "cannot open referenced file";
      return false;
    case terminal_protocol::ResultKind::LOAD_SLOT:
      if(open_slot(result.args)) return true;
      line_error_message = "cannot load nested slot";
      return false;
    case terminal_protocol::ResultKind::LOAD_BINARY:
      if(trap_context_valid()) {
        line_error_message = "binary load is not allowed in a trap handler";
        return false;
      }
      if(load_binary_program(current_script_directory(), result.args)) return true;
      line_error_message = program_load::error();
      return false;
    case terminal_protocol::ResultKind::GOTO_LABEL:
      if(goto_label(result.args)) return true;
      line_error_message = "label not found or invalid";
      return false;
    case terminal_protocol::ResultKind::WAIT:
      if(result.key <= 0 || result.key > 60000) {
        line_error_message = "invalid wait duration";
        return false;
      }
      wait_until_ms = runner_millis() + (u32) result.key;
      runner_state = RunnerState::WAIT_TIME;
      return true;
    case terminal_protocol::ResultKind::RETURN_SCRIPT:
      return return_from_script();
    case terminal_protocol::ResultKind::REINIT_CALCULATOR:
      if(trap_context_valid()) {
        line_error_message = "reinit is not allowed in a trap handler";
        return false;
      }
      clear_active_handlers();
      display_claimed = false;
      program_load::reset();
      reinit_mk61_calculator_state();
      return true;
    case terminal_protocol::ResultKind::ERROR:
    case terminal_protocol::ResultKind::KEY:
      line_error_message = program_load::blocked()
          ? program_load::error() : "terminal command failed";
      return false;
  }
  return false;
}

#if MK61_M61_PREPARED_CACHE
static bool execute_prepared_line(PreparedLine* cached, char* line) {
#if !defined(M61_TEXT_HOST_TEST) && !defined(MK61_CORE_STANDALONE)
  MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::M61_COMMAND);
#endif
  // A returned action can release this runtime. Keep command metadata local,
  // and never access cached after dispatching the synchronous action.
  const PreparedLine entry = *cached;
  script_pos = entry.next;
  if(entry.flags & LINE_TERMINATED) ++script_line;
  line_error_message = nullptr;
  u8 offset = 0;
  if(entry.condition.operation) {
    switch(terminal_script::evaluate_if(entry.condition, trap_context_valid())) {
      case terminal_script::IfResult::FALSE: return true;
      case terminal_script::IfResult::ERROR:
        return execute_script_result(terminal_protocol::Result::error(), cached);
      case terminal_script::IfResult::TRUE: offset = entry.tail_offset; break;
      case terminal_script::IfResult::FALLBACK:
        copy_prepared_line(entry, 0, line);
        return execute_script_line(line, cached);
    }
  }
  copy_prepared_line(entry, offset, line);
  return execute_script_result(terminal_script::execute(
      skip_spaces(line), trap_context_valid()), cached);
}
#endif

void service(void) {
#if !defined(M61_TEXT_HOST_TEST) && !defined(MK61_CORE_STANDALONE)
  MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::M61_RUNNER);
#endif
  if(runner_state == RunnerState::WAIT_TIME) {
    if(!time_reached(runner_millis(), wait_until_ms)) return;
    wait_until_ms = 0;
    runner_state = RunnerState::EXECUTING;
  }

  if(trap_pending) {
    const u16 trap_line = script_line;
    if(!enter_pending_trap()) {
      fail_script(line_error_message == NULL ? "cannot enter trap handler" : line_error_message,
                  trap_line);
      return;
    }
  }

  if(key_queue_count && !trap_context_valid() && !bind_handler_active && !bind_pending &&
     (runner_state == RunnerState::WATCH_EVENTS ||
      runner_state == RunnerState::WAIT_RUN_STOP) &&
     (key_boundary_ready || !core_61::is_RUN())) {
    const u8 event = key_queue[key_queue_head];
    key_queue_head = (u8)((key_queue_head + 1U) % KEY_QUEUE_CAPACITY);
    --key_queue_count;
    const u8 code = event & 0x3FU;
    const u8 edge = event & 0x40U ? 1 : 0;
    const u8 target = key_targets[edge][code];
    if(target != INVALID_BIND_TARGET && key_event_active(code, edge)) {
      pending_bind_target = target;
      pending_bind_sequence = 0;
      bind_pending = bind_ready = true;
      key_bind_active = true;
    }
  }

  if(bind_pending && bind_ready) {
    const u16 bind_line = script_line;
    if(!enter_pending_bind()) {
      fail_script(line_error_message == NULL
                      ? "cannot enter bind handler"
                      : line_error_message,
                  bind_line);
      return;
    }
  }

  if(runner_state == RunnerState::WAIT_RUN_STOP) {
    if(!core_61::is_CALC()) return;
    // Программа МК остановилась: управление возвращается к следующей строке сценария.
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
    bool executed = false;
#if MK61_M61_PREPARED_CACHE
    PreparedLine* cached = nullptr;
    // A larger source cannot have a prepared table. Keep its ordinary single
    // window check instead of adding a second refill/revision check per line.
    if(script_len + sizeof(PreparedHeader) + sizeof(PreparedLine) <= PREPARED_END) {
      if(!prepare_read_window()) {
        fail_script("cannot read script or line is too long", line_number);
        return;
      }
      cached = find_prepared_line();
    }
    if(cached) {
      executed = execute_prepared_line(cached, line);
    } else {
      const u16 start = script_pos;
#endif
      if(!read_next_line(line, sizeof(line))) {
        fail_script("cannot read script or line is too long", line_number);
        return;
      }
      PreparedLine* prepared = nullptr;
#if MK61_M61_PREPARED_CACHE
      prepared = remember_prepared_line(line, start, script_line != line_number);
#endif
      executed = execute_script_line(line, prepared);
#if MK61_M61_PREPARED_CACHE
    }
#endif
    if(!executed) {
      // A nested call/ret may already have reported the original failure and
      // cleared its frame. Keep that script name, line and diagnostic intact.
      if(!has_error)
        fail_script(line_error_message == NULL ? "command failed" : line_error_message, line_number);
      return;
    }
  }
}

static bool load_frame(const ScriptFrame& frame) {
  ScriptFrame next = frame;
  const bool restart_same_root =
      runner_state == RunnerState::WATCH_EVENTS &&
      return_stack_depth == 0 &&
      script_source == ScriptSource::STORE &&
      frame.source == ScriptSource::STORE &&
      script_id == frame.id;
  if(restart_same_root) {
    save_active_traps(next.active_traps);
    save_active_binds(next.active_bind_opcodes);
    memcpy(next.active_keys, active_keys, sizeof(active_keys));
  }
  if(active()) stop_runner();
  clear_error();
  if(!prepare_runtime()) {
    copy_script_name(script_name, "");
    fail_script("not enough RAM for script runtime", 0);
    return false;
  }

  const char* error_message = NULL;
  u16 error_line = 0;
  if(!activate_frame(next, error_message, error_line)) {
    fail_script(error_message, error_line);
    return false;
  }
  return_stack_depth = 0;
  script_stack_depth = 0;
  display_claimed = false;
  wait_until_ms = 0;
  clear_trap_runtime(false);
  clear_bind_runtime();
  if(!core_61::set_mk61_program_boundary_hook(
      program_boundary_hook, active_trap_boundary_hook_data())) {
    fail_script("calculator boundary hook is unavailable", 0);
    return false;
  }
  boundary_hook_installed = true;
  terminal_script::reset();
  MK61Emu_ClearCodePage();
  program_load::reset();
  runner_state = RunnerState::EXECUTING;
  service();
  return !has_error;
}

bool load_program(const char* name) {
  if(name == NULL || name[0] == 0) return false;
  LoadScope loading_scope;
  ScriptFrame frame;
  if(!make_store_frame(name, frame)) {
    copy_script_name(script_name, name);
    fail_script("script not found", 0);
    return false;
  }
  return load_frame(frame);
}

bool load_program(u16 id) {
  LoadScope loading_scope;
  ScriptFrame frame;
  if(!make_store_frame(id, frame)) return false;
  return load_frame(frame);
}

// Единственная точка открытия МК61-скрипта по имени (через OpenStoredEntry):
// изнутри выполняющегося сценария — вложенный вызов с возвратом на следующую
// строку, извне (терминал, проводник, меню) — свежая загрузка.
bool open_program(const char* name) {
  if(runner_state == RunnerState::EXECUTING) return open_store_script(name);
  return load_program(name);
}

bool open_program(u16 id) {
  if(runner_state == RunnerState::EXECUTING) return open_store_script(id);
  return load_program(id);
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

} // пространство имён m61_text
