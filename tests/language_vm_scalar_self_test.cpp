#include "language_bytecode.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
using namespace language_vm;

namespace {
void push_values() {
  uint8_t image[MAX_IMAGE];View view;
  const auto compiled=compile_expression(Language::BASIC,"I",1,image,sizeof(image));
  assert(compiled.error==Error::NONE && inspect(image,compiled.size,view)==Error::NONE);
  assert(view.expression && view.stack==1 && (Op)image[view.code]==Op::LOAD);
  Value variables[26],stack[1];
  uint32_t random=0x61F411U;
  auto next=[&](){random^=random<<13;random^=random>>17;random^=random<<5;return random;};
  const uint64_t special[]={0,UINT64_C(0x8000000000000000),1,UINT64_C(0x8000000000000001),
    UINT64_C(0x000FFFFFFFFFFFFF),UINT64_C(0x0010000000000000),
    UINT64_C(0x7FEFFFFFFFFFFFFF),UINT64_C(0xFFEFFFFFFFFFFFFF),
    UINT64_C(0x7FF0000000000000),UINT64_C(0xFFF0000000000000),
    UINT64_C(0x7FF0000000000001),UINT64_C(0x7FF8000000000000),
    UINT64_C(0xFFFFFFFFFFFFFFFF),UINT64_C(0x7FFC000100000003)};
  for(unsigned n=0;n<10000+sizeof(special)/sizeof(*special);++n) {
    const uint64_t bits=n<sizeof(special)/sizeof(*special)?special[n]:
        (uint64_t(next())<<32)|next();
    const Value input=(n<sizeof(special)/sizeof(*special) || n%3)?Value::floating_bits(bits):
        Value(mk_math::bit_copy<int32_t>((uint32_t)bits));
    variables['I'-'A']=input;
    for(unsigned full=0;full<2;++full) {
      State state={};state.variables=variables;state.stack=stack;state.stack_capacity=1;
      state.pc=state.data_pc=view.code;state.sp=(uint8_t)full;stack[0]=Value(123);
      const auto result=run(view,state,{},1,true);
      const Error expected=!input.finite()?Error::MATH:full?Error::STACK:Error::LIMIT;
      assert(result.error==expected && result.steps==1);
      assert(state.sp==(!full && input.finite()?1:full));
      assert(stack[0].representation()==(!full && input.finite()?input:Value(123)).representation());
    }
  }
}
struct Rewrite {
  uint8_t* image;uint16_t pc;Op replacement;bool proceed;unsigned calls=0;
  static bool service(void* context) {
    auto& self=*static_cast<Rewrite*>(context);++self.calls;
    self.image[self.pc]=(uint8_t)self.replacement;
    return self.proceed;
  }
};
void service_fetch() {
  // Services run before the opcode fetch. Keep this observable ordering when
  // experimenting with cached fetches or a local PC/SP in the scalar loop.
  for(Op replacement:{Op::HALT,(Op)255})for(bool proceed:{false,true}) {
    uint8_t image[MAX_IMAGE];View view;
    const char* source="10 A=1\n";
    const auto compiled=compile_basic(source,(uint16_t)std::strlen(source),image,sizeof(image),true);
    assert(compiled.error==Error::NONE && inspect(image,compiled.size,view)==Error::NONE);
    uint16_t pc=view.code;
    while((Op)image[pc]==Op::SOURCE_POS)pc=instruction_end(image,view.end,pc);
    assert(pc<view.end && (Op)image[pc]!=Op::HALT);
    Value variables[26],stack[MAX_STACK];State state={};
    state.variables=variables;state.stack=stack;state.stack_capacity=MAX_STACK;
    Rewrite rewrite={image,pc,replacement,proceed};Services host={};
    host.context=&rewrite;host.service=Rewrite::service;
    const auto result=run(view,state,host);
    const Error expected=!proceed?Error::STOPPED:replacement==Op::HALT?Error::NONE:Error::INVALID_IMAGE;
    assert(result.error==expected && result.pc==pc && result.steps==1 && rewrite.calls==1);
    assert(state.sp==0 && variables[0].zero());
  }
}
}
int main() {
  push_values();service_fetch();
  std::puts("scalar loop: 20028 value/stack cases and service-before-fetch PASS");
}
