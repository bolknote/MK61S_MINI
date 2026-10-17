#include "mk61_app.h"
#include "loadable_module_format.hpp"
#include "language_workspace.hpp"
#include <algorithm>
#include <map>
#include <memory>
#include <vector>
#define main language_vm_ram_cache_tests
#include "language_vm_image_cache_self_test.cpp"
#undef main

namespace {
struct File {
  uint16_t id,parent;uint8_t type;
  std::string name;
  std::vector<uint8_t> bytes;
};
std::map<uint16_t,File> files;
std::unique_ptr<language_workspace::Lease> buffer;
uint16_t next_id=1000;
unsigned writes,cache_reads,cache_prefix_reads,cache_full_reads,cache_reserved_reads,source_reads;
unsigned compiler_reads;
bool fail_source_read,partial_source_read,change_on_source_read;
bool driver_present=true,fail_buffer,fail_read,fail_write,change_on_cache_read;
unsigned corrupt_cache_read;
bool change_before_store;
bool change_before_start;
bool resize_after_reservation;
uint32_t cache_phase;
bool single_flow;
void* root_context;
unsigned cached_starts;
constexpr uint16_t DRIVER=901, DIRECTORY=900, BASIC=101, FOCAL=102;

void export_file(const File& file,mk61_service_file& out) {
  out={};out.id=file.id;out.parent=file.parent;out.type=file.type;
  out.size=(uint32_t)file.bytes.size();
  assert(file.name.size()<sizeof(out.name));
  memcpy(out.name,file.name.c_str(),file.name.size()+1);
}
File source_file(uint16_t id) {
  const bool focal=id==201;
  const char* text=focal?"1.10 S A=A+2\n1.20 PRINT \"RAM FOCAL\"\n1.30 EXIT\n":program(id);
  File file={id,0,(uint8_t)(focal?MK61_SERVICE_FILE_FOCAL:MK61_SERVICE_FILE_BASIC),
      "source",{}};
  if(text)file.bytes.assign(text,text+strlen(text));
  return file;
}
bool file(uint16_t id,File& out) {
  auto found=files.find(id);
  if(found!=files.end()){out=found->second;return true;}
  if(id<=7 || id==201){out=source_file(id);return !out.bytes.empty();}
  return false;
}
uint32_t read(uint32_t id,uint32_t offset,uint8_t* output,uint32_t length) {
  File e;
  if(fail_read || !file((uint16_t)id,e) || offset>e.bytes.size() || length>e.bytes.size()-offset)return 0;
  memcpy(output,e.bytes.data()+offset,length);
  if(e.parent==DIRECTORY && id!=DRIVER) {
    ++cache_reads;
    assert(!offset);
    if(length==e.bytes.size()) {
      ++cache_full_reads;
      if(cache_phase==file_cache::LOAD_RESERVED)++cache_reserved_reads;
    } else {
      assert(length==file_cache::PROBE_BYTES);++cache_prefix_reads;
    }
    if(corrupt_cache_read && --corrupt_cache_read==0 && length)output[length-1]^=1;
    if(change_on_cache_read){++revision;change_on_cache_read=false;}
  } else if(id<=7 || id==201) {
    ++source_reads;
    if(change_on_source_read){++revision;change_on_source_read=false;}
    if(fail_source_read || partial_source_read) {
      const bool partial=partial_source_read;
      fail_source_read=partial_source_read=false;
      return partial && length?length-1:0;
    }
  } else if(id==BASIC || id==FOCAL)++compiler_reads;
  return length;
}
uint32_t size(uint32_t id) {File e;return file((uint16_t)id,e)?(uint32_t)e.bytes.size():0;}
uint32_t service(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* payload) {
  switch(op) {
    case MK61_SERVICE_CAPABILITIES:return MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_MEMORY;
    case MK61_SERVICE_RESOURCE_READ: {
      if(!a)return revision;
      assert(a==5);
      const auto& span=*(mk61_service_resource*)payload;
      File source;assert(file(span.id,source) && !span.reserved);
      const unsigned chunk=source.bytes.size()<=COMPILER_WORKSPACE_SIZE?source.bytes.size():256;
      assert(span.length<=chunk && span.length<=COMPILER_WORKSPACE_SIZE);
      return span.revision==revision &&
          read(span.id,span.offset,span.output,span.length)==span.length && span.revision==revision;
    }
    case MK61_SERVICE_FILE_COUNT: {
      assert(a==MK61_SERVICE_FILE_APP);return (uint32_t)files.size();
    }
    case MK61_SERVICE_FILE_ENTRY: {
      File e;
      if(a==0) {if(!file((uint16_t)b,e))return 0;}
      else {
        assert(c==MK61_SERVICE_FILE_APP);
        if(b>=files.size())return 0;
        auto it=files.begin();std::advance(it,b);e=it->second;
      }
      export_file(e,*(mk61_service_file*)payload);return 1;
    }
    case MK61_SERVICE_MEMORY_ACQUIRE: {
      assert(a==0 && b==MK61_APP_KIND_LANGUAGE_VM && !buffer);
      auto& lease=*(mk61_service_lease*)payload;
      if(fail_buffer)return 0;
      buffer=std::make_unique<language_workspace::Lease>();
      if(!buffer->acquire(language_workspace::Owner::LANGUAGE_VM,c)){buffer.reset();return 0;}
      lease.data=(uint8_t*)buffer->data();lease.size=buffer->size();lease.fresh=buffer->fresh();return 1;
    }
    case MK61_SERVICE_MEMORY_RELEASE: {
      assert(buffer);buffer.reset();((mk61_service_lease*)payload)->data=nullptr;return 1;
    }
    case MK61_SERVICE_FILE_WRITE: {
      assert(a==DIRECTORY && c==MK61_SERVICE_FILE_APP);
      if(fail_write)return 0;
      auto& write=*(mk61_service_write*)payload;
      const auto id=b==0xFFFF?next_id++:(uint16_t)b;
      files[id]={id,DIRECTORY,MK61_SERVICE_FILE_APP,write.name,
          std::vector<uint8_t>(write.data,write.data+write.size)};
      ++writes;++revision;return 1;
    }
  }
  assert(false);return 0;
}
mk61_app_services services={MK61_APP_SERVICES_MAGIC,MK61_APP_SERVICES_VERSION,
    sizeof(mk61_app_services),nullptr,service,nullptr,nullptr,nullptr};
const void* query(uint32_t id,uint32_t version) {
  assert(id==MK61_APP_SERVICE_COMMON && version==MK61_APP_SERVICES_VERSION);
  return &services;
}
void compiler_file(uint16_t id) {
  loadable_module::Header h={};h.kind=id==BASIC?Kind::TINYBASIC:Kind::FOCAL;
  // The cache reads only the validated compiler header, never this test payload.
  h.compression=loadable_module::Compression::ZX0;
  h.flags=MK61_PORTABLE_APP_FLAG|MK61_APP_RELOCATABLE_FLAG;h.load_address=MK61_PORTABLE_APP_ADDRESS;
  h.image_size=h.memory_size=h.stored_size=h.code_stored_size=4;
  uint8_t data[68]={};data[64]=5;data[65]=0x20;data[66]=0x70;data[67]=0x47;
  h.image_crc32=h.stored_crc32=loadable_module::crc32(data+64,4);
  assert(loadable_module::encode_header(h,sizeof(data),data));
  files[id]={id,0,MK61_SERVICE_FILE_APP,id==BASIC?"BASIC":"FOCAL",{data,data+sizeof(data)}};
}
void invalidate() {++revision;}
uint16_t cache_file(uint16_t source) {
  char name[9];snprintf(name,sizeof(name),"VMC-%04x",source);
  for(const auto& [id,e]:files)if(e.parent==DIRECTORY && e.name==name)return id;
  return 0xFFFF;
}
}
extern "C" {const mk61_app_api* mk61_api;}
namespace portable_system {
bool bind(const mk61_app_api* api,uint32_t,uint32_t){mk61_api=api;return true;}
}
namespace language_vm_file_cache_test {
void before_step(mk61_app_flow* flow) {
  cache_phase=flow->current.phase;
  if(resize_after_reservation && flow->current.kind==MK61_APP_KIND_APPLICATION &&
     flow->current.phase==file_cache::LOAD_RESERVED) {
    const auto& stage=((CompilerContext*)flow->context)->compile;
    files[stage.file_id].bytes.push_back(0);resize_after_reservation=false;
  }
  if(single_flow) {
    assert(flow->context_size==sizeof(CompilerContext));
    if(!root_context)root_context=flow->context;
    assert(flow->context==root_context); // No nested FlowContext/run_flow.
  }
  if(flow->current.kind==MK61_APP_KIND_APPLICATION && flow->current.phase==file_cache::START_LOADED)
    ++cached_starts;
  if(change_before_start && flow->current.kind==MK61_APP_KIND_APPLICATION &&
     flow->current.phase==file_cache::START_LOADED) {
    ++revision;change_before_start=false;
  }
  if(change_before_store && flow->current.phase==file_cache::STORE_COMPILED) {
    ++revision;change_before_store=false;
  }
}
bool resolve(const char* path,mk61_service_file& out) {
  const uint16_t id=!strcmp(path,file_cache::DRIVER_PATH)?DRIVER:
      !strcmp(path,"/System/BASIC.APP")?BASIC:FOCAL;
  auto found=files.find(id);
  if(found==files.end())return false;
  export_file(found->second,out);return true;
}
}
namespace language_vm_test {
uint16_t file_cache_driver(){return driver_present?DRIVER:0xFFFF;}
}

int main() {
  mk61_app_api api={};api.magic=MK61_APP_API_MAGIC;api.version=MK61_APP_API_VERSION;
  api.struct_size=sizeof(api);api.file_read=read;api.file_size=size;api.query_service=query;
  assert(mk61_app_initialize(&api,123,MK61_APP_KIND_APPLICATION)==0);
  compiler_file(BASIC);compiler_file(FOCAL);
  files[DRIVER]={DRIVER,DIRECTORY,MK61_SERVICE_FILE_APP,"VMSTORE",{1}};
  assert(prepare_image_cache());
  execute(1);assert(compiles==1 && writes==1 && array[1]==2);
  assert(!source_reads && compiler_reads==1); // No source scan/header read for an absent VMC.
  const auto initial_resets=state_resets;
  const auto initial_evictions=evictions;
  const auto initial_prefix_reads=cache_prefix_reads,initial_full_reads=cache_full_reads;
  const auto initial_reserved_reads=cache_reserved_reads;
  single_flow=true;invalidate();execute(1);single_flow=false;root_context=nullptr;
  assert(compiles==1 && writes==1 && array[1]==4 && cached_starts==1);
  assert(cache_prefix_reads==initial_prefix_reads+1 && cache_full_reads==initial_full_reads+1 &&
      cache_reserved_reads==initial_reserved_reads+1); // Exactly one full read, after reserve.
  assert(state_resets==initial_resets+1); // One reset, in the original flow.
  assert(evictions==initial_evictions); // Keep VMSTORE through START_LOADED.
  const auto before_reads=source_reads;
  execute(1);assert(compiles==1 && source_reads==before_reads && array[1]==6);
  program1="10 READ @(0)\n20 @(1)=@(1)+@(0)\n30 DATA 5\n40 END\n";
  invalidate();execute(1);assert(compiles==2 && writes==2 && array[1]==11);
  invalidate();execute(1);assert(compiles==2 && writes==2 && array[1]==16);
  // Missing driver and optional buffer exhaustion never prevent execution.
  driver_present=false;invalidate();execute(2);assert(compiles==3);
  driver_present=true;fail_buffer=true;invalidate();execute(2);assert(compiles==4);
  fail_buffer=false;invalidate();execute(2);assert(compiles==5 && cache_file(2)!=0xFFFF);
  // Corruption falls back but does not overwrite an unrecognised file.
  auto& damaged=files[cache_file(2)].bytes;damaged.back()^=1;
  const unsigned before_writes=writes;
  invalidate();execute(2);assert(compiles==6 && writes==before_writes);
  // A user file with a coincident cache-like name is preserved too.
  files[next_id]={next_id,DIRECTORY,MK61_SERVICE_FILE_APP,"VMC-0004",{1,2,3}};++next_id;
  const unsigned c0=compiles;
  input_text="3";invalidate();execute(4);assert(compiles==c0+1 && writes==before_writes);
  files.erase(cache_file(4));invalidate();execute(4);assert(writes==before_writes+1);
  const unsigned input_compiles=compiles;
  single_flow=true;invalidate();execute(4);single_flow=false;root_context=nullptr;
  assert(compiles==input_compiles);
  cancel_input=true;single_flow=true;invalidate();execute(4,1,2);single_flow=false;root_context=nullptr;
  assert(compiles==input_compiles);cancel_input=false;
  // The source/media epoch may change while a cache record is being read.
  change_on_cache_read=true;invalidate();execute(1);assert(compiles==input_compiles+1);
  // Replacing the compiler invalidates a cache even with unchanged source.
  auto& compiler_bytes=files[BASIC].bytes;
  loadable_module::Header compiler_header;
  assert(loadable_module::decode_header(compiler_bytes.data(),(uint32_t)compiler_bytes.size(),
      compiler_header)==loadable_module::HeaderStatus::OK);
  ++compiler_header.image_crc32;
  assert(loadable_module::encode_header(compiler_header,(uint32_t)compiler_bytes.size(),compiler_bytes.data()));
  const unsigned old_compiles=compiles,old_writes=writes,old_source_reads=source_reads;
  invalidate();execute(1);
  if(compiles!=old_compiles+1 || writes!=old_writes+1)
    fprintf(stderr,"compiler replacement: compiles %u -> %u, writes %u -> %u\n",old_compiles,compiles,old_writes,writes);
  assert(compiles==old_compiles+1 && writes==old_writes+1);
  assert(source_reads==old_source_reads); // Incompatible compiler rejected before source CRC.
  invalidate();execute(1);assert(compiles==old_compiles+1 && writes==old_writes+1);
  // A read fault after reservation must roll back BUILDING before compiling.
  const unsigned before_reserved_fault=compiles;
  const unsigned before_reserved_reads=cache_reserved_reads;
  corrupt_cache_read=2;invalidate();execute(1);
  assert(compiles==before_reserved_fault+1 && !corrupt_cache_read &&
      cache_reserved_reads==before_reserved_reads+1); // Second read is now prefix -> full.
  invalidate();execute(1);assert(compiles==before_reserved_fault+1);
  // Neither a checked header/key prefix nor an unverified payload may publish
  // malformed data. Header/key reject before reserve; payload rejects after it.
  auto& record=files[cache_file(1)].bytes;
  const auto valid_record=record;
  const uint8_t key_magic[]={'V','M','C','1'};
  const auto key_at=std::search(record.begin()+64,record.end(),std::begin(key_magic),std::end(key_magic));
  assert(key_at!=record.end());
  const unsigned key_offset=(unsigned)(key_at-record.begin());
  for(const unsigned at:{60U,key_offset+4,key_offset+8,(unsigned)record.size()-1}) {
    record[at]^=1;
    const unsigned before=compiles,full=cache_reserved_reads,written=writes,reads=source_reads;
    invalidate();execute(1);
    assert(compiles==before+1 && writes==written &&
        cache_reserved_reads==full+(at==valid_record.size()-1?1U:0U));
    assert(source_reads==reads+((at==key_offset+8 || at==valid_record.size()-1)?1U:0U));
    record=valid_record;
  }
  // Check exact size again after host reserve even if a broken storage backend
  // fails to advance its revision when changing the file.
  const unsigned before_resized=compiles,before_resized_reads=cache_reserved_reads;
  resize_after_reservation=true;invalidate();execute(1);
  assert(!resize_after_reservation && compiles==before_resized+1 &&
      cache_reserved_reads==before_resized_reads);
  record=valid_record;invalidate();execute(1);assert(compiles==before_resized+1);
  // Valid outer C6/key CRCs cannot stand in for the executable VM verifier.
  const auto word=[](const uint8_t* p){return(uint16_t)(p[0]|((uint16_t)p[1]<<8));};
  const auto* plain=valid_record.data()+key_offset;
  file_cache::Key valid_key={};
  memcpy(&valid_key.compiler_crc,plain+4,4);memcpy(&valid_key.source_crc,plain+8,4);
  valid_key.source_id=word(plain+12);valid_key.source_size=word(plain+14);
  valid_key.language=(Language)plain[20];
  const uint16_t vm_size=word(plain+16);
  std::vector<uint8_t> invalid_vm(plain+file_cache::KEY_BYTES,plain+file_cache::KEY_BYTES+vm_size);
  invalid_vm[0]^=1;
  record.resize(MAX_MODULE+128);uint16_t invalid_length=0;
  assert(file_cache::pack(valid_key,invalid_vm.data(),vm_size,record.data(),
      (uint16_t)record.size(),invalid_length));record.resize(invalid_length);
  const uint8_t* ignored_image=nullptr;uint16_t ignored_size=0;
  assert(file_cache::view(valid_key,record.data(),invalid_length,ignored_image,ignored_size));
  const unsigned before_invalid_vm=compiles,before_invalid_reads=cache_reserved_reads;
  invalidate();execute(1);
  assert(compiles==before_invalid_vm+1 && cache_reserved_reads==before_invalid_reads+1);
  record=valid_record;invalidate();execute(1);assert(compiles==before_invalid_vm+1);
  // Recheck after HOST committed the workspace, not only during file reads.
  const unsigned before_committed_race=compiles;
  change_before_start=true;invalidate();execute(1);
  assert(!change_before_start && compiles==before_committed_race+1);
  invalidate();execute(1);assert(compiles==before_committed_race+1);
  uint32_t result=99;
  assert(invoke_resident(Language::FOCAL,Command::FOCAL_RUN_ID,201,0,result)==RuntimeStatus::OK && result==0);
  const auto focal_compiles=compiles;
  invalidate();assert(invoke_resident(Language::FOCAL,Command::FOCAL_RUN_ID,201,0,result)==RuntimeStatus::OK && result==0);
  assert(compiles==focal_compiles && variables[0]==4);
  // Filesystem failure on first population is optional, never a RUN failure.
  fail_write=true;invalidate();execute(5,1,4);assert(cache_file(5)==0xFFFF);fail_write=false;
  const unsigned before_raced_write=writes;
  change_before_store=true;invalidate();execute(6);
  assert(!change_before_store && writes==before_raced_write && cache_file(6)==0xFFFF);
  // The already-owned prefix is the only source/codec buffer. A source that
  // fits gets one read; one byte over the bound keeps 256-byte paging. Check
  // the full 16-bit source range without changing VM/APP/workspace budgets.
  const char* saved_program=program1;
  for(const unsigned length:{4175U,4176U,4177U,65534U}) {
    const std::string head="10 REM ",tail="\n20 END\n";
    const std::string source=head+std::string(length-head.size()-tail.size(),'x')+tail;
    program1=source.c_str();
    const auto before=compiles,reads=source_reads;
    invalidate();execute(1);
    assert(compiles==before+1 && source_reads==reads); // Source-size mismatch is also a prefilter.
    const auto loaded=source_reads;
    invalidate();execute(1);
    assert(compiles==before+1 && source_reads==loaded+(length<=COMPILER_WORKSPACE_SIZE?1U:(length+255)/256));
    if(length==4176) {
      for(unsigned fault=0;fault<3;++fault) {
        fail_source_read=fault==0;partial_source_read=fault==1;change_on_source_read=fault==2;
        const auto compiled=compiles,started=cached_starts;
        invalidate();execute(1);
        assert(compiles==compiled+1 && cached_starts==started);
        assert(!fail_source_read && !partial_source_read && !change_on_source_read);
      }
    }
  }
  program1=saved_program;invalidate();
#if MK61_ENABLE_USB_SCREEN
  {
    shared_memory::Lease session(shared_memory::Arena::OVERLAY,shared_memory::Owner::USB_SCREEN,2793);
    assert(session.ok());memset(session.data(),0xB7,session.size());usb_session=&session;
    invalidate();execute(1);check_usb();
    const unsigned c=compiles;
    invalidate();execute(1);check_usb();assert(compiles==c);
    usb_session=nullptr;
  }
#endif
  // Quota exhaustion does not evict or overwrite any preexisting file.
  for(unsigned i=0;i<file_cache::MAX_FILES;++i) {
    char name[12];snprintf(name,sizeof(name),"VMC-x%04u",i);
    files[next_id]={next_id,DIRECTORY,MK61_SERVICE_FILE_APP,name,{1}};++next_id;
  }
  const unsigned quota_writes=writes;
  invalidate();execute(6);assert(writes==quota_writes && cache_file(6)==0xFFFF);
  assert(!buffer && shared_memory::validate_invariants());
  puts("VM file cache flow: cold/store, warm/load, source/compiler key, corruption, collision, epoch race, quota, OOM, INPUT/ESC, FOCAL, USB PASS");
}
