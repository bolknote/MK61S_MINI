// Finite UART1/STM32 diagnostic. No calculator/state/RTC/settings/Flash writes.
#include "mk61_app.h"
#include "stm3_client.h"
#include "pico_uart1.h"
#include "module_package.h"
#include <string.h>
static const mk61_app_services*svc;
static stm3_client client;
static stm3_pico_uart1 uart;
static uint8_t input[332],answer[256],request[256];
static uint32_t module_id,job_id,checked;
static int touched_module;
static uint32_t micros(void*p){(void)p;return *(volatile uint32_t*)(uintptr_t)0x40054028u;}
static void line(const char*p){while(*p){unsigned n=(unsigned)strlen(p);if(n>128)n=128;svc->call(MK61_SERVICE_DEBUG_WRITE,n,0,0,(void*)p);p+=n;}}
static void message(const char*stage,int code){
 char s[128];mk61_app_snprintf(svc,s,sizeof(s),"S3PROBE %s code=%d tx=%lu rx=%lu uart_errors=%lu\n",stage,code,(unsigned long)client.sent,(unsigned long)client.received,(unsigned long)uart.errors);line(s);
}
static int cmd(uint8_t op,const void*data,unsigned n,unsigned*used){
 *used=sizeof(answer);return stm3_client_request(&client,op,data,n,answer,used,250000);
}
static int run(void){
 unsigned used;int error=cmd(S3_HELLO,0,0,&used);if(error)return error;
 if(used!=36||stm3_get32(answer)!=1||stm3_get32(answer+4)!=0x70301||
    stm3_get32(answer+8)!=6144||stm3_get32(answer+12)!=512||
    stm3_get32(answer+16)!=0||stm3_get32(answer+28)!=2250000||stm3_get32(answer+32)!=3)return -10;
 message("HELLO",0);
 stm3_put32(request,sizeof(stm3_package));error=cmd(S3_LOAD_BEGIN,request,4,&used);if(error)return error;
 touched_module=1;
 for(unsigned at=0;at<sizeof(stm3_package);){
  unsigned n=(unsigned)sizeof(stm3_package)-at;if(n>252)n=252;
  stm3_put32(request,at);memcpy(request+4,stm3_package+at,n);
  error=cmd(S3_LOAD_CHUNK,request,n+4,&used);if(error)return error;
  at+=n;if(used!=4||stm3_get32(answer)!=at)return -11;
 }
 error=cmd(S3_LOAD_COMMIT,0,0,&used);if(error)return error;
 if(used!=4)return -12;
 module_id=stm3_get32(answer);message("LOADED",0);
 for(unsigned test=0;test<4;++test){
  stm3_put32(input,0x31544451);stm3_put32(input+4,16);stm3_put32(input+8,32);
  for(unsigned i=0;i<32;++i){
   int x=(i&1)?32767:-32768;if(test>1)x=(int)((i*1777u+test*319u)&65535u)-32768;
   input[12+2*i]=(uint8_t)x;input[13+2*i]=(uint8_t)((uint32_t)x>>8);
  }
  for(unsigned row=0;row<16;++row)for(unsigned j=0;j<16;++j)
   input[76+16*row+j]=(uint8_t)(((j*14+row*5+test)&15)|(((j*14+7+row*5+test)&15)<<4));
  for(unsigned at=0;at<sizeof(input);){
   unsigned n=(unsigned)sizeof(input)-at;if(n>252)n=252;
   stm3_put32(request,at);memcpy(request+4,input+at,n);
   error=cmd(S3_WRITE,request,n+4,&used);if(error)return error;at+=n;
  }
  stm3_put32(request,module_id);stm3_put32(request+4,sizeof(input));stm3_put32(request+8,1000);
  error=cmd(S3_START,request,12,&used);if(error)return error;
  if(used!=4)return -13;
  job_id=stm3_get32(answer);
  if(test==0){
   used=sizeof(answer);error=stm3_client_replay(&client,answer,&used,250000);
   if(error||used!=4||stm3_get32(answer)!=job_id)return -14;
  }
  unsigned state=0;
  for(unsigned count=0;count<100;++count){
   stm3_put32(request,job_id);error=cmd(S3_STATUS,request,4,&used);if(error)return error;
   if(used!=28||stm3_get32(answer)!=job_id)return -15;
   state=stm3_get32(answer+4);if(state==4)break;if(state!=3)return -16;
   if(mk61_api->key_poll()==MK61_APP_KEY_ESC)return -27;
   mk61_api->delay_ms(1);
  }
  if(state!=4)return -17;
  stm3_put32(request,job_id);stm3_put32(request+4,0);stm3_put32(request+8,72);
  error=cmd(S3_READ,request,12,&used);if(error)return error;
  if(used!=72||stm3_get32(answer)!=16||stm3_get32(answer+4)!=test+1)return -18;
  for(unsigned row=0;row<16;++row){
   int64_t reference=0;
   for(unsigned j=0;j<32;++j){
    const int x=(int16_t)((unsigned)input[12+2*j]|(unsigned)input[13+2*j]<<8);
    const int w=(int)((input[76+16*row+j/2]>>(4*(j&1)))&15)-8;reference+=(int64_t)x*w;
   }
   if((int32_t)stm3_get32(answer+8+4*row)!=reference)return -19;
   ++checked;
  }
  message("JOB",(int)test);mk61_api->delay_ms(1);
 }
 return 0;
}
int main(void){
 svc=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FORMAT|MK61_SERVICE_CAP_DEBUG_IO);
 if(!svc)return MK61_APP_RUNTIME_ERROR;
 mk61_api->display_clear();mk61_api->display_write_m8(0,0,"STM32 UART probe",16);
 line("S3PROBE BEGIN v=1 uart=1 tx=8 rx=9 baud=2250000\n");
 if(!stm3_pico_uart1_begin(&uart,micros,0,48000000,2250000)){message("CLAIM_FAIL",-30);return MK61_APP_OK;}
 const stm3_client_io io={&uart,stm3_pico_uart1_micros,stm3_pico_uart1_send,stm3_pico_uart1_read};
 stm3_client_init(&client,&io);const uint32_t start=micros(0);
 int result=run();
 if(touched_module){
  unsigned used;if(job_id){stm3_put32(request,job_id);(void)cmd(S3_CANCEL,request,4,&used);}
  int cleanup=cmd(S3_UNLOAD,0,0,&used);if(!result&&cleanup)result=cleanup;
  if(!cleanup){cleanup=cmd(S3_HELLO,0,0,&used);if(!result&&(cleanup||used!=36||stm3_get32(answer+16)!=0))result=-20;}
 }
 stm3_pico_uart1_end(&uart);
 char s[192];mk61_app_snprintf(svc,s,sizeof(s),"S3PROBE %s code=%d rows=%lu requests=%lu tx=%lu rx=%lu us=%lu max_rtt_us=%lu baud_actual=%lu uart_errors=%lu\n",
   result?"FAIL":"PASS",result,(unsigned long)checked,(unsigned long)client.requests,(unsigned long)client.sent,
   (unsigned long)client.received,(unsigned long)(micros(0)-start),(unsigned long)client.max_us,
   (unsigned long)uart.actual_baud,(unsigned long)uart.errors);line(s);
 mk61_api->display_write_m8(0,1,result?"UART probe failed":"UART probe passed",17);
 // Diagnostic outcome is in the structured record, not a generic APP error page.
 return MK61_APP_OK;
}
