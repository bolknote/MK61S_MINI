#include "config.h"
#if MK61_RESIDENT_LANGUAGE_VM || MK61_OVERLAY_LANGUAGE_VM
#include <string.h>
#include "language_vm_resident.hpp"
#include "language_vm_flow.hpp"
#include "dwt_profiler.hpp"
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
uint16_t resolve_name(language_vm::Language, uint32_t);
#endif
#endif
}
#endif

namespace language_vm {
namespace {
#if MK61_OVERLAY_LANGUAGE_VM
constexpr uint32_t SESSION_MAGIC = 0x37564D4CUL;
#else
constexpr uint32_t SESSION_MAGIC = 0x33564D4CUL;
#endif
struct Persistent {
  uint32_t magic;
  uint16_t selected[2];
  Value variables[2][26];
  Value array[385];
  Value focal_array[64];
};
static_assert(sizeof(Persistent) == 4016, "language values layout changed");
static_assert(sizeof(Persistent) == VALUES_SIZE, "workspace partition ABI changed");
static_assert(sizeof(Persistent) < shared_memory::WORKSPACE_SIZE,
              "values need workspace");
bool busy;
#if MK61_OVERLAY_LANGUAGE_VM && MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
static_assert(MK61_LANGUAGE_VM_CACHE_DENSITY == 0 || MK61_LANGUAGE_VM_CACHE_DENSITY == 1,
              "cache density must be 0 or 1");
using ProgramCache = ImageCache<MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES, 16,
    MK61_LANGUAGE_VM_CACHE_DENSITY ? CachePolicy::REUSE_DENSITY : CachePolicy::LRU>;
ProgramCache image_cache;
static_assert(sizeof(ProgramCache)<=MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES,"cache exceeds total RAM budget");
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
bool saved_run(Language language,loadable_module::Command command) {
  using C=loadable_module::Command;
  return language==Language::BASIC ? command==C::TINYBASIC_RUN_ID_STATUS || command==C::TINYBASIC_RUN_ID ||
      command==C::TINYBASIC_RUN_INDEX || command==C::TINYBASIC_RUN_NAME :
      command==C::FOCAL_RUN_ID || command==C::FOCAL_RUN_INDEX || command==C::FOCAL_RUN_NAME;
}
uint16_t cached_source(Language language,loadable_module::Command command,uint32_t a,const PersistentValues& values) {
  using C=loadable_module::Command;
  if(command==C::TINYBASIC_RUN_INDEX || command==C::FOCAL_RUN_INDEX)
    return a ? 0xFFFF : values.selected[language==Language::BASIC?0:1];
  if(command!=C::TINYBASIC_RUN_NAME && command!=C::FOCAL_RUN_NAME) return a<=0xFFFF?(uint16_t)a:0xFFFF;
#if defined(LANGUAGE_VM_HOST_TEST)
  return language_vm_test::resolve_name(language,a);
#else
  if(!a) return 0xFFFF;
  const auto type=language==Language::BASIC?program_store::ProgramType::TINYBASIC:program_store::ProgramType::FOCAL;
  for(int i=0;i<program_store::count(type);++i) {
    program_store::Entry e={};
    if(program_store::entry(type,i,e) && !strcmp(e.name,(const char*)(uintptr_t)a)) return e.id;
  }
  return 0xFFFF;
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
  memset(static_cast<void*>(&state), 0, sizeof(state));
  state.magic = SESSION_MAGIC;
  state.selected[0] = state.selected[1] = 0xFFFF;
  for(auto& language : state.variables) for(auto& value : language) value=Value(0);
  for(auto& value : state.array) value=Value(0);
  for(auto& value : state.focal_array) value=Value(0);
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
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
  bool cacheable;
  ProgramCache::Handle object;
  ~CompilerServices() {if(object) (void)image_cache.release(object);}
#endif
};
loadable_module::RuntimeStatus compiler_memory(void* raw, app_flow::Step& step) {
  auto& binding = *(CompilerServices*)raw;
  if(step.context != binding.context || step.context_size != sizeof(CompilerContext))
    return loadable_module::RuntimeStatus::CORRUPT_MODULE;
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
  if(step.current.phase==app_flow::PUBLISH_IMAGE) {
    if(!binding.context->prepared || !binding.object) return loadable_module::RuntimeStatus::CORRUPT_MODULE;
    image_cache.synchronize(image_revision());
    if(!image_cache.publish(binding.object,binding.context->vm.program_validated)) return loadable_module::RuntimeStatus::IO_ERROR;
#if MK61_DWT_RUNTIME_DETAIL_SUPPORTED
    dwt_profiler::record_vm_image(binding.context->source_id, binding.context->vm.program_validated.size);
#endif
    mk61_app_flow_next(&step,mk61_app_flow_to(MK61_APP_KIND_LANGUAGE_VM,
        MK61_APP_FLOW_SYSTEM_FILE,FLOW_RUN_PROGRAM));return loadable_module::RuntimeStatus::OK;
  }
#endif
  if(binding.context->prepared) return loadable_module::RuntimeStatus::CORRUPT_MODULE;
  auto& plan = binding.context->compile.transfer;
  if(step.current.phase == app_flow::RESERVE_IMAGE) {
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
    auto& request=binding.context->compile.request;
    if(binding.cacheable && request.source_id!=0xFFFF && request.resources==ResourceMode::EMBEDDED) {
      const uint32_t revision=image_revision();
      if(request.source_revision!=revision) return loadable_module::RuntimeStatus::IO_ERROR;
      binding.object=image_cache.reserve({revision,request.source_id,binding.context->language,0},(uint16_t)plan.size);
      if(binding.object) {
        plan.image=image_cache.building(binding.object);binding.context->cache_target=true;
        mk61_app_flow_return(&step,1,MK61_FLOW_OK);return loadable_module::RuntimeStatus::OK;
      }
    }
#endif
    if(plan.size>shared_memory::WORKSPACE_SIZE) return loadable_module::RuntimeStatus::BUSY;
    const auto status = binding.memory->reserve(plan);
    if(status != loadable_module::RuntimeStatus::OK) return status;
    mk61_app_flow_return(&step, 1, MK61_FLOW_OK);
  } else if(step.current.phase == app_flow::COMMIT_IMAGE) {
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
    if(binding.context->cache_target && (!binding.object || plan.image!=image_cache.building(binding.object)))
      return loadable_module::RuntimeStatus::CORRUPT_MODULE;
#endif
    const auto status = binding.context->cache_target ? binding.memory->retain_image(plan) : binding.memory->commit(plan);
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
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
  static uint32_t error_revision=0;
#endif
  if(language == Language::BASIC && command == Command::TINYBASIC_EDIT_ID && a == error_id) {
    if(!b) b =
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
        error_revision && error_revision!=image_revision() ? STALE_SOURCE_POSITION :
#endif
        ((uint32_t)error_line << 16) | error_column;
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
  const bool cacheable = saved_run(language,command);
  const uint32_t revision = image_revision();
  const uint16_t source_id=cacheable?cached_source(language,command,a,*values):0xFFFF;
  if(cacheable) {
    ProgramCache::Handle cached;
    {
      MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::VM_CACHE_LOOKUP);
      cached=image_cache.find({revision,source_id,language,0});
    }
#if MK61_DWT_RUNTIME_DETAIL_SUPPORTED
    dwt_profiler::record_vm_cache(source_id, (bool)cached, cached ? image_cache.certificate(cached)->size : 0);
#endif
    if(cached) {
      struct PinScope {ProgramCache::Handle h;~PinScope(){(void)image_cache.release(h);}} pin={cached};
      shared_memory::Lease state;
      ExecuteRequest execution = {};
      const auto* certificate=image_cache.certificate(cached);
      ExecutionState* continuation;
      {
        MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::VM_PREPARE);
        values->selected[language==Language::BASIC?0:1] = source_id;
        if(!workspace(state)) return RuntimeStatus::BUSY;
        execution.size=sizeof(execution); execution.version=REQUEST_VERSION;
        execution.image=image_cache.image(cached); execution.image_size=certificate->size;
        execution.variables=values->variables[language==Language::BASIC?0:1];
        execution.array=language==Language::BASIC?values->array:values->focal_array;
        execution.array_count=language==Language::BASIC?385:64;
        execution.mode=command==Command::TINYBASIC_RUN_ID_STATUS?(uint8_t)b:0;
        continuation=state.as<ExecutionState>();
        // Before validated_view only the language tag is read. The checked
        // cached path initializes the complete state exactly once below.
        continuation->language=language;
      }
      const auto status=execute_overlay(execution,*continuation,command,result,certificate);
      if(status != RuntimeStatus::OK) return status;
      if(language==Language::BASIC) {
        error_id=execution.result.error==Error::NONE?0xFFFF:source_id;
        error_line=(uint16_t)execution.result.line; error_column=execution.error_column;
        error_revision=revision;
        if(edit_id && edit_position && execution.mode==0 && execution.edit_requested && execution.result.line) {
          *edit_id=source_id;*edit_position=revision==image_revision() ?
              (execution.result.line<<16)|execution.error_column : STALE_SOURCE_POSITION;
        }
      }
      return RuntimeStatus::OK;
    }
  }
#endif
  CompilerContext context = {};
  context.compile.magic=FLOW_CONTEXT_MAGIC; context.compile.original_command=(uint32_t)command;
  context.compile.values=values; context.compile.command=(uint32_t)command;
  context.compile.argument0=a; context.compile.argument1=b; context.language=language;
  app_flow::Transfer memory(shared_memory::Owner::LANGUAGE_VM);
  CompilerServices services = {&context, &memory
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
      ,cacheable,{}
#endif
  };
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
  if(language==Language::BASIC) {
    error_id=execution.result.error==Error::NONE?0xFFFF:context.source_id;
    error_line=(uint16_t)execution.result.line; error_column=execution.error_column;
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
    error_revision=revision;
#endif
  }
  if(edit_id && edit_position && language==Language::BASIC && execution.mode==0 &&
     execution.edit_requested && execution.result.line && context.source_id!=0xFFFF) {
    *edit_id=context.source_id;
    *edit_position=
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
        revision==image_revision() ? (execution.result.line<<16)|execution.error_column : STALE_SOURCE_POSITION;
#else
        (execution.result.line<<16)|execution.error_column;
#endif
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
    for(auto& value : saved->variables[index]) value=Value(0);
    if(language==Language::BASIC){for(auto& value:saved->array)value=Value(0);}
    else {for(auto& value:saved->focal_array)value=Value(0);}
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
  execution.array = language==Language::BASIC?values->array:values->focal_array;
  execution.array_count = language == Language::BASIC ? 385 : 64;
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
bool cache_diagnostics(CacheDiagnostics& out) {
  out={};
#if MK61_OVERLAY_LANGUAGE_VM && MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
  const auto& s=image_cache.statistics();
  out={MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES,ProgramCache::PAYLOAD_CAPACITY,image_cache.used(),
       s.lookups,s.hits,s.misses,s.reservations,s.reservation_failures,s.publications,s.evictions,s.invalidations};
  return true;
#else
  return false;
#endif
}
}  // namespace language_vm
#endif
