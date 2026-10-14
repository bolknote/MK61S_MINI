// Full sizing + owned-resource EMIT in an ordinary APP. The compiler copy
// and sources are prepared privately; native timing excludes file/USB I/O.
#include "mk61_app.h"
#define MK61_MATH_BACKEND 1
#include "language_bytecode.hpp"
#include "vm_compile_fixture.hpp"

static uint8_t report[1536];
static uint8_t image[VM_COMPILE_IMAGE_CAPACITY];
static constexpr uint32_t image_capacity=sizeof(image);
static uint32_t failures;
static uint32_t latest_size,latest_crc;
static volatile uint32_t sink;
static volatile uint32_t& reg(uint32_t address) { return *(volatile uint32_t*)(uintptr_t)address; }
static uint32_t cycles() {
  __asm__ __volatile__("" ::: "memory");
  const uint32_t value=reg(0xE0001004U);
  __asm__ __volatile__("" ::: "memory");
  return value;
}
static void put8(unsigned at,uint8_t value) {
  report[at+(at>=176 ? 16 : 0)+(at>=352 ? 16 : 0)]=value;
}
static void put32(unsigned at,uint32_t value) {
  for(unsigned i=0;i<4;++i) put8(at+i,(uint8_t)(value>>(i*8)));
}
static language_vm::CompileResult compile(unsigned dataset,uint8_t* output) {
  const CompileSource& source=compile_sources[dataset];
  language_vm::ResourceSource resources={42,1};
  resources.mode=language_vm::ResourceMode::EMBEDDED;
#if VM_COMPILE_FOCAL
  return language_vm::compile_focal(source.data,source.length,output,
      (uint16_t)image_capacity,true,&resources);
#else
  return language_vm::compile_basic(source.data,source.length,output,
      (uint16_t)image_capacity,true,&resources);
#endif
}
static bool compile_pair(unsigned dataset) {
  const auto sized=compile(dataset,nullptr);
  if(sized.error!=language_vm::Error::NONE) {++failures;return false;}
  const auto emitted=compile(dataset,image);
  latest_size=emitted.size;
  if(emitted.error!=language_vm::Error::NONE || latest_size!=compile_sources[dataset].image_bytes) {
    ++failures;return false;
  }
  sink+=latest_size;
  return true;
}
static void stats_frame() {
  __builtin_memset(report,0,sizeof(report));
  constexpr unsigned samples=7,iterations=3;
  for(unsigned dataset=0;dataset<compile_source_count;++dataset) {
    for(unsigned i=0;i<2;++i) (void)compile_pair(dataset);
    uint32_t times[samples];
    for(unsigned sample=0;sample<samples;++sample) {
      const uint32_t started=cycles();
      for(unsigned i=0;i<iterations;++i) (void)compile_pair(dataset);
      times[sample]=cycles()-started;
      mk61_api->service();
    }
    for(unsigned i=1;i<samples;++i) {
      const uint32_t value=times[i];unsigned j=i;
      while(j && times[j-1]>value) {times[j]=times[j-1];--j;}
      times[j]=value;
    }
    latest_crc=language_vm::checksum(image,latest_size);
    if(latest_crc!=compile_sources[dataset].image_crc) ++failures;
    const unsigned at=40+dataset*24;
    put32(at,latest_size);put32(at+4,latest_crc);put32(at+8,iterations);
    put32(at+12,times[0]);put32(at+16,times[samples/2]);put32(at+20,times[samples-1]);
  }
  report[0]='V';report[1]='C';report[2]='C';report[3]='1';
  put32(4,1);put32(8,VM_COMPILE_VARIANT);put32(12,compile_source_count);
  put32(16,failures);put32(20,VM_COMPILE_FOCAL);
  put32(24,(uint32_t)(uintptr_t)compile_pair);put32(28,sink);
}
static unsigned image_frame(unsigned dataset,unsigned offset) {
  __builtin_memset(report,0,sizeof(report));
  if(!offset) {
    (void)compile_pair(dataset);
    latest_crc=language_vm::checksum(image,latest_size);
  }
  const unsigned available=latest_size-offset;
  const unsigned count=available<1464 ? available : 1464;
  report[0]='V';report[1]='C';report[2]='I';report[3]='1';
  put32(4,1);put32(8,dataset);put32(12,latest_size);put32(16,offset);
  put32(20,count);put32(24,latest_crc);put32(28,failures);
  for(unsigned i=0;i<count;++i) put8(40+i,image[offset+i]);
  return offset+count;
}
extern "C" int main() {
  if(!mk61_app_api_compatible(mk61_api,sizeof(*mk61_api),
       MK61_APP_CAP_TIME|MK61_APP_CAP_GRAPHICS|MK61_APP_CAP_KEYBOARD)) return MK61_APP_RUNTIME_ERROR;
  failures=0;sink=0;
  const uint32_t demcr=reg(0xE000EDFCU),control=reg(0xE0001000U);
  reg(0xE000EDFCU)=demcr|(1U<<24);reg(0xE0001000U)=control|1U;
  int result=MK61_APP_OK;
  if(!mk61_api->graphics_begin()) result=MK61_APP_RUNTIME_ERROR;
  else {
    stats_frame();(void)mk61_api->graphics_present(report,sizeof(report));
    unsigned dataset=0,offset=0;
    for(;;) {
      const int key=mk61_api->key_poll();
      if(key==MK61_APP_KEY_ESC) break;
      if(key==MK61_APP_KEY_DIGIT_1 && dataset<compile_source_count) {
        offset=image_frame(dataset,offset);
        (void)mk61_api->graphics_present(report,sizeof(report));
        if(offset==latest_size) {++dataset;offset=0;}
      }
      mk61_api->delay_ms(1);
    }
    mk61_api->graphics_end();
    if(failures) result=MK61_APP_RUNTIME_ERROR;
  }
  reg(0xE0001000U)=control;reg(0xE000EDFCU)=demcr;
  return result;
}
