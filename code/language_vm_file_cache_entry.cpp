// Optional ordinary APP. All file I/O/codec/verifier code remains external;
// the resident merely grants a scoped cache handle and invokes the shared VM.
#if defined(MK61_BUILD_VM_FILE_CACHE_MODULE)
#include "mk61_app.h"
#include "language_compiler_flow.hpp"
#include "language_vm_file_cache.hpp"
#include <string.h>
#if defined(LANGUAGE_VM_HOST_TEST)
namespace portable_system {bool bind(const mk61_app_api*,uint32_t,uint32_t);}
namespace language_vm_file_cache_test {bool resolve(const char*,mk61_service_file&);}
#endif
namespace {
using namespace language_vm;
const mk61_app_services* api;
uint32_t call(uint32_t op,uint32_t a=0,uint32_t b=0,uint32_t c=0,void* p=nullptr) {
  return api->call(op,a,b,c,p);
}
struct Buffer {
  mk61_service_lease lease={};
  Buffer(){(void)call(MK61_SERVICE_MEMORY_ACQUIRE,0,MK61_APP_KIND_LANGUAGE_VM,COMPILER_WORKSPACE_SIZE,&lease);}
  ~Buffer(){if(lease.data)(void)call(MK61_SERVICE_MEMORY_RELEASE,0,0,0,&lease);}
  explicit operator bool()const{return lease.data && lease.size>=COMPILER_WORKSPACE_SIZE;}
};
bool entry(uint16_t id,mk61_service_file& out) {
  return call(MK61_SERVICE_FILE_ENTRY,0,id,0,&out)!=0;
}
bool resolve(const char* path,mk61_service_file& out) {
#if defined(LANGUAGE_VM_HOST_TEST)
  return language_vm_file_cache_test::resolve(path,out);
#else
  return call(MK61_SERVICE_FILE_RESOLVE,0xFFFF,MK61_SERVICE_FILE_APP,(uint32_t)(uintptr_t)path,&out)==0;
#endif
}
void name(uint16_t id,char* out) {
  memcpy(out,"VMC-",4);
  const char hex[]="0123456789abcdef";
  for(unsigned i=0;i<4;++i)out[4+i]=hex[(id>>(12-4*i))&15];
  out[8]=0;
}
bool find(uint16_t parent,const char* name,mk61_service_file& out) {
  const unsigned n=call(MK61_SERVICE_FILE_COUNT,MK61_SERVICE_FILE_APP);
  for(unsigned i=0;i<n;++i) {
    mk61_service_file e={};
    if(call(MK61_SERVICE_FILE_ENTRY,1,i,MK61_SERVICE_FILE_APP,&e) &&
       e.parent==parent && !strcmp(e.name,name)){out=e;return true;}
  }
  return false;
}
bool compiler(Language language,uint8_t* buffer,uint32_t& crc) {
  mk61_service_file file={};
  if(!resolve(language==Language::BASIC?"/System/BASIC.APP":"/System/FOCAL.APP",file) ||
     mk61_api->file_read(file.id,0,buffer,64)!=64)return false;
  loadable_module::Header h;
  const auto kind=language==Language::BASIC?loadable_module::Kind::TINYBASIC:loadable_module::Kind::FOCAL;
  if(loadable_module::decode_header(buffer,file.size,kind,h)!=loadable_module::HeaderStatus::OK)return false;
  // Including the header's own trailing CRC produces a fixed CRC residue!
  // Hash only the checked 60-byte prefix (which includes payload/image CRCs).
  crc=loadable_module::crc32(buffer,60);return true;
}
mk61_app_flow_target frontend(const CompilerContext& c) {
  return mk61_app_flow_to(c.language==Language::BASIC?MK61_APP_KIND_TINYBASIC:MK61_APP_KIND_FOCAL,
      MK61_APP_FLOW_SYSTEM_FILE,FLOW_COMPILE_SOURCE);
}
void miss(mk61_app_flow* flow,CompilerContext& c) {
  c.cache_target=false;
  c.compile.transfer={};
  c.compile.file_validated={};
  mk61_app_flow_next(flow,frontend(c));
}
void discard(mk61_app_flow* flow) {
  mk61_app_flow_call(flow,mk61_app_flow_to(MK61_APP_FLOW_HOST,
      MK61_APP_FLOW_SYSTEM_FILE,app_flow::DISCARD_CACHE_IMAGE),file_cache::AFTER_DISCARD);
}
bool executable(const uint8_t* image,uint16_t bytes,const file_cache::Key& key,View& view) {
  uint32_t source_crc=0;
  if(bytes>=HEADER_SIZE)memcpy(&source_crc,image+16,4);
  return inspect(image,bytes,view)==Error::NONE && !view.expression &&
      view.language==key.language && view.source_size==key.source_size && source_crc==key.source_crc &&
      (!(image[7]&RESOURCE_FLAG) || (image[7]&OWNED_RESOURCE_FLAG));
}
bool quota(uint16_t parent,uint16_t replace,unsigned added) {
  unsigned count=0,total=added;
  const unsigned n=call(MK61_SERVICE_FILE_COUNT,MK61_SERVICE_FILE_APP);
  for(unsigned i=0;i<n;++i) {
    mk61_service_file e={};
    if(call(MK61_SERVICE_FILE_ENTRY,1,i,MK61_SERVICE_FILE_APP,&e) && e.parent==parent &&
       e.id!=replace && !memcmp(e.name,"VMC-",4)){++count;total+=e.size;}
  }
  return count<file_cache::MAX_FILES && total<=file_cache::MAX_TOTAL_BYTES;
}
}
#if !defined(LANGUAGE_VM_HOST_TEST)
extern "C" int main(){return MK61_APP_RUNTIME_ERROR;}
#endif
extern "C" uint32_t mk61_app_initialize(const mk61_app_api* app,uint32_t crc,uint32_t kind) {
  if(!portable_system::bind(app,crc,kind))return MK61_APP_RUNTIME_ERROR;
  api=mk61_app_get_services(app,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_MEMORY);
  return api?0:MK61_APP_RUNTIME_ERROR;
}
extern "C" uint32_t mk61_app_flow_step(mk61_app_flow* flow) {
  if(!api || !mk61_app_flow_compatible(flow) || flow->context_size!=sizeof(CompilerContext))return 0;
  auto& c=*(CompilerContext*)flow->context;
  if(c.compile.magic!=FLOW_CONTEXT_MAGIC || (c.language!=Language::BASIC && c.language!=Language::FOCAL))return 0;
  if(flow->current.phase==file_cache::AFTER_DISCARD) {
    if(c.prepared || flow->status!=MK61_FLOW_OK)return 0;
    miss(flow,c);return 1;
  }
  if(flow->current.phase==file_cache::START_LOADED) {
    if(c.prepared || !c.cache_target || c.compile.file_validated.magic!=VALIDATED_MAGIC)return 0;
    if(c.compile.request.source_revision!=call(MK61_SERVICE_RESOURCE_READ)) {
      discard(flow);return 1;
    }
    // Consume the certificate before prepare switches the compiler/VM union.
    const auto checked=c.compile.file_validated;
    c.cache_driver=0xFFFF; // Publish a file hit without rewriting it.
    if(!prepare_compiled_flow(flow))return 0;
    c.vm.program_validated=checked;
    View view;
    if(!validated_view(c.vm.program,view))return 0;
    initialize_validated_state(c.execution,checked,*c.vm.program.state);
    if(call(MK61_SERVICE_CAPABILITIES)&MK61_SERVICE_CAP_TEXT_FONT)
      (void)call(MK61_SERVICE_TEXT_FONT,MK61_TEXT_FONT_ACTIVATE);
    // Publish through the existing host phase, then tail into the shared VM.
    // No second context or recursive cooperative interpreter is needed.
    mk61_app_flow_next(flow,mk61_app_flow_to(MK61_APP_FLOW_HOST,
        MK61_APP_FLOW_SYSTEM_FILE,app_flow::PUBLISH_IMAGE));return 1;
  }
  Buffer buffer;
  if(flow->current.phase==file_cache::STORE_COMPILED) {
    if(!c.prepared || !execution_compatible(&c.vm.program))return 0;
    auto& p=c.vm.program;
    const auto& r=*p.execution;
    // Only a retained readonly image may share the workspace with the writer.
    // Uncached/transient images keep the established execution fallback.
    if(buffer && c.cache_target && c.source_id!=0xFFFF &&
       c.vm.file_cache_revision==call(MK61_SERVICE_RESOURCE_READ) &&
       (!(p.validated->flags&RESOURCE_FLAG) || (p.validated->flags&OWNED_RESOURCE_FLAG)) &&
       r.image_size+128<=buffer.lease.size) {
      mk61_service_file driver={},old={};char filename[9];name(c.source_id,filename);
      file_cache::Key key={};key.source_id=c.source_id;key.source_size=p.validated->source_size;key.language=c.language;
      memcpy(&key.source_crc,r.image+16,4);
      uint16_t length=0;
      const bool located=resolve(file_cache::DRIVER_PATH,driver);
      const bool existing=located && find((uint16_t)driver.parent,filename,old);
      const bool replaceable=!existing || (old.size<=buffer.lease.size &&
          mk61_api->file_read(old.id,0,buffer.lease.data,old.size)==old.size &&
          file_cache::owned(c.source_id,c.language,buffer.lease.data,(uint16_t)old.size));
      if(located && replaceable && compiler(c.language,buffer.lease.data,key.compiler_crc) &&
         file_cache::pack(key,r.image,(uint16_t)r.image_size,buffer.lease.data,
             (uint16_t)buffer.lease.size,length)) {
        if(quota((uint16_t)driver.parent,existing?(uint16_t)old.id:0xFFFF,length) &&
           c.vm.file_cache_revision==call(MK61_SERVICE_RESOURCE_READ)) {
          mk61_service_write write={filename,buffer.lease.data,length,0xFFFF};
          (void)call(MK61_SERVICE_FILE_WRITE,driver.parent,existing?old.id:0xFFFF,
              MK61_SERVICE_FILE_APP,&write);
        }
      }
      // The source/codec buffer borrowed the continuation prefix before START.
      initialize_validated_state(r,*p.validated,*p.state);
    }
    mk61_app_flow_next(flow,mk61_app_flow_to(MK61_APP_KIND_LANGUAGE_VM,
        MK61_APP_FLOW_SYSTEM_FILE,FLOW_RUN_PROGRAM));return 1;
  }
  if(c.prepared)return 0;
  auto& stage=c.compile;
  if(flow->current.phase==file_cache::TRY_LOAD) {
    mk61_service_file source={},driver={},cache={};char filename[9];name(c.source_id,filename);
    const uint32_t revision=call(MK61_SERVICE_RESOURCE_READ);
    stage.file_validated={};
    if(!buffer || c.source_id==0xFFFF || !entry(c.source_id,source) || source.kind || !source.size ||
       source.size>source::MAX_SIZE ||
       source.type!=(c.language==Language::BASIC?MK61_SERVICE_FILE_BASIC:MK61_SERVICE_FILE_FOCAL)) {
      miss(flow,c);return 1;
    }
    uint32_t source_crc=0xFFFFFFFFU;
    for(unsigned at=0;at<source.size;) {
      const unsigned n=source.size-at<256?source.size-at:256;
      const mk61_service_resource span={revision,(uint16_t)source.id,(uint16_t)at,
          buffer.lease.data,(uint16_t)n,0};
      if(!call(MK61_SERVICE_RESOURCE_READ,5,0,0,(void*)&span)) {miss(flow,c);return 1;}
      for(unsigned i=0;i<n;++i) {
        source_crc^=buffer.lease.data[i];
        for(unsigned bit=0;bit<8;++bit)source_crc=(source_crc>>1)^(0xEDB88320U & (0U-(source_crc&1U)));
      }
      at+=n;
    }
    if(call(MK61_SERVICE_RESOURCE_READ)!=revision) {miss(flow,c);return 1;}
    stage.file_key={0,~source_crc,c.source_id,
        (uint16_t)source.size,c.language};
    if(!compiler(c.language,buffer.lease.data,stage.file_key.compiler_crc) ||
       !resolve(file_cache::DRIVER_PATH,driver) || !find((uint16_t)driver.parent,filename,cache) ||
       cache.size>buffer.lease.size || cache.size<file_cache::PROBE_BYTES ||
       mk61_api->file_read(cache.id,0,buffer.lease.data,file_cache::PROBE_BYTES)!=file_cache::PROBE_BYTES) {
      miss(flow,c);return 1;
    }
    uint16_t bytes=0;
    if(!file_cache::probe(stage.file_key,buffer.lease.data,file_cache::PROBE_BYTES,(uint16_t)cache.size,bytes) ||
       call(MK61_SERVICE_RESOURCE_READ)!=revision){miss(flow,c);return 1;}
    stage.request={};stage.request.size=sizeof(Request);stage.request.version=REQUEST_VERSION;
    stage.request.source_id=c.source_id;stage.request.source_revision=revision;
    stage.request.resources=ResourceMode::EMBEDDED;stage.request.language=(uint8_t)c.language;
    stage.request.compiled.size=bytes;stage.request.compiled.error=Error::NONE;
    stage.file_id=(uint16_t)cache.id;
    stage.file_reserved=(uint16_t)cache.size;
    stage.transfer.size=bytes;stage.transfer.prefix=sizeof(ExecutionState);
    mk61_app_flow_call(flow,mk61_app_flow_to(MK61_APP_FLOW_HOST,
        MK61_APP_FLOW_SYSTEM_FILE,app_flow::RESERVE_CACHE_IMAGE),file_cache::LOAD_RESERVED);
    return 1;
  }
  if(flow->current.phase!=file_cache::LOAD_RESERVED)return 0;
  if(flow->status!=MK61_FLOW_OK || !stage.transfer.image || !buffer) {
    if(flow->status==MK61_FLOW_OK)discard(flow);
    else miss(flow,c);
    return 1;
  }
  const uint32_t file_size=mk61_api->file_size(stage.file_id);
  const uint8_t* image=nullptr;uint16_t bytes=0;View view={};
  if(file_size!=stage.file_reserved || file_size>buffer.lease.size ||
     mk61_api->file_read(stage.file_id,0,buffer.lease.data,file_size)!=file_size ||
     !file_cache::view(stage.file_key,buffer.lease.data,(uint16_t)file_size,image,bytes) ||
     bytes!=stage.transfer.size || !executable(image,bytes,stage.file_key,view) ||
     call(MK61_SERVICE_RESOURCE_READ)!=stage.request.source_revision) {
    discard(flow);return 1;
  }
  memcpy(stage.transfer.image,image,bytes);
  stage.file_validated={VALIDATED_MAGIC,view.size,view.code,view.source_size,view.end,
      (uint8_t)view.lines,view.stack,(uint8_t)((view.requires_rf?2:0)|(image[7]&12)),view.language};
  stage.values->selected[c.language==Language::BASIC?0:1]=c.source_id;
  stage.transfer.next=mk61_app_flow_to(MK61_APP_KIND_APPLICATION,
      flow->current.file_id,file_cache::START_LOADED);
  c.execution={};c.execution.size=sizeof(ExecuteRequest);c.execution.version=REQUEST_VERSION;
  c.execution.variables=stage.values->variables[c.language==Language::BASIC?0:1];
  c.execution.array=c.language==Language::BASIC?stage.values->array:stage.values->focal_array;
  c.execution.array_count=c.language==Language::BASIC?385:64;
  c.execution.mode=stage.original_command==(uint32_t)loadable_module::Command::TINYBASIC_RUN_ID_STATUS
      ?(uint8_t)stage.argument1:0;
  mk61_app_flow_next(flow,mk61_app_flow_to(MK61_APP_FLOW_HOST,
      MK61_APP_FLOW_SYSTEM_FILE,app_flow::COMMIT_IMAGE));return 1;
}
#endif
