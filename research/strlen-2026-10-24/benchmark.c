/* Bounded strlen experiment. All transport/firmware/RTC ownership is external. */
#include "mk61_app.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "binding.h"

#define ROWS 7u
#define ROUNDS 7u
#define LIMIT 2048u
#if defined(__ARM_ARCH_6M__)
#define LEAVES 7u
#define NOMINAL_HZ 125000000u
#define WARMUP 200000u
static uint32_t tick(void) { __asm__ volatile("":::"memory");return *(volatile uint32_t*)0x40054028u; }
#else
#define LEAVES 11u
#define NOMINAL_HZ 96000000u
#define WARMUP 19200000u
static uint32_t tick(void) { __asm__ volatile("":::"memory");return *(volatile uint32_t*)0xe0001004u; }
#endif
#define FUNCTIONS (LEAVES+3u)
typedef size_t (*Length)(const char*);
extern size_t baseline(const char*),libc_strlen(const char*),byte1(const char*),byte4(const char*);
extern size_t word1(const char*),word2(const char*),word4(const char*),runtime_strlen(const char*);
#if !defined(__ARM_ARCH_6M__)
extern size_t dsp1(const char*),dsp4(const char*),dsp8(const char*),dsp32(const char*);
#endif
extern const mk61_service_runtime_function* bench_strlen_runtime;
typedef struct { uint32_t length,alignment,source,loops,copy,reserved; } Input;
/* raw round: control-before, baseline-before, time[function index],
 * baseline-after, control-after. Function execution order rotates/reverses. */
typedef struct { Input input;uint32_t raw[ROUNDS][FUNCTIONS+4u]; } Row;
static struct { uint32_t h[64];Row rows[ROWS]; } report;
static uint8_t buffer[LIMIT+64u] __attribute__((aligned(16)));
static volatile size_t sink;
_Static_assert(sizeof(report)<=4096,"Bounded report");
_Static_assert(sizeof(mk61_app_services)==28,"Existing provider");
_Static_assert(MK61_RUNTIME_COUNT==26 && MK61_RUNTIME_SLOT_strlen==20,"Existing runtime");
static __attribute__((naked,noipa,aligned(4))) size_t control(const char* p __attribute__((unused))) {
  __asm__("movs r0,#0\nbx lr\n");
}
static uint32_t byte_at(uintptr_t p) {
  uint32_t value;__asm__ volatile("ldrb %0,[%1]":"=l"(value):"l"(p):"memory");return value;
}
static uint32_t crc(const void* data,unsigned length) {
  uint32_t value=~0u;
  for(unsigned i=0;i<length;++i) {
    value^=byte_at((uintptr_t)data+i);
    for(unsigned b=0;b<8;++b)value=(value>>1)^(0xedb88320u&(0u-(value&1u)));
  }
  return ~value;
}
static uint8_t wanted(Input input,unsigned i) {
  unsigned first=32u+input.alignment;
  if(i<first || i>first+input.length)return 1;
  if(i==first+input.length)return 0;
  unsigned at=LIMIT+input.copy-input.length+i-first;
  return (uint8_t)(((at*31u+(at>>3)*7u)%255u)+1u);
}
static void prepare(Input input) {
  for(unsigned i=0;i<sizeof(buffer);++i)buffer[i]=wanted(input,i);
}
static int unchanged(Input input) {
  for(unsigned i=0;i<sizeof(buffer);++i)if(buffer[i]!=wanted(input,i))return 0;
  return 1;
}
static const char* data(Input input) {
  return input.source?(const char*)(FLASH_STRINGS+input.copy*FLASH_STRIDE+LIMIT+input.copy-input.length):
      (const char*)buffer+32u+input.alignment;
}
static __attribute__((noipa)) uint32_t measure(Length fn,const char* text,unsigned loops) {
  uint32_t begin=tick();
  for(unsigned i=0;i<loops;++i)sink=fn(text);
  return tick()-begin;
}
static unsigned anchors(const mk61_app_services* s) {
  if(s->struct_size!=28 || !s->runtime || (uintptr_t)s->runtime!=RUNTIME_TABLE)return 10;
  const mk61_service_runtime_function* runtime=s->runtime;
  /* Keep Flash and relocatable APP pointers separate in the APP word-fixup ABI. */
  __asm__ volatile("":"+r"(runtime));
  for(unsigned i=0;i<26;++i)if((uintptr_t)runtime[i]!=expected_runtime[i])return 11+i;
  for(unsigned i=0;i<40;++i)if(byte_at(FOOTER_ADDRESS+i)!=expected_footer[i])return 40+i;
  if(*(const uint32_t*)BUILD_LITERAL_ADDRESS!=TARGET_BUILD)return 80;
  report.h[19]=crc((const void*)NATIVE_STRLEN,NATIVE_BYTES);
  report.h[23]=crc((const void*)FLASH_STRINGS,FLASH_STRINGS_BYTES);
  report.h[26]=crc((const void*)FLASH_CODE,FLASH_CODE_BYTES);
  if(report.h[19]!=NATIVE_CRC)return 81;
  if(report.h[23]!=FLASH_STRINGS_CRC)return 82;
  return report.h[26]!=FLASH_CODE_CRC?83:0;
}
int main(void) {
  const mk61_app_services* s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
  if(!s || !s->runtime)return MK61_APP_RUNTIME_ERROR;
  mk61_service_file file={0};
  if(s->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_MK61_BINARY,
      (uint32_t)(uintptr_t)(BENCH_ROOT "/INPUT.bin"),&file))return MK61_APP_IO_ERROR;
  struct { uint32_t h[4];Input rows[ROWS]; } input;
  if(mk61_api->file_read(file.id,0,(uint8_t*)&input,sizeof(input))!=sizeof(input) ||
     input.h[0]!=0x53544c49u || input.h[1]!=1 || !input.h[2] || input.h[2]>ROWS ||
     input.h[3]>=368)return MK61_APP_INVALID_FILE;
  for(unsigned c=0;c<input.h[2];++c) {
    Input row=input.rows[c];
    if(row.length>LIMIT || row.alignment>7 || row.source>1 || row.reserved ||
       row.copy!=((row.length+row.alignment)&7u) || row.loops!=16384u/(row.length+16u))return MK61_APP_INVALID_FILE;
    report.rows[c].input=row;
  }
  Length functions[FUNCTIONS]={baseline,libc_strlen,byte1,byte4,word1,word2,word4,
#if !defined(__ARM_ARCH_6M__)
    dsp1,dsp4,dsp8,dsp32,
#endif
    strlen,(Length)s->runtime[MK61_RUNTIME_SLOT_strlen],runtime_strlen};
#ifdef BENCH_CODE_FLASH
  for(unsigned f=0;f<LEAVES;++f)if(leaf_offsets[f]!=UINT32_MAX)
    functions[f]=(Length)(FLASH_CODE+leaf_offsets[f]+1u);
  report.h[9]=1;
#endif
#ifdef MK61_APP_SHARED_RUNTIME
  report.h[10]=1;
#endif
  report.h[0]=0x53544c52u;report.h[1]=1;report.h[2]=FUNCTIONS;report.h[3]=input.h[2];report.h[4]=ROUNDS;
  report.h[8]=input.h[3];report.h[11]=*(const uint32_t*)0xe000ed00u;
  report.h[12]=TARGET_BUILD;report.h[13]=TARGET_CRC;report.h[15]=NOMINAL_HZ;
  report.h[16]=(uintptr_t)s;report.h[17]=(uintptr_t)s->runtime;report.h[18]=(uintptr_t)s->runtime[20];
  report.h[20]=NATIVE_STRLEN;report.h[21]=FLASH_STRINGS;report.h[22]=FLASH_STRINGS_BYTES;
  report.h[24]=FLASH_CODE;report.h[25]=FLASH_CODE_BYTES;report.h[27]=crc(&input,sizeof(input));
  __asm__ volatile("mrs %0,ipsr":"=r"(report.h[28]));
  __asm__ volatile("mrs %0,primask":"=r"(report.h[29]));
  __asm__ volatile("mrs %0,control":"=r"(report.h[30]));
#if defined(__ARM_ARCH_6M__)
  report.h[31]=*(const uint32_t*)0xd0000000u;
#endif
  report.h[60]=(uintptr_t)buffer;report.h[61]=(uintptr_t)&report;report.h[62]=(uintptr_t)control;
  for(unsigned f=0;f<FUNCTIONS;++f)report.h[32+f]=(uintptr_t)functions[f];
  bench_strlen_runtime=s->runtime;
  uint32_t demcr=0,dwt=0,changed_dwt=0;
  unsigned reason=report.h[28]?1:report.h[29]?2:(report.h[30]&1u)?3:report.h[31]?4:anchors(s);
  if(reason) {
    report.h[63]=reason;
    report.h[6]=1;report.h[7]=1;goto finished;
  }
  for(unsigned f=0;f<LEAVES;++f) {
    report.h[32+FUNCTIONS+f]=crc((const void*)((uintptr_t)functions[f]&~1u),leaf_sizes[f]);
    if(report.h[32+FUNCTIONS+f]!=leaf_crcs[f]) { report.h[6]=1;report.h[7]=1;report.h[63]=256+f;goto finished; }
  }
  for(unsigned c=0;c<input.h[2];++c) {
    Input row=input.rows[c];prepare(row);
    for(unsigned f=0;f<FUNCTIONS;++f) {
      size_t actual=functions[f](data(row));++report.h[5];
      if(actual!=row.length) { report.h[6]=1;report.h[7]=2;report.h[63]=actual;goto finished; }
      if(!unchanged(row)) { report.h[6]=1;report.h[7]=3;report.h[63]=crc(buffer,sizeof(buffer));goto finished; }
    }
  }
#if !defined(__ARM_ARCH_6M__)
  demcr=*(volatile uint32_t*)0xe000edfcu;dwt=*(volatile uint32_t*)0xe0001000u;
  *(volatile uint32_t*)0xe000edfcu=demcr|0x1000000u;*(volatile uint32_t*)0xe0001000u=dwt|1u;changed_dwt=1;
#endif
  {
    uint32_t probe=tick();mk61_api->delay_ms(1);
    if(tick()==probe) { report.h[6]=1;report.h[7]=4;goto finished; }
    Input warm={128,0,0,1,0,0};prepare(warm);uint32_t begin=tick(),wall=mk61_api->millis_ms();
    do {
      for(unsigned f=0;f<FUNCTIONS;++f)sink=functions[f](data(warm));
      mk61_api->service();
      if(mk61_api->millis_ms()-wall>2000u) { report.h[6]=1;report.h[7]=4;goto finished; }
    } while((report.h[14]=tick()-begin)<WARMUP);
  }
  for(unsigned c=0;c<input.h[2];++c) {
    Input row=input.rows[c];prepare(row);const char* text=data(row);
    for(unsigned round=0;round<ROUNDS;++round) {
      uint32_t* raw=report.rows[c].raw[round];mk61_api->service();
      raw[0]=measure(control,text,row.loops);raw[1]=measure(functions[0],text,row.loops);
      for(unsigned order=0;order<FUNCTIONS;++order) {
        unsigned f=(round+c+(round&1u?FUNCTIONS-1u-order:order))%FUNCTIONS;
        raw[2u+f]=measure(functions[f],text,row.loops);
      }
      raw[2u+FUNCTIONS]=measure(functions[0],text,row.loops);
      raw[3u+FUNCTIONS]=measure(control,text,row.loops);
    }
  }
  if((reason=anchors(s))) { report.h[6]=1;report.h[7]=5;report.h[63]=reason; }
finished:
#if !defined(__ARM_ARCH_6M__)
  if(changed_dwt) { *(volatile uint32_t*)0xe0001000u=dwt;*(volatile uint32_t*)0xe000edfcu=demcr; }
#else
  (void)demcr;(void)dwt;(void)changed_dwt;
#endif
  {
    mk61_service_write out={"RESULT",(const uint8_t*)&report,sizeof(report),MK61_SERVICE_INVALID_ID};
    if(!s->call(MK61_SERVICE_FILE_WRITE,file.parent,MK61_SERVICE_INVALID_ID,
        MK61_SERVICE_FILE_MK61_BINARY,&out))return MK61_APP_IO_ERROR;
  }
  return report.h[6]?MK61_APP_RUNTIME_ERROR:MK61_APP_OK;
}
