// Real C9/NOR + real resident selection/lifetimes. Only native APP delivery
// and UI callbacks are modeled; the compiler, verifier, VM and caches are real.
#define main program_store_unused_main
#include "program_store_self_test.cpp"
#undef main
#include "language_vm_resident.hpp"
#include "language_compiler_flow.hpp"
#include "language_flash_program.hpp"
#include "app_flow.hpp"
#include "workspace_swap.hpp"
#include "keyboard.h"
namespace {
using namespace language_vm;
using namespace loadable_module;
unsigned compiled,prepared_calls,normal_calls,input_calls,finished;
bool expanded=true,cancelled=false,legacy=false,fail_vm=false,edit=false;
uint32_t edited_position;
double refs[20];
Language compiling;
bool background(void*){return !cancelled;}
bool reference(void*,bool write,uint8_t index,double& value){if(write)refs[index]=value;else value=refs[index];return true;}
bool event(void*,Event,const char*,uint16_t,double&){return true;}
const Services services={nullptr,background,nullptr,nullptr,nullptr,reference,event,true,true};
uint32_t execute(OverlayRequest* p) {
  if(fail_vm)return 0;
  assert(execution_compatible(p));auto& r=*p->execution;auto& s=*p->state;
  flash::Reader reader(r.paged);View v;assert(validated_view(*p,v,r.paged.read?&reader:nullptr));
  if(p->action==OverlayAction::ABORT){r.result.error=s.cancelled?Error::STOPPED:Error::IO;return 1;}
  const Bindings b={r.variables,r.array,s.array_count,s.stack,MAX_STACK};
  if(p->action==OverlayAction::EXPRESSION){r.result=evaluate_input(v,s,b,services);return 1;}
  const bool resume=p->action==OverlayAction::RESUME;
  if(!resume) {
    if(r.image && r.storage && !r.storage->read)++prepared_calls;else ++normal_calls;
    assert(!s.control.sp && !s.control.call_count && !s.control.loop_count && !s.output[0]);
  } else s.stack[s.control.sp++]=s.input_value;
  r.result=run(v,s.control,b,services,0,resume);s.steps+=r.result.steps;r.result.steps=s.steps;
  if(r.result.error==Error::YIELDED) {
    assert(Op(v.byte(r.result.pc))==Op::READ_INPUT);
    s.prompt_offset=r.result.pc+3;s.prompt_length=flash::word(v.at(r.result.pc+1));
    if(r.paged.read)assert(v.read(s.prompt_offset,s.prompt,s.prompt_length));
  }
  return 1;
}
uint32_t input(InputRequest* r) {
  ++input_calls;
  if(cancelled){r->result=InputResult::CANCELLED;return 1;}
  if(r->language==Language::FOCAL){r->result=InputResult::VALUE;r->value=3;return 1;}
  const auto e=compile_expression(Language::BASIC,"1+2",3,r->image,r->capacity);
  assert(e.error==Error::NONE);r->result=InputResult::EXPRESSION;r->image_size=e.size;return 1;
}
uint32_t finish(OverlayRequest* p) {
  ++finished;
  if(edit && p->execution->result.error!=Error::NONE) {
    p->execution->error_column=7;p->execution->edit_requested=1;
  }
  return 1;
}
uint32_t frontend(Command command,uint32_t id,uint32_t position,Request* r,uint32_t& result) {
  if(command==Command::TINYBASIC_EDIT_ID){edited_position=position;result=1;return MK61_FLOW_OK;}
  assert(r && r->storage);program_store::Entry file;assert(program_store::entry_by_id(uint16_t(id),file));
  std::string text(file.data_len,'\0');uint16_t n=0;
  assert(program_store::read_source_range_id(file.id,0,(uint8_t*)text.data(),uint16_t(text.size()),&n) && n==text.size());
  shared_memory::Lease source;
  assert(workspace_swap::acquire(compiling==Language::BASIC?shared_memory::Owner::TINYBASIC:shared_memory::Owner::FOCAL,COMPILER_WORKSPACE_SIZE,
      workspace_swap::AcquireMode::REQUIRED,source));
  source::Reader reader(text.data(),uint16_t(text.size()));
  r->source_id=file.id;r->mode=command==Command::TINYBASIC_RUN_ID_STATUS?uint8_t(position):0;
  r->compiled=compile_flash_source(compiling,reader,*r->storage,expanded,source.data()+FLASH_FRONTEND_BYTES);
  if(r->compiled.error!=Error::NONE)fprintf(stderr,"resident fixture compile: file=%s error=%s line=%u offset=%u bytes=%zu\n",file.name,error_name(r->compiled.error),r->compiled.line,r->compiled.source_offset,text.size());
  assert(r->compiled.error==Error::NONE);r->run_requested=1;++compiled;result=1;return MK61_FLOW_OK;
}
uint16_t put(Language language,const char* name,const std::string& text,uint16_t id=program_store::INVALID_ID) {
  assert(program_store::write_file(program_store::ROOT_ID,id,language==Language::BASIC?ProgramType::TINYBASIC:ProgramType::FOCAL,
      name,(const uint8_t*)text.data(),uint16_t(text.size()),&id));return id;
}
void run_file(Language language,uint16_t id,uint32_t expected) {
  uint32_t result;
  const auto status=invoke_resident(language,language==Language::BASIC?Command::TINYBASIC_RUN_ID_STATUS:Command::FOCAL_RUN_ID,id,1,result);
  if(status!=RuntimeStatus::OK || result!=expected)
    fprintf(stderr,"cached call failed: language=%u id=%u status=%u result=%u expected=%u compiled=%u normal=%u INPUT=%u\n",
        unsigned(language),unsigned(id),unsigned(status),unsigned(result),unsigned(expected),compiled,normal_calls,input_calls);
  assert(status==RuntimeStatus::OK && result==expected);
  assert(shared_memory::validate_invariants() && !shared_memory::workspace_partitioned());
}
}
void idle_main_process(){}
namespace kbd {isize scan(){return 0;}}
namespace core_61 {bool expanded_program_is_on(){return expanded;}}
namespace resident_firmware {u32 build_id(){return 12345;}}
i32 program_store_text_font_activate(){return 0;}
namespace loadable_module {RuntimeStatus evict_cached(){return RuntimeStatus::OK;}}
namespace language_vm_test {
loadable_module::RuntimeStatus overlay(loadable_module::Kind kind,loadable_module::Command command,void* payload,uint32_t& result) {
  using namespace loadable_module;
  if(command==Command::APP_FLOW_INFO){result=legacy?0:MK61_APP_FLOW_MAGIC;return RuntimeStatus::OK;}
  assert(command==Command::APP_FLOW_STEP);auto* step=(mk61_app_flow*)payload;
  if(kind==Kind::FOCAL || kind==Kind::TINYBASIC){compiling=kind==Kind::FOCAL?Language::FOCAL:Language::BASIC;result=flow_compile(step,frontend);}
  else if(kind==Kind::LANGUAGE_VM)result=flow_vm(step,execute);
  else {assert(kind==Kind::LANGUAGE_INPUT);result=flow_input(step,validate_execution,input,finish);}
  return RuntimeStatus::OK;
}
}
int main() {
  fresh(512U*1024U);uint16_t system;
  assert(program_store::create_directory(program_store::ROOT_ID,"System",program_store::INVALID_ID,&system));
  const uint8_t payload[]={1,2,3,4};
  for(const char* name:{"BASIC","FOCAL","LANGVM","LANGIN"})
    assert(program_store::write_file(system,program_store::INVALID_ID,ProgramType::APP,name,payload,sizeof(payload)));
  const uint16_t basic=put(Language::BASIC,"BASICRUN","10 A=A+1;.RA=A;END\n");
  const uint16_t focal=put(Language::FOCAL,"FOCALRUN","1.1 S A=A+2;S .RB=A;E\n");
  run_file(Language::BASIC,basic,1);run_file(Language::FOCAL,focal,0);
  // The other initial compile changed C9: one additional run rebinds the
  // first metadata record to the final mutation epoch.
  run_file(Language::BASIC,basic,1);
  run_file(Language::FOCAL,focal,0);
  const auto cold_compiled=compiled;const auto begin_fast=prepared_calls;
  SPIFlash::resetOperationCounts();
  for(unsigned i=0;i<20;++i){run_file(Language::BASIC,basic,1);run_file(Language::FOCAL,focal,0);}
  fprintf(stderr,"warm C9: compiled=%u/%u reads=%u writes=%u separate_calls=%u\n",compiled,cold_compiled,SPIFlash::readOperations(),SPIFlash::mutationOperations(),prepared_calls-begin_fast);
  assert(compiled==cold_compiled && SPIFlash::readOperations()==0 && SPIFlash::mutationOperations()==0);
  (void)begin_fast;
  assert(prepared_calls==0);
  assert(refs[14]==22 && refs[15]==44);
  put(Language::BASIC,"BASICRUN","10 A=A+10;.RA=A;END\n",basic);run_file(Language::BASIC,basic,1);assert(refs[14]==32);
  run_file(Language::BASIC,basic,1);assert(refs[14]==42);
  const uint16_t ask=put(Language::BASIC,"ASK","10 INPUT B;A=A+B;.RA=A;END\n");
  run_file(Language::BASIC,ask,1);run_file(Language::BASIC,ask,1);assert(input_calls==2 && refs[14]==48);
  const auto before_input=input_calls;cancelled=true;run_file(Language::BASIC,ask,2);cancelled=false;
  assert(input_calls==before_input); // cancellation at the first service poll
  run_file(Language::BASIC,ask,1);assert(refs[14]==51);
  uint32_t result;legacy=true;
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID_STATUS,ask,1,result)==RuntimeStatus::INCOMPATIBLE_FIRMWARE);
  legacy=false;fail_vm=true;
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID_STATUS,ask,1,result)==RuntimeStatus::CORRUPT_MODULE);
  fail_vm=false;run_file(Language::BASIC,ask,1);assert(refs[14]==54);
  // Dynamic line lookup must come from the pinned raw image, not from an
  // APP-local object or a filesystem adapter that has gone out of scope.
  const uint16_t branch=put(Language::BASIC,"BRANCH","10 L=30;GOTO L\n20 .RC=99;END\n30 .RC=7;END\n");
  run_file(Language::BASIC,branch,1);run_file(Language::BASIC,branch,1);assert(refs[16]==7);
  const uint16_t error=put(Language::BASIC,"ERROR","10 A=1/0;END\n");
  run_file(Language::BASIC,error,4);run_file(Language::BASIC,error,4);
  edit=true;
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID,error,0,result)==RuntimeStatus::OK && result==0);
  assert(edited_position==((10U<<16)|7));edit=false;
  run_file(Language::BASIC,error,4); // record a new noninteractive error location
  put(Language::BASIC,"ERROR","10 A=2/0;END\n",error);
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_EDIT_ID,error,0,result)==RuntimeStatus::OK);
  assert(edited_position==STALE_SOURCE_POSITION);
  const uint16_t focal_input=put(Language::FOCAL,"FOCINPUT","1.1 A B;S .RD=B;E\n");
  run_file(Language::FOCAL,focal_input,0);run_file(Language::FOCAL,focal_input,0);assert(refs[17]==3);
  std::string large="1 GOTO 30000\n";
  for(unsigned i=20;i<720;++i)large+=std::to_string(i)+" A=A+1\n";
  large+="30000 .RC=11;END\n";
  const uint16_t paged=put(Language::BASIC,"PAGED",large);
  const auto before_paged=normal_calls;const auto fast_paged=prepared_calls;
  run_file(Language::BASIC,paged,1);run_file(Language::BASIC,paged,1);
  assert(normal_calls==before_paged+2 && prepared_calls==fast_paged && refs[16]==11);
  const uint16_t damaged=put(Language::BASIC,"DAMAGED","10 .RA=73;END\n");
  run_file(Language::BASIC,damaged,1);
  char path[128];program_store::Entry manifest,image_page;
  snprintf(path,sizeof(path),"/System/VMCache/Pages/%04X/Manifest.bin",unsigned(damaged));
  assert(storage_path::resolve_file(program_store::ROOT_ID,path,ProgramType::MK61_BINARY,manifest)==storage_path::Status::OK);
  snprintf(path,sizeof(path),"/System/VMCache/Pages/%04X/Image0/00000000.bin",unsigned(damaged));
  assert(storage_path::resolve_file(program_store::ROOT_ID,path,ProgramType::MK61_BINARY,image_page)==storage_path::Status::OK);
  uint8_t marker[64],page[flash::WRITE_BYTES];uint16_t copied;
  assert(program_store::read_source_range_id(manifest.id,0,marker,sizeof(marker),&copied) && copied==sizeof(marker));
  assert(program_store::read_source_range_id(image_page.id,0,page,sizeof(page),&copied) && copied==sizeof(page));
  page[7]=marker[16+7]=16; // invalid certificate flags, intact lengths/identity
  flash::dword(marker+60,mk61_crc32::calculate(marker,60));
  assert(program_store::write_file(image_page.parent_id,image_page.id,ProgramType::MK61_BINARY,image_page.name,page,sizeof(page)));
  assert(program_store::write_file(manifest.parent_id,manifest.id,ProgramType::MK61_BINARY,manifest.name,marker,sizeof(marker)));
  for(unsigned retry=0;retry<2;++retry)
    assert(invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID_STATUS,damaged,1,result)==RuntimeStatus::CORRUPT_MODULE);
  run_file(Language::BASIC,basic,1);const auto before_poison=refs[14];
  {
    shared_memory::Lease hold(shared_memory::Arena::WORKSPACE,shared_memory::Owner::LANGUAGE_VM,8192);
    assert(hold.ok() && !hold.fresh());memset(hold.data(),0xD3,COMPILER_WORKSPACE_SIZE);
  }
  shared_memory::reset_statistics();run_file(Language::BASIC,basic,1);
  assert(refs[14]==before_poison+10);
  const auto cleared=shared_memory::snapshot(shared_memory::Arena::WORKSPACE).cleared_bytes;
  assert(cleared==0);
  {
    shared_memory::Lease hold(shared_memory::Arena::WORKSPACE,shared_memory::Owner::LANGUAGE_VM,8192);
    assert(hold.ok());for(unsigned i=0;i<COMPILER_WORKSPACE_SIZE;++i)assert(hold.data()[i]==0);
  }
  printf("Real C9 cached calls: compiled=%u normal=%u separate=%u INPUT=%u finish=%u; warm NOR reads/writes=0, BASIC/FOCAL/epochs/resume/ABI/failures PASS\n",compiled,normal_calls,prepared_calls,input_calls,finished);
}
