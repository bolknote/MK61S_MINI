/* Run from SRAM, compare real resident Flash memset with real factory ROM. */
#include "mk61_app.h"
#include <stdint.h>

typedef void* (*Fill)(void*, int, size_t);
static const uint16_t lengths[] = {
#ifndef ROMBEN_LOCAL
  0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,
#endif
  16,17,
  31,32,33,63,64,65,127,128,129,255,256,257,511,512,513,1023,1024,1025,2048,4096};
enum { SAMPLES = 128, ROUNDS = 9, CASES = 4 * sizeof(lengths)/sizeof(*lengths) };
struct Row { uint16_t size; uint8_t alignment, fill; uint32_t control, before, rom, repeat; };
struct Output { uint32_t header[12]; struct Row rows[CASES]; };
static struct Output output;
static uint8_t buffer[4224] __attribute__((aligned(32)));
static volatile uintptr_t sink;

#ifdef ROMBEN_LOCAL
#include "bulk-fill.h"
#if ROMBEN_LOCAL == 2
#define rom_fill local_bulk_style
#elif ROMBEN_LOCAL == 4
#define rom_fill local_bulk_edges_loop
#else
#define rom_fill local_bulk_edges
#endif
#else
__attribute__((noipa)) static void* rom_fill(void* p, int value, size_t n) {
  return ((void*(*)(void*,size_t,int))(uintptr_t)0x1FFF3BD5u)(p,n,value);
}
#endif
__attribute__((noipa)) static void* control(void* p, int value, size_t n) {
  (void)value; (void)n; return p;
}
static uint32_t cycles(void) {
  __asm__ volatile ("" ::: "memory");
  return *(volatile uint32_t*)0xE0001004u;
}
__attribute__((noipa)) static uint32_t measure(Fill fn, void* p, int value, size_t n) {
  uint32_t samples[ROUNDS];
  for (unsigned r=0; r<ROUNDS; ++r) {
    mk61_api->service();
    for(unsigned i=0;i<8;++i) sink=(uintptr_t)fn(p,value,n);
    uint32_t begin=cycles();
    for(unsigned i=0;i<SAMPLES;++i) sink=(uintptr_t)fn(p,value,n);
    samples[r]=cycles()-begin;
  }
  for(unsigned i=1;i<ROUNDS;++i)
    for(unsigned j=i;j && samples[j]<samples[j-1];--j) {
      uint32_t tmp=samples[j];samples[j]=samples[j-1];samples[j-1]=tmp;
    }
  return samples[ROUNDS/2];
}
static int check(Fill fn,unsigned n,unsigned alignment,unsigned value) {
  for(unsigned i=0;i<sizeof(buffer);++i) buffer[i]=0x5A;
  unsigned begin=32+alignment,end=begin+n;
  if(fn(buffer+begin,value,n)!=buffer+begin) return 1;
  for(unsigned i=0;i<sizeof(buffer);++i)
    if(buffer[i] != (i>=begin && i<end ? value : 0x5Au)) return 2;
  return 0;
}
static int save(const mk61_app_services* services,const char* name,const void* data,uint32_t size) {
  mk61_service_write request={name,(const uint8_t*)data,size,MK61_SERVICE_INVALID_ID};
  return services->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,
      MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&request);
}
int main(void) {
  const mk61_app_services* services=mk61_app_get_services(mk61_api,
      MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
  if(!services || !services->runtime ||
     !(*(volatile uint32_t*)0xE0001000u&1u)) return MK61_APP_RUNTIME_ERROR;
  uint32_t crc=0xFFFFFFFFu;
  for(unsigned i=0;i<0x7800u;++i) {
    crc^=((volatile const uint8_t*)0x1FFF0000u)[i];
    for(unsigned b=0;b<8;++b) crc=(crc>>1)^(0xEDB88320u&(0u-(crc&1u)));
    if(!(i&1023u))mk61_api->service();
  }
  if(~crc!=0x9F8F7DEDu) return MK61_APP_RUNTIME_ERROR;
  Fill resident=(Fill)services->runtime[MK61_RUNTIME_SLOT_memset];
#ifdef ROMBEN_BULK_ONLY
  /* Pinned to the captured 3AB3DD45 image; isolate the existing bulk helper. */
  if((uintptr_t)resident!=0x08008A21u) return MK61_APP_RUNTIME_ERROR;
  resident=(Fill)(uintptr_t)0x08008935u;
#endif
  uintptr_t resident_address=(uintptr_t)resident;
  if(resident_address<0x08000200u || resident_address>=0x08080000u)
    return MK61_APP_RUNTIME_ERROR;
  uintptr_t code_begin=(resident_address&~255u)-512u;
  uint32_t header[12]={0x31424D52u,1,CASES,SAMPLES,ROUNDS,resident_address,
      0x1FFF3BD5u,~crc,0,code_begin,1536,*(volatile uint32_t*)0x40023C00u};
#ifdef ROMBEN_LOCAL
  header[1]=ROMBEN_LOCAL;
  header[6]=(uintptr_t)rom_fill;
#endif
  for(unsigned i=0;i<12;++i)output.header[i]=header[i];
  unsigned checks=0;
  for(unsigned n=
#ifdef ROMBEN_LOCAL
      16
#else
      0
#endif
      ;n<=65;++n) for(unsigned a=0;a<8;++a) {
    mk61_api->service();
    for(unsigned v=0;v<4;++v) {
      unsigned value=v==0?0:v==1?1:v==2?165:255;
      if(check(rom_fill,n,a,value)) return MK61_APP_RUNTIME_ERROR;
      ++checks;
    }
  }
  for(unsigned i=0;i<CASES;++i) {
    struct Row* row=&output.rows[i];
    row->size=lengths[i/4];row->alignment=i%4;row->fill=(i/4)&1?0:165;
    if(check(resident,row->size,row->alignment,row->fill) ||
       check(rom_fill,row->size,row->alignment,row->fill)) return MK61_APP_RUNTIME_ERROR;
    checks+=2;
    void* p=buffer+32+row->alignment;
    row->control=measure(control,p,row->fill,row->size);
    row->before=measure(resident,p,row->fill,row->size);
    row->rom=measure(rom_fill,p,row->fill,row->size);
    row->repeat=measure(resident,p,row->fill,row->size);
  }
  output.header[8]=checks;
  if(!save(services,"ROMBEN",&output,sizeof(output)) ||
     !save(services,"ROMBASE",(const void*)code_begin,1536)) return MK61_APP_IO_ERROR;
  return MK61_APP_OK;
}
