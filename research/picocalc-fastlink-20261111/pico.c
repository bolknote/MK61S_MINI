/* This diagnostic binds SDK resource allocators from one verified resident
 * image. It is deliberately not a public APP ABI or a production transport. */
#include "mk61_app.h"
#include "stm3_client.h"
#include "stm3_module.h"
#include "pico_uart1.h"
#include "link.h"
#include "identity_guard.h"
#include "native_pins.h"
#include "packages.h"
#include <string.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define PIO 0x50200000u
#define DMA 0x50000000u
#define I2C 0x40048000u
#define UART 0x40038000u
#define GPIO(n) (0x40014004u+8u*(n))
#define PAD(n) (0x4001c004u+4u*(n))
#define RESET 0x4000c000u
#include "resource_guard.h"
#include "idle_fence.h"
#include "native_health.h"
#include "logical_fence.h"
#define SM (PIO+0xc8u+24u*(unsigned)sm)
#define CH (DMA+64u*(unsigned)channel)
typedef struct {const uint16_t *instructions;uint8_t length;int8_t origin;uint8_t version;} program;
typedef struct {uint32_t clkdiv,execctrl,shiftctrl,pinctrl;} config;
static const mk61_app_services *svc;
static stm3_client client;
static stm3_pico_uart1 uart;
static uint8_t request[256],answer[256],expected[FL_MAX_BYTES];
static uint32_t received[FL_MAX_BYTES/3],module_id,job_id,cases,total_bytes;
static int module_loaded;
static int sm=-1,channel=-1,program_at=-1,sm_saved;
static uint16_t instructions[5];
static program code={instructions,5,-1,0};
static uint32_t pio_reset,sm_before[5],dma_before[4];
static uint32_t gpio_before[4],pad_before[4],i2c_before,uart_before;
static int pins_active,uart_borrowed;
static fl_idle_snapshot idle_trace;
static fl_logical_snapshot logical_trace;
static uint32_t micros(void *p){(void)p;return R(0x40054028u);}
static void line(const char *p) {
 while(*p){unsigned n=(unsigned)strlen(p);if(n>96)n=96;svc->call(MK61_SERVICE_DEBUG_WRITE,n,0,0,(void *)p);p+=n;}
}
static void note(const char *stage,int error) {
 char text[160];mk61_app_snprintf(svc,text,sizeof(text),"FL %s code=%d requests=%u tx=%u rx=%u uart_errors=%u\n",
  stage,error,client.requests,client.sent,client.received,uart.errors);line(text);
}
static int command(unsigned op,const void *input,unsigned n,unsigned *used) {
 *used=sizeof(answer);return stm3_client_request(&client,(uint8_t)op,input,n,answer,used,250000);
}
static int hello(void) {
 unsigned n;int e=command(S3_HELLO,0,0,&n);if(e)return e;
 const unsigned caps=S3_TRANSPORT_RX_DMA|S3_TRANSPORT_TX_DMA|S3_TRANSPORT_START_RESULT|
                     S3_TRANSPORT_START_RESULT_INPUT|S3_TRANSPORT_RESULT_V2;
 return n!=36||fl_get(answer)!=1||fl_get(answer+4)!=STM3_TARGET||
  fl_get(answer+8)!=6144||fl_get(answer+12)!=512||fl_get(answer+16)!=0||
  fl_get(answer+28)!=2250000||(fl_get(answer+32)&caps)!=caps?-10:0;
}
static int load(const uint8_t *p,unsigned bytes) {
 unsigned n;fl_put(request,bytes);int e=command(S3_LOAD_BEGIN,request,4,&n);if(e)return e;
 module_loaded=1;
 for(unsigned at=0;at<bytes;) {
  unsigned take=bytes-at;if(take>252)take=252;
  fl_put(request,at);memcpy(request+4,p+at,take);
  e=command(S3_LOAD_CHUNK,request,take+4,&n);if(e)return e;
  at+=take;if(n!=4||fl_get(answer)!=at)return -11;
  mk61_api->service();
  if(!fl_native_edge(FL_NATIVE_LOAD_SERVICE))return -45;
 }
 e=command(S3_LOAD_COMMIT,0,0,&n);if(e)return e;
 if(n!=4)return -12;
 module_id=fl_get(answer);return 0;
}
static int unload(void) {
 if(!module_loaded)return 0;
 unsigned n;int e=command(S3_UNLOAD,0,0,&n);if(!e){module_loaded=0;job_id=0;module_id=0;}return e;
}
static int identity(void) {
 int e=load(identity_package,sizeof(identity_package));if(e)return e;
 fl_put(request,module_id);fl_put(request+4,4);fl_put(request+8,1000);fl_put(request+12,120);
 fl_put(request+16,FL_ID_MAGIC);unsigned n;
 e=command(S3_START_RESULT_INPUT,request,20,&n);if(e)return e;
 if(n!=128||fl_get(answer+116)!=FL_ID_MAGIC)return -13;
 const uint8_t *p=answer+8;char text[256];
 mk61_app_snprintf(svc,text,sizeof(text),
  "FL ID bytes=%u crc=%08X calculated=%08X device=%08X cpuid=%08X flash_kib=%u rcc=%08X apb1=%08X dma7=%08X afio=%08X max_slice_us=%u\n",
  fl_get(p+16),fl_get(p+20),fl_get(p+36),fl_get(p+40),fl_get(p+112),fl_get(p+44),fl_get(p+48),
  fl_get(p+52),fl_get(p+56),fl_get(p+64),fl_get(answer+4));line(text);
 if(!fl_identity_valid(p,120)||fl_get(answer+4)>2000)return -14;
 return unload();
}
static int claim(void) {
 if(!fl_native_matches())return -20;
 channel=((int (*)(int))(uintptr_t)FL_DMA_CLAIM)(0);if(channel<0)return -21;
 for(unsigned i=0;i<4;++i)dma_before[i]=R(CH+4*i);
 if(R(CH+8)||(R(CH+12)&0x61000000u))return -22;
 if((R(DMA+0x400)|R(DMA+0x404)|R(DMA+0x414))&(1u<<(unsigned)channel))return -23;
 sm=((int (*)(uint32_t,int))(uintptr_t)FL_PIO_CLAIM)(PIO,0);if(sm<0)return -24;
 pio_reset=R(RESET)&(1u<<10);R(RESET+0x3000)=1u<<10;
 const uint32_t u=micros(0);while(!(R(RESET+8)&(1u<<10)))if(micros(0)-u>100)return -25;
 for(unsigned i=0;i<3;++i)sm_before[i]=R(SM+4*i);
 sm_before[3]=R(SM+20);sm_before[4]=R(SM+12);sm_saved=1;
 if(!fl_pio_resources_free((unsigned)sm))return -26;
 return 0;
}
static int remove_program(void) {
 if(program_at<0)return 0;
 R(PIO+0x3000)=1u<<(unsigned)sm;
 ((void (*)(uint32_t,const program *,unsigned))(uintptr_t)FL_PIO_REMOVE)(PIO,&code,(unsigned)program_at);
 program_at=-1;return 0;
}
static int configure(unsigned mode,unsigned bytes) {
 remove_program();
 const unsigned clock=mode==FL_SOFT3?6:7,data=mode==FL_SOFT3?7:6,bits=mode==FL_SOFT3?3:1;
 instructions[0]=(uint16_t)(0x2000u|clock); /* WAIT 0 GPIO clock */
 instructions[1]=(uint16_t)(0x2080u|clock); /* WAIT 1 GPIO clock */
 instructions[2]=(uint16_t)(0x4000u|bits); /* IN pins,bits */
 instructions[3]=0x0040u;                /* JMP X--,0 (SDK relocates) */
 instructions[4]=0x0004u;                /* finite idle at last instruction */
 if(!((int (*)(uint32_t,const program *))(uintptr_t)FL_PIO_CAN_ADD)(PIO,&code))return -27;
 program_at=(int)((unsigned (*)(uint32_t,const program *))(uintptr_t)FL_PIO_ADD)(PIO,&code);
 config c={0x10000u,((unsigned)(program_at+4)<<12)|((unsigned)program_at<<7),
           (24u<<20)|(1u<<16)|(1u<<19),data<<15};
 if(((int (*)(uint32_t,unsigned,unsigned,const config *))(uintptr_t)FL_PIO_INIT)
    (PIO,(unsigned)sm,(unsigned)program_at,&c)<0)return -28;
 ((void (*)(uint32_t,unsigned,unsigned,unsigned,int))(uintptr_t)FL_PIO_PINDIRS)(PIO,(unsigned)sm,6,4,0);
 /* Seed X before joining FIFOs; the receiver stops after the exact bit count. */
 R(PIO+0x10+4*(unsigned)sm)=bytes*8/bits-1;
 R(SM+16)=0x80a0u; /* PULL block */
 R(SM+16)=0x6020u; /* OUT X,32 */
 R(SM+8)=c.shiftctrl|(1u<<31);
 R(PIO+8)=(1u<<(unsigned)sm)|(1u<<(8+(unsigned)sm))|
           (1u<<(16+(unsigned)sm))|(1u<<(24+(unsigned)sm));
 memset(received,0xcc,sizeof(received));
 R(CH+0x10)=((unsigned)channel<<11); /* AL1_CTRL: non-triggering */
 R(CH)=PIO+0x20+4*(unsigned)sm;R(CH+4)=(uint32_t)(uintptr_t)received;R(CH+8)=bytes/3;
 R(CH+12)=1u|8u|32u|((unsigned)channel<<11)|((4u+(unsigned)sm)<<15)|(1u<<21);
 R(PIO+0x2000)=1u<<(unsigned)sm;return 0;
}
static __attribute__((noinline,noclone,noipa)) int take_pins(void) {
 if(!fl_native_edge(FL_NATIVE_BEFORE_LOGICAL))return -45;
 const int logical=fl_finish_keyboard(mk61_api->service,&logical_trace);
 if(!fl_native_edge(FL_NATIVE_AFTER_LOGICAL))return -45;
 if(!logical)return -44;
 /* No services after logical completion: only core0 can post the next
  * keyboard request. Core1 now has no unfinished logical transaction. */
 const int physical=fl_i2c_idle_fence(&idle_trace);
 if(!fl_native_edge(FL_NATIVE_AFTER_PHYSICAL))return -45;
 if(!physical)return -30;
 for(unsigned i=0;i<4;++i){gpio_before[i]=R(GPIO(6+i));pad_before[i]=R(PAD(6+i));}
 i2c_before=R(I2C+0x6c);uart_before=R(UART+0x30);pins_active=1;
 R(I2C+0x6c)=0;
 const uint32_t u=micros(0);while(R(I2C+0x9c)&1u)if(micros(0)-u>100)return -31;
 for(unsigned i=0;i<2;++i){R(PAD(6+i))=(pad_before[i]&~0x8cu)|0x48u;R(GPIO(6+i))=(gpio_before[i]&~31u)|6u;}
 return 0;
}
static void native_snapshot(const char *name,const fl_native_snapshot *s) {
 char text[320];
 mk61_app_snprintf(svc,text,sizeof(text),
  "FL NATIVE_%s at=%u timeouts=%u resets=%u aborts=%u errors=%u stage=%u result=%d pending=%u phase=%u online=%u\n",
  name,s->at,s->timeouts,s->resets,s->aborts,s->errors,s->stage,(int32_t)s->result,s->pending,s->phase,s->online);line(text);
}
static void native_fault(void) {
 if(!fl_native_fault)return;
 char text[160];
 mk61_app_snprintf(svc,text,sizeof(text),"FL NATIVE_FAIL case=%u boundary=%u previous_boundary=%u\n",
  cases,fl_native_fault,fl_native_fault_previous_edge);line(text);
 native_snapshot("BEFORE",&fl_native_fault_before);native_snapshot("AFTER",&fl_native_fault_after);
}
static void fence_error(int error) {
 char text[384];
 if(error==-44 || error==-45) {
  mk61_app_snprintf(svc,text,sizeof(text),
   "FL LOGICAL_STOP code=%d us=%u calls=%u initial_pending=%u initial_phase=%u pending=%u phase=%u\n",
   error,logical_trace.waited,logical_trace.calls,logical_trace.initial_pending,logical_trace.initial_phase,
   logical_trace.pending,logical_trace.phase);line(text);return;
 }
 mk61_app_snprintf(svc,text,sizeof(text),
  "FL FENCE_FAIL code=%d logical_us=%u calls=%u initial_pending=%u initial_phase=%u pending=%u phase=%u idle_us=%u samples=%u stable=%u mask=%08X tx=%u rx=%u status=%08X pins=%02X raw=%08X en=%08X es=%08X\n",
  error,logical_trace.waited,logical_trace.calls,logical_trace.initial_pending,logical_trace.initial_phase,
  logical_trace.pending,logical_trace.phase,idle_trace.waited,idle_trace.samples,idle_trace.stable,
  idle_trace.mask,idle_trace.tx,idle_trace.rx,idle_trace.status,idle_trace.pins,idle_trace.raw,idle_trace.enable,idle_trace.enabled);line(text);
}
static void borrow_uart(void) {
 R(UART+0x30)=0;uart_borrowed=1;
 for(unsigned i=2;i<4;++i){R(PAD(6+i))=(pad_before[i]&~0x8cu)|0x48u;R(GPIO(6+i))=(gpio_before[i]&~31u)|6u;}
}
static int restore_pins(void) {
 if(!pins_active)return 0;
 for(unsigned i=0;i<4;++i){R(GPIO(6+i))=gpio_before[i];R(PAD(6+i))=pad_before[i];}
 if(uart_borrowed){R(UART+4)=0;R(UART+0x30)=uart_before;uart_borrowed=0;}
 R(I2C+0x6c)=i2c_before;pins_active=0;
 const uint32_t u=micros(0);while((R(I2C+0x9c)&1u)!=(i2c_before&1u))if(micros(0)-u>100)return -32;
 for(unsigned i=0;i<4;++i)if(R(GPIO(6+i))!=gpio_before[i]||R(PAD(6+i))!=pad_before[i])return -33;
 return R(UART+0x30)!=uart_before?-34:0;
}
static void stop_capture(void) {
 if(sm>=0)R(PIO+0x3000)=1u<<(unsigned)sm;
 if(channel>=0) {
  R(CH+0x10)=R(CH+12)&~1u;
  R(DMA+0x444)=1u<<(unsigned)channel;
  const uint32_t u=micros(0);while((R(DMA+0x444)&(1u<<(unsigned)channel))&&micros(0)-u<100){}
  R(DMA+0x400)=1u<<(unsigned)channel;
 }
}
static void finish_claim(void) {
 stop_capture();remove_program();
 if(sm>=0&&sm_saved) {
  R(SM)=sm_before[0];R(SM+4)=sm_before[1];R(SM+8)=sm_before[2];R(SM+20)=sm_before[3];
  R(SM+16)=sm_before[4]&31u;
  if(pio_reset)R(RESET+0x2000)=1u<<10;
 }
 if(sm>=0){((void (*)(uint32_t,unsigned))(uintptr_t)FL_PIO_UNCLAIM)(PIO,(unsigned)sm);sm=-1;sm_saved=0;}
 if(channel>=0) {
  for(unsigned i=0;i<3;++i)R(CH+4*i)=dma_before[i];
  R(CH+0x10)=dma_before[3]&0x00ffffffu;
  ((void (*)(unsigned))(uintptr_t)FL_DMA_UNCLAIM)((unsigned)channel);channel=-1;
 }
}
static int one(unsigned mode,unsigned bytes,unsigned rate,unsigned pattern,uint32_t seed) {
 unsigned n;int e=0,capture_error=0;uint32_t work=0,mix=1,first=0,last=0;
 fl_pattern(expected,bytes,pattern,seed);
 if(mode!=FL_UART){e=take_pins();if(e){fence_error(e);return e;}e=configure(mode,bytes);if(e)return e;}
 else if(!fl_native_edge(FL_NATIVE_BEFORE_LOGICAL))return -45;
 fl_put(request,module_id);fl_put(request+4,24);fl_put(request+8,1000);
 fl_put(request+12,mode==FL_UART?96+bytes:96);fl_put(request+16,FL_MAGIC);
 fl_put(request+20,mode);fl_put(request+24,bytes);fl_put(request+28,rate);
 fl_put(request+32,pattern);fl_put(request+36,seed);
 const uint32_t start=micros(0);
 e=stm3_client_begin(&client,S3_START_RESULT_INPUT,request,40,250000);if(e)return e;
 while(R(UART+0x18)&8u)if(micros(0)-start>=500)return -35;
 const uint32_t sent=micros(0);
 if(mode==FL_SOFT3)borrow_uart();
 if(mode!=FL_UART) {
  while(R(CH+8)&&micros(0)-sent<2200) {
   for(unsigned i=0;i<16;++i){mix=mix*1664525u+1013904223u;mix^=mix>>13;}work+=16;
   unsigned left=R(CH+8);if(!first&&left<bytes/3)first=micros(0);
  }
  last=micros(0);capture_error=R(CH+8)?-36:(R(CH+12)&0x60000000u)?-37:0;
  if(R(PIO+8)&(1u<<(unsigned)sm))capture_error=-38;
  stop_capture();
  /* Allow a failed/partial burst to finish restoring M3's GPIO before UART
   * reception is re-enabled. The module defers its result until >=4ms. */
  while(micros(0)-sent<2500)__asm__ volatile("nop");
  int cleanup=restore_pins();if(cleanup)return cleanup;
  (void)fl_native_edge(FL_NATIVE_AFTER_RESTORE);
 }
 n=sizeof(answer);e=stm3_client_finish(&client,answer,&n,250000);if(e)return e;
 if(fl_native_fault)return -45;
 if(n!=(mode==FL_UART?104+bytes:104)||fl_get(answer+8)!=FL_MAGIC||
    fl_get(answer+12)!=mode||fl_get(answer+16)!=bytes||fl_get(answer+20)!=rate)return -39;
 job_id=fl_get(answer);
 char text[768];mk61_app_snprintf(svc,text,sizeof(text),
  "FL CASE i=%u mode=%u bytes=%u rate_arg=%u pattern=%u seed=%08X m3_error=%u crc=%08X prep_us=%u prep_cycles=%u burst_us=%u burst_cycles=%u wire_us=%u wire_cycles=%u m3_work=%u pico_work=%u capture_span_us=%u total_us=%u max_slice_us=%u capture_error=%d mix=%08X idle_us=%u idle_samples=%u logical_us=%u logical_calls=%u\n",
  cases,mode,bytes,rate,pattern,seed,fl_get(answer+24),fl_get(answer+28),fl_get(answer+32),fl_get(answer+36),
  fl_get(answer+40),fl_get(answer+44),fl_get(answer+60),fl_get(answer+64),fl_get(answer+48),work,first?last-first:0,micros(0)-start,
  fl_get(answer+4),capture_error,mix,idle_trace.waited,idle_trace.samples,logical_trace.waited,logical_trace.calls);line(text);
 mk61_app_snprintf(svc,text,sizeof(text),
  "FL BUS i=%u entry_flags=%08X before_sr1=%08X before_sr2=%08X before_idr=%08X restore_flags=%08X after_sr1=%08X after_sr2=%08X\n",
  cases,fl_get(answer+72),fl_get(answer+76),fl_get(answer+80),fl_get(answer+84),fl_get(answer+88),fl_get(answer+92),fl_get(answer+96));line(text);
 if(fl_get(answer+24)||fl_get(answer+68)||fl_get(answer+4)>2000)return -40;
 if(capture_error)return capture_error;
 if(fl_get(answer+28)!=~fl_crc_step(~0u,expected,bytes))return -41;
 for(unsigned i=0;i<bytes;++i) {
  unsigned value=mode==FL_UART?answer[104+i]:(received[i/3]>>(16-8*(i%3)))&255u;
  if(value!=expected[i]){mk61_app_snprintf(svc,text,sizeof(text),"FL MISMATCH byte=%u expected=%02X actual=%02X\n",i,expected[i],value);line(text);return -42;}
 }
 mk61_api->service();if(!fl_native_edge(FL_NATIVE_POST_SERVICE))return -45;
 ++cases;total_bytes+=bytes;return 0;
}
static int run(void) {
 int e=hello();if(e)return e;note("HELLO",0);
 e=identity();if(e)return e;
 e=claim();if(e)return e;note("CLAIMED",0);
 e=load(link_package,sizeof(link_package));if(e)return e;
 /* Rate progression is explicit. The first failure ends the entire run. */
 const unsigned modes[]={FL_UART,FL_SOFT1,FL_SOFT3,FL_DMA1};
 for(unsigned m=0;m<4;++m) {
  const unsigned mode=modes[m];
  const unsigned count=mode==FL_DMA1?4:mode==FL_UART?1:3;
  for(unsigned r=0;r<count;++r)for(unsigned kind=0;kind<7;++kind) {
   const unsigned rate=mode==FL_DMA1?(r==0?36:r==1?18:r==2?8:4):mode==FL_UART?0:r==0?8:r==1?2:0;
   e=one(mode,24,rate,kind,0x9e3779b9u+cases*17u);if(e)return e;
   const int key=mk61_api->key_poll();
   if(!fl_native_edge(FL_NATIVE_POST_KEYPOLL))return -45;
   if(key==MK61_APP_KEY_ESC)return -43;
  }
 }
 for(unsigned mode=FL_SOFT1;mode<=FL_SOFT3;++mode)for(unsigned kind=0;kind<7;++kind) {
  e=one(mode,96,0,kind,0xa55a39c6u+cases*29u);if(e)return e;
 }
 e=unload();if(e)return e;
 return identity();
}
int main(void) {
 svc=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FORMAT|MK61_SERVICE_CAP_DEBUG_IO);
 if(!svc)return MK61_APP_RUNTIME_ERROR;
 line("FL BEGIN v=1 expected_build=7C38C634 pico_hz=125000000 m3_hz=72000000 ram_only=1\n");
 if(mk61_app_compute_hz(svc)!=125000000u||!fl_native_matches()){note("IDENTITY_FAIL",-50);return 0;}
 fl_native_start();
 if(!stm3_pico_uart1_begin(&uart,micros,0,48000000,2250000)){note("UART_FAIL",-51);return 0;}
 const stm3_client_io io={&uart,stm3_pico_uart1_micros,stm3_pico_uart1_send,stm3_pico_uart1_read};
 stm3_client_init(&client,&io);
 int error=run();stop_capture();int cleanup=restore_pins();if(!error&&cleanup)error=cleanup;
 finish_claim();cleanup=unload();if(!error&&cleanup)error=cleanup;
 if(!cleanup){cleanup=hello();if(!error&&cleanup)error=cleanup;}
 stm3_pico_uart1_end(&uart);
 if(!fl_native_edge(FL_NATIVE_CLEANUP)&&!error)error=-45;
 native_fault();
 char text[160];mk61_app_snprintf(svc,text,sizeof(text),"FL %s code=%d cases=%u bytes=%u uart_errors=%u resources_released=1\n",
  error?"FAIL":"PASS",error,cases,total_bytes,uart.errors);line(text);
 return MK61_APP_OK;
}
