#include "config.h"
#ifndef MK61_LANGUAGE_VM_CACHE_MIXED
#define MK61_LANGUAGE_VM_CACHE_MIXED 0
#endif
// Absolute ELF metadata lets every bundle frontend select the executor that
// was compiled into this resident, including implicit config.h defaults.
// This symbol occupies no Flash or SRAM and survives LTO/section collection.
#if defined(__arm__)
#if MK61_OVERLAY_LANGUAGE_VM
__asm__(".global mk61_language_vm_mode\n.set mk61_language_vm_mode, 2");
#elif MK61_RESIDENT_LANGUAGE_VM
__asm__(".global mk61_language_vm_mode\n.set mk61_language_vm_mode, 1");
#else
__asm__(".global mk61_language_vm_mode\n.set mk61_language_vm_mode, 0");
#endif
#if MK61_VM_FILE_CACHE && MK61_OVERLAY_LANGUAGE_VM && MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
__asm__(".global mk61_vm_file_cache_enabled\n.set mk61_vm_file_cache_enabled, 1");
#else
__asm__(".global mk61_vm_file_cache_enabled\n.set mk61_vm_file_cache_enabled, 0");
#endif
#endif
#if MK61_RESIDENT_LANGUAGE_VM || MK61_OVERLAY_LANGUAGE_VM
#include <string.h>
#include <new>
#include "language_vm_resident.hpp"
#include "language_vm_flow.hpp"
#include "dwt_profiler.hpp"
#include "language_compiler_flow.hpp"
#include "app_flow_transfer.hpp"
#include "shared_memory.hpp"
#include "native_libc.h"
#include "workspace_swap.hpp"
#if !defined(LANGUAGE_VM_HOST_TEST)
#include "basic_graphics.hpp"
#endif
#if MK61_OVERLAY_LANGUAGE_VM && MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
#include "language_vm_image_cache.hpp"
#if !defined(LANGUAGE_VM_HOST_TEST)
#include "program_store.hpp"
#include "development.hpp"
#if MK61_VM_FILE_CACHE
#include "storage_path.hpp"
#endif
#endif
#endif

#if MK61_FLASH_LANGUAGE_VM
#include "language_flash_store.hpp"
#include "resident_firmware.hpp"
#include "loadable_module_system_app.hpp"
#include "development.hpp"
extern void idle_main_process(void);
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
#if MK61_VM_FILE_CACHE
uint16_t file_cache_driver();
#endif
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
    MK61_LANGUAGE_VM_CACHE_DENSITY ? CachePolicy::REUSE_DENSITY : CachePolicy::LRU,
    MK61_LANGUAGE_VM_CACHE_MIXED != 0>;
#if defined(STM32F411xE)
#define MK61_LAZY_STRING_INNER(x) #x
#define MK61_LAZY_STRING(x) MK61_LAZY_STRING_INNER(x)
#if MK61_USE_NATIVE_LIBC
static_assert(sizeof(ProgramCache) <= MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES,
              "native lazy cache reserve must include all metadata");
__asm__(".global mk61_lazy_vm_cache_bytes\n.set mk61_lazy_vm_cache_bytes, "
        MK61_LAZY_STRING(MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES));
#else
__asm__(".global mk61_lazy_vm_cache_bytes\n.set mk61_lazy_vm_cache_bytes, "
        MK61_LAZY_STRING(MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES) " + 32");
#endif
class LazyProgramCache {
  ProgramCache* value_;
public:
  bool ensure() {
    if(value_) return true;
    void* memory = shared_memory::allocate_retained_buffer(sizeof(ProgramCache));
    if(memory) value_ = new(memory) ProgramCache{};
    return value_ != nullptr;
  }
  ProgramCache::Handle find(ProgramCache::Key key) { return ensure() ? value_->find(key) : ProgramCache::Handle{}; }
#if MK61_LANGUAGE_VM_CACHE_MIXED
  ProgramCache::Handle find(ProgramCache::Key key,ProgramCache::Scratch scratch) { return ensure() ? value_->find(key,scratch) : ProgramCache::Handle{}; }
#endif
  ProgramCache::Handle reserve(ProgramCache::Key key, uint16_t size) { return ensure() ? value_->reserve(key,size) : ProgramCache::Handle{}; }
  void synchronize(uint32_t revision) { if(value_) value_->synchronize(revision); }
  uint8_t* building(ProgramCache::Handle h) { return value_ ? value_->building(h) : nullptr; }
  const uint8_t* image(ProgramCache::Handle h) { return value_ ? value_->image(h) : nullptr; }
  const ValidatedImage* certificate(ProgramCache::Handle h) { return value_ ? value_->certificate(h) : nullptr; }
  bool publish(ProgramCache::Handle h,const ValidatedImage& v) { return value_ && value_->publish(h,v); }
  bool release(ProgramCache::Handle h) { return value_ && value_->release(h); }
  unsigned used() const { return value_ ? value_->used() : 0; }
  const ProgramCache::Statistics& statistics() const { static const ProgramCache::Statistics empty={}; return value_ ? value_->statistics() : empty; }
  ProgramCache::PackingStatistics packing_statistics() const { return value_ ? value_->packing_statistics() : ProgramCache::PackingStatistics{}; }
};
LazyProgramCache image_cache;
#else
ProgramCache image_cache;
#endif
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
                                 shared_memory::capacity(shared_memory::Arena::WORKSPACE),
                                 workspace_swap::AcquireMode::REQUIRED, lease);
}
void initialize(Persistent& state) {
  state.magic = SESSION_MAGIC;
  state.selected[0] = state.selected[1] = 0xFFFF;
  static_assert(offsetof(Persistent,variables)==8 &&
      sizeof(Persistent)==8+(2*26+385+64)*sizeof(Value),
      "persistent numeric region must remain contiguous");
  // All three numeric banks have the same tagged zero representation. Byte
  // copies are legal across their array boundaries; Value* arithmetic is not.
  const Value zero(0);
  auto* bytes=reinterpret_cast<uint8_t*>(&state);
  for(unsigned offset=8;offset<sizeof(state);offset+=sizeof(Value))
    memcpy(bytes+offset,&zero,sizeof(zero));
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
#endif
}  // namespace
#if MK61_OVERLAY_LANGUAGE_VM
namespace {
struct CompilerServices {
  CompilerContext* context;
  app_flow::Transfer* memory;
#if MK61_FLASH_LANGUAGE_VM
  flash::Store* store;
  flash::IO* storage;
#endif
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
  bool cacheable;
  ProgramCache::Handle object;
  ~CompilerServices() {if(object) (void)image_cache.release(object);}
#endif
};
#if MK61_VM_FILE_CACHE && MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
uint16_t file_cache_driver() {
#if defined(LANGUAGE_VM_HOST_TEST)
  return language_vm_test::file_cache_driver();
#else
  program_store::Entry entry={};
  return storage_path::resolve_file(program_store::ROOT_ID,file_cache::DRIVER_PATH,
      program_store::ProgramType::APP,entry)==storage_path::Status::OK?entry.id:0xFFFF;
#endif
}
#endif
loadable_module::RuntimeStatus compiler_memory(void* raw, app_flow::Step& step) {
  auto& binding = *(CompilerServices*)raw;
  if(step.context != binding.context || step.context_size != sizeof(CompilerContext))
    return loadable_module::RuntimeStatus::CORRUPT_MODULE;
#if MK61_FLASH_LANGUAGE_VM
  auto& c=*binding.context;
  if(step.current.phase==app_flow::PUBLISH_IMAGE && c.execution.paged.read) {
    // Publication is a cache optimization. A full disk may prevent the
    // manifest update, while the already-verified private image can run.
    (void)binding.store->publish(c.vm.program_validated);
    mk61_app_flow_next(&step,c.vm.publication.next);return loadable_module::RuntimeStatus::OK;
  }
  if(step.current.phase==app_flow::COMMIT_FLASH_IMAGE && !c.prepared) {
    auto& stage=c.compile;auto& r=c.execution;auto& plan=stage.transfer;
    if(!stage.request.storage || stage.request.compiled.error!=Error::NONE || plan.size!=stage.request.compiled.size)
      return loadable_module::RuntimeStatus::CORRUPT_MODULE;
    const auto status=binding.memory->commit_paged(plan);
    if(status!=loadable_module::RuntimeStatus::OK)return status;
    binding.store->invalidate();
    r={};r.size=sizeof(r);r.version=REQUEST_VERSION;r.storage=binding.storage;
    r.paged=binding.store->input(plan.size);r.image_size=plan.size;
    const bool basic=c.language==Language::BASIC;
    r.variables=stage.values->variables[basic?0:1];r.array=basic?stage.values->array:stage.values->focal_array;
    r.array_count=basic?385:64;r.mode=stage.request.mode;c.cache_target=true;
    mk61_app_flow_next(&step,plan.next);return loadable_module::RuntimeStatus::OK;
  }
#endif
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
#if MK61_VM_FILE_CACHE
  if(step.current.phase==app_flow::DISCARD_CACHE_IMAGE) {
    if(binding.object)(void)image_cache.release(binding.object);
    binding.memory->release_workspace();
    binding.object={};
    mk61_app_flow_return(&step,1,MK61_FLOW_OK);
    return loadable_module::RuntimeStatus::OK;
  }
#endif
  if(step.current.phase==app_flow::PUBLISH_IMAGE) {
    if(!binding.context->prepared || !binding.object) return loadable_module::RuntimeStatus::CORRUPT_MODULE;
    image_cache.synchronize(image_revision());
    if(!image_cache.publish(binding.object,binding.context->vm.program_validated)) return loadable_module::RuntimeStatus::IO_ERROR;
#if MK61_DWT_RUNTIME_DETAIL_SUPPORTED
    dwt_profiler::record_vm_image(binding.context->source_id, binding.context->vm.program_validated.size);
#endif
    binding.context->vm.publication.revision=image_revision();
    mk61_app_flow_next(&step,binding.context->vm.publication.next);
    return loadable_module::RuntimeStatus::OK;
  }
#endif
  if(binding.context->prepared) return loadable_module::RuntimeStatus::CORRUPT_MODULE;
  auto& plan = binding.context->compile.transfer;
#if MK61_VM_FILE_CACHE && MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
  const bool file_request=step.current.phase==app_flow::RESERVE_CACHE_IMAGE;
#else
  constexpr bool file_request=false;
#endif
  if(step.current.phase == app_flow::RESERVE_IMAGE || file_request) {
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
    auto& request=binding.context->compile.request;
    if(binding.cacheable && request.source_id!=0xFFFF && request.resources==ResourceMode::EMBEDDED) {
      const uint32_t revision=image_revision();
      if(request.source_revision==revision)
        binding.object=image_cache.reserve({revision,request.source_id,binding.context->language,0},(uint16_t)plan.size);
      else if(!file_request)return loadable_module::RuntimeStatus::IO_ERROR;
      if(binding.object) {
        plan.image=image_cache.building(binding.object);binding.context->cache_target=true;
        mk61_app_flow_return(&step,1,MK61_FLOW_OK);return loadable_module::RuntimeStatus::OK;
      }
    }
#endif
    if(file_request) {
      // Filesystem hits require a pinned RAM image. With no reservation, let
      // the helper fall back to the compiler, never to transient file data.
      mk61_app_flow_return(&step,1,MK61_FLOW_BUSY);return loadable_module::RuntimeStatus::OK;
    }
    if(plan.size>shared_memory::WORKSPACE_SIZE) return loadable_module::RuntimeStatus::BUSY;
    const auto status = binding.memory->reserve(plan);
    if(status != loadable_module::RuntimeStatus::OK) return status;
    mk61_app_flow_return(&step, 1, MK61_FLOW_OK);
  } else if(step.current.phase == app_flow::COMMIT_IMAGE) {
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
    if(binding.context->cache_target && (!binding.object || plan.image!=image_cache.building(binding.object)))
      return loadable_module::RuntimeStatus::CORRUPT_MODULE;
#endif
#if MK61_VM_FILE_CACHE && MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
    const bool evict=binding.context->compile.file_validated.magic!=VALIDATED_MAGIC;
#else
    constexpr bool evict=true;
#endif
    const auto status = binding.context->cache_target ? binding.memory->retain_image(plan,evict) : binding.memory->commit(plan);
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
#if MK61_FLASH_LANGUAGE_VM
namespace {
uint16_t flash_source(Language language,loadable_module::Command command,uint32_t a,const PersistentValues& values) {
  using C=loadable_module::Command;
  if(command==(language==Language::BASIC?C::TINYBASIC_RUN_INDEX:C::FOCAL_RUN_INDEX))
    return a?0xFFFF:values.selected[language==Language::BASIC?0:1];
  if(command==(language==Language::BASIC?C::TINYBASIC_RUN_NAME:C::FOCAL_RUN_NAME)) {
    if(!a)return 0xFFFF;
    const auto type=language==Language::BASIC?program_store::ProgramType::TINYBASIC:program_store::ProgramType::FOCAL;
    for(int i=0;i<program_store::count(type);++i) {
      program_store::Entry entry;
      if(program_store::entry(type,i,entry) && !strcmp(entry.name,(const char*)(uintptr_t)a))return entry.id;
    }
    return 0xFFFF;
  }
  if(command==C::TINYBASIC_RUN_ID_STATUS || command==(language==Language::BASIC?C::TINYBASIC_RUN_ID:C::FOCAL_RUN_ID))
    return a<=0xFFFF?uint16_t(a):0xFFFF;
  return 0xFFFF;
}
uint32_t flash_fingerprint(Language language) {
  uint32_t crc=0;program_store::Entry entry;
  const loadable_module::Kind kinds[]={language==Language::BASIC?loadable_module::Kind::TINYBASIC:loadable_module::Kind::FOCAL,
    loadable_module::Kind::LANGUAGE_VM,loadable_module::Kind::LANGUAGE_INPUT};
  for(auto kind:kinds) {
    uint32_t stamp;
    if(!loadable_module::find_system_app(kind,entry) || !program_store::content_stamp(entry.id,stamp))return 0;
    crc=(crc<<7)|(crc>>25);crc^=stamp;
  }
  return crc^COMPILER_MAGIC^resident_firmware::build_id();
}
}
#endif
static loadable_module::RuntimeStatus invoke_resident_impl(Language language,
    loadable_module::Command command, uint32_t a, uint32_t b, uint32_t& result,
    uint16_t* edit_id = nullptr, uint32_t* edit_position = nullptr) {
  using namespace loadable_module;
  result = 0;
  if(busy || (language != Language::BASIC && language != Language::FOCAL)) return RuntimeStatus::BUSY;
  struct BusyScope { BusyScope(){ busy=true; } ~BusyScope(){ busy=false; } } busy_scope;
#if !defined(LANGUAGE_VM_HOST_TEST)
  basic_graphics::RunScope graphics_scope;
#endif
  static uint16_t error_id = 0xFFFF, error_line = 0, error_column = 0;
#if MK61_FLASH_LANGUAGE_VM
  static uint32_t error_stamp=0;
#endif
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
  static uint32_t error_revision=0;
#endif
  if(language == Language::BASIC && command == Command::TINYBASIC_EDIT_ID && a == error_id) {
    if(!b) {
#if MK61_FLASH_LANGUAGE_VM
      uint32_t stamp;
      b=program_store::content_stamp(uint16_t(a),stamp) && stamp==error_stamp
          ? (uint32_t(error_line)<<16)|error_column : STALE_SOURCE_POSITION;
#elif MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
      b=error_revision && error_revision!=image_revision()?STALE_SOURCE_POSITION:
          (uint32_t(error_line)<<16)|error_column;
#else
      b=(uint32_t(error_line)<<16)|error_column;
#endif
    }
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
#endif
  // Initialize only the union member used by this launch. A RAM hit never
  // enters the compiler stage; clearing both stages repeats 184 bytes per RUN.
  CompilerContext context;
  context.storage=nullptr;
  context.execution={}; context.source_id=0; context.language=language;
  context.clear_requested=0; context.prepared=false; context.cache_target=false;
  context.cache_driver=0xFFFF;
#if MK61_VM_FILE_CACHE && MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
  context.source_id=source_id;
#endif
#if MK61_FLASH_LANGUAGE_VM
  flash::Store store(&context.compile.request.source_id,flash_fingerprint(language),
      [](){idle_main_process();return true;},partition.tail()-FLASH_CACHE_BYTES);
  auto flash_io=store.io();context.storage=&flash_io;
#endif
  app_flow::Transfer memory(shared_memory::Owner::LANGUAGE_VM);
  CompilerServices services = {&context, &memory
#if MK61_FLASH_LANGUAGE_VM
      ,&store,&flash_io
#endif
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
      ,cacheable,{}
#endif
  };
  auto first=mk61_app_flow_to(language==Language::BASIC?MK61_APP_KIND_TINYBASIC:MK61_APP_KIND_FOCAL,
      MK61_APP_FLOW_SYSTEM_FILE,FLOW_COMPILE_SOURCE);
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
  if(cacheable) {
    ProgramCache::Handle cached;
    {
      MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::VM_CACHE_LOOKUP);
#if MK61_LANGUAGE_VM_CACHE_MIXED
      // Partition protects all BASIC/FOCAL values. No ExecutionState exists
      // in this prefix yet; the same lease will become its owner on a hit.
      auto& prefix=memory.workspace_lease();
      if(!workspace(prefix)) return RuntimeStatus::BUSY;
      cached=image_cache.find({revision,source_id,language,0},
          {prefix.data(),(unsigned)prefix.size()});
      // A miss enters VMSTORE/the compiler, which must acquire this prefix
      // under its own owner. Never retain or loan its live source buffer.
      if(!cached) memory.release_workspace();
#else
      cached=image_cache.find({revision,source_id,language,0});
#endif
    }
#if MK61_DWT_RUNTIME_DETAIL_SUPPORTED
    dwt_profiler::record_vm_cache(source_id, (bool)cached, cached ? image_cache.certificate(cached)->size : 0);
#endif
    if(cached) {
      services.object=cached; // One scoped pin for warm and cold paths alike.
      auto& execution=context.execution;
      const auto* certificate=image_cache.certificate(cached);
      {
        MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::VM_PREPARE);
        values->selected[language==Language::BASIC?0:1] = source_id;
        auto& state=memory.workspace_lease();
#if MK61_LANGUAGE_VM_CACHE_MIXED
        if(!state.ok() && !workspace(state)) return RuntimeStatus::BUSY;
#else
        if(!workspace(state)) return RuntimeStatus::BUSY;
#endif
        execution.size=sizeof(execution); execution.version=REQUEST_VERSION;
        execution.image=image_cache.image(cached); execution.image_size=certificate->size;
        execution.variables=values->variables[language==Language::BASIC?0:1];
        execution.array=language==Language::BASIC?values->array:values->focal_array;
        execution.array_count=language==Language::BASIC?385:64;
        execution.mode=command==Command::TINYBASIC_RUN_ID_STATUS?(uint8_t)b:0;
        auto* continuation=state.as<ExecutionState>();
        continuation->language=language;
        context.vm={};context.vm.magic=FLOW_CONTEXT_MAGIC;
        context.vm.original_command=(uint32_t)command;
        context.vm.program_validated=*certificate;
        context.vm.program={sizeof(OverlayRequest),REQUEST_VERSION,&execution,
            continuation,&context.vm.program_validated,OverlayAction::START,{0,0,0}};
        context.source_id=source_id;context.prepared=true;context.cache_target=true;
        View view;
        if(!validated_view(context.vm.program,view))return RuntimeStatus::CORRUPT_MODULE;
        initialize_validated_state(execution,*certificate,*continuation);
      }
      activate_cached_text_font();
      first=mk61_app_flow_to(MK61_APP_KIND_LANGUAGE_VM,MK61_APP_FLOW_SYSTEM_FILE,FLOW_RUN_PROGRAM);
    }
  }
#endif
  if(!context.prepared) {
    context.compile={};
    context.compile.magic=FLOW_CONTEXT_MAGIC; context.compile.original_command=(uint32_t)command;
    context.compile.values=values; context.compile.command=(uint32_t)command;
    context.compile.argument0=a; context.compile.argument1=b;
  }
#if MK61_FLASH_LANGUAGE_VM
  const uint16_t flash_id=flash_source(language,command,a,*values);
  if(!context.prepared && flash_id!=0xFFFF) {
    context.compile.request.source_id=flash_id;
    ValidatedImage certificate;
    if(store.load(certificate) && certificate.language==language &&
       (!(certificate.flags&2) || language!=Language::FOCAL || core_61::expanded_program_is_on())) {
      auto& stage=context.compile;auto& r=context.execution;auto& plan=stage.transfer;
      stage.request.compiled={Error::NONE,certificate.size,0,0,certificate.stack};
      stage.request.storage=&flash_io;
      plan.size=certificate.size;plan.prefix=sizeof(ExecutionState);
      const auto committed=memory.commit_paged(plan);
      if(committed!=RuntimeStatus::OK)return committed;
      store.invalidate();
      r.size=sizeof(r);r.version=REQUEST_VERSION;r.paged=store.input(certificate.size);r.storage=&flash_io;
      r.variables=values->variables[language==Language::BASIC?0:1];
      r.array=language==Language::BASIC?values->array:values->focal_array;r.array_count=language==Language::BASIC?385:64;
      r.mode=command==Command::TINYBASIC_RUN_ID_STATUS?uint8_t(b):0;
      app_flow::Step step={};step.size=sizeof(step);step.version=MK61_APP_FLOW_VERSION;step.current=first;step.context=&context;step.context_size=sizeof(context);
      if(!prepare_compiled_flow(&step))return RuntimeStatus::CORRUPT_MODULE;
      context.vm.program_validated=certificate;
      View view;if(!validated_view(context.vm.program,view))return RuntimeStatus::CORRUPT_MODULE;
      initialize_validated_state(r,certificate,*context.vm.program.state);
      values->selected[language==Language::BASIC?0:1]=flash_id;
      (void)program_store_text_font_activate();
      first=mk61_app_flow_to(MK61_APP_KIND_LANGUAGE_VM,MK61_APP_FLOW_SYSTEM_FILE,FLOW_RUN_PROGRAM);
    }
  }
#endif
#if MK61_VM_FILE_CACHE && MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
  const uint16_t driver=!context.prepared && cacheable && source_id!=0xFFFF?file_cache_driver():0xFFFF;
  context.cache_driver=driver;
  if(driver!=0xFFFF)first=mk61_app_flow_to(MK61_APP_KIND_APPLICATION,driver,file_cache::TRY_LOAD);
#endif
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
#if MK61_FLASH_LANGUAGE_VM
    error_stamp=store.source_stamp();
#endif
#if MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
    error_revision=revision;
#endif
  }
  if(edit_id && edit_position && language==Language::BASIC && execution.mode==0 &&
     execution.edit_requested && execution.result.line && context.source_id!=0xFFFF) {
    *edit_id=context.source_id;
    *edit_position=
#if MK61_FLASH_LANGUAGE_VM
        [&](){uint32_t stamp;return program_store::content_stamp(context.source_id,stamp) && stamp==store.source_stamp()
          ? (execution.result.line<<16)|execution.error_column : STALE_SOURCE_POSITION;}();
#elif MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
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
#if !defined(LANGUAGE_VM_HOST_TEST)
  basic_graphics::RunScope graphics_scope;
#endif
  static uint16_t basic_error_id = 0xFFFF, basic_error_line = 0, basic_error_column = 0;
  if (language == Language::BASIC && command == Command::TINYBASIC_EDIT_ID && a == basic_error_id) {
    if (!b) b = ((uint32_t)basic_error_line << 16) | basic_error_column;
    basic_error_id = 0xFFFF;
  }
  const unsigned index = language == Language::BASIC ? 0 : 1;
  // The resident-executor experiment retains its original staging layout.
  shared_memory::Lease transfer(shared_memory::Arena::OVERLAY,
                                shared_memory::Owner::LOADABLE_MODULE,
                                sizeof(Persistent)
#if MK61_FLASH_LANGUAGE_VM
                                + FLASH_CACHE_BYTES
#else
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
#if MK61_FLASH_LANGUAGE_VM
  flash::Store store(&request.source_id,COMPILER_MAGIC,[](){idle_main_process();return true;},transfer.data()+sizeof(Persistent));
  auto flash_io=store.io();request.storage=&flash_io;request.capacity=UINT32_MAX;
#else
  request.output = transfer.data() + sizeof(Persistent);
  request.capacity = MAX_IMAGE;
#endif
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
      (!request.storage && request.compiled.size > MAX_IMAGE))
    return RuntimeStatus::CORRUPT_MODULE;
#if MK61_FLASH_LANGUAGE_VM
  const auto unloaded=loadable_module::evict_cached();
  if(unloaded!=RuntimeStatus::OK)return unloaded;
#else
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
#endif
  ExecuteRequest execution = {};
  execution.size = sizeof(execution);
  execution.version = REQUEST_VERSION;
#if MK61_FLASH_LANGUAGE_VM
  execution.paged=store.input(request.compiled.size);execution.storage=&flash_io;
#else
  execution.image = image;
#endif
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
  MK61_RUNTIME_PROFILE_SCOPE(dwt_profiler::Point::VM_INVOKE);
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
bool prepare_image_cache() {
#if MK61_OVERLAY_LANGUAGE_VM && MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES && defined(STM32F411xE)
  return image_cache.ensure();
#else
  return true;
#endif
}
bool cache_diagnostics(CacheDiagnostics& out) {
  out={};
#if MK61_OVERLAY_LANGUAGE_VM && MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES
  const auto& s=image_cache.statistics();
  out={MK61_LANGUAGE_VM_IMAGE_CACHE_BYTES,ProgramCache::PAYLOAD_CAPACITY,image_cache.used(),
       s.lookups,s.hits,s.misses,s.reservations,s.reservation_failures,s.publications,s.evictions,s.invalidations};
#if MK61_LANGUAGE_VM_CACHE_MIXED
  const auto p=image_cache.packing_statistics();
  out.packs=p.packs;out.thaws=p.thaws;out.packed=p.packed;
#endif
  return true;
#else
  return false;
#endif
}
}  // namespace language_vm
#endif
