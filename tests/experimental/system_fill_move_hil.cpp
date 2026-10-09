// One unchanged APP measures the real public-runtime Flash functions in
// matched baseline/candidate residents. Results use only public FILE_WRITE.
#include "mk61_app.h"
#include <string.h>
static const unsigned lengths[]={0,1,2,3,4,5,6,7,8,9,12,15,16,17,31,32,33,63,64,65,128,256,512,2048,8192};
static constexpr unsigned pages=sizeof(lengths)/sizeof(lengths[0])*2;
alignas(4) static unsigned char buffer[2*8192+64];
static unsigned char report[688];
static uint32_t rows,failures,demcr_before,control_before;
static volatile uint32_t sink;
static const mk61_app_services* services;
using Function=void*(*)(unsigned char*,const unsigned char*,size_t,int);
#define KERNEL __attribute__((noipa,aligned(16),optimize("Os")))
extern "C" KERNEL void* fill_move_call_move(unsigned char* d,const unsigned char* s,size_t n,int) {return memmove(d,s,n);}
extern "C" KERNEL void* fill_move_call_fill(unsigned char* d,const unsigned char*,size_t n,int v) {return memset(d,v,n);}
static const Function functions[]={fill_move_call_move,fill_move_call_fill};
static volatile uint32_t& reg(uint32_t a) {return *(volatile uint32_t*)(uintptr_t)a;}
static uint32_t cycles() {__asm__ __volatile__("" ::: "memory");uint32_t n=reg(0xE0001004U);__asm__ __volatile__("" ::: "memory");return n;}
static void put32(unsigned at,uint32_t n) {for(unsigned i=0;i<4;++i)report[at+i]=(unsigned char)(n>>(8*i));}
static unsigned char pattern(unsigned i) {return (unsigned char)(i*37+13);}
static unsigned scenarios(unsigned family) {return family?3:7;}
static void prepare(unsigned family,unsigned scenario,unsigned align,unsigned n,unsigned char*& d,const unsigned char*& s,int& value) {
  d=buffer+32+align;s=d;value=scenario==0?0:scenario==1?-1:0x1234;
  if(!family) {
    const int shifts[]={-17,-1,0,1,17};
    if(scenario<5)d+=shifts[scenario];
    else if(scenario==5)d+=n+17;
    else s+=n+17;
  }
  for(unsigned i=0;i<sizeof(buffer);++i)buffer[i]=pattern(i);
}
static void measure(unsigned family,unsigned scenario,unsigned align,unsigned n) {
  unsigned char* d;const unsigned char* s;int value;
  prepare(family,scenario,align,n,d,s,value);
  const unsigned begin=(unsigned)(d-buffer),source=(unsigned)(s-buffer);
  if(functions[family](d,s,n,value)!=d)++failures;
  for(unsigned i=0;i<sizeof(buffer);++i) {
    const bool written=i>=begin&&i-begin<n;
    const unsigned char expected=written?(family?(unsigned char)value:pattern(source+i-begin)):pattern(i);
    if(buffer[i]!=expected){++failures;break;}
  }
  const unsigned iterations=n<=16?512:n<=128?256:n<=512?128:n<=2048?32:8;
  uint32_t times[7];
  for(unsigned sample=0;sample<7;++sample) {
    prepare(family,scenario,align,n,d,s,value);
    for(unsigned i=0;i<4;++i)sink+=(uint32_t)(uintptr_t)functions[family](d,s,n,value);
    const uint32_t start=cycles();
    for(unsigned i=0;i<iterations;++i)sink+=(uint32_t)(uintptr_t)functions[family](d,s,n,value);
    times[sample]=cycles()-start;mk61_api->service();
  }
  for(unsigned i=1;i<7;++i){const uint32_t v=times[i];unsigned j=i;while(j&&times[j-1]>v){times[j]=times[j-1];--j;}times[j]=v;}
  const unsigned at=64+rows*20;
  report[at]=(unsigned char)family;report[at+1]=(unsigned char)align;report[at+2]=(unsigned char)scenario;report[at+3]=0;
  put32(at+4,iterations);put32(at+8,times[0]);put32(at+12,times[3]);put32(at+16,times[6]);++rows;
}
static bool benchmark(unsigned page) {
  __builtin_memset(report,0,sizeof(report));rows=0;
  const unsigned family=page%2,n=lengths[page/2];
  for(unsigned scenario=0;scenario<scenarios(family);++scenario)
    for(unsigned align=0;align<4;++align)measure(family,scenario,align,n);
  report[0]='F';report[1]='M';report[2]='C';report[3]='1';
  put32(4,1);put32(8,page);put32(12,rows);put32(16,failures);put32(20,n);put32(24,family);put32(28,pages);
  put32(32,demcr_before);put32(36,control_before);put32(40,sink);
  const unsigned slots[]={MK61_RUNTIME_SLOT_memmove,MK61_RUNTIME_SLOT_memset,MK61_RUNTIME_SLOT_memcpy,MK61_RUNTIME_SLOT_memcmp};
  for(unsigned i=0;i<4;++i)put32(44+i*4,(uint32_t)(uintptr_t)services->runtime[slots[i]]);
  for(unsigned f=0;f<2;++f) {
    const auto* code=(const unsigned char*)((uintptr_t)services->runtime[slots[f]]&~1U);
    for(unsigned i=0;i<32;++i)report[64+rows*20+f*32+i]=code[i];
  }
  static const char alphabet[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const unsigned size=128+rows*20;unsigned at=0;
  for(unsigned i=0;i<size;i+=3) {
    const unsigned v=(unsigned)report[i]<<16|(i+1<size?(unsigned)report[i+1]<<8:0)|(i+2<size?report[i+2]:0);
    buffer[at++]=alphabet[(v>>18)&63];buffer[at++]=alphabet[(v>>12)&63];
    buffer[at++]=i+1<size?alphabet[(v>>6)&63]:'=';buffer[at++]=i+2<size?alphabet[v&63]:'=';
  }
  char name[]="FILMOV00";name[6]=(char)('0'+page/10);name[7]=(char)('0'+page%10);
  mk61_service_write file={name,buffer,at,MK61_SERVICE_INVALID_ID};
  return services->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_TEXT,&file)!=0;
}
extern "C" int main() {
  if(!mk61_app_api_compatible(mk61_api,sizeof(*mk61_api),MK61_APP_CAP_TIME))return MK61_APP_RUNTIME_ERROR;
  services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_RUNTIME|MK61_SERVICE_CAP_FILES);
  if(!services||!services->runtime)return MK61_APP_RUNTIME_ERROR;
  demcr_before=reg(0xE000EDFCU);control_before=reg(0xE0001000U);failures=0;sink=0;
  reg(0xE000EDFCU)=demcr_before|(1U<<24);reg(0xE0001000U)=control_before|1U;
  int result=MK61_APP_OK;
  for(unsigned page=0;page<pages;++page)if(!benchmark(page)||failures){result=MK61_APP_RUNTIME_ERROR;break;}
  reg(0xE0001000U)=control_before;reg(0xE000EDFCU)=demcr_before;return result;
}
