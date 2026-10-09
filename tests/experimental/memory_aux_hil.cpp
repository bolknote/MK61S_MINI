// Qualification-only APP: actual pinned resident helpers in Flash plus
// matched byte/unrolled controls in SRAM. It never replaces resident code.
#include "mk61_app.h"
#include "memory_aux_candidates.hpp"
#include "memory_aux_resident.hpp" // generated from the exact sealed ELF/BIN
#include <string.h>
static const unsigned lengths[] = {0,1,2,3,4,7,8,16,32,128,512,2048};
static constexpr unsigned page_count = sizeof(lengths) / sizeof(lengths[0]) * 7;
alignas(4) static unsigned char buffer[8192];
alignas(4) static char left[2054], right[2054];
// 64-byte header, at most 60 timing triples, and two 32-byte code anchors.
// Base64 fits the public TEXT file limit (1536 bytes) without Flash APIs.
static unsigned char report[848];
static uint32_t failures, rows, demcr_before, control_before;
static volatile uint32_t sink;
static const mk61_app_services* services;
#define KERNEL __attribute__((noipa,aligned(16),optimize("Os")))
using Function = uintptr_t(*)(unsigned char*,const unsigned char*,size_t,int);
extern "C" KERNEL uintptr_t aux_move_resident(unsigned char* d,const unsigned char* s,size_t n,int) {return (uintptr_t)memmove(d,s,n);}
extern "C" KERNEL uintptr_t aux_move_scalar(unsigned char* d,const unsigned char* s,size_t n,int) {return (uintptr_t)memory_aux::move_scalar(d,s,n);}
extern "C" KERNEL uintptr_t aux_move_word(unsigned char* d,const unsigned char* s,size_t n,int) {return (uintptr_t)memory_aux::move_word(d,s,n);}
extern "C" KERNEL uintptr_t aux_fill_resident(unsigned char* d,const unsigned char*,size_t n,int v) {return (uintptr_t)memset(d,v,n);}
extern "C" KERNEL uintptr_t aux_fill_scalar(unsigned char* d,const unsigned char*,size_t n,int v) {return (uintptr_t)memory_aux::fill_scalar(d,v,n);}
extern "C" KERNEL uintptr_t aux_fill_word(unsigned char* d,const unsigned char*,size_t n,int v) {return (uintptr_t)memory_aux::fill_word(d,v,n);}
extern "C" KERNEL uintptr_t aux_length_resident(unsigned char* d,const unsigned char*,size_t,int) {return strlen((const char*)d);}
extern "C" KERNEL uintptr_t aux_length_scalar(unsigned char* d,const unsigned char*,size_t,int) {return memory_aux::length_scalar((const char*)d);}
extern "C" KERNEL uintptr_t aux_length_unrolled(unsigned char* d,const unsigned char*,size_t,int) {return memory_aux::length_unrolled((const char*)d);}
extern "C" KERNEL uintptr_t aux_nlength_resident(unsigned char* d,const unsigned char*,size_t n,int) {return ((size_t(*)(const char*,size_t))(uintptr_t) AUX_RESIDENT_STRNLEN)((const char*)d,n);}
extern "C" KERNEL uintptr_t aux_nlength_scalar(unsigned char* d,const unsigned char*,size_t n,int) {return memory_aux::bounded_length_scalar((const char*)d,n);}
extern "C" KERNEL uintptr_t aux_nlength_unrolled(unsigned char* d,const unsigned char*,size_t n,int) {return memory_aux::bounded_length_unrolled((const char*)d,n);}
extern "C" KERNEL uintptr_t aux_compare_resident(unsigned char* d,const unsigned char* s,size_t,int) {return (uintptr_t)((int(*)(const char*,const char*))(uintptr_t) AUX_RESIDENT_STRCMP)((const char*)d,(const char*)s);}
extern "C" KERNEL uintptr_t aux_compare_scalar(unsigned char* d,const unsigned char* s,size_t,int) {return (uintptr_t)memory_aux::string_compare_scalar((const char*)d,(const char*)s);}
extern "C" KERNEL uintptr_t aux_compare_unrolled(unsigned char* d,const unsigned char* s,size_t,int) {return (uintptr_t)memory_aux::string_compare_unrolled((const char*)d,(const char*)s);}
extern "C" KERNEL uintptr_t aux_ncompare_resident(unsigned char* d,const unsigned char* s,size_t n,int) {return (uintptr_t)strncmp((const char*)d,(const char*)s,n);}
extern "C" KERNEL uintptr_t aux_ncompare_scalar(unsigned char* d,const unsigned char* s,size_t n,int) {return (uintptr_t)memory_aux::bounded_compare_scalar((const char*)d,(const char*)s,n);}
extern "C" KERNEL uintptr_t aux_ncompare_unrolled(unsigned char* d,const unsigned char* s,size_t n,int) {return (uintptr_t)memory_aux::bounded_compare_unrolled((const char*)d,(const char*)s,n);}
extern "C" KERNEL uintptr_t aux_copy_resident(unsigned char* d,const unsigned char* s,size_t n,int) {return (uintptr_t)memcpy(d,s,n);}
extern "C" KERNEL uintptr_t aux_copy_scalar(unsigned char* d,const unsigned char* s,size_t n,int) {for(size_t i=0;i<n;++i)d[i]=s[i];return (uintptr_t)d;}
extern "C" KERNEL uintptr_t aux_copy_word(unsigned char* d,const unsigned char* s,size_t n,int) {return (uintptr_t)mk61_memory_copy(d,s,n);}
static const Function kernels[][3] = {
 {aux_move_resident,aux_move_scalar,aux_move_word}, {aux_fill_resident,aux_fill_scalar,aux_fill_word},
 {aux_length_resident,aux_length_scalar,aux_length_unrolled}, {aux_nlength_resident,aux_nlength_scalar,aux_nlength_unrolled},
 {aux_compare_resident,aux_compare_scalar,aux_compare_unrolled}, {aux_ncompare_resident,aux_ncompare_scalar,aux_ncompare_unrolled},
 {aux_copy_resident,aux_copy_scalar,aux_copy_word}};
static volatile uint32_t& reg(uint32_t a) {return *(volatile uint32_t*)(uintptr_t)a;}
static uint32_t cycles() {__asm__ __volatile__("" ::: "memory");uint32_t n=reg(0xE0001004U);__asm__ __volatile__("" ::: "memory");return n;}
static void put8(unsigned at,unsigned char n) {report[at]=n;}
static void put32(unsigned at,uint32_t n) {for(unsigned i=0;i<4;++i)put8(at+i,(unsigned char)(n>>(i*8)));}
static unsigned scenarios(unsigned family) {return family==0?5:family==1||family==3?2:family==4||family==5?3:1;}
static int shift(unsigned scenario) {const int moves[]={-17,-1,0,1,17};return moves[scenario];}
static unsigned char pattern(unsigned i) {return (unsigned char)(i*37+13);}
static void prepare(unsigned family,unsigned scenario,unsigned align,unsigned n,unsigned char*& d,const unsigned char*& s,size_t& limit,int& value) {
  d=buffer+3072+align;s=buffer+3072+align;limit=n;value=scenario?0x1234:0;
  if(family==0)d+=shift(scenario);
  if(family==6)d+=n+32;
  if(family==0||family==1||family==6) {for(unsigned i=0;i<sizeof(buffer);++i)buffer[i]=pattern(i);return;}
  char* a=left+align;char* b=right+((align+1)&3);
  for(unsigned i=0;i<n;++i)a[i]=b[i]=(char)(1+i*37%255);
  a[n]=b[n]=a[n+1]=b[n+1]=0;
  if((family==4||family==5)&&scenario)b[scenario==1?0:n?n-1:0]^=0x81;
  d=(unsigned char*)a;s=(const unsigned char*)b;
  if(family==3)limit=scenario?n+8:n;
  if(family==5)limit=n+1;
}
static int sign(uintptr_t n) {const int32_t v=(int32_t)n;return(v>0)-(v<0);}
static void validate(unsigned family,unsigned scenario,unsigned align,unsigned n,unsigned variant) {
  unsigned char* d;const unsigned char* s;size_t limit;int value;
  prepare(family,scenario,align,n,d,s,limit,value);
  const uintptr_t result=kernels[family][variant](d,s,limit,value);
  if(family==0||family==1||family==6) {
    if(result!=(uintptr_t)d)++failures;
    const unsigned begin=(unsigned)(d-buffer);
    const int offset=family==0?shift(scenario):(int)(n+32);
    for(unsigned i=0;i<sizeof(buffer);++i) {
      const bool written=i>=begin&&i-begin<n;
      const unsigned char expected=written?(family==1?(unsigned char)value:pattern((unsigned)((int)i-offset))):pattern(i);
      if(buffer[i]!=expected){++failures;break;}
    }
  } else if(family==2||family==3) {if(result!=n)++failures;}
  else {
    const int expected=family==4?memory_aux::string_compare_scalar((char*)d,(const char*)s):
        memory_aux::bounded_compare_scalar((char*)d,(const char*)s,limit);
    if(sign(result)!=sign((uintptr_t)expected))++failures;
  }
}
static void measure(unsigned family,unsigned scenario,unsigned align,unsigned n,unsigned variant) {
  validate(family,scenario,align,n,variant);
  const unsigned iterations=n<=16?512:n<=128?256:n<=512?128:32;
  constexpr unsigned samples=7;uint32_t times[samples];
  const Function function=kernels[family][variant];
  for(unsigned sample=0;sample<samples;++sample) {
    unsigned char* d;const unsigned char* s;size_t limit;int value;
    prepare(family,scenario,align,n,d,s,limit,value);
    for(unsigned i=0;i<4;++i)sink+=(uint32_t)function(d,s,limit,value);
    const uint32_t start=cycles();
    for(unsigned i=0;i<iterations;++i)sink+=(uint32_t)function(d,s,limit,value);
    times[sample]=cycles()-start;mk61_api->service();
  }
  for(unsigned i=1;i<samples;++i){const uint32_t t=times[i];unsigned j=i;while(j&&times[j-1]>t){times[j]=times[j-1];--j;}times[j]=t;}
  // Scenario/alignment/variant order and iterations follow the fixed matrix;
  // store only the three measured totals to keep the public file bounded.
  const unsigned at=64+rows*12;
  put32(at,times[0]);put32(at+4,times[3]);put32(at+8,times[6]);++rows;
}
static void benchmark(unsigned page) {
  __builtin_memset(report,0,sizeof(report));rows=0;
  const unsigned family=page%7,n=lengths[page/7];
  for(unsigned scenario=0;scenario<scenarios(family);++scenario)for(unsigned align=0;align<4;++align)
    for(unsigned order=0;order<3;++order)measure(family,scenario,align,n,(page+order)%3);
  report[0]='M';report[1]='A';report[2]='U';report[3]='2';
  put32(4,2);put32(8,page);put32(12,rows);put32(16,failures);put32(20,n);put32(24,family);put32(28,page_count);
  put32(32,demcr_before);put32(36,control_before);put32(40,sink);
  put32(44,(uint32_t)(uintptr_t)services->runtime[MK61_RUNTIME_SLOT_memmove]);
  put32(48,(uint32_t)(uintptr_t)services->runtime[MK61_RUNTIME_SLOT_memset]);
  put32(52,AUX_RESIDENT_STRCMP);put32(56,AUX_RESIDENT_STRNLEN);
  put32(60,(uint32_t)(uintptr_t)services->runtime[MK61_RUNTIME_SLOT_memcpy]);
  for(unsigned i=0;i<32;++i){put8(64+rows*12+i,((const unsigned char*)(uintptr_t)(AUX_RESIDENT_STRCMP&~1U))[i]);put8(96+rows*12+i,((const unsigned char*)(uintptr_t)(AUX_RESIDENT_STRNLEN&~1U))[i]);}
}
static bool save_report(unsigned page) {
  static const char alphabet[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const unsigned size=128+rows*12;
  unsigned at=0;
  for(unsigned i=0;i<size;i+=3) {
    const unsigned n=(unsigned)report[i]<<16|(i+1<size?(unsigned)report[i+1]<<8:0)|(i+2<size?report[i+2]:0);
    buffer[at++]=alphabet[(n>>18)&63];buffer[at++]=alphabet[(n>>12)&63];
    buffer[at++]=i+1<size?alphabet[(n>>6)&63]:'=';buffer[at++]=i+2<size?alphabet[n&63]:'=';
  }
  char name[]="MEMAUX00";name[6]=(char)('0'+page/10);name[7]=(char)('0'+page%10);
  mk61_service_write file={name,buffer,at,MK61_SERVICE_INVALID_ID};
  return services->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,
                       MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_TEXT,&file)!=0;
}
extern "C" int main() {
  if(!mk61_app_api_compatible(mk61_api,sizeof(*mk61_api),MK61_APP_CAP_TIME))return MK61_APP_RUNTIME_ERROR;
  services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_RUNTIME|MK61_SERVICE_CAP_FILES);
  if(!services||!services->runtime||(uintptr_t)services->runtime[MK61_RUNTIME_SLOT_memcpy]!=AUX_ANCHOR_MEMCPY||
      (uintptr_t)services->runtime[MK61_RUNTIME_SLOT_memcmp]!=AUX_ANCHOR_MEMCMP)return MK61_APP_RUNTIME_ERROR;
  failures=0;sink=0;demcr_before=reg(0xE000EDFCU);control_before=reg(0xE0001000U);
  reg(0xE000EDFCU)=demcr_before|(1U<<24);reg(0xE0001000U)=control_before|1U;
  int result=MK61_APP_OK;
  for(unsigned page=0;page<page_count;++page) {
    benchmark(page);
    if(!save_report(page)||failures){result=MK61_APP_RUNTIME_ERROR;break;}
    mk61_api->service();
  }
  reg(0xE0001000U)=control_before;reg(0xE000EDFCU)=demcr_before;return result;
}
