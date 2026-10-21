/* Qualification-only APP. All compared implementations execute from Flash/ROM. */
#include "mk61_app.h"
#include <stdint.h>
#include "flash-layout.h"

typedef void* (*Fill)(void*,int,size_t);
static const uint16_t lengths[]={0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,
  31,32,33,63,64,65,127,128,129,255,256,257,511,512,513,1023,1024,1025,2048,4096};
enum {CASES=sizeof(lengths)/sizeof(*lengths)*4,SAMPLES=128,ROUNDS=9,PAGE_ROWS=64};
struct Row {uint16_t n;uint8_t align,value;uint32_t control,before,after,times[VARIANTS-1];};
struct Output {uint32_t header[20];struct Row rows[PAGE_ROWS];};
static struct Output output;
static uint8_t buffer[4224] __attribute__((aligned(32)));
static volatile uintptr_t sink;
__attribute__((noipa)) static void* empty(void* p,int v,size_t n){(void)v;(void)n;return p;}
static uint32_t cycles(void){__asm__ volatile("" ::: "memory");return *(volatile uint32_t*)0xE0001004u;}
static uint32_t crc(const void* p,uint32_t n){uint32_t c=~0u;const volatile uint8_t* b=p;
  for(uint32_t i=0;i<n;++i){c^=b[i];for(unsigned k=0;k<8;++k)c=(c>>1)^(0xEDB88320u&(0u-(c&1u)));if(!(i&1023u))mk61_api->service();}return ~c;}
__attribute__((noipa)) static uint32_t measure(Fill f,void* p,int v,size_t n){uint32_t a[ROUNDS];
  for(unsigned r=0;r<ROUNDS;++r){mk61_api->service();for(unsigned i=0;i<8;++i)sink=(uintptr_t)f(p,v,n);
    uint32_t begin=cycles();for(unsigned i=0;i<SAMPLES;++i)sink=(uintptr_t)f(p,v,n);a[r]=cycles()-begin;}
  for(unsigned i=1;i<ROUNDS;++i)for(unsigned j=i;j&&a[j]<a[j-1];--j){uint32_t t=a[j];a[j]=a[j-1];a[j-1]=t;}
  return a[ROUNDS/2];}
static int check(Fill f,unsigned n,unsigned a,unsigned v){for(unsigned i=0;i<sizeof(buffer);++i)buffer[i]=0x5A;
  unsigned begin=32+a,end=begin+n;if(f(buffer+begin,(int)v,n)!=buffer+begin)return 1;
  for(unsigned i=0;i<sizeof(buffer);++i)if(buffer[i]!=(i>=begin&&i<end?(v&255):0x5A))return 2;
  return 0;}
static int save(const mk61_app_services* s,unsigned page,unsigned count){char name[]="FLBN0";name[4]+=page;
  output.header[2]=page;output.header[3]=count;
  mk61_service_write req={name,(const uint8_t*)&output,80+count*sizeof(struct Row),MK61_SERVICE_INVALID_ID};
  return s->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&req);}
int main(void){const mk61_app_services* s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
  if(!s||!s->runtime||(uintptr_t)s->runtime[MK61_RUNTIME_SLOT_memset]!=0x08008A21u||!(*(volatile uint32_t*)0xE0001000u&1))return MK61_APP_RUNTIME_ERROR;
  uint32_t proof[3]={0x31435246u,0x80000u,crc((void*)0x08000000u,0x80000u)};
  mk61_service_write proof_req={"FLCRC",(const uint8_t*)proof,sizeof(proof),MK61_SERVICE_INVALID_ID};
  if(!s->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&proof_req))return MK61_APP_IO_ERROR;
#ifdef CHECK_ONLY
  return MK61_APP_OK;
#endif
  if(crc((void*)PAYLOAD_BASE,PAYLOAD_BYTES)!=PAYLOAD_CRC||crc((void*)0x1FFF0000u,0x7800)!=0x9F8F7DEDu)return MK61_APP_RUNTIME_ERROR;
  unsigned checks=0;
  for(unsigned f=0;f<VARIANTS;++f)for(unsigned n=0;n<=65;++n)for(unsigned a=0;a<8;++a){mk61_api->service();
    for(unsigned k=0;k<4;++k){unsigned v=k==0?0:k==1?1:k==2?0x1234u:0xFFFFFFFFu;
      if(check((Fill)entry_addresses[f],n,a,v))return MK61_APP_RUNTIME_ERROR;
      ++checks;}}
  uint32_t header[20]={0x31424C46u,1,0,0,CASES,VARIANTS,SAMPLES,ROUNDS,checks,PAYLOAD_CRC,*(volatile uint32_t*)0x40023C00u,0};
  for(unsigned i=0;i<12;++i)output.header[i]=header[i];
  for(unsigned i=0;i<VARIANTS;++i)output.header[12+i]=entry_addresses[i];
  unsigned count=0,page=0;
  for(unsigned i=0;i<CASES;++i){struct Row* r=&output.rows[count];r->n=lengths[i/4];r->align=i%4;r->value=(i/4)&1?0:165;
    void* p=buffer+32+r->align;
    for(unsigned f=0;f<VARIANTS;++f){if(check((Fill)entry_addresses[f],r->n,r->align,r->value))return MK61_APP_RUNTIME_ERROR;++checks;}
    r->control=measure(empty,p,r->value,r->n);r->before=measure((Fill)entry_addresses[0],p,r->value,r->n);
    for(unsigned order=0;order<VARIANTS-1;++order){unsigned f=1+(i+order)%(VARIANTS-1);r->times[f-1]=measure((Fill)entry_addresses[f],p,r->value,r->n);}
    r->after=measure((Fill)entry_addresses[0],p,r->value,r->n);output.header[8]=checks;
    if(++count==PAGE_ROWS||i+1==CASES){if(!save(s,page++,count))return MK61_APP_IO_ERROR;count=0;}}
  return MK61_APP_OK;
}
