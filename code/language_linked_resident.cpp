#include "config.h"
#if defined(MK61_LINKED_VM_POC) && MK61_LINKED_VM_POC
#include "language_linked_program.hpp"
#include "language_vm_resident.hpp"
#include "language_compiler_flow.hpp"
#include "language_flash_cache.hpp"
#include "program_store.hpp"
#include "storage_path.hpp"
#include "tools.hpp"
#include "mk_math.hpp"
#include <new>
extern void idle_main_process(void);

namespace language_vm {
namespace {
using namespace linked;
constexpr unsigned CATALOG_CAPACITY=(COMPILER_WORKSPACE_SIZE-sizeof(ExecutionState)-sizeof(Session))/sizeof(Member);
static_assert(CATALOG_CAPACITY>=25,"linked PoC must fit the unchanged compiler prefix");
struct Context {
  flash::ReadCache& cache;PersistentValues& values;ExecutionState& state;
  Program program;ExecuteRequest execution{};OverlayRequest overlay{};
  Storage storage;
  uint32_t window=UINT32_MAX;
  uint8_t page[flash::WRITE_BYTES];
  const Member* loading=nullptr;
  const Services* services=nullptr;
  Context(flash::ReadCache& a,PersistentValues& b,ExecutionState& c):cache(a),values(b),state(c){}
  bool current() const {return storage.revision==program_store::media_revision();}
  static uint32_t epoch(void*){return program_store::media_revision();}
  static bool poll(void*) {idle_main_process();return true;}
  static bool read(void* raw,uint32_t at,uint8_t* output,uint16_t n) {
    auto& c=*(Context*)raw;
    const auto& s=c.storage;
    if(!c.current() || at>s.size || n>s.size-at)return false;
    while(n) {
      const uint32_t page=at/flash::WRITE_BYTES;
      if(c.window!=page) {
        const uint16_t file=s.files[at/FRAGMENT_BYTES];
        const unsigned chunk=(at%FRAGMENT_BYTES)/flash::WRITE_BYTES;
        if(!c.cache.get(s.revision,file,chunk,c.page)) {
          const uint32_t begin=page*flash::WRITE_BYTES;
          const auto count=uint16_t(s.size-begin<flash::WRITE_BYTES?s.size-begin:flash::WRITE_BYTES);
          uint16_t copied=0;
          if(!program_store::read_source_range_id(file,uint16_t(begin%FRAGMENT_BYTES),c.page,count,&copied) || copied!=count)return false;
          if(count<flash::WRITE_BYTES)memset(c.page+count,0,flash::WRITE_BYTES-count);
          c.cache.put(s.revision,file,chunk,c.page);
        }
        c.window=page;
      }
      const unsigned inside=at%flash::WRITE_BYTES;
      const auto count=uint16_t(n<flash::WRITE_BYTES-inside?n:flash::WRITE_BYTES-inside);
      memcpy(output,c.page+inside,count);at+=count;output+=count;n=uint16_t(n-count);
    }
    return c.current();
  }
  static bool image_read(void* raw,flash::Space space,uint32_t at,uint8_t* output,uint16_t n) {
    auto& c=*(Context*)raw;
    if(space!=flash::IMAGE || !c.loading || at>c.loading->validated.size)return false;
    const uint32_t remaining=c.loading->validated.size-at;
    const auto real=uint16_t(n<remaining?n:remaining);
    if(!read(raw,c.loading->offset+at,output,real))return false;
    if(real<n)memset(output+real,0,n-real);
    return true;
  }
  static bool bind(void* raw,Language language,Bindings& b) {
    auto& c=*(Context*)raw;const bool basic=language==Language::BASIC;
    b={c.values.variables[basic?0:1],basic?c.values.array:c.values.focal_array,
       uint16_t(basic?385:64),c.state.stack,MAX_STACK};return true;
  }
  static bool enter(void* raw,uint32_t,uint16_t,Language language) {
    auto& c=*(Context*)raw;reset_execution_state(c.state);
    c.state.language=language;c.state.array_count=language==Language::BASIC?385:64;
    c.execution.pause_final=0;c.execution.image=nullptr;return true;
  }
  static bool next(void* raw,uint32_t,uint32_t& symbol) {
    auto& c=*(Context*)raw;
    double value;
    // The explicit experiment uses .RE=99 as its external-script return.
    if(!c.services || !c.services->reference || !c.services->reference(c.services->context,false,18,value))return false;
    if(!mk_math::is_finite(value) || value<0 || value>UINT32_MAX || mk_math::floor(value)!=value)return false;
    symbol=value==99?0:uint32_t(value);return true;
  }
  static bool borrow(void* raw,const Member& m,const uint8_t*& image) {
    auto& c=*(Context*)raw;c.loading=&m;
    flash::IO io{};io.context=&c;io.read=image_read;io.service=poll;
    const bool ok=c.cache.borrow(c.storage.revision,uint16_t(0xF000U|m.source_id),m.validated.size,io,image);
    c.loading=nullptr;
    // Reader is an APP-private type. This first PoC deliberately accepts only
    // raw cache loans; no mismatched resident Reader crosses the APP boundary.
    if(!ok || !image)return false;
    c.execution.image=image;c.execution.image_size=m.validated.size;return c.current();
  }
  static void release(void* raw,const uint8_t* image){((Context*)raw)->cache.release(image);}
};
struct Pinned {
  bool active=false;
  ~Pinned() {
    if(active) {
      uint32_t ignored;
      loadable_module::invoke(loadable_module::Kind::LANGUAGE_VM,
          (loadable_module::Command)KERNEL_EXPORT_COMMAND,0,0,0,0,ignored);
      loadable_module::unpin(loadable_module::Kind::LANGUAGE_VM);
    }
  }
};
}
bool linked_poc_run(uint16_t directory,uint8_t* prefix,PersistentValues& values,flash::ReadCache& cache) {
  auto& state=*new(prefix) ExecutionState;
  auto& session=*new(prefix+sizeof(ExecutionState)) Session;
  auto* members=(Member*)(prefix+sizeof(ExecutionState)+sizeof(Session));
  Context c{cache,values,state};
  Input input{};input.paged={&c,Context::read,0};input.epoch=Context::epoch;
  LoadRequest request{sizeof(LoadRequest),LOAD_MAGIC,directory,CATALOG_CAPACITY,
      &c.storage,members,&c.program,input,Context::poll};
  program_store::Entry driver{};
  if(storage_path::resolve_file(program_store::ROOT_ID,file_cache::DRIVER_PATH,
      program_store::ProgramType::APP,driver)!=storage_path::Status::OK)return false;
  uint32_t loaded=0;
  if(loadable_module::run_flow(mk61_app_flow_to(MK61_APP_KIND_APPLICATION,driver.id,LOAD_PHASE),
      &request,sizeof(request),loaded)!=loadable_module::RuntimeStatus::OK || !loaded ||
      request.error!=Error::NONE || !linked::current(c.program))return false;
  c.execution.size=sizeof(c.execution);c.execution.version=REQUEST_VERSION;
  c.overlay={sizeof(c.overlay),REQUEST_VERSION,&c.execution,&state,&members[0].validated,OverlayAction::START,{0,0,0}};
  Pinned pin;
  if(loadable_module::pin(loadable_module::Kind::LANGUAGE_VM)!=loadable_module::RuntimeStatus::OK)return false;
  pin.active=true;uint32_t exported=0;
  if(loadable_module::invoke(loadable_module::Kind::LANGUAGE_VM,
       (loadable_module::Command)KERNEL_EXPORT_COMMAND,uint32_t(uintptr_t(&c.overlay)),0,0,0,exported)!=loadable_module::RuntimeStatus::OK || !exported)return false;
  const auto& api=*(const KernelExport*)(uintptr_t)exported;
  if(api.magic!=KERNEL_EXPORT_MAGIC || !api.kernel || !api.services)return false;
  c.services=api.services;
  if(!start(c.program,session))return false;
  const Host host={&c,Context::bind,Context::enter,Context::next,Context::borrow,Context::release};
  const auto result=execute_with(c.program,session,host,*api.services,api.kernel);
  // INPUT expression/editor swaps need a separate cold handoff. Do not restart
  // or silently discard a yielded continuation in this chess-only experiment.
  return result.status==Status::DONE || (result.status==Status::ERROR && result.run.error==Error::STOPPED);
}
}
#endif
