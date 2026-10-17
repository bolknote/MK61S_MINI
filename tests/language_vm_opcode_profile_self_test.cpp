#include "language_bytecode.hpp"
#include "language_vm_profile.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>

namespace {
struct Row {uint64_t cycles=0;uint32_t count=0,integers=0;};
Row rows[9];
uint32_t clock_value=0,reads=0;
unsigned applied=0;
void reset() {for(auto& row:rows)row={};clock_value=reads=applied=0;}
}
namespace portable_system {
uint32_t call(uint32_t operation,uint32_t group,uint32_t count,uint32_t integers,void* payload) {
  using language_vm::Op;
  assert(group & MK61_VM_PROFILE_RAW_OPCODE);
  assert(group & MK61_VM_PROFILE_CYCLE_PAIR);
  const auto raw=count>1?256:group & ~(MK61_VM_PROFILE_RAW_OPCODE|MK61_VM_PROFILE_CYCLE_PAIR);
  const auto op=(Op)raw;
  group=raw==256?8:
    ((op>=Op::LOAD && op<=Op::STORE) || op==Op::UPDATE_LOCAL)?1:
    (op==Op::LOAD_ARRAY || op==Op::STORE_ARRAY || op==Op::LOAD_ARRAY_FIXED || op==Op::ARRAY_CELL || op==Op::TARGET_ARRAY)?2:
    (op==Op::ADD || op==Op::SUB)?3:op==Op::MUL?4:
    (op==Op::DIV || op==Op::MOD || op==Op::FLOOR_DIV)?5:
    ((op>=Op::EQ && op<=Op::XOR) || op==Op::COMPARE_FALSE)?6:
    ((op>=Op::CONST_0 && op<=Op::CONST_15) || op==Op::CONST_I8 || op==Op::CONST_I16 || op==Op::CONST_I32 || op==Op::CONST_F64 || op==Op::CONST_DEC8 || op==Op::CONST_DEC16)?0:7;
  assert(operation==MK61_SERVICE_VM_PROFILE && group<9 && count && integers<=count && payload);
  uint64_t cycles;std::memcpy(&cycles,payload,sizeof(cycles));
  // The wire flag is set by the APP; this test receiver mirrors subtraction.
  const uint32_t elapsed=(uint32_t)cycles,overhead=(uint32_t)(cycles>>32);
  cycles=elapsed>overhead ? elapsed-overhead : 0;
  rows[group].count+=count;rows[group].integers+=integers;rows[group].cycles+=cycles;
  return 1;
}
}
namespace language_vm {
uint32_t opcode_profile_test_cycles() {clock_value+=(reads++<2?1U:11U);return clock_value;}
void integer_block_applied(uint16_t,uint8_t count) {assert(count>=3 && count<=5);++applied;}
}
int main() {
  using namespace language_vm;
  reset();
  {
    OpcodeProfile profile(View{});
    Continuation state={};Bindings data={};
    {OpcodeProfile::Sample sample(profile,Op::CONST_I16,state,data);sample.fused(5);}
  }
  assert(rows[8].count==5 && rows[8].integers==(MK61_VM_OPCODE_PROFILE_INTEGER_COUNTS?5U:0U) &&
         rows[8].cycles==(MK61_VM_OPCODE_PROFILE_TIMING?10U:0U));
  for(unsigned i=0;i<8;++i)assert(!rows[i].count && !rows[i].cycles);
  reset();
  {
    OpcodeProfile profile(View{});
    Continuation state={};Bindings data={};
    {OpcodeProfile::Sample sample(profile,Op::LOAD,state,data);sample.fused(3,false);}
  }
  assert(rows[8].count==3 && rows[8].integers==0);
  reset();
  {
    OpcodeProfile profile(View{});
    Value operands[2]={7,2};Continuation state={};state.sp=2;
    Bindings data={};data.stack=operands;data.stack_capacity=2;
    {OpcodeProfile::Sample sample(profile,Op::FLOOR_DIV,state,data);}
  }
  assert(rows[5].count==1 && rows[5].integers==(MK61_VM_OPCODE_PROFILE_INTEGER_COUNTS?1U:0U));

  const char source[]="10 A=128+I\n";
  uint8_t image[MAX_IMAGE]={};View view={};
  const auto compiled=compile(Language::BASIC,source,sizeof(source)-1,image,sizeof(image));
  assert(compiled.error==Error::NONE && inspect(image,compiled.size,view)==Error::NONE);
  Value variables[26]={},stack[MAX_STACK]={};variables[8]=7;
  State state={};state.variables=variables;state.stack=stack;state.stack_capacity=MAX_STACK;
  reset();
  const auto result=run(view,state,Services{});
  assert(result.error==Error::NONE && variables[0]==135);
  uint32_t total=0;for(const auto& row:rows)total+=row.count;
  assert(total==result.steps);
#if MK61_VM_INTEGER_BLOCK
  assert(applied==1 && rows[8].count==4 && rows[8].integers==(MK61_VM_OPCODE_PROFILE_INTEGER_COUNTS?4U:0U));
  assert((rows[8].cycles!=0)==(MK61_VM_OPCODE_PROFILE_TIMING!=0));
  assert(!rows[0].count && !rows[1].count && !rows[3].count);
#else
  assert(!applied && !rows[8].count);
  assert(rows[0].count==1 && rows[1].count==2 && rows[3].count==1);
  assert(rows[3].integers==(MK61_VM_OPCODE_PROFILE_INTEGER_COUNTS?1U:0U));
#endif
  // A limit before the block's last instruction must keep scalar semantics,
  // not report an executed block which the VM had to reject.
  reset();variables[0]=0;state={};state.variables=variables;state.stack=stack;state.stack_capacity=MAX_STACK;
  const auto limited=run(view,state,Services{},3);
  assert(limited.error==Error::LIMIT && variables[0]==0 && !applied && !rows[8].count);
  total=0;for(const auto& row:rows)total+=row.count;
  assert(total==limited.steps);
  // A marked comparison keeps three logical counts. Floating values deopt
  // and must never be reported as an integer block by the diagnostic census.
  for(Value input:{Value(0),Value(.5)}) {
    const char conditional[]="10 IF I<1 A=3 ELSE A=4\n";
    const auto c=compile(Language::BASIC,conditional,sizeof(conditional)-1,image,sizeof(image));
    assert(c.error==Error::NONE && inspect(image,c.size,view)==Error::NONE);
    reset();variables[0]=0;variables[8]=input;state={};
    state.variables=variables;state.stack=stack;state.stack_capacity=MAX_STACK;
    const auto r=run(view,state,Services{});
    assert(r.error==Error::NONE && variables[0]==3 && !applied);
    total=0;for(const auto& row:rows)total+=row.count;
    assert(total==r.steps && rows[8].count==(input.integer()?3U:0U));
  }
  // The same-width short block copies finite fractional cells and uses the
  // original ABS Value operation. It is fused work, not an integer census.
  const char copied[]="10 I=1;@(I)=.25;A=@(I);B=ABS(A)\n";
  const auto c=compile(Language::BASIC,copied,sizeof(copied)-1,image,sizeof(image));
  assert(c.error==Error::NONE && inspect(image,c.size,view)==Error::NONE);
  Value array[2]={};reset();state={};state.variables=variables;state.stack=stack;
  state.stack_capacity=MAX_STACK;state.array=array;state.array_count=2;
  const auto r=run(view,state,Services{});
  assert(r.error==Error::NONE && variables[0]==.25 && variables[1]==.25);
  assert(rows[8].count==6 && rows[8].integers==0);
  total=0;for(const auto& row:rows)total+=row.count;assert(total==r.steps);
  std::puts("VM opcode profile: active block, logical counts, single elapsed attribution and limit fallback PASS");
}
