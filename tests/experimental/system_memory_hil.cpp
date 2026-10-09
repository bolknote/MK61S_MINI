// One unchanged public-runtime APP compares the old and new resident Flash
// implementations, including short lengths and every source/dest alignment.
#include "mk61_app.h"
#include <string.h>
static constexpr unsigned lengths[]={0,1,2,3,4,7,8,15,16,31,32,63,64,128,256,512,1024,4096};
static constexpr unsigned page_count=sizeof(lengths)/sizeof(lengths[0])*3;
alignas(4) static unsigned char source_storage[4100],alternate_storage[4100],target_storage[4100];
static unsigned char report[1536];
static uint32_t failures,rows,demcr_before,control_before;
static volatile uint32_t sink;
static const mk61_app_services* services;
#define KERNEL __attribute__((noipa,aligned(16)))
extern "C" KERNEL uint32_t mem_check_compare(unsigned char* a,const unsigned char* b,size_t n) {return (uint32_t)memcmp(a,b,n);}
extern "C" KERNEL uint32_t mem_check_copy(unsigned char* a,const unsigned char* b,size_t n) {(void)memcpy(a,b,n);return 0;}
extern "C" KERNEL uint32_t mem_check_update(unsigned char* a,const unsigned char* b,size_t n) {if(memcmp(a,b,n)==0)return 0;(void)memcpy(a,b,n);return 1;}
using Function=uint32_t(*)(unsigned char*,const unsigned char*,size_t);
static const Function kernels[]={mem_check_compare,mem_check_copy,mem_check_update};
static volatile uint32_t& reg(uint32_t a) {return *(volatile uint32_t*)(uintptr_t)a;}
static uint32_t cycles() {__asm__ __volatile__("" ::: "memory");uint32_t n=reg(0xE0001004U);__asm__ __volatile__("" ::: "memory");return n;}
static void put8(unsigned a,unsigned char value) {report[a+(a>=176?16:0)+(a>=352?16:0)]=value;}
static void put32(unsigned a,uint32_t n) {for(unsigned i=0;i<4;++i)put8(a+i,(unsigned char)(n>>(i*8)));}
static void prepare(unsigned n,unsigned pattern,unsigned sa,unsigned ta) {
  unsigned char* p=source_storage+sa;unsigned char* q=alternate_storage+sa;unsigned char* out=target_storage+ta;
  uint32_t random=0x61F411;
  for(unsigned i=0;i<n;++i) {random^=random<<13;random^=random>>17;random^=random<<5;p[i]=q[i]=out[i]=(unsigned char)random;}
  if(pattern && n) p[pattern==1?0:n-1]^=0x81;
}
static int reference(const unsigned char* a,const unsigned char* b,unsigned n) {
  for(unsigned i=0;i<n;++i) if(a[i]!=b[i]) return (int)a[i]-b[i];
  return 0;
}
static int sign(uint32_t value) {const int32_t v=(int32_t)value;return (v>0)-(v<0);}
static void validate() {
  for(unsigned sa=0;sa<4;++sa)for(unsigned ta=0;ta<4;++ta) {
    for(unsigned n=0;n<=96;++n) {
      prepare(n,0,sa,ta);unsigned char* a=target_storage+ta;unsigned char* b=source_storage+sa;
      for(unsigned at=0;at<=n;++at) {
        if(at<n)b[at]^=0x81;
        if(sign(mem_check_compare(a,b,n))!=sign((uint32_t)reference(a,b,n)))++failures;
        if(sign(mem_check_compare(b,a,n))!=sign((uint32_t)reference(b,a,n)))++failures;
        if(at<n)b[at]^=0x81;
      }
      for(unsigned i=0;i<n;++i)a[i]^=0xFF;
      (void)mem_check_copy(a,b,n);if(reference(a,b,n)!=0)++failures;
    }
    mk61_api->service();
  }
}
static void measure(unsigned kernel,unsigned n,unsigned pattern,unsigned sa,unsigned ta) {
  constexpr unsigned samples=7;
  const unsigned iterations=n<=16?512:n<=128?256:n<=512?128:n<=1024?64:16;
  const Function function=kernels[kernel];uint32_t times[samples];
  for(unsigned sample=0;sample<samples;++sample) {
    prepare(n,pattern,sa,ta);
    unsigned char* out=target_storage+ta;const unsigned char* source=source_storage+sa;const unsigned char* alternate=alternate_storage+sa;
    for(unsigned i=0;i<4;++i)sink+=function(out,kernel==2&&(i&1)?alternate:source,n);
    const uint32_t start=cycles();
    for(unsigned i=0;i<iterations;++i)sink+=function(out,kernel==2&&(i&1)?alternate:source,n);
    times[sample]=cycles()-start;
    if(kernel!=0 && reference(out,kernel==2?alternate:source,n)!=0)++failures;
    mk61_api->service();
  }
  for(unsigned i=1;i<samples;++i){const uint32_t value=times[i];unsigned j=i;while(j&&times[j-1]>value){times[j]=times[j-1];--j;}times[j]=value;}
  const unsigned at=64+rows*20;put8(at,(unsigned char)kernel);put8(at+1,(unsigned char)pattern);put8(at+2,(unsigned char)sa);put8(at+3,(unsigned char)ta);
  put32(at+4,iterations);put32(at+8,times[0]);put32(at+12,times[samples/2]);put32(at+16,times[samples-1]);++rows;
}
static void benchmark(unsigned page) {
  __builtin_memset(report,0,sizeof(report));rows=0;
  const unsigned n=lengths[page/3],pattern=page%3;
  for(unsigned sa=0;sa<4;++sa)for(unsigned ta=0;ta<4;++ta)
    for(unsigned order=0;order<3;++order){const unsigned kernel=(page+order)%3;if(kernel==1&&pattern)continue;measure(kernel,n,pattern,sa,ta);}
  report[0]='S';report[1]='M';report[2]='C';report[3]='1';
  put32(4,1);put32(8,page);put32(12,rows);put32(16,failures);
  put32(20,(uint32_t)(uintptr_t)services->runtime[MK61_RUNTIME_SLOT_memcmp]);
  put32(24,(uint32_t)(uintptr_t)services->runtime[MK61_RUNTIME_SLOT_memcpy]);
  put32(28,n);put32(32,pattern);put32(36,page_count);put32(40,demcr_before);put32(44,control_before);put32(48,sink);
  const unsigned slots[]={MK61_RUNTIME_SLOT_memcmp,MK61_RUNTIME_SLOT_memcpy};
  for(unsigned k=0;k<2;++k){const uint32_t a=(uint32_t)(uintptr_t)services->runtime[slots[k]]&~1U;
    if(a<0x08000000U||a+64U>0x08080000U){++failures;continue;}
    for(unsigned i=0;i<64;++i)put8(1376+k*64+i,((const unsigned char*)(uintptr_t)a)[i]);}
  put32(16,failures);
}
extern "C" int main() {
  if(!mk61_app_api_compatible(mk61_api,sizeof(*mk61_api),MK61_APP_CAP_TIME|MK61_APP_CAP_GRAPHICS|MK61_APP_CAP_KEYBOARD))return MK61_APP_RUNTIME_ERROR;
  services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_RUNTIME);if(!services||!services->runtime)return MK61_APP_RUNTIME_ERROR;
  failures=0;sink=0;demcr_before=reg(0xE000EDFCU);control_before=reg(0xE0001000U);
  reg(0xE000EDFCU)=demcr_before|(1U<<24);reg(0xE0001000U)=control_before|1U;
  validate();int result=MK61_APP_OK;
  if(!mk61_api->graphics_begin())result=MK61_APP_RUNTIME_ERROR;
  else{unsigned page=0;benchmark(page);(void)mk61_api->graphics_present(report,sizeof(report));
    for(;;){int key=mk61_api->key_poll();if(key==MK61_APP_KEY_ESC)break;
      if(key==MK61_APP_KEY_DIGIT_1&&page+1<page_count){benchmark(++page);(void)mk61_api->graphics_present(report,sizeof(report));}mk61_api->delay_ms(1);}
    mk61_api->graphics_end();if(failures)result=MK61_APP_RUNTIME_ERROR;}
  reg(0xE0001000U)=control_before;reg(0xE000EDFCU)=demcr_before;return result;
}
