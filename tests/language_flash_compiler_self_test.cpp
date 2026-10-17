#include "language_flash_fixture.hpp"
#include "language_vm_abi.hpp"
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
int main() {compile_many(Language::BASIC);compile_many(Language::FOCAL);}
