#include "language_linked_program.hpp"
using namespace language_vm;
namespace {
linked::Member members[linked::MAX_MEMBERS];
linked::Session sessions[2];
Value variables[2][26],arrays[2][385],stack[MAX_STACK];
double refs[20];
const uint8_t* image;uint32_t image_size,revision=1,polls=0,entered=0;
bool read(void*,uint32_t at,uint8_t* out,uint16_t n) {
  if(at>image_size || n>image_size-at)return false;
  memcpy(out,image+at,n);return true;
}
bool scratch_read(void*,flash::Space,uint32_t,uint8_t*,uint16_t){return false;}
bool scratch_write(void*,flash::Space,uint32_t,const uint8_t*,uint16_t){return false;}
bool scratch_truncate(void*,flash::Space,uint32_t n){return !n;}
}
extern "C" uint32_t linked_probe(uint32_t address,uint32_t size,uint32_t mode) {
  image=(const uint8_t*)address;image_size=size;polls=entered=0;
  linked::Input in{};in.size=size;in.epoch=[](void*){return revision;};
  if(mode&1)in.paged={nullptr,read,size};else in.bytes=image;
  linked::Program program;
  const flash::IO scratch={nullptr,scratch_read,scratch_write,scratch_truncate};
  auto error=linked::inspect(in,members,linked::MAX_MEMBERS,program,scratch);
  if(error!=Error::NONE)return 0xE000U+unsigned(error);
  auto* session=sessions;
  if(!linked::start(program,*session))return 1;
  linked::Host host={nullptr,[](void*,Language language,Bindings& b){unsigned i=language==Language::BASIC?0:1;b={variables[i],arrays[i],uint16_t(i?64:385),stack,MAX_STACK};return true;},
    [](void*,uint32_t,uint16_t,Language){++entered;return true;},
    [](void*,uint32_t,uint32_t& next){next=uint32_t(refs[18]);return true;}};
  Services services={};services.service=[](void*){++polls;return true;};
  services.reference=[](void*,bool write,uint8_t ref,double& value){if(ref>=20)return false;if(write)refs[ref]=value;else value=refs[ref];return true;};
  services.event=[](void*,Event,const char*,uint16_t,double&){return true;};
  auto result=linked::execute(program,*session,host,services,(mode&2)?7:0);
  const Value answer(13);
  for(unsigned calls=0;result.status==linked::Status::AWAIT_INPUT || result.status==linked::Status::BUDGET;++calls) {
    if(calls>2000)return 2;
    auto* next=session==sessions?sessions+1:sessions;
    memcpy(next,session,sizeof(*session));memset(session,0xA5,sizeof(*session));session=next;
    result=linked::execute(program,*session,host,services,(mode&2)?7:0,
        result.status==linked::Status::AWAIT_INPUT?&answer:nullptr);
  }
  if(result.status!=linked::Status::DONE)return 3+unsigned(result.status);
  if(variables[0][0]!=Value(5050) || variables[0][1]!=Value(5063) || variables[1][0]!=Value(7))return 20;
  if(session->members!=3 || entered!=3 || !polls)return 21;
  return 0x61A0;
}
// No external runtime archives: keep this fixture's memory helpers local.
extern "C" void* memcpy(void* d,const void* s,size_t n){auto* out=(uint8_t*)d;auto* in=(const uint8_t*)s;for(size_t i=0;i<n;++i)out[i]=in[i];return d;}
extern "C" void* memset(void* d,int v,size_t n){auto* out=(uint8_t*)d;for(size_t i=0;i<n;++i)out[i]=uint8_t(v);return d;}
extern "C" void* memmove(void* d,const void* s,size_t n){auto* out=(uint8_t*)d;auto* in=(const uint8_t*)s;if(out<in)for(size_t i=0;i<n;++i)out[i]=in[i];else while(n){--n;out[n]=in[n];}return d;}
extern "C" int memcmp(const void* a,const void* b,size_t n){auto* x=(const uint8_t*)a;auto* y=(const uint8_t*)b;for(size_t i=0;i<n;++i)if(x[i]!=y[i])return int(x[i])-int(y[i]);return 0;}
