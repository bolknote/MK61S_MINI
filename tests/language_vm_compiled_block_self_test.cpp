#include "language_bytecode.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <limits>
#include <string>
#include <vector>
namespace language_vm { uint16_t trace_following(const View&,uint16_t); }
using namespace language_vm;
namespace {
struct Snapshot {
  std::vector<uint64_t> trace, events, results, cells, control;
  std::string text;
  unsigned polls=0, inputs=0;
  bool operator==(const Snapshot& b)const {
    return trace==b.trace && events==b.events && results==b.results &&
        cells==b.cells && control==b.control && text==b.text && polls==b.polls && inputs==b.inputs;
  }
};
Snapshot* recording;
unsigned comparisons=0, index_applied=0, compare_applied=0;
struct Fixture {
  uint8_t image[MAX_IMAGE]; View view={};
  Value vars[26]={}, array[385]={}, stack[MAX_STACK]={}; State state={};
  Snapshot result;
  unsigned stop=0;
  static bool service(void* p) {
    auto& f=*static_cast<Fixture*>(p);
    ++f.result.polls;return !f.stop || f.result.polls<f.stop;
  }
  static bool event(void* p,Event kind,const char* text,uint16_t length,double& value) {
    auto& f=*static_cast<Fixture*>(p);
    f.result.events.insert(f.result.events.end(),{(uint64_t)kind,length,mk_math::binary64_bits(value)});
    if(text)f.result.text.append(text,length);
    return true;
  }
  explicit Fixture(const char* source,Language language,Value lhs,Value rhs) {
    auto c=compile(language,source,(uint16_t)strlen(source),image,sizeof(image));
    if(c.error!=Error::NONE)std::fprintf(stderr,"fixture compile %u/%u: %s\n",(unsigned)c.error,c.line,source);
    assert(c.error==Error::NONE && inspect(image,c.size,view)==Error::NONE);
    vars['I'-'A']=lhs;vars['J'-'A']=rhs;
    for(unsigned n=0;n<385;++n)array[n]=Value((int32_t)n-100);
    for(unsigned n=0;n<MAX_STACK;++n)stack[n]=Value((int32_t)n+123);
    state.variables=vars;state.array=array;state.array_count=385;
    state.stack=stack;state.stack_capacity=MAX_STACK;
  }
  void seal() {
    const auto crc=checksum(image+HEADER_SIZE,view.size-HEADER_SIZE);
    for(unsigned n=0;n<4;++n)image[20+n]=(uint8_t)(crc>>(8*n));
  }
  void scalar() {
    // Independent reference: restore original bytecodes, not merely a flag in
    // the optimized handler. All instruction/source PCs and widths stay exact.
    for(uint16_t pc=view.code;pc<view.end;) {
      const auto following=trace_following(view,pc);assert(following);
      if((Op)image[pc]==Op::BLOCK_COMPARE)image[pc]=(uint8_t)Op::LOAD;
      if((Op)image[pc]==Op::BLOCK_INDEX)image[pc]=(uint8_t)Op::CONST_I16;
      pc=following;
    }
    seal();assert(inspect(image,view.size,view)==Error::NONE);
  }
  uint16_t marked(Op op)const {
    for(uint16_t pc=view.code;pc<view.end;pc=trace_following(view,pc))if((Op)image[pc]==op)return pc;
    return 0;
  }
  Snapshot execute(unsigned limit,bool resume=false) {
    recording=&result;
    Services host={};host.context=this;host.service=service;host.event=event;host.yield_input=true;
    for(unsigned phase=0;;++phase) {
      assert(phase<8);
      const auto r=language_vm::run(view,state,host,limit,resume);
      result.results.insert(result.results.end(),{(uint64_t)r.error,r.pc,r.line,r.steps,source_column(view,r.pc)});
      if(r.error!=Error::YIELDED)break;
      ++result.inputs;assert(state.sp<MAX_STACK);stack[state.sp++]=Value(7);resume=true;
    }
    recording=nullptr;
    for(const auto& v:vars)result.cells.push_back(v.representation());
    for(const auto& v:array)result.cells.push_back(v.representation());
    for(const auto& v:stack)result.cells.push_back(v.representation());
    result.control={state.pc,state.data_pc,state.data_index,state.sp,state.call_count,state.loop_count};
    for(unsigned n=0;n<state.call_count;++n) {
      const auto& f=state.calls[n];result.control.insert(result.control.end(),
          {f.resume,f.end,f.loops,f.group,f.base,f.mode,f.print_width,f.arguments});
    }
    for(unsigned n=0;n<state.loop_count;++n) {
      const auto& f=state.loops[n];result.control.insert(result.control.end(),
          {f.body,f.end,f.variable,f.step.representation(),f.limit.representation(),f.value.representation()});
    }
    return result;
  }
};
void equal(Fixture& fast,Fixture& reference,unsigned limit,bool resume=false) {
  reference.scalar();
  const auto a=fast.execute(limit,resume),b=reference.execute(limit,resume);
  if(!(a==b)) {
    std::fprintf(stderr,"compiled block mismatch limit=%u stop=%u resume=%u cases=%u\n",limit,fast.stop,resume,comparisons);
    assert(false);
  }
  ++comparisons;
}
}
namespace language_vm {
uint16_t trace_following(const View&,uint16_t);
void trace_instruction(const View&,uint16_t pc,uint32_t steps) {
  if(recording)recording->trace.insert(recording->trace.end(),{pc,steps});
}
void compare_block_applied(uint16_t) {++compare_applied;}
void integer_block_applied(uint16_t,uint8_t) {++index_applied;}
}
int main() {
  const char* programs[]={
    "10 IF I=0 A=1 ELSE A=2\n20 END\n",
    "10 IF I#0 A=1 ELSE A=2\n20 END\n",
    "10 IF I<1 A=1 ELSE A=2\n20 END\n",
    "10 IF I<=15 A=1 ELSE A=2\n20 END\n",
    "10 IF I>0 A=1 ELSE A=2\n20 END\n",
    "10 IF I>=15 A=1 ELSE A=2\n20 END\n",
    "10 IF I<J A=1 ELSE A=2\n20 END\n",
    "10 IF I>=J A=1 ELSE A=2\n20 END\n",
    "10 FOR K=1 TO 9;GOSUB 100;NEXT K;END\n100 IF I<J A=A+1 ELSE A=A-1\n110 RETURN\n",
    "10 FOR K=1 TO 9;IF I<1 A=A+1 ELSE A=A-1\n20 NEXT K\n",
    "10 A=128+I;B=@(128+I)\n",
    "10 GOSUB 100;END\n100 INPUT A\n110 IF I<J B=1 ELSE B=2\n120 RETURN\n",
    "10 IF I<16 A=1 ELSE A=2\n", // Unsupported RHS stays scalar.
    "10 IF I<.5 A=1 ELSE A=2\n",
    "10 IF I<-1 A=1 ELSE A=2\n"
  };
  const Value values[]={Value(INT32_MIN),Value(-1),Value(0),Value(1),Value(15),Value(16),Value(INT32_MAX),
    Value(.5),Value(2147483648.),Value::floating_bits(UINT64_C(0x8000000000000000)),
    Value(std::numeric_limits<double>::infinity()),Value(-std::numeric_limits<double>::infinity()),
    Value(std::numeric_limits<double>::quiet_NaN())};
  unsigned marked=0;
  for(const char* source:programs)for(Value lhs:values)for(Value rhs:{Value(0),Value(.5),Value(INT32_MAX)})
    for(unsigned limit:{0U,1U,2U,3U,4U,5U,6U,7U,8U,9U,30U,31U,32U,33U,34U,65U})
      for(unsigned stop:{0U,1U,2U,3U}) {
        Fixture fast(source,Language::BASIC,lhs,rhs),reference(source,Language::BASIC,lhs,rhs);
        if(fast.marked(Op::BLOCK_COMPARE))++marked;
        fast.stop=reference.stop=stop;equal(fast,reference,limit);
      }
  assert(marked>1000);
  for(const char* source:{"1.10 S A=128+I\n","1.10 F K=1,9;S A=128+I\n",
                         "1.10 D 2,3;EXIT\n2.10 S A=128+I;RETURN ARG(1)\n"})
    for(Value lhs:values)for(unsigned limit:{0U,1U,2U,3U,4U,5U,6U,31U,32U,33U,64U}) {
      Fixture fast(source,Language::FOCAL,lhs,0),reference(source,Language::FOCAL,lhs,0);
      assert(fast.marked(Op::BLOCK_INDEX));equal(fast,reference,limit);
    }
  // Resume at each original instruction, every comparison mask and target.
  for(unsigned offset:{0U,2U,3U})for(Value lhs:values)for(unsigned mask=0;mask<16;++mask)
    for(unsigned target:{0U,1U,2U})for(unsigned capacity:{0U,1U,2U,(unsigned)MAX_STACK}) {
      Fixture fast(programs[0],Language::BASIC,lhs,0),reference(programs[0],Language::BASIC,lhs,0);
      const auto first=fast.marked(Op::BLOCK_COMPARE);assert(first);
      for(Fixture* f:{&fast,&reference}) {
        f->state.pc=(uint16_t)(first+offset);f->state.data_pc=f->view.code;
        f->state.sp=offset==0?0:offset==2?1:2;f->stack[0]=lhs;f->stack[1]=0;
        f->state.stack_capacity=(uint8_t)capacity;f->image[first+4]=(uint8_t)mask;
        if(target) {const uint16_t to=target==1?0:f->view.end;
          f->image[first+5]=(uint8_t)to;f->image[first+6]=(uint8_t)(to>>8);}
      }
      // Keep the known-good reference View; deliberately invalid branch targets
      // exercise run() without pretending that the cold verifier accepted it.
      for(uint16_t pc=reference.view.code;pc<reference.view.end;pc=trace_following(reference.view,pc)) {
        if((Op)reference.image[pc]==Op::BLOCK_COMPARE)reference.image[pc]=(uint8_t)Op::LOAD;
      }
      const auto a=fast.execute(64,true),b=reference.execute(64,true);assert(a==b);++comparisons;
    }
  // Truncated public Views: never read past the caller's declared code end.
  for(unsigned program:{0U,6U,10U}) {
    Fixture full(programs[program],Language::BASIC,0,0);
    for(uint16_t end=full.view.code;end<=full.view.end;++end)for(unsigned limit:{0U,1U,2U,3U,4U,31U,32U}) {
      Fixture fast(programs[program],Language::BASIC,0,0),reference(programs[program],Language::BASIC,0,0);
      reference.scalar();fast.view.end=reference.view.end=end;
      assert(fast.execute(limit)==reference.execute(limit));++comparisons;
    }
  }
  // Cold proofs reject malformed marks even if the outer CRC was recomputed.
  for(unsigned field:{0U,1U,2U,3U}) {
    Fixture f(programs[0],Language::BASIC,0,0);const auto first=f.marked(Op::BLOCK_COMPARE);
    if(field==0)f.image[first+1]=26;
    if(field==1)f.image[first+2]=(uint8_t)Op::CONST_I8;
    if(field==2)f.image[first+3]=(uint8_t)Op::ADD;
    if(field==3)f.image[first+4]=16;
    f.seal();View rejected;assert(inspect(f.image,f.view.size,rejected)==Error::INVALID_IMAGE);
  }
  for(unsigned field:{3U,4U,5U}) {
    Fixture f(programs[10],Language::BASIC,0,0);const auto first=f.marked(Op::BLOCK_INDEX);assert(first);
    f.image[first+field]=255;f.seal();View rejected;
    assert(inspect(f.image,f.view.size,rejected)==Error::INVALID_IMAGE);
  }
#if MK61_VM_INTEGER_BLOCK
  assert(index_applied>100);
#else
  assert(index_applied==0);
#endif
#if MK61_VM_COMPARE_BLOCK
  assert(compare_applied>100);
#else
  assert(compare_applied==0);
#endif
  std::printf("compiled VM blocks: %u scalar-reference comparisons, exact trace/steps/stack/errors/INPUT/ESC, verifier PASS\n",comparisons);
}
