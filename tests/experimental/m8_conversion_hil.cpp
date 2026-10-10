#include "mk61_app.h"
#include "m8_conversion_candidates.hpp"
#include "mk8_literal.hpp"
#include <string.h>
static const unsigned lengths[]={0,1,2,3,4,7,8,12,16,31,64,128,512};
alignas(4) static u8 m8[520],utf8[1552];
alignas(4) static u16 utf16[520],output[776],expected[776];
static u8 report[384];
static const mk61_app_services* services;
static volatile u32 sink;
static u32 failures,rows,demcr_before,control_before;
static usize encoded_size;
using Convert=bool(*)(const void*,usize,void*,usize,usize&);
#define KERNEL __attribute__((noipa,aligned(16),optimize("Os")))
#define SCALAR(name,ns) \
extern "C" KERNEL bool name##_to8(const void*p,usize n,void*q,usize c,usize&w){return ns::to_utf8((const u8*)p,n,(u8*)q,c,w);} \
extern "C" KERNEL bool name##_from8(const void*p,usize n,void*q,usize c,usize&w){return ns::from_utf8((const u8*)p,n,(u8*)q,c,w);} \
extern "C" KERNEL bool name##_to16(const void*p,usize n,void*q,usize c,usize&w){return ns::to_utf16((const u8*)p,n,(u16*)q,c,w);} \
extern "C" KERNEL bool name##_from16(const void*p,usize n,void*q,usize c,usize&w){return ns::from_utf16((const u16*)p,n,(u8*)q,c,w);}
SCALAR(m8_legacy,m8_conversion_reference)
SCALAR(m8_mapped,mk8)
#define BLOCK(name,kind) \
extern "C" KERNEL bool name##_to8(const void*p,usize n,void*q,usize c,usize&w){return m8_conversion_candidates::to_utf8<kind>((const u8*)p,n,(u8*)q,c,w);} \
extern "C" KERNEL bool name##_from8(const void*p,usize n,void*q,usize c,usize&w){return m8_conversion_candidates::from_utf8<kind>((const u8*)p,n,(u8*)q,c,w);} \
extern "C" KERNEL bool name##_to16(const void*p,usize n,void*q,usize c,usize&w){return m8_conversion_candidates::to_utf16<kind>((const u8*)p,n,(u16*)q,c,w);} \
extern "C" KERNEL bool name##_from16(const void*p,usize n,void*q,usize c,usize&w){return m8_conversion_candidates::from_utf16<kind>((const u16*)p,n,(u8*)q,c,w);}
BLOCK(m8_word,false)
BLOCK(m8_dsp,true)
static const Convert functions[][4]={
 {m8_legacy_to8,m8_mapped_to8,m8_word_to8,m8_dsp_to8},
 {m8_legacy_from8,m8_mapped_from8,m8_word_from8,m8_dsp_from8},
 {m8_legacy_to16,m8_mapped_to16,m8_word_to16,m8_dsp_to16},
 {m8_legacy_from16,m8_mapped_from16,m8_word_from16,m8_dsp_from16}};
static volatile u32& reg(u32 at){return *(volatile u32*)(uintptr_t)at;}
static u32 cycles(){__asm__ __volatile__("":::"memory");const u32 n=reg(0xE0001004U);__asm__ __volatile__("":::"memory");return n;}
static void put32(unsigned at,u32 n){for(unsigned i=0;i<4;++i)report[at+i]=(u8)(n>>(i*8));}
static void verify_span(unsigned family,const void* input,usize length,usize capacity) {
  memset(expected,0xA7,sizeof(expected));usize count=0;
  const bool reference=functions[family][0](input,length,expected,capacity,count);
  for(unsigned variant=1;variant<4;++variant) {
    memset(output,0xA7,sizeof(output));usize written=0;
    const bool result=functions[family][variant](input,length,output,capacity,written);
    if(result!=reference||written!=count||memcmp(output,expected,sizeof(output)))++failures;
  }
}
static void verify_edge_cases() {
  for(unsigned b=0;b<256;++b) {
    for(unsigned i=0;i<8;++i)m8[i]=(u8)(0xC0+i*7);
    m8[3]=(u8)b;verify_span(0,m8,8,24);verify_span(2,m8,8,8);
    const u8 encoded[]={0xD0,0x90,0xD0,0xBF,0xD1,0x80,0xD1,0x8F};
    memcpy(utf8,encoded,sizeof(encoded));utf8[2]=(u8)b;verify_span(1,utf8,8,8);
    memcpy(utf8,encoded,sizeof(encoded));utf8[3]=(u8)b;verify_span(1,utf8,8,8);
    mk61_api->service();
  }
  for(unsigned cp=0;cp<65536;++cp) {
    utf16[0]=0x0410;utf16[1]=(u16)cp;utf16[2]=0x0430;utf16[3]=0x044F;
    verify_span(3,utf16,4,4);
    if((cp&255)==0)mk61_api->service();
  }
  for(unsigned capacity=0;capacity<9;++capacity) {
    for(unsigned i=0;i<8;++i)m8[i]=(u8)(0xC0+i*7);
    usize n=0;(void)m8_conversion_reference::to_utf8(m8,8,utf8,sizeof(utf8),n);
    verify_span(0,m8,8,capacity);verify_span(1,utf8,n,capacity);verify_span(2,m8,8,capacity);
    for(unsigned i=0;i<8;++i)utf16[i]=(u16)(0x0410+i);
    verify_span(3,utf16,8,capacity);
  }
}
static void prepare(unsigned n,unsigned pattern,unsigned align) {
  static constexpr auto program=M8_ARRAY("10 PRINT \"Привет → мир\"\n20 GOTO 10\n");
  static const u8 extras[]={0xA8,0xB8,0x0F,0x88,0xB9,0x12,0x84,0x1F};
  for(unsigned i=0;i<n;++i)m8[align+i]=pattern==0?(u8)(' '+i%95):pattern==1?(u8)(0xC0+i%64):
    pattern==2?(i&1?(u8)(0xC0+i%64):(u8)('A'+i%26)):pattern==3?extras[i%sizeof(extras)]:
    (u8)program[i%(sizeof(program)-1)];
  usize units=0;
  if(!m8_conversion_reference::to_utf8(m8+align,n,utf8+align,sizeof(utf8)-align,encoded_size)||
     !m8_conversion_reference::to_utf16(m8+align,n,utf16+(align&1),520-(align&1),units)||units!=n)++failures;
}
static void measure(unsigned family,unsigned variant,unsigned pattern,unsigned align,unsigned n) {
  prepare(n,pattern,align);
  const void* input=family==1?(const void*)(utf8+align):family==3?(const void*)(utf16+(align&1)):(const void*)(m8+align);
  const usize length=family==1?encoded_size:n,capacity=family==0?encoded_size:n;
  const unsigned offset=family==2?2*(align&1):align;
  void* destination=(u8*)output+offset;void* oracle=(u8*)expected+offset;
  memset(output,0xA7,sizeof(output));memset(expected,0xA7,sizeof(expected));
  usize a=0,b=0;
  const bool reference=functions[family][0](input,length,oracle,capacity,a);
  const bool success=functions[family][variant](input,length,destination,capacity,b);
  if(!reference||!success||a!=b||memcmp(output,expected,sizeof(output)))++failures;
  const unsigned iterations=n<=16?128:n<=128?64:16;u32 times[7];
  for(unsigned sample=0;sample<7;++sample) {
    for(unsigned i=0;i<4;++i){usize w=0;sink+=functions[family][variant](input,length,destination,capacity,w)+w;}
    const u32 start=cycles();
    for(unsigned i=0;i<iterations;++i){usize w=0;sink+=functions[family][variant](input,length,destination,capacity,w)+w;}
    times[sample]=cycles()-start;mk61_api->service();
  }
  for(unsigned i=1;i<7;++i){const u32 v=times[i];unsigned j=i;while(j&&times[j-1]>v){times[j]=times[j-1];--j;}times[j]=v;}
  const unsigned at=64+20*rows;
  report[at]=(u8)variant;report[at+1]=(u8)align;report[at+2]=success;report[at+3]=0;
  put32(at+4,iterations);put32(at+8,times[0]);put32(at+12,times[3]);put32(at+16,times[6]);++rows;
}
static bool benchmark(unsigned index,unsigned local) {
  const unsigned family=local%4,pattern=local/4,n=lengths[index];rows=0;memset(report,0,sizeof(report));
  for(unsigned align=0;align<4;++align)for(unsigned order=0;order<4;++order)
    measure(family,(local+order)%4,pattern,align,n);
  report[0]='M';report[1]='8';report[2]='C';report[3]='1';
  put32(4,1);put32(8,index*20+local);put32(12,rows);put32(16,failures);put32(20,n);put32(24,family);put32(28,pattern);
  put32(32,index);put32(36,demcr_before);put32(40,control_before);put32(44,sink);
  put32(48,family==1?encoded_size:n);put32(52,family==0?encoded_size:n);
#if defined(__ARM_FEATURE_SIMD32)
  put32(56,1);
#endif
  static const char alphabet[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  unsigned at=0;
  for(unsigned i=0;i<sizeof(report);i+=3) {
    const unsigned v=(unsigned)report[i]<<16|(unsigned)report[i+1]<<8|report[i+2];
    utf8[at++]=alphabet[(v>>18)&63];utf8[at++]=alphabet[(v>>12)&63];utf8[at++]=alphabet[(v>>6)&63];utf8[at++]=alphabet[v&63];
  }
  char name[]="M8CV00";name[4]=(char)('0'+local/10);name[5]=(char)('0'+local%10);
  mk61_service_write file={name,utf8,at,MK61_SERVICE_INVALID_ID};
  return services->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_TEXT,&file)!=0;
}
extern "C" int main() {
  if(!mk61_app_api_compatible(mk61_api,sizeof(*mk61_api),MK61_APP_CAP_TIME|MK61_APP_CAP_FILES))return MK61_APP_RUNTIME_ERROR;
  services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
  if(!services)return MK61_APP_RUNTIME_ERROR;
  mk61_service_file control={};const char* path="/M8CFG.txt";u8 selected=0;
  if(services->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_TEXT,(u32)(uintptr_t)path,&control)!=0||
     mk61_api->file_size(control.id)!=1||mk61_api->file_read(control.id,0,&selected,1)!=1||
     selected<'A'||selected>='A'+sizeof(lengths)/sizeof(lengths[0]))return MK61_APP_RUNTIME_ERROR;
  failures=0;sink=0;demcr_before=reg(0xE000EDFCU);control_before=reg(0xE0001000U);
  // Run the expensive BMP matrix once per pass through the length list.
  if(selected=='A')verify_edge_cases();
  reg(0xE000EDFCU)=demcr_before|(1U<<24);reg(0xE0001000U)=control_before|1U;
  int result=MK61_APP_OK;
  for(unsigned local=0;local<20;++local)if(!benchmark(selected-'A',local)||failures){result=MK61_APP_RUNTIME_ERROR;break;}
  if(result==MK61_APP_OK) {
    selected=(u8)('A'+(selected-'A'+1)%(sizeof(lengths)/sizeof(lengths[0])));
    mk61_service_write next={"M8CFG",&selected,1,control.id};
    if(!services->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,control.id,MK61_SERVICE_FILE_TEXT,&next))result=MK61_APP_RUNTIME_ERROR;
  }
  reg(0xE0001000U)=control_before;reg(0xE000EDFCU)=demcr_before;return result;
}
