#include "language_vm_resident.hpp"
#include "language_vm_image_cache.hpp"
#include "shared_memory.hpp"
#include "workspace_swap.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace language_vm;
using namespace loadable_module;
namespace {
uint32_t revision=1;
unsigned compiles,validations,finishes,swaps,activations;
uint32_t selected_id,selected_mode;
Kind cached=(Kind)0;
double* array;
const char* program1="10 READ @(0)\n20 @(1)=@(1)+@(0)\n30 DATA 2\n40 END\n";
const char* program(uint32_t id) {
  if(id==1)return program1;
  if(id==2)return "10 @(1)=@(1)*3\n20 END\n";
  return "10 @(1)=7\n20 END\n";
}
void select(Kind kind) {if(cached!=kind){++swaps;cached=kind;}}
}
namespace loadable_module {
RuntimeStatus evict_cached(){cached=(Kind)0;return RuntimeStatus::OK;}
}
namespace language_vm_test {
uint32_t media_revision(){return revision;}
void activate_text_font(){++activations;}
RuntimeStatus frontend(Kind kind,Command command,uint32_t a,uint32_t b,Request* r,uint32_t& result) {
  select(kind);
  if(command==Command::LANGUAGE_COMPILER_INFO){result=COMPILER_MAGIC;return RuntimeStatus::OK;}
  shared_memory::Lease workspace;
  assert(workspace_swap::acquire(shared_memory::Owner::TINYBASIC,COMPILER_WORKSPACE_SIZE,
                                workspace_swap::AcquireMode::REQUIRED,workspace));
  if(command!=Command::LANGUAGE_COMPILER_EMIT){selected_id=a;selected_mode=b;}
  const char* source=program(selected_id);
  r->compiled=compile(Language::BASIC,source,(uint16_t)strlen(source),r->output,(uint16_t)r->capacity);
  assert(r->compiled.error==Error::NONE);
  r->source_id=(uint16_t)selected_id;r->run_requested=1;r->mode=(uint8_t)selected_mode;
  r->language=(uint8_t)Language::BASIC;r->clear_requested=selected_id==3;
  if(command!=Command::LANGUAGE_COMPILER_EMIT)++compiles;
  result=1;return RuntimeStatus::OK;
}
RuntimeStatus overlay(Kind kind,Command command,void* payload,uint32_t& result) {
  select(kind);
  if(command==Command::LANGUAGE_VM_INFO){result=kind==Kind::LANGUAGE_VM?OVERLAY_MAGIC:INPUT_MAGIC;return RuntimeStatus::OK;}
  auto& p=*(OverlayRequest*)payload;
  result=1;
  if(command==Command::LANGUAGE_VM_VALIDATE){++validations;result=validate_execution(&p);return RuntimeStatus::OK;}
  if(command==Command::LANGUAGE_VM_FINISH){++finishes;return RuntimeStatus::OK;}
  assert(command==Command::LANGUAGE_VM_RUN);
  View v;assert(validated_view(p,v));
  array=p.execution->array;
  Bindings bindings={p.execution->variables,array,p.state->array_count,p.state->stack,MAX_STACK};
  Services services={};
  p.execution->result=run(v,p.state->control,bindings,services);
  return RuntimeStatus::OK;
}
}
void execute(uint16_t id,uint32_t mode=1) {
  uint32_t result=0;
  auto status=invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID_STATUS,id,mode,result);
  if(status!=RuntimeStatus::OK)std::fprintf(stderr,"id %u status %u, compiles %u, validations %u\n",id,(unsigned)status,compiles,validations);
  assert(status==RuntimeStatus::OK);
  assert(result==1); // TinyBasicRunStatus::COMPLETED reserves zero for old APPs.
}
int main() {
  execute(1);assert(array[1]==2 && compiles==1 && validations==1 && finishes==0);
  const unsigned initial_swaps=swaps;
  for(unsigned i=0;i<20;++i)execute(1);
  assert(array[1]==42 && compiles==1 && validations==1 && swaps==initial_swaps && activations==20);
  execute(2);assert(array[1]==126);
  execute(1);assert(array[1]==128 && compiles==2 && validations==2);
  program1="10 READ @(0)\n20 @(1)=@(1)+@(0)\n30 DATA 5\n40 END\n";
  ++revision;execute(1);assert(array[1]==133 && compiles==3 && validations==3);
  execute(1,0);assert(array[1]==138 && compiles==4 && finishes==1);
  execute(3);assert(array[1]==7);execute(3);assert(array[1]==7 && compiles==6);
  ImageCache<64,2> small;
  ValidatedImage cert={VALIDATED_MAGIC,16,16,0,4,1,0,Language::BASIC,0};
  uint8_t a[16],b[16],c[16];memset(a,1,16);memset(b,2,16);memset(c,3,16);
  assert(small.store(1,1,a,cert)&&small.store(2,1,b,cert));
  assert(small.find(1,1));assert(small.store(3,1,c,cert));
  assert(!small.find(2,1));auto* e=small.find(1,1);assert(e&&small.image(*e)[0]==1);
  e=small.find(3,1);assert(e&&small.image(*e)[0]==3);
  assert(!small.find(1,2)&&small.used()==0);
  cert.flags=1;assert(!small.store(4,2,a,cert));
  std::puts("language_vm_image_cache_self_test: source invalidation, LRU, values, DATA cursor, clear and no APP swaps PASS");
}
