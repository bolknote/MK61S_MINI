/* Trusted diagnostic S3M, at stock 72MHz. No Flash, I2C2, TIM1/2/3 writes.
 * One <=1ms burst per job; IRQs remain enabled. All hardware is restored
 * before returning to the resident loop, including on a local timeout. */
#include "stm3_module.h"
#include "link.h"
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define PB 0x40010c00u
#define PC 0x40011000u
#define I2C 0x40005400u
#define UART 0x40004800u
#define TIM 0x40000800u
#define DMA 0x40020000u
#define CH7 (DMA+0x80u)
#define RCC 0x40021000u
#define CYC R(0xe0001004u)
#define CTRL R(0xe0001000u)
#define DEMCR R(0xe000edfcu)
static uint8_t payload[FL_MAX_BYTES];
static uint32_t wave[2*FL_DMA_BYTES*8+1];
static uint32_t started,phase,mode,size,rate,seed,pattern;
static uint32_t prep_us,prep_cycles,burst_us,burst_cycles,wire_us,wire_cycles,work,checksum;
static uint32_t saved_b,saved_c,saved_bo,saved_co,saved_i,saved_i2,saved_u1,saved_u3;
static uint32_t saved_i_config[4],entry_flags,entry_sr1,entry_sr2,entry_idr,restore_flags,post_sr1,post_sr2;
static uint32_t saved_clk,saved_tim[10],saved_dma[4];
static uint32_t saved_demcr,saved_ctrl,saved_cycles;
static const unsigned tim_offsets[10]={0,12,24,28,32,40,44,36,16,8};
static unsigned acquired;
static void gpio(uint32_t port,uint32_t mask,uint32_t value) {
 R(port+16)=(value&mask)|((~value&mask)<<16);
}
static int clock_ok(void) {
 /* SWS=PLL, HPRE=/1, PPRE1=/2, PPRE2=/1, PLLSRC=HSE, PLLMUL=x9. */
 return (R(RCC+4)&0x003ffffcu)==0x001d0408u && !(R(0x40010004u)&(1u<<12));
}
static int acquire(void) {
 entry_sr1=R(I2C+0x14);entry_sr2=R(I2C+0x18);entry_idr=R(PB+8);
 entry_flags=(!clock_ok()?1u:0)|((entry_sr2&2u)?2u:0)|(!(R(I2C)&1u)?4u:0)|
  ((entry_sr1&0xff00u)?8u:0)|((R(0xe000e200u)&0x80000000u)?16u:0)|
  ((R(0xe000e204u)&1u)?32u:0)|((R(UART)&0x0fu)?64u:0)|(!(R(UART)&0x40u)?128u:0);
 if(entry_flags)return 10;
 if(mode==FL_DMA1 && ((R(RCC+28)&4u)||(R(CH7)&1u)||(R(DMA)&0x0f000000u)||
    (R(0xe000e100u)&(1u<<17))||(R(0xe000e200u)&(1u<<17))))return 11;
 saved_b=R(PB+4)&0xffu;saved_bo=R(PB+12)&0x300u;
 saved_c=R(PC+4)&0xff00u;saved_co=R(PC+12)&0xc00u;
 saved_i=R(I2C);saved_i2=R(I2C+4);saved_u1=R(UART+12);saved_u3=R(UART+20);
 saved_i_config[0]=R(I2C+8);saved_i_config[1]=R(I2C+12);
 saved_i_config[2]=R(I2C+28);saved_i_config[3]=R(I2C+32);
 if(mode==FL_SOFT3 && ((R(DMA+0x1c)&1u)||(R(DMA+0x20))||
                       !(R(DMA+0x30)&1u)))return 12;
 /* No active I2C transaction. Disable only this interface, not PMU/I2C2. */
 R(I2C+4)=saved_i2&~0x700u;R(I2C)=saved_i&~1u;
 if(mode==FL_SOFT3) {
  R(UART+20)=saved_u3&~(0xc0u);R(DMA+0x30)&=~1u;R(UART+12)=0;
  gpio(PC,0xc00u,0xc00u);R(PC+4)=(R(PC+4)&~0xff00u)|0x3300u;
 }
 gpio(PB,0x300u,0x300u);R(PB+4)=(R(PB+4)&~0xffu)|0x33u;
 acquired=1;
 if(mode==FL_DMA1) {
  saved_clk=R(RCC+28)&4u;R(RCC+28)|=4u;
  for(unsigned i=0;i<10;++i)saved_tim[i]=R(TIM+tim_offsets[i]);
  for(unsigned i=0;i<4;++i)saved_dma[i]=R(CH7+4*i);
  if(saved_tim[0]||saved_tim[1]||saved_tim[2]||saved_tim[3]||saved_tim[4]||saved_tim[8]||saved_dma[0])return 13;
  acquired=2;
 }
 return 0;
}
static int level(const stm3_api *api,uint32_t mask,uint32_t wanted) {
 const uint32_t start=api->micros(api->context);
 do {if((R(PB+8)&mask)==wanted)return 1;}while(api->micros(api->context)-start<8u);
 return 0;
}
static int release(const stm3_api *api) {
 if(!acquired)return 0;
 if(mode==FL_DMA1) {
  R(TIM)=0;R(TIM+12)=0;R(CH7)=0;
  R(DMA+4)=0x0f000000u;
  for(unsigned i=1;i<10;++i)R(TIM+tim_offsets[i])=saved_tim[i];
  R(TIM)=saved_tim[0];
  for(unsigned i=1;i<4;++i)R(CH7+4*i)=saved_dma[i];
  R(CH7)=saved_dma[0];R(RCC+28)=(R(RCC+28)&~4u)|saved_clk;
 }
 /* ES096 Rev15 2.8.7: return the analog inputs through a verified OD
  * START/STOP sequence, then SWRST and restore I2C1's full configuration.
  * This is a peripheral reset, never an MCU reset. I2C2 is untouched.
  * Source: https://www.st.com/resource/en/errata_sheet/cd00190234-stm32f101x8-b-stm32f102x8-b-and-stm32f103x8-b-medium-density-device-limitations-stmicroelectronics.pdf */
 restore_flags=0;R(PB+4)=(R(PB+4)&~0xffu)|0x77u;gpio(PB,0x300u,0x300u);
 if(!level(api,0x300u,0x300u))restore_flags|=1;
 gpio(PB,0x200u,0);if(!level(api,0x200u,0))restore_flags|=2;
 gpio(PB,0x100u,0);if(!level(api,0x100u,0))restore_flags|=4;
 gpio(PB,0x100u,0x100u);if(!level(api,0x100u,0x100u))restore_flags|=8;
 gpio(PB,0x200u,0x200u);if(!level(api,0x200u,0x200u))restore_flags|=16;
 R(PB+4)=(R(PB+4)&~0xffu)|saved_b;gpio(PB,0x300u,saved_bo);
 R(I2C)=1u<<15;R(I2C)=0;
 R(I2C+4)=saved_i2&~0x700u;R(I2C+8)=saved_i_config[0];R(I2C+12)=saved_i_config[1];
 R(I2C+28)=saved_i_config[2];R(I2C+32)=saved_i_config[3];
 if(mode==FL_SOFT3) {
  R(PC+4)=(R(PC+4)&~0xff00u)|saved_c;gpio(PC,0xc00u,saved_co);
  R(UART+12)=saved_u1;R(DMA+0x30)|=1u;R(UART+20)=saved_u3;
 }
 R(I2C)=saved_i;R(I2C+4)=saved_i2;acquired=0;
 post_sr1=R(I2C+20);post_sr2=R(I2C+24);
 if((post_sr1&0xff00u)||(post_sr2&2u))restore_flags|=32;
 return restore_flags||(R(PB+4)&0xffu)!=saved_b||(R(PB+12)&0x300u)!=saved_bo||R(I2C)!=saved_i||
  R(I2C+4)!=saved_i2||R(I2C+8)!=saved_i_config[0]||R(I2C+12)!=saved_i_config[1]||
  R(I2C+28)!=saved_i_config[2]||R(I2C+32)!=saved_i_config[3]||
  (mode==FL_SOFT3 && ((R(PC+4)&0xff00u)!=saved_c||(R(PC+12)&0xc00u)!=saved_co||
                     R(UART+12)!=saved_u1||R(UART+20)!=saved_u3));
}
static void delay(unsigned n) {while(n--)__asm__ volatile("nop");}
static int soft(const stm3_api *api) {
 const uint32_t begin=api->micros(api->context),cycles=CYC;
 int error=0;
 const unsigned count=mode==FL_SOFT1?size*8:size*8/3;
 const uint32_t clock=mode==FL_SOFT1?0x100u:0x200u;
 for(unsigned i=0;i<count;++i) {
  if(mode==FL_SOFT1) {
   const uint32_t data=(payload[i/8]>>(7-(i&7)))&1u;
   gpio(PB,0x300u,data<<9);
  } else {
   const unsigned v=fl_group(payload,i);
   gpio(PB,0x300u,(v&1u)<<8);gpio(PC,0xc00u,((v&2u)<<10)|((v&4u)<<8));
  }
  delay(rate);R(PB+16)=clock;delay(rate);
  if((i&31u)==31u && api->micros(api->context)-begin>=FL_BURST_US){error=20;break;}
 }
 /* Keep clock high while data is released; restoration follows in this call. */
 gpio(PB,0x300u,0x300u);if(mode==FL_SOFT3)gpio(PC,0xc00u,0xc00u);
 wire_cycles=CYC-cycles;wire_us=api->micros(api->context)-begin;
 return error?error:wire_us>=FL_BURST_US?20:0;
}
static int dma(const stm3_api *api) {
 const unsigned levels=2*size*8;
 R(TIM)=0;R(TIM+12)=0;R(TIM+24)=0;R(TIM+28)=0;R(TIM+32)=0;
 R(TIM+40)=0;R(TIM+44)=rate-1;R(TIM+36)=0;R(TIM+20)=1;R(TIM+16)=0;
 R(CH7)=0;R(CH7+4)=levels;R(CH7+8)=PB+16;R(CH7+12)=(uint32_t)(uintptr_t)(wave+1);
 R(DMA+4)=0x0f000000u;R(PB+16)=wave[0];
 R(CH7)=1u|16u|128u|512u|2048u|0x2000u; /* 32->32, MINC, mem->periph, high */
 R(TIM+12)=1u<<8;
 const uint32_t begin=api->micros(api->context),cycles=CYC;
 int error=0;R(TIM)=1;
 while(!(R(DMA)&(0x0au<<24))) {
  /* Synthetic available work, no data movement or per-bit servicing by CPU. */
  for(unsigned i=0;i<16;++i){checksum=checksum*1664525u+1013904223u;checksum^=checksum>>13;}
  work+=16;
  if(api->micros(api->context)-begin>=FL_BURST_US){error=21;break;}
 }
 wire_cycles=CYC-cycles;wire_us=api->micros(api->context)-begin;
 return error?error:wire_us>=FL_BURST_US?21:(R(DMA)&(1u<<27))?22:0;
}
__attribute__((section(".text.module_entry"),used))
uint32_t module_entry(uint32_t op,const stm3_api *api,stm3_job *job) {
 if(!api||api->abi!=STM3_ABI||api->size!=sizeof(*api))return STM3_INVALID;
 if(op==STM3_CANCEL||op==STM3_FINI) {if(acquired)release(api);phase=0;return STM3_DONE;}
 if(job->output_capacity<96)return STM3_INVALID;
 if(op==STM3_INIT) {
  if(job->input_bytes!=24||fl_get(job->input)!=FL_MAGIC||acquired)return STM3_INVALID;
  mode=fl_get(job->input+4);size=fl_get(job->input+8);rate=fl_get(job->input+12);
  pattern=fl_get(job->input+16);seed=fl_get(job->input+20);
  if(!size||size>FL_MAX_BYTES||size%3||pattern>6||
     (mode!=FL_SOFT1&&mode!=FL_SOFT3&&mode!=FL_DMA1&&mode!=FL_UART)||
     (mode==FL_DMA1&&(size>FL_DMA_BYTES||(rate!=36&&rate!=18&&rate!=8&&rate!=4)))||
     (mode!=FL_DMA1&&rate>8))return STM3_INVALID;
  saved_demcr=DEMCR;saved_ctrl=CTRL;saved_cycles=CYC;
  DEMCR|=1u<<24;CTRL|=1u;
  const uint32_t u=api->micros(api->context),c=CYC;
  fl_pattern(payload,size,pattern,seed);work=checksum=wire_us=wire_cycles=0;
  entry_flags=entry_sr1=entry_sr2=entry_idr=restore_flags=post_sr1=post_sr2=0;
  if(mode==FL_DMA1)for(unsigned i=0;i<size*8;++i) {
   uint32_t data=((payload[i/8]>>(7-(i&7)))&1u)<<9;
   wave[2*i]=(data&0x300u)|((~data&0x300u)<<16);
   wave[2*i+1]=1u<<8;
  }
  if(mode==FL_DMA1)wave[2*size*8]=0x1000000u|0x200u; /* finite idle tail */
  prep_us=api->micros(api->context)-u;prep_cycles=CYC-c;
  CTRL=saved_ctrl;if(!(saved_ctrl&1u))CYC=saved_cycles;DEMCR=saved_demcr;
  started=api->micros(api->context);phase=1;return STM3_MORE;
 }
 if(op!=STM3_STEP||!phase)return STM3_INVALID;
 if(phase==1) {
  if(api->micros(api->context)-started<FL_READY_US)return STM3_MORE;
  int error=0;
  saved_demcr=DEMCR;saved_ctrl=CTRL;saved_cycles=CYC;
  DEMCR|=1u<<24;CTRL|=1u;
  const uint32_t u=api->micros(api->context),c=CYC;
  if(mode!=FL_UART)error=acquire();
  if(!error&&mode!=FL_UART)error=mode==FL_DMA1?dma(api):soft(api);
  burst_cycles=CYC-c;burst_us=api->micros(api->context)-u;
  int restored=release(api);CTRL=saved_ctrl;
  if(!(saved_ctrl&1u))CYC=saved_cycles;DEMCR=saved_demcr;
  if(restored&&!error)error=30;
  fl_put(job->output,FL_MAGIC);fl_put(job->output+4,mode);fl_put(job->output+8,size);
  fl_put(job->output+12,rate);fl_put(job->output+16,(uint32_t)error);
  fl_put(job->output+20,~fl_crc_step(~0u,payload,size));
  fl_put(job->output+24,prep_us);fl_put(job->output+28,prep_cycles);
  fl_put(job->output+32,burst_us);fl_put(job->output+36,burst_cycles);
  fl_put(job->output+40,work);fl_put(job->output+44,checksum);
  fl_put(job->output+48,R(RCC+4));fl_put(job->output+52,wire_us);
  fl_put(job->output+56,wire_cycles);fl_put(job->output+60,(uint32_t)restored);
  fl_put(job->output+64,entry_flags);fl_put(job->output+68,entry_sr1);fl_put(job->output+72,entry_sr2);
  fl_put(job->output+76,entry_idr);fl_put(job->output+80,restore_flags);
  fl_put(job->output+84,post_sr1);fl_put(job->output+88,post_sr2);fl_put(job->output+92,1);
  job->output_bytes=96;
  if(mode==FL_UART){for(unsigned i=0;i<size;++i)job->output[96+i]=payload[i];job->output_bytes+=size;}
  phase=2;return STM3_MORE;
 }
 if(api->micros(api->context)-started<FL_REPLY_US)return STM3_MORE;
 phase=0;job->progress=size;return STM3_DONE;
}
