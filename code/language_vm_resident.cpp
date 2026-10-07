#include "config.h"
#if MK61_RESIDENT_LANGUAGE_VM || MK61_OVERLAY_LANGUAGE_VM
#include <string.h>
#include "language_vm_resident.hpp"
#include "language_vm_flow.hpp"
#include "language_compiler_flow.hpp"
#include "app_flow_transfer.hpp"
#include "shared_memory.hpp"
#include "workspace_swap.hpp"
#if MK61_OVERLAY_LANGUAGE_VM && MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
#include "language_vm_image_cache.hpp"
#if !defined(LANGUAGE_VM_HOST_TEST)
#include "program_store.hpp"
#include "development.hpp"
#endif
#endif

#if defined(LANGUAGE_VM_HOST_TEST)
namespace language_vm_test {
loadable_module::RuntimeStatus frontend(loadable_module::Kind,
    loadable_module::Command,uint32_t,uint32_t,language_vm::Request*,uint32_t&);
#if MK61_OVERLAY_LANGUAGE_VM
loadable_module::RuntimeStatus overlay(loadable_module::Kind,
    loadable_module::Command,void*,uint32_t&);
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
uint32_t media_revision();
void activate_text_font();
#endif
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
#if MK61_OVERLAY_LANGUAGE_VM && MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
ImageCache<MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES> image_cache;
uint32_t image_revision() {
#if defined(LANGUAGE_VM_HOST_TEST)
  return language_vm_test::media_revision();
#else
  return program_store::media_revision();
#endif
}
void activate_cached_text_font() {
#if defined(LANGUAGE_VM_HOST_TEST)
  language_vm_test::activate_text_font();
#else
  (void)program_store_text_font_activate();
#endif
}
#endif
#if !MK61_OVERLAY_LANGUAGE_VM
loadable_module::RuntimeStatus frontend(loadable_module::Kind kind,
    loadable_module::Command command,uint32_t a,uint32_t b,Request* request,uint32_t& result) {
#if defined(LANGUAGE_VM_HOST_TEST)
  return language_vm_test::frontend(kind,command,a,b,request,result);
#else
  return loadable_module::invoke(kind,command,a,b,(uint32_t)(uintptr_t)request,0,result);
#endif
}
#endif
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
#if !MK61_OVERLAY_LANGUAGE_VM
bool is_index(Language language, loadable_module::Command command) {
  return command == (language == Language::BASIC
                         ? loadable_module::Command::TINYBASIC_RUN_INDEX
                         : loadable_module::Command::FOCAL_RUN_INDEX);
}
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
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
loadable_module::RuntimeStatus execute_overlay(ExecuteRequest& execution,
    ExecutionState& state, loadable_module::Command original, uint32_t& result,
    const ValidatedImage* cached = nullptr, ValidatedImage* checked_image = nullptr) {
  FlowContext context = {};
  context.magic = FLOW_CONTEXT_MAGIC;
  context.original_command = (uint32_t)original;
  context.program = {sizeof(OverlayRequest), REQUEST_VERSION, &execution,
                     &state, &context.program_validated, OverlayAction::START, {0, 0, 0}};
  if(cached) {
    context.program_validated = *cached;
    View view;
    if(!validated_view(context.program, view)) return loadable_module::RuntimeStatus::CORRUPT_MODULE;
    initialize_validated_state(execution, context.program_validated, state);
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
    activate_cached_text_font();
#endif
  }
  const auto first = mk61_app_flow_to(cached ? MK61_APP_KIND_LANGUAGE_VM : MK61_APP_KIND_LANGUAGE_INPUT,
      MK61_APP_FLOW_SYSTEM_FILE, cached ? FLOW_RUN_PROGRAM : FLOW_VALIDATE_PROGRAM);
#if defined(LANGUAGE_VM_HOST_TEST)
  const auto status = (loadable_module::RuntimeStatus)app_flow::run(
      first, &context, sizeof(context), result, flow_invoke);
#else
  const auto status = loadable_module::run_flow(first, &context, sizeof(context), result);
#endif
  if(checked_image) *checked_image = context.program_validated;
  return status;
}
#endif
#endif
}  // namespace
#if MK61_OVERLAY_LANGUAGE_VM
namespace {
struct CompilerServices {
  CompilerContext* context;
  app_flow::Transfer* memory;
};
loadable_module::RuntimeStatus compiler_memory(void* raw, app_flow::Step& step) {
  auto& binding = *(CompilerServices*)raw;
  if(step.context != binding.context || step.context_size != sizeof(CompilerContext))
    return loadable_module::RuntimeStatus::CORRUPT_MODULE;
  auto& plan = binding.context->transfer;
  if(step.current.phase == app_flow::RESERVE_IMAGE) {
    const auto status = binding.memory->reserve(plan);
    if(status != loadable_module::RuntimeStatus::OK) return status;
    mk61_app_flow_return(&step, 1, MK61_FLOW_OK);
  } else if(step.current.phase == app_flow::COMMIT_IMAGE) {
    const auto status = binding.memory->commit(plan);
    if(status != loadable_module::RuntimeStatus::OK) return status;
    mk61_app_flow_next(&step, plan.next);
  } else return loadable_module::RuntimeStatus::CORRUPT_MODULE;
  return loadable_module::RuntimeStatus::OK;
}
#if defined(LANGUAGE_VM_HOST_TEST)
app_flow::Status compiler_flow_invoke(void* raw, const app_flow::Target& target, app_flow::Step& step) {
  if(target.kind == MK61_APP_FLOW_HOST) return (app_flow::Status)compiler_memory(raw, step);
  return flow_invoke(nullptr, target, step);
}
#endif
}
static loadable_module::RuntimeStatus invoke_resident_impl(Language language,
    loadable_module::Command command, uint32_t a, uint32_t b, uint32_t& result,
    uint16_t* edit_id = nullptr, uint32_t* edit_position = nullptr) {
  using namespace loadable_module;
  result = 0;
  if(busy || (language != Language::BASIC && language != Language::FOCAL)) return RuntimeStatus::BUSY;
  struct BusyScope { BusyScope(){ busy=true; } ~BusyScope(){ busy=false; } } busy_scope;
  static uint16_t error_id = 0xFFFF, error_line = 0, error_column = 0;
  if(language == Language::BASIC && command == Command::TINYBASIC_EDIT_ID && a == error_id) {
    if(!b) b = ((uint32_t)error_line << 16) | error_column;
    error_id = 0xFFFF;
  }
  shared_memory::WorkspacePartition partition;
  {
    shared_memory::Lease full;
    if(!workspace(full)) return RuntimeStatus::BUSY;
    auto* values = (Persistent*)(full.data() + COMPILER_WORKSPACE_SIZE);
    if(full.fresh() || values->magic != SESSION_MAGIC) initialize(*values);
  }
  if(!partition.open(shared_memory::Owner::LANGUAGE_VM, VALUES_SIZE)) return RuntimeStatus::BUSY;
  auto* values = (PersistentValues*)partition.tail();
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
  const bool cacheable = language == Language::BASIC &&
      command == Command::TINYBASIC_RUN_ID_STATUS && b == 1;
  const uint32_t revision = image_revision();
  if(cacheable) {
    if(const auto* cached = image_cache.find((uint16_t)a, revision)) {
      values->selected[0] = (uint16_t)a;
      shared_memory::Lease state;
      if(!workspace(state)) return RuntimeStatus::BUSY;
      ExecuteRequest execution = {};
      execution.size=sizeof(execution); execution.version=REQUEST_VERSION;
      execution.image=image_cache.image(*cached); execution.image_size=cached->validated.size;
      execution.variables=values->variables[0]; execution.array=values->array;
      execution.array_count=385; execution.mode=1;
      auto* continuation=state.as<ExecutionState>();
      *continuation={}; continuation->language=language;
      const auto status=execute_overlay(execution,*continuation,command,result,&cached->validated);
      if(status != RuntimeStatus::OK) return status;
      error_id=execution.result.error==Error::NONE?0xFFFF:(uint16_t)a;
      error_line=(uint16_t)execution.result.line; error_column=execution.error_column;
      return RuntimeStatus::OK;
    }
  }
#endif
  CompilerContext context = {};
  context.vm.magic=FLOW_CONTEXT_MAGIC; context.vm.original_command=(uint32_t)command;
  context.values=values; context.command=(uint32_t)command;
  context.argument0=a; context.argument1=b; context.language=language;
  app_flow::Transfer memory(shared_memory::Owner::LANGUAGE_VM);
  CompilerServices services = {&context, &memory};
  const auto first=mk61_app_flow_to(language==Language::BASIC?MK61_APP_KIND_TINYBASIC:MK61_APP_KIND_FOCAL,
      MK61_APP_FLOW_SYSTEM_FILE,FLOW_COMPILE_SOURCE);
#if defined(LANGUAGE_VM_HOST_TEST)
  const auto status=(RuntimeStatus)app_flow::run(first,&context,sizeof(context),result,
                                               compiler_flow_invoke,&services);
#else
  const auto status=loadable_module::run_flow_service(first,&context,sizeof(context),result,
                                                     compiler_memory,&services);
#endif
  if(status != RuntimeStatus::OK || !context.prepared) return status;
  auto& execution=context.execution;
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
  if(cacheable && context.compiler.source_id==a && !context.compiler.clear_requested &&
     context.compiler.mode==1 && execution.result.error==Error::NONE)
    (void)image_cache.store((uint16_t)a,revision,execution.image,context.vm.program_validated);
#endif
  if(language==Language::BASIC) {
    error_id=execution.result.error==Error::NONE?0xFFFF:context.compiler.source_id;
    error_line=(uint16_t)execution.result.line; error_column=execution.error_column;
  }
  if(edit_id && edit_position && language==Language::BASIC && execution.mode==0 &&
     execution.edit_requested && execution.result.line && context.compiler.source_id!=0xFFFF) {
    *edit_id=context.compiler.source_id;
    *edit_position=(execution.result.line<<16)|execution.error_column;
  }
  return RuntimeStatus::OK;
}
#else
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
  // The resident-executor experiment retains its original staging layout.
  shared_memory::Lease transfer(shared_memory::Arena::OVERLAY,
                                shared_memory::Owner::LOADABLE_MODULE,
                                sizeof(Persistent) + MAX_IMAGE);
  if (!transfer.ok()) return RuntimeStatus::BUSY;
  auto* saved = transfer.as<Persistent>();
  {
    shared_memory::Lease state;
    if (!workspace(state)) return RuntimeStatus::BUSY;
    auto* values = state.as<Persistent>();
    if (state.fresh() || values->magic != SESSION_MAGIC) initialize(*values);
    memcpy(saved, values, sizeof(*saved));
  }
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
  request.output = transfer.data() + sizeof(Persistent);
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
  shared_memory::Lease state;
  if (!workspace(state)) return RuntimeStatus::BUSY;
  auto* values = state.as<Persistent>();
  memcpy(values, saved, sizeof(*saved));
  if (status != RuntimeStatus::OK || !request.run_requested) return status;
  if (request.compiled.error != Error::NONE || request.compiled.size < HEADER_SIZE ||
      request.compiled.size > MAX_IMAGE)
    return RuntimeStatus::CORRUPT_MODULE;
  View view;
  if (inspect(request.output, request.compiled.size, view) != Error::NONE ||
      view.language != language || view.expression) return RuntimeStatus::CORRUPT_MODULE;
  const auto unloaded = loadable_module::evict_cached();
  if (unloaded != RuntimeStatus::OK) return unloaded;
  const uint8_t* image = request.output;
  constexpr size_t state_bytes = sizeof(Persistent);
  static_assert(state_bytes < shared_memory::WORKSPACE_SIZE, "VM state needs workspace");
  if (request.compiled.size <= state.size() - state_bytes) {
    uint8_t* destination = state.data() + state_bytes;
    memcpy(destination, image, request.compiled.size);
    image = destination;
    transfer.reset();
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
  if (!execute_resident(execution)) return RuntimeStatus::INVALID_MODULE;
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
  result = run_status(language, original, execution.result.error);
  return RuntimeStatus::OK;
}
#endif
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
