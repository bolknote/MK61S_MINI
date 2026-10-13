#include "language_bytecode.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <limits>
#include <initializer_list>
using namespace language_vm;
static uint64_t digest=UINT64_C(1469598103934665603);
static unsigned applied;
namespace language_vm {
void integer_block_applied(uint16_t, uint8_t count) {assert(count>=3 && count<=5);++applied;}
}
static void hash(const void* raw, size_t n) {
  const auto* p=(const uint8_t*)raw;
  while(n--)digest=(digest^*p++)*UINT64_C(1099511628211);
}
struct Fixture {
  uint8_t image[MAX_IMAGE]={};View view={};
  Value vars[26]={},array[385]={},stack[MAX_STACK]={};State state={};
  unsigned polls=0,stop=0;
  static bool service(void* raw){auto& f=*(Fixture*)raw;return !f.stop || ++f.polls<f.stop;}
  explicit Fixture(const char* source,Language language,Value input,unsigned capacity,unsigned stop_at)
      : stop(stop_at) {
    const auto compiled=compile(language,source,(uint16_t)strlen(source),image,sizeof(image));
    assert(compiled.error==Error::NONE && inspect(image,compiled.size,view)==Error::NONE);
    vars[8]=input;
    for(unsigned i=0;i<385;++i)array[i]=(int32_t)i*11-1000;
    state.variables=vars;state.array=array;state.array_count=385;
    state.stack=stack;state.stack_capacity=(uint8_t)capacity;
  }
  void run(unsigned limit) {
    Services host={};host.context=this;host.service=service;
    const auto result=language_vm::run(view,state,host,limit);
    hash(&result.error,sizeof(result.error));hash(&result.pc,sizeof(result.pc));
    hash(&result.line,sizeof(result.line));hash(&result.steps,sizeof(result.steps));
    const auto column=source_column(view,result.pc);hash(&column,sizeof(column));
    hash(vars,sizeof(vars));hash(array,sizeof(array));hash(stack,sizeof(stack));
    hash(&state.pc,sizeof(state.pc));hash(&state.sp,sizeof(state.sp));
    hash(&state.call_count,sizeof(state.call_count));hash(&state.loop_count,sizeof(state.loop_count));
    hash(&polls,sizeof(polls));
  }
};
int main() {
  const char* basic[]={"10 A=128+I\n","10 A=@(128+I)\n",
    "10 B=@(128+I);A=128+B\n","10 A=128+I+2\n",
    "10 A=(128+I)/2\n","10 A=0;FOR J=1 TO 80;A=128+I;NEXT J\n",
    "10 FOR J=1 TO 40;GOSUB 100;NEXT J;END\n100 A=@(128+I);RETURN\n",
    "10 A=@(128+I);IF A>0 THEN GOTO 30\n20 END\n30 A=128+I;END\n"};
  const char* focal[]={"1.10 S A=128+I\n","1.10 S A=(128+I)/2\n",
    "1.10 F J=1,80;S A=128+I\n","1.10 D 2\n1.20 E\n2.10 S A=128+I\n"};
  const Value inputs[]={Value(-129),Value(-128),Value(0),Value(255),Value(256),
    Value(INT32_MAX),Value(INT32_MIN),Value(.5),Value(-128.00000001),
    Value::floating_bits(UINT64_C(0x8000000000000000)),
    Value(std::numeric_limits<double>::infinity()),Value(std::numeric_limits<double>::quiet_NaN())};
  unsigned cases=0;
  for(auto language:{Language::BASIC,Language::FOCAL}) {
    const unsigned count=language==Language::BASIC?sizeof(basic)/sizeof(*basic):sizeof(focal)/sizeof(*focal);
    for(unsigned program=0;program<count;++program)for(Value input:inputs)
      for(unsigned limit:{0U,1U,2U,3U,4U,5U,6U,7U,31U,32U,33U,34U,64U,100000U})
        for(unsigned stop:{0U,1U,2U,3U}) {
          Fixture f(language==Language::BASIC?basic[program]:focal[program],language,input,MAX_STACK,stop);
          f.run(limit);++cases;
        }
  }
  // Deopt must preserve errors and all intermediate cells for a small stack,
  // an absent array, or a floating/NaN array element, not just the final value.
  for(unsigned capacity:{1U,2U,3U,(unsigned)MAX_STACK})for(unsigned mode=0;mode<4;++mode) {
    Fixture f(basic[1],Language::BASIC,Value(0),capacity,0);
    if(mode==1)f.state.array=nullptr;
    if(mode==2)f.array[128]=Value(.5);
    if(mode==3)f.array[128]=Value(std::numeric_limits<double>::quiet_NaN());
    f.run(0);++cases;
  }
  // Bounds, trailing SOURCE_POS and stop/limit semantics must remain exact
  // even when a caller hands run() a truncated view of otherwise valid bytes.
  Fixture complete(basic[1],Language::BASIC,Value(0),MAX_STACK,0);
  for(uint16_t end=complete.view.code;end<=complete.view.end;++end)
    for(unsigned limit:{0U,1U,2U,3U,4U,5U,6U,31U,32U}) {
      Fixture f(basic[1],Language::BASIC,Value(0),MAX_STACK,0);
      f.view.end=end;f.run(limit);++cases;
    }
#if MK61_VM_INTEGER_BLOCK
  assert(applied>100);
#else
  assert(!applied);
#endif
  std::printf("integer block differential cases=%u digest=%016llx\n",cases,(unsigned long long)digest);
}
