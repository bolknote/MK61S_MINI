#include "language_bytecode.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <vector>
using namespace language_vm;
namespace {
struct Fixture {
  std::vector<uint8_t> image;
  Value variables[26]{},array[32]{},stack[MAX_STACK]{};
  State state{};View view{};
  flash::Reader reader;
  unsigned polls=0,reads=0,mutation=0;
  bool paged;
  static bool read(void* raw,uint32_t at,uint8_t* out,uint16_t n) {
    auto& f=*static_cast<Fixture*>(raw);++f.reads;
    assert(at<=f.image.size() && n<=f.image.size()-at);
    std::copy_n(f.image.data()+at,n,out);return true;
  }
  Fixture(bool page,bool prefixes,bool wide):image(32,0),reader({this,read,1024}),paged(page) {
    image.push_back(uint8_t(Op::LINE));
    for(unsigned i=0;i<80;++i) {
      if(prefixes)image.insert(image.end(),{uint8_t(Op::SOURCE_POS),uint8_t(i),0});
      image.insert(image.end(),{uint8_t(Op::CONST_I8),uint8_t(i),uint8_t(Op::STORE),0});
    }
    image.push_back(uint8_t(Op::HALT));
    // The reader's bound is the actual image size, including short tails.
    reader=flash::Reader({this,read,uint32_t(image.size())});
    view={page?nullptr:image.data(),uint32_t(image.size()),32,0,1,MAX_STACK,
          Language::BASIC,false,false,uint32_t(image.size()),page?&reader:nullptr,wide};
    state.variables=variables;state.array=array;state.array_count=32;
    state.stack=stack;state.stack_capacity=MAX_STACK;
    for(unsigned i=0;i<MAX_STACK;++i)stack[i]=int32_t(100+i);
  }
  static bool service(void* raw) {
    auto& f=*static_cast<Fixture*>(raw);++f.polls;
    if(f.polls!=1)return true;
    if(f.mutation==1 || f.mutation==2) {
      f.image[f.state.pc]=uint8_t(f.mutation==1?Op::HALT:Op::SOURCE_POS);
      if(f.paged)f.reader.invalidate();
    } else if(f.mutation==3) {
      if(f.paged)f.reader.invalidate();
    } else if(f.mutation==4 && f.paged)f.reader.fail();
    else if(f.mutation==5)return false;
    return true;
  }
  RunResult run(unsigned limit,bool poll=true) {
    Services host{};host.context=this;host.service=poll?service:nullptr;
    return language_vm::run(view,state,host,limit);
  }
};
}
int main() {
  unsigned cases=0;
  for(bool paged:{false,true})for(bool prefixes:{false,true})for(bool wide:{false,true})
    for(bool poll:{false,true})for(unsigned limit:{0U,1U,2U,3U,31U,32U,33U,63U,64U,65U,161U,162U,163U}) {
      Fixture f(paged,prefixes,wide);auto r=f.run(limit,poll);
      const unsigned steps=limit && limit<162?limit:162;
      assert(r.steps==steps && r.error==(limit && limit<162?Error::LIMIT:Error::NONE));
      assert(f.polls==(poll?(steps+31)/32:0));
      assert(f.state.sp==(steps>1 && steps%2==0 && steps<162?1:0));
      if(steps>=3)assert(f.variables[0]==Value(int32_t((std::min(steps,161U)-3)/2)));
      if(steps==162)assert(f.variables[0]==79);
      ++cases;
    }
  // The prefix scan precedes service. A changed byte must be fetched again,
  // but a new SOURCE_POS from service must not be skipped retroactively.
  for(bool paged:{false,true})for(unsigned mutation:{1U,2U,3U,4U,5U}) {
    Fixture f(paged,true,true);f.mutation=mutation;auto r=f.run(0);
    assert(f.polls>=1);
    if(mutation==1)assert(r.error==Error::NONE && r.pc==32 && r.steps==1);
    if(mutation==2)assert(r.error==Error::INVALID_IMAGE && r.pc==32 && r.steps==1);
    if(mutation==3 || (mutation==4 && !paged))assert(r.error==Error::NONE && r.steps==162 && f.variables[0]==79);
    if(mutation==4 && paged)assert(r.error==Error::IO && r.steps==1);
    if(mutation==5)assert(r.error==Error::STOPPED && r.steps==1 && r.pc==32);
    ++cases;
  }
  // Prefix tails and fixed-width tails remain checked before operand access.
  for(bool paged:{false,true})for(Op op:{Op::SOURCE_POS,Op::CONST_I16,Op::CONST_I32,Op::CONST_F64}) {
    const unsigned width=op==Op::SOURCE_POS || op==Op::CONST_I16?3:op==Op::CONST_I32?5:9;
    for(unsigned tail=1;tail<width;++tail) {
      Fixture f(paged,false,false);f.image.resize(32+tail);f.image[32]=uint8_t(op);
      f.reader=flash::Reader({&f,Fixture::read,uint32_t(f.image.size())});
      f.view.bytes=paged?nullptr:f.image.data();f.view.size=f.view.end=uint32_t(f.image.size());
      auto r=f.run(10);
      assert(r.error==Error::INVALID_IMAGE && r.pc==32 && r.steps==(op==Op::SOURCE_POS?0:1));
      ++cases;
    }
  }
  std::printf("VM fetch: %u raw/paged, prefixes, service mutation, limits and exact-tail cases PASS\n",cases);
}
