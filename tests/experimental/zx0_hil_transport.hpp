#ifndef MK61_ZX0_HIL_TRANSPORT_HPP
#define MK61_ZX0_HIL_TRANSPORT_HPP
#include "mk61_app.h"
#include "zx0_bench_fixture.hpp"
#include <string.h>
static const mk61_app_services* services;
static u8 report[384],base64_report[512];
static u32 failures,rows,demcr_before,control_before;
static volatile u32 checksum;
static volatile u32& reg(u32 at) {return *(volatile u32*)(uintptr_t)at;}
static u32 cycles() {
  __asm__ __volatile__("":::"memory");const u32 value=reg(0xE0001004U);
  __asm__ __volatile__("":::"memory");return value;
}
static void put32(unsigned at,u32 value) {
  for(unsigned i=0;i<4;++i)report[at+i]=(u8)(value>>(i*8));
}
static void row(unsigned variant,unsigned align,unsigned iterations,u32* times) {
  for(unsigned i=1;i<7;++i) {
    const u32 value=times[i];unsigned j=i;
    while(j&&times[j-1]>value){times[j]=times[j-1];--j;}times[j]=value;
  }
  const unsigned at=64+20*rows++;
  report[at]=(u8)variant;report[at+1]=(u8)align;report[at+2]=1;
  put32(at+4,iterations);put32(at+8,times[0]);put32(at+12,times[3]);put32(at+16,times[6]);
}
static bool store_report(unsigned index,unsigned local) {
  const auto& test=bench_cases[index];
  report[0]='Z';report[1]='X';report[2]='0';report[3]='1';
  put32(4,1);put32(8,index);put32(12,rows);put32(16,failures);
  put32(20,test.family);put32(24,test.size);put32(28,test.parameter);put32(32,test.pattern);
  put32(36,ZX0_BENCH_KIND);put32(40,demcr_before);put32(44,control_before);
  put32(48,checksum);put32(52,bench_case_count);
#if defined(__ARM_FEATURE_SIMD32)
  put32(56,1);
#endif
  static const char alphabet[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  unsigned at=0;
  for(unsigned i=0;i<sizeof(report);i+=3) {
    const u32 value=(u32)report[i]<<16|(u32)report[i+1]<<8|report[i+2];
    base64_report[at++]=alphabet[(value>>18)&63];base64_report[at++]=alphabet[(value>>12)&63];
    base64_report[at++]=alphabet[(value>>6)&63];base64_report[at++]=alphabet[value&63];
  }
  char name[]="ZX0R00";name[4]=(char)('0'+local/10);name[5]=(char)('0'+local%10);
  mk61_service_write file={name,base64_report,at,MK61_SERVICE_INVALID_ID};
  return services->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_TEXT,&file)!=0;
}
static void native_checks();
static void benchmark(unsigned index);
extern "C" int main() {
  if(!mk61_app_api_compatible(mk61_api,sizeof(*mk61_api),MK61_APP_CAP_TIME|MK61_APP_CAP_FILES))return MK61_APP_RUNTIME_ERROR;
  services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
  if(!services)return MK61_APP_RUNTIME_ERROR;
  mk61_service_file control={};const char* path="/ZX0CFG.txt";u8 selected=0;
  constexpr unsigned chunks=(bench_case_count+7)/8;
  static_assert(chunks<=26,"one-letter control exhausted");
  if(services->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_TEXT,(u32)(uintptr_t)path,&control)!=0||
     mk61_api->file_size(control.id)!=1||mk61_api->file_read(control.id,0,&selected,1)!=1||
     selected<'A'||selected>='A'+chunks)return MK61_APP_RUNTIME_ERROR;
  failures=rows=0;checksum=0;
  if(selected=='A')native_checks();
  demcr_before=reg(0xE000EDFCU);control_before=reg(0xE0001000U);
  reg(0xE000EDFCU)=demcr_before|(1U<<24);reg(0xE0001000U)=control_before|1U;
  int result=MK61_APP_OK;
  const unsigned first=(selected-'A')*8;
  for(unsigned local=0;local<8&&first+local<bench_case_count;++local) {
    memset(report,0,sizeof(report));rows=0;benchmark(first+local);
    if(!store_report(first+local,local)||failures){result=MK61_APP_RUNTIME_ERROR;break;}
    mk61_api->service();
  }
  if(result==MK61_APP_OK) {
    selected=(u8)('A'+(selected-'A'+1)%chunks);
    mk61_service_write next={"ZX0CFG",&selected,1,control.id};
    if(!services->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,control.id,MK61_SERVICE_FILE_TEXT,&next))result=MK61_APP_RUNTIME_ERROR;
  }
  reg(0xE0001000U)=control_before;reg(0xE000EDFCU)=demcr_before;
  return result;
}
#endif
