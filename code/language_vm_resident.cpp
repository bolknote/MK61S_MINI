#include "config.h"
#if MK61_RESIDENT_LANGUAGE_VM || MK61_OVERLAY_LANGUAGE_VM
#include <string.h>
#include "language_vm_resident.hpp"
#include "language_vm_flow.hpp"
#include "shared_memory.hpp"
#include "workspace_swap.hpp"
#if MK61_SCREEN_BUFFER_LOAN && MK61_OVERLAY_LANGUAGE_VM
#include "display_buffer_loan.hpp"
#endif

#if defined(LANGUAGE_VM_HOST_TEST)
namespace language_vm_test {
loadable_module::RuntimeStatus frontend(loadable_module::Kind,
    loadable_module::Command,uint32_t,uint32_t,language_vm::Request*,uint32_t&);
#if MK61_OVERLAY_LANGUAGE_VM
loadable_module::RuntimeStatus overlay(loadable_module::Kind,
    loadable_module::Command,void*,uint32_t&);
#endif
}
#endif

namespace language_vm {
namespace {
#if MK61_OVERLAY_LANGUAGE_VM
constexpr uint32_t SESSION_MAGIC = 0x35564D4CUL;
#else
constexpr uint32_t SESSION_MAGIC = 0x31564D4CUL;
#endif
struct Persistent {
  uint32_t magic;
  uint16_t selected[2];
  double variables[2][26];
  double array[385];
};
static_assert(sizeof(Persistent) == 3504, "language values layout changed");
static_assert(sizeof(Persistent) == VALUES_SIZE, "workspace partition ABI changed");
static_assert(sizeof(Persistent) < shared_memory::WORKSPACE_SIZE,
              "values need workspace");
bool busy;
loadable_module::RuntimeStatus frontend(loadable_module::Kind kind,
    loadable_module::Command command,uint32_t a,uint32_t b,Request* request,uint32_t& result) {
#if defined(LANGUAGE_VM_HOST_TEST)
  return language_vm_test::frontend(kind,command,a,b,request,result);
#else
  return loadable_module::invoke(kind,command,a,b,(uint32_t)(uintptr_t)request,0,result);
#endif
}
bool workspace(shared_memory::Lease& lease) {
  return workspace_swap::acquire(shared_memory::Owner::LANGUAGE_VM,
                                 shared_memory::workspace_partitioned()
                                     ? COMPILER_WORKSPACE_SIZE : shared_memory::WORKSPACE_SIZE,
                                 workspace_swap::AcquireMode::REQUIRED, lease);
}
void initialize(Persistent& state) {
  memset(&state, 0, sizeof(state));
  state.magic = SESSION_MAGIC;
  state.selected[0] = state.selected[1] = 0xFFFF;
}
bool is_index(Language language, loadable_module::Command command) {
  return command == (language == Language::BASIC
                         ? loadable_module::Command::TINYBASIC_RUN_INDEX
                         : loadable_module::Command::FOCAL_RUN_INDEX);
}
#if !MK61_OVERLAY_LANGUAGE_VM
uint32_t run_status(Language language, loadable_module::Command command, Error error) {
  using C = loadable_module::Command;
  if (language == Language::BASIC) {
    if (command == C::TINYBASIC_RUN_ID_STATUS)
      return error == Error::NONE ? 1 : error == Error::STOPPED ? 2 : 4;
    if (command == C::TINYBASIC_RUN_ID || command == C::TINYBASIC_RUN_NAME)
      return error == Error::NONE || error == Error::STOPPED;
    return error == Error::NONE;
  }
  if (command == C::FOCAL_RUN_INDEX || command == C::FOCAL_RUN_ID ||
      command == C::FOCAL_RUN_NAME)
    return error == Error::NONE ? 0 : error == Error::STOPPED ? 1 : 3;
  return error == Error::NONE;
}
#endif
#if MK61_OVERLAY_LANGUAGE_VM
#if defined(LANGUAGE_VM_HOST_TEST)
app_flow::Status flow_invoke(void*, const app_flow::Target& target, app_flow::Step& step) {
  uint32_t result = 0;
  const auto info = language_vm_test::overlay((loadable_module::Kind)target.kind,
      loadable_module::Command::APP_FLOW_INFO, nullptr, result);
  if(info != loadable_module::RuntimeStatus::OK) return (app_flow::Status)info;
  if(result != MK61_APP_FLOW_MAGIC) return MK61_FLOW_INCOMPATIBLE;
  const auto status = language_vm_test::overlay((loadable_module::Kind)target.kind,
      loadable_module::Command::APP_FLOW_STEP, &step, result);
  return status != loadable_module::RuntimeStatus::OK ? (app_flow::Status)status
      : result == 1 ? MK61_FLOW_OK : MK61_FLOW_CORRUPT;
}
#endif
loadable_module::RuntimeStatus execute_overlay(ExecuteRequest& execution,
    ExecutionState& state, loadable_module::Command original, uint32_t& result) {
  FlowContext context = {};
  context.magic = FLOW_CONTEXT_MAGIC;
  context.original_command = (uint32_t)original;
  context.program = {sizeof(OverlayRequest), REQUEST_VERSION, &execution,
                     &state, &context.program_validated, OverlayAction::START, {0, 0, 0}};
  const auto first = mk61_app_flow_to(MK61_APP_KIND_LANGUAGE_INPUT,
      MK61_APP_FLOW_SYSTEM_FILE, FLOW_VALIDATE_PROGRAM);
#if defined(LANGUAGE_VM_HOST_TEST)
  return (loadable_module::RuntimeStatus)app_flow::run(
      first, &context, sizeof(context), result, flow_invoke);
#else
  return loadable_module::run_flow(first, &context, sizeof(context), result);
#endif
}
#endif
}  // namespace
static loadable_module::RuntimeStatus invoke_resident_impl(Language language,
                                                           loadable_module::Command command,
                                                           uint32_t a, uint32_t b, uint32_t& result,
                                                           uint16_t* edit_id = nullptr,
                                                           uint32_t* edit_position = nullptr) {
  using namespace loadable_module;
  result = 0;
  if (busy || (language != Language::BASIC && language != Language::FOCAL))
    return RuntimeStatus::BUSY;
  struct BusyScope {
    BusyScope() { busy = true; }
    ~BusyScope() { busy = false; }
  } scope;
  static uint16_t basic_error_id = 0xFFFF, basic_error_line = 0, basic_error_column = 0;
  if (language == Language::BASIC && command == Command::TINYBASIC_EDIT_ID && a == basic_error_id) {
    if (!b) b = ((uint32_t)basic_error_line << 16) | basic_error_column;
    basic_error_id = 0xFFFF;
  }
  const unsigned index = language == Language::BASIC ? 0 : 1;
#if MK61_OVERLAY_LANGUAGE_VM
  // Retained values stay at the upper end of the existing WORKSPACE. Only
  // the lower prefix changes owner during the foreground compiler transaction.
  shared_memory::WorkspacePartition partition;
  {
    shared_memory::Lease full;
    if (!workspace(full)) return RuntimeStatus::BUSY;
    auto* values = (Persistent*)(full.data() + COMPILER_WORKSPACE_SIZE);
    if (full.fresh() || values->magic != SESSION_MAGIC) initialize(*values);
  }
  if (!partition.open(shared_memory::Owner::LANGUAGE_VM, sizeof(Persistent)))
    return RuntimeStatus::BUSY;
  auto* saved = (Persistent*)partition.tail();
  shared_memory::Lease transfer;
#if MK61_ENABLE_USB_SCREEN
  shared_memory::OverlayBuffer usb_transfer;
#endif
#if MK61_SCREEN_BUFFER_LOAN
  DisplayBufferLoan screen_transfer;
#endif
#else
  // The resident-executor experiment retains its original staging layout.
  shared_memory::Lease transfer(shared_memory::Arena::OVERLAY,
                                shared_memory::Owner::LOADABLE_MODULE,
                                sizeof(Persistent)
#if !MK61_OVERLAY_LANGUAGE_VM
                                    + MAX_IMAGE
#endif
                                );
  if (!transfer.ok()) return RuntimeStatus::BUSY;
  auto* saved = transfer.as<Persistent>();
  {
    shared_memory::Lease state;
    if (!workspace(state)) return RuntimeStatus::BUSY;
    auto* values = state.as<Persistent>();
    if (state.fresh() || values->magic != SESSION_MAGIC) initialize(*values);
    memcpy(saved, values, sizeof(*saved));
  }
#endif
  const Command original = command;
  if (is_index(language, command)) {
    if (a != 0 || saved->selected[index] == 0xFFFF) {
      result = language == Language::BASIC ? 0 : 4;
      return RuntimeStatus::OK;
    }
    a = saved->selected[index];
    command =
        language == Language::BASIC ? Command::TINYBASIC_RUN_ID : Command::FOCAL_RUN_ID;
  }
  Request request = {};
  request.size = sizeof(request);
  request.version = REQUEST_VERSION;
#if !MK61_OVERLAY_LANGUAGE_VM
  request.output = transfer.data() + sizeof(Persistent);
#endif
  request.capacity = MAX_IMAGE;
  request.source_id = 0xFFFF;
  request.language = (uint8_t)language;
  const Kind kind = language == Language::BASIC ? Kind::TINYBASIC : Kind::FOCAL;
  uint32_t info = 0;
  RuntimeStatus status = frontend(kind,Command::LANGUAGE_COMPILER_INFO,0,0,nullptr,info);
  if (status == RuntimeStatus::OK && info != COMPILER_MAGIC)
    status = RuntimeStatus::INCOMPATIBLE_FIRMWARE;
  if (status == RuntimeStatus::OK)
    status = frontend(kind,command,a,b,&request,result);
  if (request.source_id != 0xFFFF) saved->selected[index] = request.source_id;
  if (request.clear_requested) {
    memset(saved->variables[index], 0, sizeof(saved->variables[index]));
    if (language == Language::BASIC) memset(saved->array, 0, sizeof(saved->array));
  }
#if MK61_OVERLAY_LANGUAGE_VM
  // First pass retained the editor/source in the compiler's prefix. Reserve
  // only the measured image size; no variables backup is needed.
  // This also preserves an unsaved editor RUN: no second UI or file reload.
  if (status == RuntimeStatus::OK && request.run_requested) {
    const uint16_t expected = request.compiled.size;
    if (request.compiled.error != Error::NONE || expected < HEADER_SIZE || expected > MAX_IMAGE)
      status = RuntimeStatus::CORRUPT_MODULE;
    else {
      u8* staging = nullptr;
#if MK61_SCREEN_BUFFER_LOAN
      if(screen_transfer.acquire(expected)) staging = screen_transfer.data();
#endif
      // Never evict the compiler while reserving output: that would discard
      // an unsaved editor RUN between sizing and EMIT. Active USB, a large
      // image or an unavailable screen loan needs separately owned staging.
#if MK61_ENABLE_USB_SCREEN
      if(!staging && shared_memory::active_owner(shared_memory::Arena::OVERLAY) ==
                      shared_memory::Owner::USB_SCREEN) {
        // USB owns its parser/immutable frame snapshot, not all free RAM.
        // This exact-size buffer cannot evict the still-live compiler APP.
        if(!usb_transfer.acquire(shared_memory::Owner::LOADABLE_MODULE,expected))
          return RuntimeStatus::BUSY;
        staging = usb_transfer.data();
      }
#endif
      if(!staging) {
        if(((expected+7U)&~7U) > shared_memory::capacity(shared_memory::Arena::OVERLAY) ||
           !transfer.acquire(shared_memory::Arena::OVERLAY,
                             shared_memory::Owner::LOADABLE_MODULE,expected))
          return RuntimeStatus::BUSY;
        staging = transfer.data();
      }
      request.output = staging; request.capacity = expected;
      request.run_requested = 0;
      status = frontend(kind, Command::LANGUAGE_COMPILER_EMIT, 0, 0, &request, result);
      if (status == RuntimeStatus::OK &&
          (!request.run_requested || request.compiled.error != Error::NONE ||
           request.compiled.size != expected)) status = RuntimeStatus::CORRUPT_MODULE;
    }
  }
#endif
  shared_memory::Lease state;
  if (!workspace(state)) return RuntimeStatus::BUSY;
#if MK61_OVERLAY_LANGUAGE_VM
  auto* values = saved;
#else
  auto* values = state.as<Persistent>();
  memcpy(values, saved, sizeof(*saved));
#endif
  if (status != RuntimeStatus::OK || !request.run_requested) return status;
  if (request.compiled.error != Error::NONE || request.compiled.size < HEADER_SIZE ||
      request.compiled.size > MAX_IMAGE)
    return RuntimeStatus::CORRUPT_MODULE;
#if MK61_RESIDENT_LANGUAGE_VM
  View view;
  if (inspect(request.output, request.compiled.size, view) != Error::NONE ||
      view.language != language || view.expression) return RuntimeStatus::CORRUPT_MODULE;
#endif
  const auto unloaded = loadable_module::evict_cached();
  if (unloaded != RuntimeStatus::OK) return unloaded;
  const uint8_t* image = request.output;
#if MK61_OVERLAY_LANGUAGE_VM
  constexpr size_t state_bytes = sizeof(ExecutionState);
#else
  constexpr size_t state_bytes = sizeof(Persistent);
#endif
  static_assert(state_bytes < shared_memory::WORKSPACE_SIZE, "VM state needs workspace");
  if (request.compiled.size <= state.size() - state_bytes) {
    uint8_t* destination = state.data() + state_bytes;
    memcpy(destination, image, request.compiled.size);
    image = destination;
    transfer.reset();
#if MK61_OVERLAY_LANGUAGE_VM && MK61_ENABLE_USB_SCREEN
    usb_transfer.reset();
#endif
#if MK61_SCREEN_BUFFER_LOAN && MK61_OVERLAY_LANGUAGE_VM
    screen_transfer.reset();
#endif
#if MK61_OVERLAY_LANGUAGE_VM && MK61_ENABLE_USB_SCREEN
  } else if(usb_transfer.ok()) {
    image = usb_transfer.data();
#endif
  } else {
    if(!transfer.ok()) return RuntimeStatus::CORRUPT_MODULE;
    memmove(transfer.data(),image,request.compiled.size);
    if(!transfer.shrink_to(request.compiled.size))return RuntimeStatus::BUSY;
    image=transfer.data();
  }
  // A maximum-size image that cannot coexist with all retained array values
  // stays in the transient arena during RUN; it never forces a flash cache.
  ExecuteRequest execution = {};
  execution.size = sizeof(execution);
  execution.version = REQUEST_VERSION;
  execution.image = image;
  execution.image_size = request.compiled.size;
  execution.variables = values->variables[index];
  execution.array = language == Language::BASIC ? values->array : nullptr;
  execution.array_count = language == Language::BASIC ? 385 : 0;
  execution.mode = request.mode;
#if MK61_OVERLAY_LANGUAGE_VM
  auto* continuation = (ExecutionState*)state.data();
  *continuation = {}; continuation->language = language;
  status = execute_overlay(execution, *continuation, original, result);
  if (status != RuntimeStatus::OK) return status;
#else
  if (!execute_resident(execution)) return RuntimeStatus::INVALID_MODULE;
#endif
  if (language == Language::BASIC) {
    basic_error_id = execution.result.error == Error::NONE ? 0xFFFF : request.source_id;
    basic_error_line = (uint16_t)execution.result.line;
    basic_error_column = execution.error_column;
  }
  if (edit_id && edit_position && language == Language::BASIC && execution.mode == 0 &&
      execution.edit_requested && execution.result.line && request.source_id != 0xFFFF) {
    *edit_id = request.source_id;
    *edit_position = (execution.result.line << 16) | execution.error_column;
  }
#if !MK61_OVERLAY_LANGUAGE_VM
  result = run_status(language, original, execution.result.error);
#endif
  return RuntimeStatus::OK;
}
loadable_module::RuntimeStatus invoke_resident(Language language, loadable_module::Command command,
                                               uint32_t a, uint32_t b, uint32_t& result) {
  uint16_t edit_id = 0xFFFF;
  uint32_t edit_position = 0;
  const auto status =
      invoke_resident_impl(language, command, a, b, result, &edit_id, &edit_position);
  // The run's image/state leases and BUSY guard have ended before opening the
  // compiler/editor again. Never load a new APP over an active VM allocation.
  if (status == loadable_module::RuntimeStatus::OK && edit_id != 0xFFFF) {
    uint32_t ignored = 0;
    (void)invoke_resident_impl(Language::BASIC, loadable_module::Command::TINYBASIC_EDIT_ID,
                               edit_id, edit_position, ignored);
  }
  return status;
}
}  // namespace language_vm
#endif
