#include "language_bytecode.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <vector>
using namespace language_vm;
namespace language_vm {RunResult reference_run(const View&,State&,const Services&,uint32_t,bool);}
namespace {
struct Fixture {
  std::vector<uint8_t> image;
  Value variables[26]{},array[32]{},stack[MAX_STACK]{};
  State state{};View view{};flash::Reader reader;
  std::vector<uint64_t> observations;
  unsigned stop=0,polls=0;
  static bool read(void* raw,uint32_t at,uint8_t* out,uint16_t n) {
    auto& f=*static_cast<Fixture*>(raw);
    assert(at<=f.image.size() && n<=f.image.size()-at);
    std::copy_n(f.image.data()+at,n,out);return true;
  }
  Fixture(const std::vector<uint8_t>& bytes,bool paged,bool wide,Value initial,unsigned stop_at)
      :image(bytes),reader({this,read,uint32_t(bytes.size())}),stop(stop_at) {
    view={paged?nullptr:image.data(),uint32_t(image.size()),32,0,1,MAX_STACK,
          Language::BASIC,false,false,uint32_t(image.size()),paged?&reader:nullptr,wide};
    state.variables=variables;state.array=array;state.array_count=32;state.stack=stack;state.stack_capacity=MAX_STACK;
    for(unsigned i=0;i<MAX_STACK;++i)stack[i]=int32_t(i+100);
    variables[0]=initial;
  }
  void cells() {
    observations.insert(observations.end(),{state.pc,state.sp,state.call_count,state.loop_count});
    for(auto v:variables)observations.push_back(v.representation());
    for(auto v:array)observations.push_back(v.representation());
    for(auto v:stack)observations.push_back(v.representation());
  }
  static bool service(void* raw) {
    auto& f=*static_cast<Fixture*>(raw);++f.polls;f.cells();
    return !f.stop || f.polls<f.stop;
  }
  void execute(bool reference,unsigned limit) {
    Services host{};host.context=this;host.service=service;
    const auto r=reference?reference_run(view,state,host,limit,false):run(view,state,host,limit,false);
    observations.insert(observations.end(),{uint64_t(r.error),r.pc,r.line,r.steps,polls});
    cells();
  }
};
struct Program {
  std::vector<uint8_t> bytes=std::vector<uint8_t>(32,0);unsigned address_bytes;
  explicit Program(bool wide) {View v{};v.wide=wide;address_bytes=v.address_bytes();}
  uint32_t pc()const{return uint32_t(bytes.size());}
  void op(Op o){bytes.push_back(uint8_t(o));}
  void byte(unsigned n){bytes.push_back(uint8_t(n));}
  void prefix(){op(Op::SOURCE_POS);byte(3);byte(0);}
  uint32_t target(){const auto at=pc();bytes.resize(bytes.size()+address_bytes);return at;}
  void patch(uint32_t at,uint32_t to){for(unsigned i=0;i<address_bytes;++i)bytes[at+i]=uint8_t(to>>(8*i));}
};
unsigned comparisons=0;
void compare(const Program& p,bool wide,Value initial,unsigned limit,unsigned stop) {
  for(bool paged:{false,true}) {
    Fixture fast(p.bytes,paged,wide,initial,stop),reference(p.bytes,paged,wide,initial,stop);
    fast.execute(false,limit);reference.execute(true,limit);
    if(fast.observations!=reference.observations) {
      std::fprintf(stderr,"control span mismatch #%u paged=%u wide=%u initial=%016llx limit=%u stop=%u size=%zu\n",
        comparisons,paged,wide,(unsigned long long)initial.representation(),limit,stop,p.bytes.size());
      assert(false);
    }
    assert(fast.image==reference.image);++comparisons;
  }
}
}
int main() {
  for(bool wide:{false,true})for(unsigned mask=0;mask<256;++mask) {
    Program p(wide);p.op(Op::INTEGER_SPAN);p.byte(0);p.prefix();
    p.op(Op::CONST_I8);p.byte(1);p.op(Op::COMPARE_FALSE);p.byte(mask);const auto otherwise=p.target();
    p.op(Op::CONST_0);p.op(Op::STORE);p.byte(1);p.op(Op::JUMP);const auto finish=p.target();
    p.patch(otherwise,p.pc());p.op(Op::LINE);p.prefix();p.op(Op::CONST_15);p.op(Op::STORE);p.byte(1);
    p.patch(finish,p.pc());p.op(Op::HALT);
    for(Value initial:{Value(-1),Value(0),Value(1),Value(2),Value(.5),Value(INT32_MIN),Value(INT32_MAX)})
      for(unsigned limit:{0U,1U,2U,3U,4U,5U,6U,7U,8U,31U,32U,33U})compare(p,wide,initial,limit,0);
    // Invalid taken targets retain the ordinary decoder's pop/error PC.
    for(uint32_t to:{0U,p.pc(),UINT32_MAX}) {
      auto invalid=p;invalid.patch(otherwise,to);
      compare(invalid,wide,0,0,0);compare(invalid,wide,2,0,0);
    }
  }
  for(bool wide:{false,true})for(bool prefixes:{false,true})for(bool direct:{false,true}) {
    Program p(wide);const auto start=p.pc();
    p.op(Op::INTEGER_SPAN);p.byte(0);p.op(Op::CONST_I8);p.byte(1);p.op(Op::SUB);p.op(Op::STORE);p.byte(0);
    if(prefixes)p.prefix();
    p.op(Op::LOAD);p.byte(0);p.op(Op::JUMP_FALSE);const auto finish=p.target();
    p.op(direct?Op::GOTO_DIRECT:Op::JUMP);const auto again=p.target();p.patch(again,start);
    p.patch(finish,p.pc());p.op(Op::LINE);p.op(Op::HALT);
    for(Value initial:{Value(-1),Value(0),Value(1),Value(2),Value(3),Value(17),Value(.5),Value(INT32_MIN),Value(INT32_MAX)})
      for(unsigned limit:{1U,2U,3U,4U,5U,6U,7U,31U,32U,33U,63U,64U,65U,99U})
        for(unsigned stop:{0U,1U,2U,3U})compare(p,wide,initial,limit,stop);
    for(uint32_t end=start;end<=p.pc();++end) {
      auto truncated=p;truncated.bytes.resize(end);compare(truncated,wide,2,99,0);
    }
  }
  // A self branch cannot grow the native stack or postpone polling/ESC.
  for(bool wide:{false,true}) {
    Program p(wide);const auto start=p.pc();p.op(Op::INTEGER_SPAN);p.byte(0);
    p.op(Op::STORE);p.byte(0);p.op(Op::JUMP);const auto again=p.target();p.patch(again,start);
    for(unsigned limit:{31U,32U,33U,64U,65U,100U})for(unsigned stop:{0U,1U,2U,3U})compare(p,wide,3,limit,stop);
  }
  // A merged fetch must not commit a SOURCE_POS tail prematurely. Exercise
  // complete/repeated/truncated prefixes, empty code tails and failing HALT
  // at both sides of the original 32-step poll/limit boundary.
  for(bool wide:{false,true})for(unsigned padding:{0U,27U,28U,29U,30U,31U,32U,33U})
    for(unsigned prefixes:{0U,1U,3U})for(unsigned tail=0;tail<6;++tail) {
      Program p(wide);p.op(Op::INTEGER_SPAN);p.byte(0);p.op(Op::STORE);p.byte(0);
      for(unsigned i=0;i<padding;++i)p.op(Op::LINE);
      for(unsigned i=0;i<prefixes;++i)p.prefix();
      switch(tail) {
        case 0:p.op(Op::HALT);break;
        case 1:p.op(Op(uint8_t(Op::CONST_0)+1));p.op(Op::HALT);break;
        case 2:p.byte(255);break;
        case 3:break;
        case 4:p.op(Op::SOURCE_POS);p.byte(3);break;
        case 5:p.op(Op::SOURCE_POS);break;
      }
      for(unsigned limit:{0U,31U,32U,33U,64U})for(unsigned stop:{0U,2U})
        compare(p,wide,3,limit,stop);
    }
  std::printf("Control integer spans: %u full-state raw/paged comparisons, all masks, forward/back/self branches, limits/ESC/truncation PASS\n",comparisons);
}
