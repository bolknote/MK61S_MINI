// APP-only experiment. Files and firmware service calls are outside timing.
#include "mk61_app.h"
#include "kernels.h"
#include "api.h"
#include "vectors.h"
#include <stdint.h>
#ifndef INTERP_DIRECTORY
#define INTERP_DIRECTORY "/INTRP02"
#endif
#ifndef INTERP_ROUNDS
#define INTERP_ROUNDS 7
#endif
#ifndef INTERP_SAMPLES
#define INTERP_SAMPLES 4096
#endif
#ifndef INTERP_VARIANT
#define INTERP_VARIANT 0
#endif
#if INTERP_VARIANT==1
#define FIRST_GROUP 0
#define LOCAL_GROUPS 1
#elif INTERP_VARIANT==2
#define FIRST_GROUP 1
#define LOCAL_GROUPS 2
#elif INTERP_VARIANT==3
#define FIRST_GROUP 3
#define LOCAL_GROUPS 2
#elif INTERP_VARIANT==4
#define FIRST_GROUP 5
#define LOCAL_GROUPS 2
#endif
enum {ROUNDS=INTERP_ROUNDS,SAMPLES=INTERP_SAMPLES,CASES=3,GROUPS=LOCAL_GROUPS,ROWS=GROUPS*CASES*2,STREAM=32};
typedef struct {uint32_t words[14];} State;
typedef struct {uint64_t a,b;} Pair;
typedef struct {
  uint32_t group,mode,input;
  uint64_t a,b,result_a,result_b;
  uint32_t raw[ROUNDS][4],empty[ROUNDS][2],checksum[ROUNDS][4];
} Row;
static struct {
  uint32_t magic,version,bytes,rows,rounds,samples,checks,failures;
  uint32_t status,core,control,ipsr,primask,restored;
  uint32_t clocks_before[7],clocks_after[7],divider_before[4],divider_after[4];
  State state_before,state_after;
  Row row[ROWS];
} output;
static Pair inputs[STREAM];
static volatile uint64_t sink;
static volatile uint32_t last_checksum;
static uint32_t reg(uint32_t address) {return *(volatile uint32_t*)(uintptr_t)address;}
static void put(uint32_t address,uint32_t value) {*(volatile uint32_t*)(uintptr_t)address=value;}
static uint32_t micros(void) {__asm__ volatile("":::"memory");return reg(0x40054028);}
static void save(State* state) {
  static const uint8_t offsets[]={0,4,8,12,16,44,48};
  for(unsigned b=0;b<2;++b)for(unsigned k=0;k<7;++k)
    state->words[7*b+k]=reg(0xD0000080+64*b+offsets[k]);
}
static void restore(const State* state) {
  static const uint8_t offsets[]={0,4,8,12,16,44,48};
  for(unsigned b=0;b<2;++b)for(unsigned k=0;k<7;++k) {
    uint32_t value=state->words[7*b+k];
    if(k==5)value&=b?0x005FFFFFU:0x003FFFFFU;
    if(k==6)value&=0x001FFFFFU;
    put(0xD0000080+64*b+offsets[k],value);
  }
}
static int same(const State* a,const State* b) {
  for(unsigned k=0;k<14;++k)if(a->words[k]!=b->words[k])return 0;
  return 1;
}
static void clocks(uint32_t* out) {
  static const uint32_t addresses[]={0x4000803C,0x40008040,0x40008044,0x40028000,0x40028004,0x40028008,0x4002800C};
  for(unsigned k=0;k<7;++k)out[k]=reg(addresses[k]);
}
static void save_divider(uint32_t* out) {
  out[0]=reg(0xD0000060);out[1]=reg(0xD0000064);
  out[3]=reg(0xD0000074);out[2]=reg(0xD0000070);
}
static void restore_divider(const uint32_t* in) {
  put(0xD0000060,in[0]);put(0xD0000064,in[1]);
  put(0xD0000074,in[3]);put(0xD0000070,in[2]);(void)reg(0xD0000070);
}
static uint32_t random32(uint32_t* s) {uint32_t x=*s;x^=x<<13;x^=x>>17;x^=x<<5;return *s=x;}
static void fill(unsigned group,unsigned kind) {
  uint32_t random=0x725abc11U+kind*37U;
  for(unsigned i=0;i<STREAM;++i) {
    if(group==1 || group==2) {
      inputs[i].a=((uint64_t)random32(&random)<<32)|random32(&random);
      inputs[i].b=kind==0?32:kind==1?256:1024;
    } else {inputs[i].a=fo_inputs[kind][i];inputs[i].b=0;}
  }
}
#if INTERP_VARIANT==1
static UnaryPair* const left[]={fo_ln_cpu};
static UnaryPair* const right[]={fo_ln_interp};
#elif INTERP_VARIANT==2
static UnaryPair* const left[]={fo_texture_cpu,fo_audio_cpu};
static UnaryPair* const right[]={fo_texture_pop,fo_audio_interp};
#elif INTERP_VARIANT==3
static UnaryPair* const left[]={fo_sqrt_base,fo_sqrt_base};
static UnaryPair* const right[]={fo_sqrt_new_cpu,fo_sqrt_new_interp};
#elif INTERP_VARIANT==4
static UnaryPair* const left[]={fo_rsqrt_base,fo_rsqrt_base};
static UnaryPair* const right[]={fo_rsqrt_new_cpu,fo_rsqrt_new_interp};
#endif
static void setup(unsigned group) {
#if INTERP_VARIANT==1
  (void)group;fo_lookup_setup();
#elif INTERP_VARIANT==2
  if(group==1)fo_texture_setup();else fo_audio_setup();
#else
  (void)group;fo_root_setup();
#endif
}
static __attribute__((noipa)) uint64_t identity(uint64_t a,uint64_t b) {(void)b;return a;}
#if INTERP_VARIANT==2
static uint32_t time_batch(UnaryPair* function,unsigned group,unsigned mode,int hardware) {
  uint32_t elapsed=0,sum=0;
  if(hardware && !mode)setup(group);
  for(unsigned k=0;k<SAMPLES;++k) {
    const Pair in=inputs[k&(STREAM-1)];uint64_t result;const uint32_t start=micros();
    if(hardware && mode){State state;save(&state);setup(group);result=function(in.a,in.b);restore(&state);}
    else result=function(in.a,in.b);
    elapsed+=micros()-start;
    // Whole output validation and hashing deliberately follow the stop timer.
    if(function!=identity) {
      output.failures+=fo_pop_verify(group-1,in.a,(unsigned)in.b);
      const uint32_t bytes=(unsigned)in.b*(group==2?2:1);
      sum=interp_checksum_step(sum,((uint64_t)fo_pop_hash(bytes)<<32)|(uint32_t)(result^(result>>32)),k);
    } else sum=interp_checksum_step(sum,result,k);
    mk61_api->service();
  }
  sink=sum;last_checksum=sum;
  restore(&output.state_before);restore_divider(output.divider_before);
  State now;save(&now);if(!same(&now,&output.state_before))++output.failures;
  return elapsed;
}
#else
static uint32_t time_batch(UnaryPair* function,unsigned group,unsigned mode,int hardware) {
  uint32_t sum=0;
  // Prepared state is amortised across the batch; mode 1 includes the full
  // per-call snapshot, setup and restore. Neither mode disables interrupts.
  if(hardware && !mode)setup(group);
  const uint32_t start=micros();
  for(unsigned k=0;k<SAMPLES;++k) {
    const Pair p=inputs[k&(STREAM-1)];
    uint64_t result;
    if(hardware && mode) {
      State state;save(&state);setup(group);
      result=function(p.a,p.b);restore(&state);
    } else result=function(p.a,p.b);
    // This shared V3 step is checked for all 64 individual result bits at
    // every repeated stream position. Its cost remains inside raw timings.
    sum=interp_checksum_step(sum,result,k);
  }
  const uint32_t elapsed=micros()-start;
  sink=sum;last_checksum=sum;
  restore(&output.state_before);restore_divider(output.divider_before);
  State now;save(&now);if(!same(&now,&output.state_before))++output.failures;
  if(reg(0xD0000000)!=output.core)++output.failures;
  return elapsed;
}
#endif
static void correctness(void) {
  for(unsigned local=0;local<GROUPS;++local)for(unsigned kind=0;kind<CASES;++kind) {
    const unsigned group=FIRST_GROUP+local;fill(group,kind);setup(group);
    for(unsigned i=0;i<STREAM;++i) {
      const Pair in=inputs[i];const uint64_t a=left[local](in.a,in.b);
#if INTERP_VARIANT==2
      output.failures+=fo_pop_verify(group-1,in.a,(unsigned)in.b);
#endif
      const uint64_t b=right[local](in.a,in.b);
#if INTERP_VARIANT==2
      output.failures+=fo_pop_verify(group-1,in.a,(unsigned)in.b);
#endif
      ++output.checks;if(a!=b)++output.failures;
#if INTERP_VARIANT==3
      if(a!=fo_sqrt_expected[kind][i])++output.failures;
#elif INTERP_VARIANT==4
      if(a!=fo_rsqrt_expected[kind][i])++output.failures;
#endif
    }
    restore(&output.state_before);restore_divider(output.divider_before);mk61_api->service();
  }
}
static void hex_word(char* p,uint32_t v) {
  static const char digits[]="0123456789ABCDEF";
  for(unsigned i=0;i<8;++i)p[i]=digits[(v>>(28-4*i))&15];
}
static uint32_t result_crc32(const uint8_t* p,unsigned n) {
  uint32_t crc=0xffffffffU;
  for(unsigned i=0;i<n;++i) {
    crc^=p[i];
    for(unsigned b=0;b<8;++b)crc=(crc>>1)^((crc&1U)?0xedb88320U:0);
  }
  return crc^0xffffffffU;
}
static int emit_result(const mk61_app_services* services,const uint8_t* p,unsigned n) {
  static const char digits[]="0123456789ABCDEF";
  char bookend[]="IFO4:B:00000000:00000000\n";
  const uint32_t crc=result_crc32(p,n);
  hex_word(bookend+7,n);hex_word(bookend+16,crc);
  if(services->call(MK61_SERVICE_DEBUG_WRITE,sizeof(bookend)-1,0,0,bookend)!=1)return 0;
  for(unsigned at=0;at<n;) {
    char line[81]="IFO4:D:00000000:";
    const unsigned count=n-at<32?n-at:32;
    hex_word(line+7,at);
    for(unsigned i=0;i<count;++i) {
      const unsigned v=p[at+i];line[16+2*i]=digits[v>>4];line[17+2*i]=digits[v&15];
    }
    line[16+2*count]='\n';
    if(services->call(MK61_SERVICE_DEBUG_WRITE,17+2*count,0,0,line)!=1)return 0;
    at+=count;
  }
  bookend[5]='E';
  return services->call(MK61_SERVICE_DEBUG_WRITE,sizeof(bookend)-1,0,0,bookend)==1;
}
int main(void) {
  const mk61_app_services* services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_DEBUG_IO);
  if(!services)return MK61_APP_RUNTIME_ERROR;
  output.magic=0x324f4649;output.version=4;output.bytes=sizeof(output);output.rows=ROWS;
  output.rounds=ROUNDS;output.samples=SAMPLES;output.core=reg(0xD0000000);
  __asm__ volatile("mrs %0,control":"=r"(output.control));
  __asm__ volatile("mrs %0,ipsr":"=r"(output.ipsr));
  __asm__ volatile("mrs %0,primask":"=r"(output.primask));
  // No peripheral mutation on an unexpected execution context or busy divider.
  if(output.core || (output.control&1U) || output.ipsr || output.primask || (reg(0xD0000078)&3U)!=1U)
    return MK61_APP_RUNTIME_ERROR;
  save(&output.state_before);save_divider(output.divider_before);clocks(output.clocks_before);
  correctness();
  if(!output.failures)for(unsigned local=0;local<GROUPS;++local)for(unsigned mode=0;mode<2;++mode)
    for(unsigned kind=0;kind<CASES;++kind) {
      const unsigned group=FIRST_GROUP+local;
      Row* row=&output.row[(local*2+mode)*CASES+kind];row->group=group;row->mode=mode;row->input=kind;
      fill(group,kind);row->a=inputs[0].a;row->b=inputs[0].b;
      setup(group);row->result_a=left[local](row->a,row->b);row->result_b=right[local](row->a,row->b);
      restore(&output.state_before);restore_divider(output.divider_before);
      for(unsigned r=0;r<ROUNDS;++r) {
        mk61_api->service();row->empty[r][0]=time_batch(identity,group,0,0);
        // Rotate ABBA/BAAB to expose order effects; store physical order.
        for(unsigned q=0;q<4;++q) {
          const int b=(q==1 || q==2)^(r&1U);mk61_api->service();
          const int hw=b && group!=3 && group!=5;
          row->raw[r][q]=time_batch(b?right[local]:left[local],group,mode,hw);
          row->checksum[r][q]=last_checksum;
        }
        if(row->checksum[r][0]!=row->checksum[r][3] || row->checksum[r][1]!=row->checksum[r][2])++output.failures;
        if(row->checksum[r][0]!=row->checksum[r][1])++output.failures;
        mk61_api->service();row->empty[r][1]=time_batch(identity,group,0,0);
      }
    }
  restore(&output.state_before);restore_divider(output.divider_before);
  save(&output.state_after);save_divider(output.divider_after);clocks(output.clocks_after);
  output.restored=same(&output.state_before,&output.state_after);
  if(!output.restored)++output.failures;
  for(unsigned i=0;i<4;++i)if(output.divider_before[i]!=output.divider_after[i])++output.failures;
  for(unsigned i=0;i<7;++i)if(output.clocks_before[i]!=output.clocks_after[i])++output.failures;
  output.status=output.failures?2:1;
  // All measurement and peripheral restoration finished above. Existing
  // resident DEBUG_WRITE emits ASCII only; no file transaction is started.
  const int emitted=emit_result(services,(const uint8_t*)&output,sizeof(output));
  return !emitted?MK61_APP_IO_ERROR:output.failures?MK61_APP_RUNTIME_ERROR:MK61_APP_OK;
}
