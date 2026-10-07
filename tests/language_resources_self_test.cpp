#include "language_resources.hpp"
#include "language_vm_abi.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
using namespace language_vm;
namespace {
struct Host {
  const std::string* source;
  const uint8_t* image;
  Host(const std::string* s, const uint8_t* i):source(s),image(i) {}
  uint32_t revision = 7;
  unsigned reads = 0, maximum_read = 0;
  std::vector<std::string> text, prompts;
  std::vector<const char*> handles;
  static bool read(void* raw, uint16_t offset, uint8_t* out, uint16_t length) {
    auto& h = *(Host*)raw;
    const uint32_t stamp = (uint32_t)resource_word(h.image+26) |
                          ((uint32_t)resource_word(h.image+28)<<16);
    if(stamp != h.revision || resource_word(h.image+24) != 42 ||
       offset > h.source->size() || length > h.source->size()-offset) return false;
    ++h.reads; h.maximum_read = std::max(h.maximum_read, (unsigned)length);
    memcpy(out, h.source->data()+offset, length); return true;
  }
  static bool append(void* raw, const char* text, uint16_t n, bool) {
    ((std::string*)raw)->append(text,n); return true;
  }
  static bool event(void* raw, Event e, const char* text, uint16_t n, double& value) {
    auto& h = *(Host*)raw;
    if(e == Event::TEXT) h.text.emplace_back(text,n);
    if(e == Event::RESOURCE_TEXT) {
      h.handles.push_back(text); std::string decoded;
      if(!resource_text((const uint8_t*)text, read, &h, append, &decoded)) return false;
      h.text.push_back(decoded);
    }
    if(e == Event::READ_INPUT) { h.prompts.emplace_back(text,n); value=h.prompts.size()+5; }
    if(e == Event::RESOURCE_INPUT) {
      h.handles.push_back(text); char decoded[96];
      if(!resource_prompt((const uint8_t*)text, decoded, read, &h)) return false;
      h.prompts.emplace_back(decoded,n); value=h.prompts.size()+5;
    }
    return true;
  }
};
struct Program {
  std::vector<uint8_t> image;
  View view = {};
  State state = {};
  double variables[26] = {}, array[385] = {}, stack[MAX_STACK] = {};
  Program(const std::string& source, Language lang, bool resources) {
    ResourceSource backing = {42,7};
    const auto sized=compile(lang,source.data(),(uint16_t)source.size(),nullptr,MAX_IMAGE,true,
                             resources?&backing:nullptr);
    if(sized.error != Error::NONE) std::fprintf(stderr,"compile %s at %u: %s\n",error_name(sized.error),sized.source_offset,source.c_str());
    assert(sized.error == Error::NONE);
    std::vector<uint8_t> staging(sized.size+16,0xA5);
    auto r=compile(lang,source.data(),(uint16_t)source.size(),staging.data()+8,sized.size,true,
                   resources?&backing:nullptr);
    assert(r.error == Error::NONE && r.size == sized.size);
    for(unsigned i=0;i<8;++i) assert(staging[i]==0xA5 && staging[sized.size+8+i]==0xA5);
    image.assign(staging.begin()+8,staging.end()-8); // native/compiler storage disappears
    std::fill(staging.begin(),staging.end(),0xCD);
    assert(inspect(image.data(),(uint16_t)image.size(),view) == Error::NONE);
    state.variables=variables; state.array=array; state.array_count=385;
    state.stack=stack; state.stack_capacity=MAX_STACK;
  }
  RunResult run(Host& h, bool yield=false, bool resume=false) {
    h.image=image.data(); Services services = {}; services.context=&h;
    services.event=Host::event; services.yield_input=yield;
    return language_vm::run(view,state,services,10000,resume);
  }
  void crc() {
    const uint32_t crc=checksum(image.data()+HEADER_SIZE,image.size()-HEADER_SIZE);
    for(unsigned i=0;i<4;++i) image[20+i]=(uint8_t)(crc>>(8*i));
  }
};
void equivalent(const std::string& source, Language lang=Language::BASIC) {
  Program inline_program(source,lang,false), resource_program(source,lang,true);
  Host a = {&source,nullptr}, b = {&source,nullptr};
  const auto ra=inline_program.run(a), rb=resource_program.run(b);
  assert(ra.error==Error::NONE && rb.error==ra.error);
  assert(a.text==b.text && a.prompts==b.prompts);
  assert(!memcmp(inline_program.variables,resource_program.variables,sizeof(inline_program.variables)));
  assert(!memcmp(inline_program.array,resource_program.array,sizeof(inline_program.array)));
  assert(b.maximum_read<=95);
}
void test_semantics_and_dedup() {
  const std::string source="10 PRINT \"SAME RESOURCE STRING\";'SAME RESOURCE STRING'\n"
                           "20 INPUT 'SAME ';'RESOURCE STRING',A\n30 END\n";
  Program p(source,Language::BASIC,true); Host h={&source,nullptr};
  assert(p.run(h).error==Error::NONE);
  assert(h.handles.size()==3 && h.handles[0]==h.handles[1] && h.handles[1]==h.handles[2]);
  assert(p.image.size()-p.view.end==6); // exactly one source-backed recipe
  const std::string needle="SAME RESOURCE STRING";
  assert(std::search(p.image.begin(),p.image.end(),needle.begin(),needle.end())==p.image.end());
  equivalent(source);
  equivalent("10 INPUT 'discard';_;'kept',A;^M;'other';^A,B\n20 PRINT A;B\n");
  equivalent("10 INPUT @(1+2);C;D\n20 PRINT @(3);C;D\n");
  equivalent("10 PRINT '';^A;_;'end'\n20 INPUT '',A\n");
  equivalent("10 INPUT '"+std::string(140,'X')+"',A\n");
  equivalent("10 PRINT '"+std::string(600,'X')+"'\n"); // multi-span, 32-byte streaming
  equivalent(std::string("10 PRINT '")+char(0xE1)+char(0xF2)+"'\n"); // M8, never UTF-8 transforms
  equivalent("1.10 PRINT \"same\"\n1.20 P \"same\"\n1.30 ASK X\n1.40 EXIT\n",Language::FOCAL);
}
void test_pool_crosses_scratch_slabs() {
  std::string source="10 PRINT ";
  for(unsigned i=0;i<520;++i) {
    if(i) source += ';';
    source += "'"; source += (char)('A'+i/26); source += (char)('A'+i%26); source += "'";
  }
  source += "\n";
  Program p(source,Language::BASIC,true); Host h={&source,nullptr};
  assert(p.image.size()-p.view.end==520*6 && p.image.size()<=MAX_IMAGE);
  assert(p.run(h).error==Error::NONE && h.text.size()==520);
  for(unsigned i=0;i<520;++i) assert(h.text[i]==std::string({(char)('A'+i/26),(char)('A'+i%26)}));
}
void test_resume_and_stale_source() {
  const std::string source="10 INPUT 'PROMPT',@(2)\n20 PRINT 'AFTER'\n30 A=@(2)\n";
  Program p(source,Language::BASIC,true); Host h={&source,nullptr};
  auto result=p.run(h,true); assert(result.error==Error::YIELDED);
  assert((Op)p.image[result.pc]==Op::INPUT_RESOURCE && p.state.sp==1);
  const auto* recipe=p.image.data()+p.view.end+resource_word(p.image.data()+result.pc+1);
  char prompt[96]; assert(resource_prompt(recipe,prompt,Host::read,&h) && !strcmp(prompt,"PROMPT"));
  // The pointer is into the immutable image, not into an unloaded native APP.
  const auto suspended=static_cast<Continuation&>(p.state);
  p.state.stack[p.state.sp++]=17;
  result=p.run(h,true,true); assert(result.error==Error::NONE && p.variables[0]==17);
  assert(suspended.call_count==0);
  Program stale(source,Language::BASIC,true); h.revision=8;
  assert(stale.run(h).error==Error::IO && stale.variables[0]==0);
}
void test_invalid_recipes() {
  const std::string source="10 PRINT 'test';'other'\n20 END\n";
  Program p(source,Language::BASIC,true); const auto good=p.image;
  const uint16_t pool=p.view.end;
  auto reject=[&] {p.crc(); View v; assert(inspect(p.image.data(),(uint16_t)p.image.size(),v)==Error::INVALID_IMAGE);p.image=good;};
  p.image[pool+2]=255; reject(); // truncated fragment table
  p.image[pool+5]=0; reject(); // zero-sized span
  p.image[pool+3]=0xFF;p.image[pool+4]=0x7F;reject(); // beyond the source
  p.image[pool]=255;reject(); // declared text length disagrees with spans
  p.image[pool+3]=1;p.image[pool+4]=0x81;reject(); // malformed one-byte constant
  // A reference to the middle of a recipe cannot masquerade as a resource.
  for(uint16_t pc=p.view.code;pc<p.view.end;++pc) if((Op)p.image[pc]==Op::PRINT_RESOURCE) {
    p.image[pc+1]=1;p.image[pc+2]=0;reject();break;
  }
  p.image[30]=(uint8_t)p.image.size();p.image[31]=(uint8_t)(p.image.size()>>8);reject();
  uint8_t guarded[112];memset(guarded,0xA5,sizeof(guarded));
  const uint8_t corrupt[]={96,0,0};
  Host h={&source,p.image.data()}; assert(!resource_prompt(corrupt,(char*)guarded+8,Host::read,&h));
  for(uint8_t byte:guarded) assert(byte==0xA5);
  // Fuzz keeps a correct CRC, so structural checks see the damaged recipes.
  uint32_t random=0x61A1;
  for(unsigned i=0;i<1000;++i) {
    random=random*1664525U+1013904223U;
    p.image[pool+random%(p.image.size()-pool)]^=(uint8_t)(random>>24);
    p.crc(); View v;(void)inspect(p.image.data(),(uint16_t)p.image.size(),v);p.image=good;
  }
}
}
int main(){test_semantics_and_dedup();test_pool_crosses_scratch_slabs();test_resume_and_stale_source();test_invalid_recipes();
  std::puts("language_resources: M8 dedup, PRINT/INPUT equivalence, streaming, relocation, resume, stale source, malformed recipes PASS");}
