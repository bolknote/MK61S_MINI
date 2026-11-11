// Trusted finite Cortex-M3 benchmark: DWT counts, unchanged offset-Q4 values.
#include "stm3_module.h"
#define WORD(a) (*(volatile uint32_t*)(uintptr_t)(a))
#define DEMCR WORD(0xe000edfcu)
#define CTRL WORD(0xe0001000u)
#define CYCLES WORD(0xe0001004u)
static uint32_t saved_demcr,saved_ctrl,claimed,runs,started_us,started_cycles;
static uint32_t get32(const uint8_t*p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void put32(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(v>>(8*i));}
struct __attribute__((packed,may_alias)) word {uint32_t value;};
typedef int32_t(*kernel)(const uint8_t*,const int16_t*);
#define KERNEL __attribute__((noinline,noclone,noipa))
static KERNEL int32_t dot_loop(const uint8_t*w,const int16_t*x){
 int32_t sum=0;
 for(unsigned i=0;i<32;i+=8){
  const uint32_t p=((const struct word*)(const void*)(w+i/2))->value;
  for(unsigned j=0;j<8;++j)sum+=((int32_t)((p>>(4*j))&15u)-8)*x[i+j];
 }return sum;
}
#define UB(bit,index) do{uint32_t v;__asm__ volatile("ubfx %0,%1,#" #bit ",#4":"=r"(v):"r"(p));sum+=((int32_t)v-8)*x[i+index];}while(0)
static KERNEL int32_t dot_ubfx(const uint8_t*w,const int16_t*x){
 int32_t sum=0;
 for(unsigned i=0;i<32;i+=8){const uint32_t p=((const struct word*)(const void*)(w+i/2))->value;
  UB(0,0);UB(4,1);UB(8,2);UB(12,3);UB(16,4);UB(20,5);UB(24,6);UB(28,7);
 }return sum;
}
#define SB(bit,index) do{int32_t v;__asm__ volatile("sbfx %0,%1,#" #bit ",#4":"=r"(v):"r"(p));sum+=v*x[i+index];}while(0)
static KERNEL int32_t dot_sbfx(const uint8_t*w,const int16_t*x){
 int32_t sum=0;
 for(unsigned i=0;i<32;i+=8){
  // Offset binary nibble n-8 becomes signed two's-complement after XOR8.
  const uint32_t p=((const struct word*)(const void*)(w+i/2))->value^0x88888888u;
  SB(0,0);SB(4,1);SB(8,2);SB(12,3);SB(16,4);SB(20,5);SB(24,6);SB(28,7);
 }return sum;
}
static const kernel kernels[3]={dot_loop,dot_ubfx,dot_sbfx};
static int start_counter(void){
 if(!claimed){
  if(CTRL&(1u<<25))return 0;
  saved_demcr=DEMCR;saved_ctrl=CTRL;claimed=1;
  DEMCR|=1u<<24;CTRL|=1u;
 }
 const uint32_t before=CYCLES;
 __asm__ volatile("dsb\n\tisb\n\tnop\n\tnop\n\tnop\n\tnop\n\tnop\n\tnop":::"memory");
 return CYCLES!=before;
}
__attribute__((section(".text.module_entry"),used))
uint32_t module_entry(uint32_t op,const stm3_api*api,stm3_job*job){
 if(!api||api->abi!=STM3_ABI||api->size!=sizeof(stm3_api))return STM3_INVALID;
 if(op==STM3_FINI){if(claimed){CTRL=saved_ctrl;DEMCR=saved_demcr;claimed=0;}return STM3_DONE;}
 if(op==STM3_CANCEL)return STM3_DONE;
 if(job->input_bytes==16&&get32(job->input)==0x314d4350u){
  if(op!=STM3_INIT||get32(job->input+4)!=512||job->output_capacity<512)return STM3_INVALID;
  const uint32_t seed=get32(job->input+8);
  for(unsigned i=0;i<512;++i)job->output[i]=(uint8_t)(seed+29u*i+(i>>4));
  job->output_bytes=512;job->progress=128;return STM3_DONE;
 }
 if(job->input_bytes<12||get32(job->input)!=0x31544451u||get32(job->input+8)!=32)return STM3_INVALID;
 const unsigned rows=get32(job->input+4);
 if(!rows||rows>16||job->input_bytes!=76+rows*16||job->output_capacity<64+4*rows)return STM3_INVALID;
 uint8_t*out=job->output;
 if(op==STM3_INIT){
  if(!start_counter())return STM3_INVALID;
  ++runs;job->progress=0;job->output_bytes=64+4*rows;
  put32(out,rows);put32(out+4,runs);put32(out+8,16);
  uint32_t overhead=~0u;
  for(unsigned i=0;i<8;++i){uint32_t a=CYCLES;__asm__ volatile("":::"memory");uint32_t delta=CYCLES-a;if(delta<overhead)overhead=delta;}
  put32(out+12,overhead);
  for(unsigned k=0;k<3;++k){put32(out+16+4*k,~0u);put32(out+28+4*k,0);put32(out+40+4*k,0);}
  put32(out+52,rows*16);put32(out+56,0);put32(out+60,0);
  started_us=api->micros(api->context);started_cycles=CYCLES;return STM3_MORE;
 }
 if(op!=STM3_STEP||job->progress>=rows)return STM3_INVALID;
 const uint8_t*w=job->input+76+16*job->progress;
 const int16_t*x=(const int16_t*)(const void*)(job->input+12);
 const int32_t reference=dot_loop(w,x);
 for(unsigned repetition=0;repetition<16;++repetition)for(unsigned k=0;k<3;++k){
  __asm__ volatile("":::"memory");const uint32_t a=CYCLES;
  const int32_t result=kernels[k](w,x);const uint32_t took=CYCLES-a;
  if(result!=reference)return STM3_INVALID;
  if(took<get32(out+16+4*k))put32(out+16+4*k,took);
  if(took>get32(out+28+4*k))put32(out+28+4*k,took);
  put32(out+40+4*k,get32(out+40+4*k)+took);
 }
 put32(out+64+4*job->progress,(uint32_t)reference);++job->progress;
 if(job->progress<rows)return STM3_MORE;
 put32(out+56,api->micros(api->context)-started_us);put32(out+60,CYCLES-started_cycles);
 return STM3_DONE;
}
