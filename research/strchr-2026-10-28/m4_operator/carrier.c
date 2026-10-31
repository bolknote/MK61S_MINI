/* Finite M4 workload. Transport, Flash programming, RTC and leases are external.
 * No reset, clock configuration, IRQ masking, USB access or retry lives here.
 */
#include "mk61_app.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "bench.h"
#include "binding.h"

#ifndef ST_CODE_FLASH
#define ST_CODE_FLASH 0
#endif
#if !defined(__ARM_ARCH_7EM__)
#error "This carrier is only the Cortex-M4 half of the experiment"
#endif

enum { ST_INPUT_MAGIC=0x34494853u, ST_REPORT_MAGIC=0x34524843u, ST_CONTEXT_WORDS=6 };
enum { E_INPUT=1,E_CONTEXT=2,E_ANCHOR=3,E_GUARD=4,E_TIMER=5,E_SEARCH=6,E_REPLAY=7,E_OUTPUT=8 };
typedef struct {
  uint32_t magic,version,mode,first,count,batch,token_a,token_b;
  uint32_t context[ST_CONTEXT_WORDS];
  uint32_t crc32,reserved;
} st_request;
typedef struct {
  uint32_t index,repeats,address;
  uint32_t raw[ST_FUNCTIONS][ST_ROUNDS];
} st_row;
typedef struct { uint32_t h[96]; st_row rows[ST_ROWS]; } st_report;
_Static_assert(sizeof(st_request)==64,"fixed input wire format");
_Static_assert(sizeof(st_key)==12,"fixed case map");
_Static_assert(sizeof(st_report)<=4096,"bounded raw report");
_Static_assert(sizeof(st_samples)==56,"retain the complete first faulty sample");
_Static_assert(MK61_RUNTIME_COUNT==26 && MK61_RUNTIME_SLOT_strchr==18,"unchanged real runtime");
static st_report report;
static uint8_t storage[513+ST_GUARD*2+16] __attribute__((aligned(16)));
static uint32_t last_batch=UINT32_MAX,last_mode=UINT32_MAX;

extern char* st_native_control(const char*,int);
extern char* st_sdk_control(const char*,int);
extern char* st_newlib_control(const char*,int);
extern char* byte1_strchr(const char*,int);
extern char* byte4_strchr(const char*,int);
extern char* word1_strchr(const char*,int);
extern char* word2_strchr(const char*,int);
extern char* dsp1_strchr(const char*,int);
extern char* dsp2_strchr(const char*,int);

static volatile uint32_t* reg(uint32_t address) { return (volatile uint32_t*)(uintptr_t)address; }
static uint32_t tick(void) {
  __asm__ volatile("":::"memory");
  uint32_t value=*reg(0xe0001004u);
  __asm__ volatile("":::"memory");
  return value;
}
static uint32_t byte_at(const void* p,unsigned at) {
  uint32_t result;
  const uintptr_t address=(uintptr_t)p+at;
  __asm__ volatile("ldrb %0,[%1]":"=l"(result):"l"(address):"memory");
  return result;
}
static uint32_t crc(const void* p,unsigned bytes) {
  uint32_t value=UINT32_MAX;
  for(unsigned i=0;i<bytes;++i) {
    value^=byte_at(p,i);
    for(unsigned bit=0;bit<8;++bit)value=(value>>1)^(0xedb88320u&(0u-(value&1u)));
  }
  return ~value;
}
static void context(uint32_t out[ST_CONTEXT_WORDS]) {
  /* Read-only clock/cache/FPU facts. Reading SysTick CTRL would clear a flag. */
  const uint32_t addresses[ST_CONTEXT_WORDS]={
    0x40023800u,0x40023804u,0x40023808u,0x40023c00u,0xe000ed14u,0xe000ed88u};
  for(unsigned i=0;i<ST_CONTEXT_WORDS;++i)out[i]=*reg(addresses[i]);
}
static int same_context(const uint32_t* wanted) {
  uint32_t observed[ST_CONTEXT_WORDS],ipsr,primask,control;
  context(observed);
  __asm__ volatile("mrs %0,ipsr":"=r"(ipsr));
  __asm__ volatile("mrs %0,primask":"=r"(primask));
  __asm__ volatile("mrs %0,control":"=r"(control));
  if(ipsr || primask || (control&1u))return 0;
  for(unsigned i=0;i<ST_CONTEXT_WORDS;++i)if(observed[i]!=wanted[i])return 0;
  return control==report.h[23];
}
static int anchors(const mk61_app_services* services) {
  if(!services || !services->runtime || (uintptr_t)services->runtime!=ST_RUNTIME)return 0;
  const mk61_service_runtime_function* runtime=services->runtime;
  __asm__ volatile("":"+r"(runtime));
  for(unsigned i=0;i<26;++i)if((uintptr_t)runtime[i]!=st_expected_runtime[i])return 0;
  for(unsigned i=0;i<40;++i)
    if(byte_at((const void*)(uintptr_t)ST_FOOTER,i)!=st_expected_footer[i])return 0;
  return crc((const void*)(uintptr_t)ST_NATIVE,ST_NATIVE_BYTES)==ST_NATIVE_CRC;
}
static void fault(unsigned reason,unsigned detail,unsigned index,unsigned function) {
  if(report.h[2])return;
  report.h[2]=reason;report.h[3]=detail;report.h[44]=index;report.h[45]=function;
}
static uint32_t repeat_count(const st_key* key) {
  const unsigned work=key->expected<0?key->length:(unsigned)key->expected;
  return 16384u/(work+16u);
}
static const char* prepare(unsigned index) {
  const st_key* key=&st_keys[index/2u];
  const uint8_t* source=(const uint8_t*)(uintptr_t)(ST_FIXTURE_BASE+key->offset);
  for(unsigned i=0;i<sizeof(storage);++i)storage[i]=0xa5;
  for(unsigned i=0;i<=(unsigned)key->length;++i)
    storage[ST_GUARD+key->alignment+i]=(uint8_t)byte_at(source,i);
  return index&1u?(const char*)source:(const char*)storage+ST_GUARD+key->alignment;
}
static int unchanged(unsigned index) {
  const st_key* key=&st_keys[index/2u];
  const uint8_t* source=(const uint8_t*)(uintptr_t)(ST_FIXTURE_BASE+key->offset);
  for(unsigned i=0;i<ST_GUARD;++i)
    if(byte_at(source-ST_GUARD,i)!=0xa5 || byte_at(source+key->length+1u,i)!=0xa5)return 0;
  const unsigned first=ST_GUARD+key->alignment,last=first+key->length;
  for(unsigned i=0;i<sizeof(storage);++i) {
    const unsigned wanted=i<first || i>last?0xa5:byte_at(source,i-first);
    if(storage[i]!=wanted)return 0;
  }
  return 1;
}
static int qualify_timer(void) {
  const uint32_t wall=mk61_api->millis_ms(),begin=tick();
  uint32_t elapsed=0,cycles=0;
  /* Both time sources may stop in a negative test: the iteration limit is
   * independent, and this APP never calls a potentially waiting delay(). */
  for(unsigned attempts=0;attempts<1000000u;++attempts) {
    elapsed=mk61_api->millis_ms()-wall;
    cycles=tick()-begin;
    if(elapsed>=8u)break;
  }
  report.h[28]=elapsed;report.h[29]=cycles;report.h[30]=ST_NOMINAL_HZ;
  if(elapsed<8u || elapsed>250u || !cycles || cycles>=0x80000000u)return 0;
  const uint64_t expected=(uint64_t)(ST_NOMINAL_HZ/1000u)*elapsed;
  const uint64_t tolerance=(uint64_t)(ST_NOMINAL_HZ/1000u)*2u;
  return (uint64_t)cycles+tolerance>=expected && (uint64_t)cycles<=expected+tolerance;
}
static void store_fault_sample(const st_samples* sample) {
  const uint8_t* bytes=(const uint8_t*)sample;
  uint8_t* out=(uint8_t*)&report.h[46];
  for(unsigned i=0;i<sizeof(*sample);++i)out[i]=bytes[i];
  report.h[79]=1;
}

int main(void) {
  const uint32_t needed=MK61_APP_CAP_TIME|MK61_APP_CAP_FILES;
  if(!mk61_app_api_compatible(mk61_api,sizeof(*mk61_api),needed))return MK61_APP_RUNTIME_ERROR;
  const mk61_app_services* services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
  if(!services || !services->call || !services->runtime)return MK61_APP_RUNTIME_ERROR;
  for(unsigned i=0;i<sizeof(report.h)/sizeof(report.h[0]);++i)report.h[i]=0;
  for(unsigned i=0;i<ST_ROWS;++i) {
    report.rows[i].index=report.rows[i].repeats=report.rows[i].address=0;
    for(unsigned f=0;f<ST_FUNCTIONS;++f)for(unsigned r=0;r<ST_ROUNDS;++r)report.rows[i].raw[f][r]=0;
  }
  report.h[0]=ST_REPORT_MAGIC;report.h[1]=1;report.h[8]=ST_FUNCTIONS;report.h[9]=ST_ROUNDS;
  report.h[11]=ST_TOKEN_A;report.h[12]=ST_TOKEN_B;
#ifdef MK61_APP_SHARED_RUNTIME
  report.h[13]=1;
#endif
  report.h[14]=ST_CODE_FLASH;report.h[15]=(uintptr_t)services->runtime;
  report.h[16]=(uintptr_t)services->runtime[18];report.h[17]=ST_NATIVE_CRC;
  report.h[20]=*reg(0xe000ed00u);
  __asm__ volatile("mrs %0,ipsr":"=r"(report.h[21]));
  __asm__ volatile("mrs %0,primask":"=r"(report.h[22]));
  __asm__ volatile("mrs %0,control":"=r"(report.h[23]));
  context(&report.h[32]);
  mk61_service_file file={0};
  if(services->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_MK61_BINARY,
      (uint32_t)(uintptr_t)(ST_NAMESPACE "/INPUT.bin"),&file))return MK61_APP_IO_ERROR;
  st_request input;
  const unsigned bytes=sizeof(input);
  if(mk61_api->file_size(file.id)!=bytes || mk61_api->file_read(file.id,0,(uint8_t*)&input,bytes)!=bytes) {
    fault(E_INPUT,1,UINT32_MAX,UINT32_MAX);goto output;
  }
  report.h[4]=input.mode;report.h[5]=input.first;report.h[6]=input.count;report.h[10]=input.batch;
  if(input.magic!=ST_INPUT_MAGIC || input.version!=1 || input.reserved ||
      input.token_a!=ST_TOKEN_A || input.token_b!=ST_TOKEN_B ||
      crc(&input,56)!=input.crc32 || input.mode>1u ||
      (input.mode==0u && (input.first || input.count || input.batch)) ||
      (input.mode==1u && (input.first>=ST_CASES || input.first%ST_ROWS ||
        input.batch!=input.first/ST_ROWS || !input.count || input.count>ST_ROWS ||
        input.count!=(ST_CASES-input.first<ST_ROWS?ST_CASES-input.first:ST_ROWS)))) {
    fault(E_INPUT,2,UINT32_MAX,UINT32_MAX);goto output;
  }
  if((!input.mode && last_mode!=UINT32_MAX) ||
      (input.mode==1u && last_mode==1u && input.batch<=last_batch)) {
    fault(E_REPLAY,0,UINT32_MAX,UINT32_MAX);goto output;
  }
  /* This cache-local guard complements, never replaces, the external
   * one-shot lease and run journal. A fresh INIT may reset APP BSS. */
  last_mode=input.mode;last_batch=input.batch;
  if(report.h[21] || report.h[22] || (report.h[23]&1u) ||
      (report.h[20]&0xff00fff0u)!=(0x410fc240u&0xff00fff0u)) {
    fault(E_CONTEXT,1,UINT32_MAX,UINT32_MAX);goto output;
  }
  if(!anchors(services)) {fault(E_ANCHOR,1,UINT32_MAX,UINT32_MAX);goto output;}
  report.h[18]=crc((const void*)(uintptr_t)ST_FIXTURE_BASE,ST_FIXTURE_BYTES);
  if(report.h[18]!=ST_FIXTURE_CRC) {fault(E_ANCHOR,2,UINT32_MAX,UINT32_MAX);goto output;}
  if(input.mode && !same_context(input.context)) {
    fault(E_CONTEXT,2,UINT32_MAX,UINT32_MAX);goto output;
  }
  st_search functions[ST_FUNCTIONS]={st_native_control,st_sdk_control,st_newlib_control,
    byte1_strchr,byte4_strchr,word1_strchr,word2_strchr,dsp1_strchr,dsp2_strchr,
    strchr,(st_search)services->runtime[18]};
#if ST_CODE_FLASH
  for(unsigned f=0;f<ST_LEAVES;++f)
    functions[f]=(st_search)(uintptr_t)(ST_FIXTURE_BASE+st_leaf_offsets[f]+1u);
#endif
  for(unsigned f=0;f<ST_FUNCTIONS;++f)report.h[64+f]=(uintptr_t)functions[f];
  for(unsigned f=0;f<ST_LEAVES;++f) {
    report.h[80+f]=crc((const void*)((uintptr_t)functions[f]&~1u),st_leaf_sizes[f]);
    if(report.h[80+f]!=st_leaf_crcs[f]) {
      fault(E_ANCHOR,3,UINT32_MAX,f);goto output;
    }
  }
#ifdef MK61_APP_SHARED_RUNTIME
  report.h[90]=crc((const void*)((uintptr_t)strchr&~1u),12);
#else
  report.h[90]=crc((const void*)((uintptr_t)strchr&~1u),24);
#endif
  report.h[91]=crc((const void*)(uintptr_t)ST_NATIVE,ST_NATIVE_BYTES);
  report.h[92]=crc(services->runtime,26u*4u);
  const uint32_t demcr=*reg(0xe000edfcu),dwt=*reg(0xe0001000u);
  report.h[24]=dwt;report.h[25]=demcr;
  *reg(0xe000edfcu)=demcr|0x01000000u;
  *reg(0xe0001000u)=dwt|1u;
  __asm__ volatile("dsb\nisb":::"memory");
  if(!qualify_timer())fault(E_TIMER,1,UINT32_MAX,UINT32_MAX);
  if(!report.h[2] && input.mode)for(unsigned row=0;row<input.count;++row) {
    const unsigned index=input.first+row;
    const st_key* key=&st_keys[index/2u];
    const char* text=prepare(index);
    st_row* result=&report.rows[row];
    result->index=index;result->repeats=repeat_count(key);result->address=(uintptr_t)text;
    st_case test={text,(size_t)key->length+1u,key->character,key->expected,result->repeats};
    for(unsigned order=0;order<ST_FUNCTIONS;++order) {
      const unsigned f=(order+index)%ST_FUNCTIONS;
      mk61_api->service();
      if(!same_context(input.context) || !unchanged(index)) {
        fault(E_CONTEXT,3,index,f);break;
      }
      st_samples sample;
      const int status=st_measure(&test,functions[f],tick,&sample);
      for(unsigned round=0;round<ST_ROUNDS;++round)result->raw[f][round]=sample.raw[round];
      if(status) {store_fault_sample(&sample);fault(E_SEARCH,(unsigned)status,index,f);break;}
      if(!unchanged(index)) {fault(E_GUARD,1,index,f);break;}
      if(!same_context(input.context)) {fault(E_CONTEXT,4,index,f);break;}
    }
    if(report.h[2])break;
    ++report.h[7];
  }
  /* Never reset CYCCNT. If it was already running its time remains monotonic. */
  *reg(0xe0001000u)=dwt;
  *reg(0xe000edfcu)=demcr;
  __asm__ volatile("dsb\nisb":::"memory");
  report.h[26]=*reg(0xe0001000u);report.h[27]=*reg(0xe000edfcu);
  if(report.h[26]!=dwt || report.h[27]!=demcr)fault(E_TIMER,2,UINT32_MAX,UINT32_MAX);
  report.h[19]=crc((const void*)(uintptr_t)ST_FIXTURE_BASE,ST_FIXTURE_BYTES);
  if(report.h[19]!=ST_FIXTURE_CRC || !anchors(services))fault(E_ANCHOR,4,UINT32_MAX,UINT32_MAX);
output:
  context(&report.h[38]);
  report.h[60]=ST_NATIVE;report.h[61]=ST_FIXTURE_BASE;
  report.h[75]=mk61_app_image_crc;report.h[76]=(uintptr_t)&report;
  report.h[77]=(uintptr_t)storage;report.h[78]=sizeof(report);
  report.h[62]=0;report.h[62]=crc(&report,sizeof(report));
  {
    mk61_service_write out={"RESULT",(const uint8_t*)&report,sizeof(report),MK61_SERVICE_INVALID_ID};
    if(!services->call(MK61_SERVICE_FILE_WRITE,file.parent,MK61_SERVICE_INVALID_ID,
        MK61_SERVICE_FILE_MK61_BINARY,&out))return MK61_APP_IO_ERROR;
  }
  return report.h[2]?MK61_APP_RUNTIME_ERROR:MK61_APP_OK;
}
