#include "vm_program_builder.hpp"
#include <cassert>
#include <cstdio>
using namespace language_vm;
using namespace language_vm::linked;
using vm_program_builder::Bytes;
namespace {
struct Fixture {
  Bytes bytes;
  Storage storage{};
  Member members[MAX_MEMBERS];
  Program program{};
  uint32_t revision=17,reads=0,polls=0,locations=0;
  unsigned fail_read=0,change_read=0,change_locate=0,change_poll=0,stop_poll=0;
  unsigned absent=MAX_FRAGMENTS,oversize=MAX_FRAGMENTS,invalid_id=MAX_FRAGMENTS;
  explicit Fixture(Bytes b):bytes(std::move(b)){}
  static uint32_t epoch(void* p){return ((Fixture*)p)->revision;}
  static bool read(void* raw,uint32_t at,uint8_t* output,uint16_t n) {
    auto& f=*(Fixture*)raw;
    ++f.reads;
    if(f.reads==f.change_read)++f.revision;
    if(f.reads==f.fail_read || at>f.storage.size || n>f.storage.size-at ||
       at>f.bytes.size() || n>f.bytes.size()-at)return false;
    // Exercise the fragment directory published by the cold APP too.
    for(uint32_t i=at;i<at+n;++i)assert(f.storage.files[i/FRAGMENT_BYTES]==100+i/FRAGMENT_BYTES);
    memcpy(output,f.bytes.data()+at,n);return true;
  }
  static bool poll(void* raw) {
    auto& f=*(Fixture*)raw;++f.polls;
    if(f.polls==f.change_poll)++f.revision;
    return f.polls!=f.stop_poll;
  }
  static bool locate(void* raw,uint16_t directory,const char* name,Fragment& file) {
    auto& f=*(Fixture*)raw;assert(directory==7);++f.locations;
    if(f.locations==f.change_locate)++f.revision;
    assert(strlen(name)==9 && !memcmp(name,"LVP",3) && !strcmp(name+5,".bin"));
    const unsigned i=unsigned(name[3]-'0')*10+unsigned(name[4]-'0');
    const unsigned at=i*FRAGMENT_BYTES;
    if(i>=f.absent || at>=f.bytes.size())return false;
    file={uint16_t(i==f.invalid_id?0xFFFF:100+i),
        i==f.oversize?FRAGMENT_BYTES+1:unsigned(std::min<size_t>(FRAGMENT_BYTES,f.bytes.size()-at))};
    return true;
  }
  LoadRequest request() {
    Input input{};input.paged={this,read,0};input.epoch_context=this;input.epoch=epoch;
    return {sizeof(LoadRequest),LOAD_MAGIC,7,MAX_MEMBERS,&storage,members,&program,input,poll};
  }
  Error run() {auto r=request();assert(load(&r,this,locate)==1);return r.error;}
};
void seal(Bytes& b) {
  flash::dword(b.data()+24,checksum(b.data()+HEADER_BYTES,b.size()-HEADER_BYTES));
  flash::dword(b.data()+28,checksum(b.data(),28));
}
void require_failure(Fixture& f) {
  assert(f.run()!=Error::NONE);assert(!f.program.members && !f.program.count);
}
}
int main() {
  auto basic=vm_program_builder::compile(Language::BASIC,"10 A=A+1;@(1)=@(1)+A;.RE=0;END\n");
  auto focal=vm_program_builder::compile(Language::FOCAL,"1.10 S A=7;S .RE=0;E\n");
  std::vector<vm_program_builder::Member> members;
  for(unsigned i=0;i<MAX_MEMBERS;++i)members.push_back({i+1,uint16_t(i+1),i&1?focal:basic});
  auto bytes=vm_program_builder::package(members,1);assert(bytes.size()>FRAGMENT_BYTES);
  Fixture good(bytes);assert(good.run()==Error::NONE);
  assert(good.program.count==MAX_MEMBERS && current(good.program));
  assert(good.program.input.paged.context==&good && good.program.input.paged.read==Fixture::read);
  assert(good.program.input.epoch==Fixture::epoch && good.program.input.epoch_context==&good);
  assert(good.storage.size==bytes.size() && good.reads && good.polls);
  // The cold APP has returned. Only resident-owned callbacks/certificates
  // remain; execute the catalog using the already existing VM kernel.
  Session session;assert(start(good.program,session));
  Value variables[26]{},array[385]{},stack[MAX_STACK]{};
  Bindings bindings{variables,array,385,stack,MAX_STACK};
  Host host{&bindings,[](void* p,Language,Bindings& b){b=*(Bindings*)p;return true;},nullptr,
      [](void*,uint32_t,uint32_t& next){next=0;return true;}};
  Services services{};services.reference=[](void*,bool write,uint8_t r,double&){return write && r==18;};
  services.event=[](void*,Event,const char*,uint16_t,double&){return true;};
  const auto result=execute(good.program,session,host,services);
  if(result.status!=Status::DONE || variables[0]!=Value(1))
    fprintf(stderr,"cold execution status=%u error=%s line=%lu pc=%lu A=%g\n",unsigned(result.status),
        error_name(result.run.error),(unsigned long)result.run.line,(unsigned long)result.run.pc,double(variables[0]));
  assert(result.status==Status::DONE && variables[0]==Value(1));
  ++good.revision;assert(!current(good.program));
  for(unsigned mode=0;mode<9;++mode) {
    Fixture bad(bytes);
    if(mode==0)bad.fail_read=1;
    if(mode==1)bad.change_read=2;
    if(mode==2)bad.change_locate=1;
    if(mode==3)bad.change_poll=2;
    if(mode==4)bad.stop_poll=1;
    if(mode==5)bad.absent=1;
    if(mode==6)bad.oversize=0;
    if(mode==7)bad.invalid_id=0;
    if(mode==8)bad.bytes.back()^=1;
    require_failure(bad);
  }
  // Valid container and image CRCs do not authorize an invalid opcode.
  auto invalid=bytes;
  const auto offset=flash::dword(invalid.data()+HEADER_BYTES+4);
  const auto size=flash::dword(invalid.data()+HEADER_BYTES+8);
  const auto code=flash::dword(invalid.data()+offset+12);
  invalid[offset+code]=0xFF;
  flash::dword(invalid.data()+offset+24,checksum(invalid.data()+offset+HEADER_SIZE,size-HEADER_SIZE));
  seal(invalid);Fixture bad_opcode(invalid);require_failure(bad_opcode);
  Fixture limited(bytes);auto request=limited.request();request.capacity=1;
  assert(load(&request,&limited,Fixture::locate)==1 && request.error!=Error::NONE && !limited.program.members);
  for(unsigned mode=0;mode<8;++mode) {
    auto r=limited.request();
    if(mode==0)--r.size;
    if(mode==1)++r.magic;
    if(mode==2)r.storage=nullptr;
    if(mode==3)r.program=nullptr;
    if(mode==4)r.members=nullptr;
    if(mode==5)r.input.epoch=nullptr;
    if(mode==6)r.input.paged.read=nullptr;
    if(mode==7)r.poll=nullptr;
    assert(load(&r,&limited,Fixture::locate)==0);
  }
  assert(load(nullptr,nullptr,nullptr)==0);
  puts("Cold linked loader: shared verifier, fragment/epoch/I/O/ABI failures and post-APP execution PASS");
}
