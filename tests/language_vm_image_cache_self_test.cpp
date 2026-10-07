#include "language_vm_resident.hpp"
#include "language_vm_image_cache.hpp"
#include "language_vm_flow.hpp"
#include "language_compiler_flow.hpp"
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
const char* input_text="4";
bool cancel_input;
const char* program1="10 READ @(0)\n20 @(1)=@(1)+@(0)\n30 DATA 2\n40 END\n";
const char* program(uint32_t id) {
  if(id==1)return program1;
  if(id==2)return "10 @(1)=@(1)*3\n20 END\n";
  if(id==4)return "10 INPUT @(0)\n20 @(1)=@(1)+@(0)\n30 END\n";
  if(id==5)return "10 @(1)=1/0\n20 END\n";
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
uint32_t compiler_frontend(Command command,uint32_t a,uint32_t b,Request* r,uint32_t& result) {
  return (uint32_t)frontend(Kind::TINYBASIC,command,a,b,r,result);
}
uint32_t validate(OverlayRequest* p) {++validations;return validate_execution(p);}
uint32_t finish(OverlayRequest* p) {
  ++finishes;
  if(p->state->cancelled) p->execution->result.error=Error::STOPPED;
  return 1;
}
uint32_t input(InputRequest* r) {
  if(cancel_input) { r->result=InputResult::CANCELLED; return 1; }
  const auto compiled=compile_expression(Language::BASIC,input_text,
      (uint16_t)strlen(input_text),r->image,r->capacity);
  assert(compiled.error==Error::NONE);
  r->image_size=compiled.size;r->result=InputResult::EXPRESSION;
  return 1;
}
uint32_t execute_image(OverlayRequest* p) {
  View v;assert(validated_view(*p,v));
  array=p->execution->array;
  Bindings bindings={p->execution->variables,array,p->state->array_count,p->state->stack,MAX_STACK};
  Services services={};services.yield_input=true;
  auto& state=*p->state;
  auto& execution=*p->execution;
  if(p->action==OverlayAction::EXPRESSION)
    execution.result=evaluate_input(v,state,bindings,services);
  else if(p->action==OverlayAction::ABORT) execution.result.error=Error::STOPPED;
  else {
    const bool resume=p->action==OverlayAction::RESUME;
    if(resume) state.stack[state.control.sp++]=state.input_value;
    execution.result=run(v,state.control,bindings,services,0,resume);
    if(execution.result.error==Error::YIELDED) {
      const auto pc=execution.result.pc;
      state.prompt_offset=pc+3;
      state.prompt_length=(uint16_t)(v.bytes[pc+1]|((uint16_t)v.bytes[pc+2]<<8));
    }
  }
  return 1;
}
RuntimeStatus overlay(Kind kind,Command command,void* payload,uint32_t& result) {
  select(kind);
  if(command==Command::APP_FLOW_INFO){result=MK61_APP_FLOW_MAGIC;return RuntimeStatus::OK;}
  assert(command==Command::APP_FLOW_STEP);
  if(kind==Kind::TINYBASIC) {
    result=flow_compile((mk61_app_flow*)payload,compiler_frontend);
    return RuntimeStatus::OK;
  }
  result=kind==Kind::LANGUAGE_VM ? flow_vm((mk61_app_flow*)payload,execute_image)
                               : flow_input((mk61_app_flow*)payload,validate,input,finish);
  return RuntimeStatus::OK;
}
}
void execute(uint16_t id,uint32_t mode=1,uint32_t expected=1) {
  uint32_t result=0;
  auto status=invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID_STATUS,id,mode,result);
  if(status!=RuntimeStatus::OK)std::fprintf(stderr,"id %u status %u, compiles %u, validations %u\n",id,(unsigned)status,compiles,validations);
  assert(status==RuntimeStatus::OK);
  assert(result==expected); // COMPLETED=1, STOPPED=2, runtime error=4.
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
  execute(4);assert(array[1]==11 && compiles==7);
  input_text="6";execute(4);assert(array[1]==17 && compiles==7);
  cancel_input=true;execute(4,1,2);assert(array[1]==17 && compiles==7);
  cancel_input=false;input_text="3";execute(4);assert(array[1]==20 && compiles==7);
  execute(5,1,4);execute(5,1,4);assert(compiles==9);
  ImageCache<64,2> small;
  ValidatedImage cert={VALIDATED_MAGIC,16,16,4,16,0,1,0,Language::BASIC};
  uint8_t a[16],b[16],c[16];memset(a,1,16);memset(b,2,16);memset(c,3,16);
  assert(small.store(1,1,a,cert)&&small.store(2,1,b,cert));
  assert(small.find(1,1));assert(small.store(3,1,c,cert));
  assert(!small.find(2,1));auto* e=small.find(1,1);assert(e&&small.image(*e)[0]==1);
  e=small.find(3,1);assert(e&&small.image(*e)[0]==3);
  assert(!small.find(1,2)&&small.used()==0);
  cert.flags=1;assert(!small.store(4,2,a,cert));
  std::puts("language_vm_image_cache_self_test: source invalidation, LRU, values, DATA, cached INPUT/cancel, errors and no APP swaps PASS");
}
