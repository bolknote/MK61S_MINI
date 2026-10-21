#include "language_flash_fixture.hpp"
#include "language_vm_abi.hpp"
#include "language_flash_program.hpp"
#include <string>
#include <cstdio>
using namespace language_vm;
static void compile_many(Language language) {
  const bool basic=language==Language::BASIC;
  std::string text=basic?"1 GOTO 32000\n":"1.0 G 9.0\n";
  for(unsigned i=0;i<5000;++i) {
    char line[64];
    if(basic)snprintf(line,sizeof(line),"%u A=1\n",i+2);
    else snprintf(line,sizeof(line),"%u.%u S A=1\n",2+i/1000,i%1000);
    text+=line;
  }
  text+=basic?"32000 .RA=42;END\n":"9.0 S .RB=42;E\n";
  assert(text.size()<=source::MAX_SIZE);
  Disk disk;source::Reader source(text.data(),uint16_t(text.size()));
  alignas(8) uint8_t scratch[FLASH_COMPILER_WORKSPACE_SIZE+16];memset(scratch,0xA5,sizeof(scratch));
  const auto result=compile_flash_source(language,source,disk.io(),true,scratch+8+FLASH_FRONTEND_BYTES);
  for(unsigned i=0;i<8+FLASH_FRONTEND_BYTES;++i)assert(scratch[i]==0xA5);
  for(unsigned i=8+FLASH_COMPILER_WORKSPACE_SIZE;i<sizeof(scratch);++i)assert(scratch[i]==0xA5);
  if(result.error!=Error::NONE)fprintf(stderr,"compile %u: %s at %u/%u\n",unsigned(language),error_name(result.error),result.line,result.source_offset);
  assert(result.error==Error::NONE && result.size>65536);
  uint8_t header[32];assert(Disk::read(&disk,IMAGE,0,header,sizeof(header)));
  assert(!memcmp(header,"LBV2",4) && header[4]==14);
  assert(flash::word(header+18)==5002 && flash::dword(header+8)==result.size);
  const uint32_t code=flash::dword(header+12);
  uint8_t first[16];assert(Disk::read(&disk,IMAGE,code,first,sizeof(first)));
  // SOURCE_POS precedes the first statement in both frontends.
  assert(first[0]==uint8_t(Op::SOURCE_POS));
  assert(first[3]==uint8_t(basic?Op::GOTO_DIRECT:Op::JUMP));
  const uint32_t target=flash::dword(first+4);
  assert(target>65536 && target<result.size);
  flash::Reader image({&disk,[](void* raw,uint32_t at,uint8_t* out,uint16_t n){return Disk::read(raw,IMAGE,at,out,n);},result.size});
  View view;
  const auto checked=inspect_flash(image,disk.io(),view);
  if(checked!=Error::NONE)fprintf(stderr,"inspect %s\n",error_name(checked));
  assert(checked==Error::NONE);
  State state={};Value variables[26]={},array[385]={},stack[MAX_STACK]={};
  state.variables=variables;state.array=array;state.array_count=385;state.stack=stack;state.stack_capacity=MAX_STACK;
  double reference=0;
  Services services={};services.context=&reference;
  services.reference=[](void* raw,bool write,uint8_t,double& value){if(write)*(double*)raw=value;else value=*(double*)raw;return true;};
  services.event=[](void*,Event,const char*,uint16_t,double&){return true;};
  const auto ran=run(view,state,services,100);
  if(ran.error!=Error::NONE)fprintf(stderr,"run %s at %u\n",error_name(ran.error),ran.pc);
  assert(ran.error==Error::NONE && reference==42 && ran.pc>65536);
  assert(disk.maximum_read<=WRITE_BYTES);
  printf("Flash compiler %s: %u lines, %zu source bytes, %u bytecode bytes, target=%u PASS\n",
      basic?"BASIC":"FOCAL",5002U,text.size(),result.size,target);
}
static void foreground_service(Language language,bool reverse) {
  const bool basic=language==Language::BASIC;
  constexpr unsigned rows=128;
  std::string text;
  for(unsigned i=0;i<rows;++i) {
    const unsigned n=reverse?rows-i:i+1;
    char line[96];
    if(basic)snprintf(line,sizeof(line),"%u A=A+1;B=B+A;C=C+B\n",n);
    else snprintf(line,sizeof(line),"%u.%03u S A=A+1;S B=B+A;S C=C+B\n",1+n/1000,n%1000);
    text+=line;
  }
  struct Foreground {
    Disk disk;
    unsigned reads=0,maximum_reads=0,polls=0;
    IO io() {
      return {this,
        [](void* raw,Space s,uint32_t at,uint8_t* out,uint16_t n) {
          auto& f=*static_cast<Foreground*>(raw);
          f.maximum_reads=std::max(f.maximum_reads,++f.reads);
          return Disk::read(&f.disk,s,at,out,n);
        },
        [](void* raw,Space s,uint32_t at,const uint8_t* in,uint16_t n) {
          return Disk::write(&static_cast<Foreground*>(raw)->disk,s,at,in,n);
        },
        [](void* raw,Space s,uint32_t n) {return Disk::truncate(&static_cast<Foreground*>(raw)->disk,s,n);},
        [](void* raw) {auto& f=*static_cast<Foreground*>(raw);++f.polls;f.reads=0;return true;}};
    }
  } foreground;
  source::Reader source(text.data(),uint16_t(text.size()));
  const auto result=compile_flash_source(language,source,foreground.io());
  assert(result.error==Error::NONE);
  // Sizing/emission, random index probes, optimization and reverse-order
  // merge must not wait for a 1-KiB output page before servicing the host.
  assert(foreground.maximum_reads<=64 && foreground.polls>=rows*4);
  Disk reference;auto io=reference.io();io.service=nullptr;
  const auto without_service=compile_flash_source(language,source,io);
  assert(without_service.error==Error::NONE && without_service.size==result.size);
  assert(reference.pages==foreground.disk.pages);
  const unsigned compiled_polls=foreground.polls;
  auto verified_io=foreground.io();
  Reader image({&foreground.disk,[](void* raw,uint32_t at,uint8_t* out,uint16_t n) {
      return Disk::read(raw,IMAGE,at,out,n);
    },result.size});
  View view;
  assert(inspect_flash(image,verified_io,view)==Error::NONE);
  assert(result.size<=WRITE_BYTES*8); // No scratch Writer can hide missing polls.
  const unsigned crc_polls=(result.size-HEADER_BYTES+63)/64;
  assert(foreground.polls-compiled_polls>=crc_polls+rows*3/32);
  // Refuse a partial verification when service fails after CRC scanning,
  // rather than ignoring cancellation throughout both instruction passes.
  unsigned verify_polls=0;
  auto interrupted_io=verified_io;
  struct VerifyStop {IO io;unsigned* count;unsigned limit;} stop={verified_io,&verify_polls,crc_polls};
  interrupted_io.context=&stop;
  interrupted_io.read=[](void* raw,Space s,uint32_t at,uint8_t* out,uint16_t n) {
    auto& f=*static_cast<VerifyStop*>(raw);return f.io.read(f.io.context,s,at,out,n);
  };
  interrupted_io.write=[](void* raw,Space s,uint32_t at,const uint8_t* in,uint16_t n) {
    auto& f=*static_cast<VerifyStop*>(raw);return f.io.write(f.io.context,s,at,in,n);
  };
  interrupted_io.truncate=[](void* raw,Space s,uint32_t n) {
    auto& f=*static_cast<VerifyStop*>(raw);return f.io.truncate(f.io.context,s,n);
  };
  interrupted_io.service=[](void* raw) {auto& f=*static_cast<VerifyStop*>(raw);return ++*f.count<=f.limit;};
  View refused;
  assert(inspect_flash(image,interrupted_io,refused)==Error::IO && !refused.size);

  // STOP from either indexing or a frontend's next record is retained,
  // rather than returning an executable partial image.
  Disk cancelled;io=cancelled.io();io.service=[](void*){return false;};
  assert(compile_flash_source(language,source,io).error==Error::STOPPED);
  // Program holds a copy of IO. Create a prepared instance with an armed
  // callback to stop specifically at line access after indexing succeeds.
  struct Cancel {Disk disk;bool stop=false;} cancel;
  io={&cancel,
    [](void* p,Space s,uint32_t at,uint8_t* out,uint16_t n){return Disk::read(&static_cast<Cancel*>(p)->disk,s,at,out,n);},
    [](void* p,Space s,uint32_t at,const uint8_t* in,uint16_t n){return Disk::write(&static_cast<Cancel*>(p)->disk,s,at,in,n);},
    [](void* p,Space s,uint32_t n){return Disk::truncate(&static_cast<Cancel*>(p)->disk,s,n);},
    [](void* p){return !static_cast<Cancel*>(p)->stop;}};
  Program interrupted(source,io);assert(interrupted.prepare(language));
  cancel.stop=true;(void)interrupted.line(0);
  assert(interrupted.error()==Error::STOPPED);
  printf("Flash compiler foreground %s reverse=%d: max %u reads between %u polls, identical image, STOP PASS\n",
      basic?"BASIC":"FOCAL",reverse,foreground.maximum_reads,foreground.polls);
}
int main() {
  compile_many(Language::BASIC);compile_many(Language::FOCAL);
  for(auto language:{Language::BASIC,Language::FOCAL})
    for(bool reverse:{false,true})foreground_service(language,reverse);
}
