// Ordinary APP measuring the shared resident helpers and matched SRAM kernels.
// No firmware patches, private callbacks, filesystem or SPI in timed batches.
#include "mk61_app.h"
#include "fs_sector_candidates.hpp"
#include <string.h>

namespace c=fs_sector_candidates;
#define KERNEL __attribute__((noipa,flatten,aligned(16),optimize("Oz")))
using Function=uint32_t(*)(uint8_t*,const uint8_t*,size_t);
alignas(4) static uint8_t source_storage[516],alternate_storage[516],target_storage[516];
static uint8_t report[1536];
static volatile uint32_t sink;
static uint32_t failures,rows,control_before,demcr_before;
static const mk61_app_services* services;
static constexpr unsigned patterns=5,page_count=patterns*4;
static constexpr unsigned positions[]={0,0,4,255,511};

extern "C" KERNEL uint32_t sector_lib_compare(uint8_t* a,const uint8_t* b,size_t n) {return (uint32_t)memcmp(a,b,n);}
extern "C" KERNEL uint32_t sector_scalar_compare(uint8_t* a,const uint8_t* b,size_t n) {return (uint32_t)c::compare_scalar(a,b,n);}
extern "C" KERNEL uint32_t sector_word_compare(uint8_t* a,const uint8_t* b,size_t n) {return (uint32_t)c::compare_word(a,b,n);}
extern "C" KERNEL uint32_t sector_dsp_compare(uint8_t* a,const uint8_t* b,size_t n) {return (uint32_t)c::compare_dsp(a,b,n);}
extern "C" KERNEL uint32_t sector_word_equal_full(uint8_t* a,const uint8_t* b,size_t n) {return !c::equal_word_full(a,b,n);}
extern "C" KERNEL uint32_t sector_dsp_equal_full(uint8_t* a,const uint8_t* b,size_t n) {return !c::equal_dsp_full(a,b,n);}
extern "C" KERNEL uint32_t sector_lib_copy(uint8_t* a,const uint8_t* b,size_t n) {(void)memcpy(a,b,n);return 0;}
extern "C" KERNEL uint32_t sector_scalar_copy(uint8_t* a,const uint8_t* b,size_t n) {c::copy_scalar(a,b,n);return 0;}
extern "C" KERNEL uint32_t sector_word_copy(uint8_t* a,const uint8_t* b,size_t n) {c::copy_word(a,b,n);return 0;}
extern "C" KERNEL uint32_t sector_unrolled_copy(uint8_t* a,const uint8_t* b,size_t n) {c::copy_word_unrolled(a,b,n);return 0;}
extern "C" KERNEL uint32_t sector_lib_update(uint8_t* a,const uint8_t* b,size_t n) {if(memcmp(a,b,n)==0) return 0;(void)memcpy(a,b,n);return 1;}
extern "C" KERNEL uint32_t sector_scalar_update(uint8_t* a,const uint8_t* b,size_t n) {if(c::equal_scalar(a,b,n)) return 0;c::copy_scalar(a,b,n);return 1;}
extern "C" KERNEL uint32_t sector_word_update(uint8_t* a,const uint8_t* b,size_t n) {if(c::compare_word(a,b,n)==0) return 0;c::copy_word(a,b,n);return 1;}
extern "C" KERNEL uint32_t sector_dsp_update(uint8_t* a,const uint8_t* b,size_t n) {if(c::compare_dsp(a,b,n)==0) return 0;c::copy_word(a,b,n);return 1;}
extern "C" KERNEL uint32_t sector_word_full_update(uint8_t* a,const uint8_t* b,size_t n) {if(c::equal_word_full(a,b,n)) return 0;c::copy_word(a,b,n);return 1;}
extern "C" KERNEL uint32_t sector_dsp_full_update(uint8_t* a,const uint8_t* b,size_t n) {if(c::equal_dsp_full(a,b,n)) return 0;c::copy_word(a,b,n);return 1;}
static const Function kernels[]={sector_lib_compare,sector_scalar_compare,sector_word_compare,sector_dsp_compare,
  sector_word_equal_full,sector_dsp_equal_full,sector_lib_copy,sector_scalar_copy,sector_word_copy,sector_unrolled_copy,
  sector_lib_update,sector_scalar_update,sector_word_update,sector_dsp_update,sector_word_full_update,sector_dsp_full_update};

static volatile uint32_t& reg(uint32_t address) {return *(volatile uint32_t*)(uintptr_t)address;}
static uint32_t cycles() {
  __asm__ __volatile__("" ::: "memory");const uint32_t value=reg(0xE0001004U);
  __asm__ __volatile__("" ::: "memory");return value;
}
static void put8(unsigned at,uint8_t value) {report[at+(at>=176 ? 16 : 0)+(at>=352 ? 16 : 0)]=value;}
static void put32(unsigned at,uint32_t value) {for(unsigned i=0;i<4;++i) put8(at+i,(uint8_t)(value>>(i*8)));}
static uint32_t runtime_address(unsigned slot) {return (uint32_t)(uintptr_t)services->runtime[slot];}
static void prepare(unsigned pattern,unsigned source_alignment,unsigned target_alignment) {
  uint8_t* source=source_storage+source_alignment;
  uint8_t* alternate=alternate_storage+source_alignment;
  uint8_t* target=target_storage+target_alignment;
  uint32_t random=0x61F411;
  for(unsigned i=0;i<512;++i) {
    random^=random<<13;random^=random>>17;random^=random<<5;
    source[i]=alternate[i]=target[i]=(uint8_t)random;
  }
  if(pattern) source[positions[pattern]]^=0x81;
}
static int sign(uint32_t value) {const int32_t signed_value=(int32_t)value;return (signed_value>0)-(signed_value<0);}
static void validate_native() {
  for(unsigned aa=0;aa<4;++aa) for(unsigned ba=0;ba<4;++ba) {
    for(unsigned n=0;n<=64;++n) {
      prepare(0,aa,ba);uint8_t* target=target_storage+ba;uint8_t* source=source_storage+aa;
      for(unsigned at=0;at<=n;++at) {
        if(at<n) source[at]^=0x81;
        const uint32_t expected=sector_scalar_compare(target,source,n);
        for(unsigned kernel=0;kernel<6;++kernel) {
          const uint32_t actual=kernels[kernel](target,source,n);
          if(kernel<4 ? sign(actual)!=sign(expected) : (actual==0)!=(expected==0)) ++failures;
        }
        if(at<n) source[at]^=0x81;
      }
      for(unsigned kernel=6;kernel<10;++kernel) {
        for(unsigned i=0;i<n;++i) target[i]^=0x55;
        (void)kernels[kernel](target,source,n);
        if(!c::equal_scalar(target,source,n)) ++failures;
      }
    }
    mk61_api->service();
  }
}
static void group(unsigned first,unsigned count,unsigned pattern,unsigned sa,unsigned ta) {
  constexpr unsigned samples=7,iterations=128;
  uint32_t times[6][samples];
  for(unsigned kernel=first;kernel<first+count;++kernel) {
    prepare(pattern,sa,ta);
    uint8_t* target=target_storage+ta;const uint8_t* source=source_storage+sa;
    const uint32_t actual=kernels[kernel](target,source,512);
    if(first==0) {
      const uint32_t expected=sector_scalar_compare(target,source,512);
      if(kernel<4 ? sign(actual)!=sign(expected) : (actual==0)!=(expected==0)) ++failures;
    } else {
      if(first==10 && actual!=(uint32_t)(pattern!=0)) ++failures;
      if(!c::equal_scalar(target,source,512)) ++failures;
    }
  }
  for(unsigned sample=0;sample<samples;++sample) for(unsigned order=0;order<count;++order) {
    const unsigned k=(sample+order)%count;
    const Function function=kernels[first+k];
    prepare(pattern,sa,ta);
    uint8_t* target=target_storage+ta;
    const uint8_t* source=source_storage+sa;const uint8_t* alternate=alternate_storage+sa;
    for(unsigned warmup=0;warmup<4;++warmup) sink+=function(target,first==10 && (warmup&1) ? alternate : source,512);
    const uint32_t started=cycles();
    for(unsigned iteration=0;iteration<iterations;++iteration) {
      const uint8_t* input=first==10 && (iteration&1) ? alternate : source;
      sink+=function(target,input,512);
    }
    times[k][sample]=cycles()-started;
    if(first!=0 && !c::equal_scalar(target,first==10 ? alternate : source,512)) ++failures;
    mk61_api->service();
  }
  for(unsigned k=0;k<count;++k) {
    for(unsigned i=1;i<samples;++i) {
      const uint32_t value=times[k][i];unsigned j=i;
      while(j && times[k][j-1]>value) {times[k][j]=times[k][j-1];--j;}
      times[k][j]=value;
    }
    const unsigned at=64+rows*20;
    put8(at,(uint8_t)(first+k));put8(at+1,(uint8_t)pattern);put8(at+2,(uint8_t)sa);put8(at+3,(uint8_t)ta);
    put32(at+4,iterations);put32(at+8,times[k][0]);put32(at+12,times[k][samples/2]);put32(at+16,times[k][samples-1]);
    ++rows;
  }
}
static void benchmark(unsigned page) {
  __builtin_memset(report,0,sizeof(report));rows=0;
  const unsigned pattern=page/4,sa=page%4;
  for(unsigned ta=0;ta<4;++ta) {
    group(0,6,pattern,sa,ta);
    if(pattern==0) group(6,4,pattern,sa,ta);
    group(10,6,pattern,sa,ta);
  }
  report[0]='F';report[1]='S';report[2]='C';report[3]='1';
  put32(4,1);put32(8,page);put32(12,rows);put32(16,failures);
  put32(20,(uint32_t)(uintptr_t)sector_word_compare);
  put32(24,runtime_address(MK61_RUNTIME_SLOT_memcmp));put32(28,runtime_address(MK61_RUNTIME_SLOT_memcpy));
  put32(32,demcr_before);put32(36,control_before);put32(40,sink);put32(44,512);
  put32(48,16);put32(52,patterns);put32(56,4);put32(60,2); // Oz
  const unsigned slots[]={MK61_RUNTIME_SLOT_memcmp,MK61_RUNTIME_SLOT_memcpy};
  for(unsigned helper=0;helper<2;++helper) {
    const uint32_t address=runtime_address(slots[helper])&~1U;
    if(address<0x08000000U || address+64U>0x08080000U) {++failures;continue;}
    const uint8_t* code=(const uint8_t*)(uintptr_t)address;
    for(unsigned i=0;i<64;++i) put8(1376+helper*64+i,code[i]);
  }
  put32(16,failures);
}
extern "C" int main() {
  if(!mk61_app_api_compatible(mk61_api,sizeof(*mk61_api),MK61_APP_CAP_TIME|MK61_APP_CAP_GRAPHICS|MK61_APP_CAP_KEYBOARD)) return MK61_APP_RUNTIME_ERROR;
  services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_RUNTIME);
  if(!services || !services->runtime) return MK61_APP_RUNTIME_ERROR;
  failures=0;sink=0;
  demcr_before=reg(0xE000EDFCU);control_before=reg(0xE0001000U);
  reg(0xE000EDFCU)=demcr_before|(1U<<24);reg(0xE0001000U)=control_before|1U;
  const uint32_t start=cycles();for(volatile unsigned i=0;i<32;++i) {}
  if(cycles()==start) ++failures;
  validate_native();
  int result=MK61_APP_OK;
  if(!mk61_api->graphics_begin()) result=MK61_APP_RUNTIME_ERROR;
  else {
    unsigned page=0;benchmark(page);(void)mk61_api->graphics_present(report,sizeof(report));
    for(;;) {
      const int key=mk61_api->key_poll();if(key==MK61_APP_KEY_ESC) break;
      if(key==MK61_APP_KEY_DIGIT_1 && page+1<page_count) {benchmark(++page);(void)mk61_api->graphics_present(report,sizeof(report));}
      mk61_api->delay_ms(1);
    }
    mk61_api->graphics_end();if(failures) result=MK61_APP_RUNTIME_ERROR;
  }
  reg(0xE0001000U)=control_before;reg(0xE000EDFCU)=demcr_before;
  return result;
}
