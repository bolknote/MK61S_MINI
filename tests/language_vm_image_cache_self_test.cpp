#include "language_vm_resident.hpp"
#include "language_vm_image_cache.hpp"
#include "language_vm_flow.hpp"
#include "language_compiler_flow.hpp"
#include "language_resources.hpp"
#include "shared_memory.hpp"
#include "workspace_swap.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

using namespace language_vm;
using namespace loadable_module;
namespace {
uint32_t revision=1;
unsigned compiles,validations,finishes,swaps,activations;
unsigned state_resets;
uint32_t selected_id,selected_mode;
Kind cached=(Kind)0;
Value* array;
const char* input_text="4";
bool cancel_input;
bool change_revision_on_input;
unsigned resource_reads;
unsigned edits;
uint32_t edit_position;
bool edit_after_error;
bool change_revision_on_validate;
#if MK61_ENABLE_USB_SCREEN
shared_memory::Lease* usb_session;
#endif
void check_usb() {
#if MK61_ENABLE_USB_SCREEN
  if(!usb_session || !usb_session->ok()) return;
  assert(shared_memory::active_owner(shared_memory::Arena::OVERLAY)==shared_memory::Owner::USB_SCREEN);
  for(size_t i=0;i<usb_session->size();++i) assert(usb_session->data()[i]==0xB7);
#endif
}
std::string output,last_prompt;
Value* variables;
const char* program1="10 READ @(0)\n20 @(1)=@(1)+@(0)\n30 DATA 2\n40 END\n";
const char* program2="10 @(1)=@(1)*3\n20 END\n";
const char* program(uint32_t id) {
  if(id==1)return program1;
  if(id==2)return program2;
  if(id==4)return "10 INPUT @(0)\n20 @(1)=@(1)+@(0)\n30 END\n";
  if(id==5)return "10 @(1)=1/0\n20 END\n";
  if(id==6)return "10 PRINT 'RAM RESOURCE';'RAM RESOURCE'\n20 INPUT 'PROMPT',@(0)\n30 @(1)=@(1)+@(0)\n";
  if(id==7)return "10 INPUT A\n20 A=1/0\n";
  return "10 @(1)=7\n20 END\n";
}
void select(Kind kind) {check_usb();if(cached!=kind){++swaps;cached=kind;}}
}
namespace language_vm {
void language_vm_test_state_reset(ExecutionState&) { ++state_resets; }
}
namespace loadable_module {
RuntimeStatus evict_cached(){cached=(Kind)0;return RuntimeStatus::OK;}
}
namespace language_vm_test {
uint32_t media_revision(){return revision;}
uint16_t resolve_name(Language,uint32_t id){return (uint16_t)id;}
void activate_text_font(){++activations;}
RuntimeStatus frontend(Kind kind,Command command,uint32_t a,uint32_t b,Request* r,uint32_t& result) {
  select(kind);
  if(command==Command::LANGUAGE_COMPILER_INFO){result=COMPILER_MAGIC;return RuntimeStatus::OK;}
  if(command==Command::TINYBASIC_EDIT_ID) {
    ++edits;edit_position=b;r->run_requested=0;result=1;return RuntimeStatus::OK;
  }
  shared_memory::Lease workspace;
  assert(workspace_swap::acquire(kind==Kind::FOCAL?shared_memory::Owner::FOCAL:shared_memory::Owner::TINYBASIC,COMPILER_WORKSPACE_SIZE,
                                workspace_swap::AcquireMode::REQUIRED,workspace));
  if(command!=Command::LANGUAGE_COMPILER_EMIT){selected_id=a;selected_mode=b;}
  const Language language=kind==Kind::FOCAL?Language::FOCAL:Language::BASIC;
  const char* source=language==Language::FOCAL ? "1.10 S A=A+2\n1.20 PRINT \"RAM FOCAL\"\n1.30 EXIT\n" : program(selected_id);
  if(command!=Command::LANGUAGE_COMPILER_EMIT)++compiles;
  if(!source) {r->run_requested=0;result=4;return RuntimeStatus::OK;}
  const ResourceSource resource={(uint16_t)selected_id,revision,r->resources};
  r->compiled=compile(language,source,(uint16_t)strlen(source),r->output,(uint16_t)r->capacity,true,&resource);
  r->source_id=(uint16_t)selected_id;r->run_requested=r->compiled.error==Error::NONE;r->mode=(uint8_t)selected_mode;
  r->source_revision=revision;
  r->language=(uint8_t)language;r->clear_requested=selected_id==3;
  result=r->run_requested?1:4;return RuntimeStatus::OK;
}
uint32_t compiler_frontend(Command command,uint32_t a,uint32_t b,Request* r,uint32_t& result) {
  return (uint32_t)frontend(r->language==(uint8_t)Language::FOCAL?Kind::FOCAL:Kind::TINYBASIC,command,a,b,r,result);
}
uint32_t validate(OverlayRequest* p) {
  ++validations;
  const uint32_t result=validate_execution(p);
  if(change_revision_on_validate) {++revision;change_revision_on_validate=false;}
  return result;
}
uint32_t finish(OverlayRequest* p) {
  ++finishes;
  if(p->state->cancelled) p->execution->result.error=Error::STOPPED;
  if(edit_after_error && p->execution->mode==0 && p->execution->result.error!=Error::NONE)
    p->execution->edit_requested=1;
  return 1;
}
uint32_t input(InputRequest* r) {
  check_usb();
  last_prompt.assign(r->prompt,r->prompt_length);
  assert(!r->resource_image); // No source read even while the hot APP is gone.
  if(change_revision_on_input) {++revision;change_revision_on_input=false;}
  if(cancel_input) { r->result=InputResult::CANCELLED; return 1; }
  const auto compiled=compile_expression(Language::BASIC,input_text,
      (uint16_t)strlen(input_text),r->image,r->capacity);
  assert(compiled.error==Error::NONE);
  r->image_size=compiled.size;r->result=InputResult::EXPRESSION;
  return 1;
}
bool event(void*,Event event,const char* text,uint16_t length,double&) {
  if(event==Event::RESOURCE_TEXT || event==Event::RESOURCE_INPUT) {++resource_reads;return false;}
  if(event==Event::TEXT) output.append(text,length);
  return true;
}
uint32_t execute_image(OverlayRequest* p) {
  check_usb();
  View v;assert(validated_view(*p,v));
  if(p->execution->array) array=p->execution->array;
  variables=p->execution->variables;
  Bindings bindings={p->execution->variables,array,p->state->array_count,p->state->stack,MAX_STACK};
  Services services={};services.yield_input=true;services.event=event;
  auto& state=*p->state;
  auto& execution=*p->execution;
  if(p->action==OverlayAction::START) {
    assert(!state.cancelled && !state.normal_stop && state.failure==Error::NONE);
    assert(!state.steps && !state.row && !state.width && !state.output_cursor && !state.output[0]);
    assert(!state.control.sp && !state.control.call_count && !state.control.loop_count);
    assert(state.input_value.representation()==0);
  }
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
      if((Op)v.bytes[pc]==Op::INPUT_RESOURCE) {
        state.prompt_offset=(uint16_t)(v.end+resource_word(v.bytes+pc+1));
        state.prompt_length=resource_word(v.bytes+state.prompt_offset);
        if(v.bytes[7]&OWNED_RESOURCE_FLAG) state.prompt_offset+=2;
      }
    }
  }
  return 1;
}
RuntimeStatus overlay(Kind kind,Command command,void* payload,uint32_t& result) {
  select(kind);
  if(command==Command::APP_FLOW_INFO){result=MK61_APP_FLOW_MAGIC;return RuntimeStatus::OK;}
  assert(command==Command::APP_FLOW_STEP);
  if(kind==Kind::TINYBASIC || kind==Kind::FOCAL) {
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
  const unsigned initial_resets=state_resets;
  for(unsigned i=0;i<20;++i)execute(1);
  assert(state_resets==initial_resets+20); // Exactly one complete reset per warm RUN.
  assert(array[1]==42 && compiles==1 && validations==1 && swaps==initial_swaps && activations==20);
  uint32_t explicit_result=0;
  for(auto command:{Command::TINYBASIC_RUN_ID,Command::TINYBASIC_RUN_NAME,Command::TINYBASIC_RUN_INDEX}) {
    assert(invoke_resident(Language::BASIC,command,command==Command::TINYBASIC_RUN_INDEX?0:1,0,explicit_result)==RuntimeStatus::OK);
    assert(explicit_result==1 && compiles==1 && validations==1);
  }
  assert(array[1]==48);
  execute(2);assert(array[1]==144);
  execute(1);assert(array[1]==146 && compiles==2 && validations==2);
  program1="10 READ @(0)\n20 @(1)=@(1)+@(0)\n30 DATA 5\n40 END\n";
  ++revision;execute(1);assert(array[1]==151 && compiles==3 && validations==3);
  const unsigned before_interactive=finishes;
  execute(1,0);assert(array[1]==156 && compiles==3 && finishes==before_interactive+1);
  execute(3);assert(array[1]==7);execute(3);assert(array[1]==7 && compiles==4);
  execute(4);assert(array[1]==11 && compiles==5);
  input_text="6";execute(4);assert(array[1]==17 && compiles==5);
  cancel_input=true;execute(4,1,2);assert(array[1]==17 && compiles==5);
  cancel_input=false;input_text="3";execute(4);assert(array[1]==20 && compiles==5);
  execute(5,1,4);execute(5,1,4);assert(compiles==6);
  const unsigned before_text=compiles;
  output.clear();input_text="2";execute(6);assert(last_prompt=="PROMPT" && output=="RAM RESOURCERAM RESOURCE");
  output.clear();change_revision_on_input=true;execute(6);
  assert(compiles==before_text+1 && !resource_reads && output=="RAM RESOURCERAM RESOURCE");
  execute(6);assert(compiles==before_text+2); // Next RUN sees the changed revision.
  execute(7,0,4);
  const unsigned before_editor=compiles;
  change_revision_on_input=edit_after_error=true;
  execute(7,0,4);
  assert(compiles==before_editor && edits==1 && edit_position==STALE_SOURCE_POSITION);
  edit_after_error=false;
  // A changed source during cold verification cannot publish a candidate.
  const unsigned before_building=compiles;
  change_revision_on_validate=true;uint32_t building_result=0;
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID_STATUS,2,1,building_result)==RuntimeStatus::IO_ERROR);
  assert(compiles==before_building+1);
  execute(2);assert(compiles==before_building+2);
  const unsigned before_focal=compiles;uint32_t focal_result=99;
  for(unsigned i=0;i<2;++i) {
    assert(invoke_resident(Language::FOCAL,Command::FOCAL_RUN_ID,1,0,focal_result)==RuntimeStatus::OK && focal_result==0);
    assert(variables[0]==2*(i+1));
  }
  assert(compiles==before_focal+1 && !resource_reads); // Same inode, different language key.
  assert(invoke_resident(Language::FOCAL,Command::FOCAL_RUN_INDEX,0,0,focal_result)==RuntimeStatus::OK);
  assert(compiles==before_focal+1 && variables[0]==6);
  assert(invoke_resident(Language::FOCAL,Command::FOCAL_RUN_NAME,1,0,focal_result)==RuntimeStatus::OK);
  assert(compiles==before_focal+1 && variables[0]==8);
  // Deleted/bad source must not fall back to an older READY image. Reusing
  // the same inode after a new revision must execute the replacement.
  const Value retained=array[1];
  program2=nullptr;++revision;execute(2,1,4);assert(array[1]==retained);
  program2="10 BROKEN STATEMENT\n";++revision;execute(2,1,4);assert(array[1]==retained);
  program2="10 @(1)=9\n";++revision;execute(2);assert(array[1]==9);
#if MK61_ENABLE_USB_SCREEN
  {
    shared_memory::Lease session(shared_memory::Arena::OVERLAY,shared_memory::Owner::USB_SCREEN,2793);
    assert(session.ok());memset(session.data(),0xB7,session.size());usb_session=&session;
    ++revision;execute(6);check_usb();
    const unsigned usb_compiles=compiles;
    execute(6);assert(compiles==usb_compiles);check_usb();
    cancel_input=true;execute(6,1,2);cancel_input=false;check_usb();
    change_revision_on_input=true;execute(6);check_usb();
    assert(compiles==usb_compiles);
    execute(6);assert(compiles==usb_compiles+1);check_usb();
    assert(shared_memory::validate_invariants());usb_session=nullptr;
  }
#endif
  ImageCache<256,2> small;
  static_assert(sizeof(small)<=256,"cache metadata outside its budget");
  ValidatedImage cert={VALIDATED_MAGIC,32,32,4,32,0,1,0,Language::BASIC};
  auto one=small.reserve({1,1,Language::BASIC,0},32);
  assert(one);memset(small.building(one),1,32);assert(small.publish(one,cert));assert(small.release(one));
  auto two=small.reserve({1,2,Language::BASIC,0},32);
  assert(two);memset(small.building(two),2,32);assert(small.publish(two,cert));assert(small.release(two));
  one=small.find({1,1,Language::BASIC,0});assert(one);
  const auto* pinned=small.image(one);
  auto three=small.reserve({1,3,Language::BASIC,0},32);
  assert(three && small.image(one)==pinned && pinned[0]==1);
  memset(small.building(three),3,32);assert(small.publish(three,cert));assert(small.release(three));
  assert(!small.find({1,2,Language::BASIC,0}));assert(small.image(one)[0]==1);
  small.synchronize(2);assert(small.image(one)==pinned && pinned[0]==1);
  assert(!small.find({2,1,Language::BASIC,0}));assert(small.release(one));assert(small.used()==0);
  auto bad=small.reserve({2,4,Language::BASIC,0},32);
  cert.flags=RESOURCE_FLAG;assert(!small.publish(bad,cert));assert(small.release(bad));
  CacheDiagnostics diagnostic={};assert(cache_diagnostics(diagnostic));
  assert(diagnostic.budget==24576 && diagnostic.payload<diagnostic.budget && diagnostic.publications);
  assert(diagnostic.hits>20 && diagnostic.invalidations && !resource_reads);
  std::puts("language_vm_image_cache_self_test: invalidation, eviction policy, values, DATA, INPUT/cancel, stale editor, BUILDING rollback and no APP swaps PASS");
}
