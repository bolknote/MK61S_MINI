#include "language_vm_resident.hpp"
#include "shared_memory.hpp"
#include "workspace_swap.hpp"
#include <assert.h>
#include <stdio.h>
#include <string.h>

namespace {
bool legacy,evicted,fail;
const char* source;
unsigned executions,frontend_calls;
uint16_t inode=42;
}
namespace loadable_module {
RuntimeStatus evict_cached() { evicted=true;return RuntimeStatus::OK; }
}
namespace language_vm_test {
loadable_module::RuntimeStatus frontend(loadable_module::Kind kind,
    loadable_module::Command command,uint32_t a,uint32_t,
    language_vm::Request* request,uint32_t& result) {
  using namespace loadable_module;using namespace language_vm;
  ++frontend_calls;
  if(command==Command::LANGUAGE_COMPILER_INFO) {
    result=legacy?0:COMPILER_MAGIC;return RuntimeStatus::OK;
  }
  evicted=false;
  shared_memory::Lease scratch;
  const auto owner=kind==Kind::TINYBASIC?shared_memory::Owner::TINYBASIC:shared_memory::Owner::FOCAL;
  assert(workspace_swap::acquire(owner,8192,workspace_swap::AcquireMode::REQUIRED,scratch));
  memset(scratch.data(),0xA5,scratch.size());
  if(fail)return RuntimeStatus::IO_ERROR;
  if(command==Command::TINYBASIC_MENU_SELECT) {
    request->clear_requested=1;result=1;return RuntimeStatus::OK;
  }
  assert(a==inode);
  const Language language=kind==Kind::TINYBASIC?Language::BASIC:Language::FOCAL;
  request->compiled=compile(language,source,(uint16_t)strlen(source),request->output,(uint16_t)request->capacity);
  assert(request->compiled.error==Error::NONE);
  request->run_requested=1;request->source_id=inode;request->language=(uint8_t)language;
  request->mode=1;result=1;return RuntimeStatus::OK;
}
}
namespace language_vm {
bool execute_resident(ExecuteRequest& request) {
  assert(evicted);++executions;
  assert(shared_memory::active_owner(shared_memory::Arena::OVERLAY)==shared_memory::Owner::NONE);
  View view;assert(inspect(request.image,(uint16_t)request.image_size,view)==Error::NONE);
  State state={};double values[MAX_STACK];state.variables=request.variables;
  state.array=request.array;state.array_count=(uint16_t)request.array_count;
  state.stack=values;state.stack_capacity=MAX_STACK;
  Services services={};
  request.result=run(view,state,services,10000);assert(request.result.error==Error::NONE);
  return true;
}
}
int main() {
  using namespace language_vm;using namespace loadable_module;
  uint32_t result=0;
  {
    shared_memory::Lease temporary(shared_memory::Arena::OVERLAY,
        shared_memory::Owner::LOADABLE_MODULE,512);
    auto* pointer=temporary.data();assert(pointer);
    pointer[0]=42;assert(!temporary.shrink_to(513));assert(!temporary.shrink_to(0));
    assert(temporary.shrink_to(64) && temporary.data()==pointer && pointer[0]==42);
    assert(temporary.size()==64 && shared_memory::validate_invariants());
  }
  source="10 A=A+1\n20 @(0)=@(0)+1\n";
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID,42,0,result)==RuntimeStatus::OK && result==1);
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_INDEX,0,0,result)==RuntimeStatus::OK);
  source="1.10 S A=A+10\n1.20 E\n";
  assert(invoke_resident(Language::FOCAL,Command::FOCAL_RUN_ID,42,0,result)==RuntimeStatus::OK && result==0);
  source="10 IF A<>2 GOTO 999\n20 IF @(0)<>2 GOTO 999\n";
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID,42,0,result)==RuntimeStatus::OK);
  assert(executions==4);
  legacy=true;
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID,42,0,result)==RuntimeStatus::INCOMPATIBLE_FIRMWARE);
  assert(executions==4);legacy=false;
  fail=true;
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID,42,0,result)==RuntimeStatus::IO_ERROR);
  fail=false;
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID,42,0,result)==RuntimeStatus::OK);
  assert(executions==5);
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_MENU_SELECT,0,0,result)==RuntimeStatus::OK);
  source="10 IF A<>0 GOTO 999\n20 IF @(0)<>0 GOTO 999\n";
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID,42,0,result)==RuntimeStatus::OK);
  source="1.10 S A=A-10\n1.20 E\n";
  assert(invoke_resident(Language::FOCAL,Command::FOCAL_RUN_ID,42,0,result)==RuntimeStatus::OK);
  assert(executions==7 && frontend_calls>14 && shared_memory::validate_invariants());
  assert(shared_memory::active_owner(shared_memory::Arena::WORKSPACE)==shared_memory::Owner::NONE);
  assert(shared_memory::active_owner(shared_memory::Arena::APP)==shared_memory::Owner::NONE);
  puts("language_vm_resident_self_test: handoff, retained vars/array, status, failures PASS");
}
