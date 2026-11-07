// RP2040-only adapter. UART0 console, I2C and all DMA channels are untouched.
// Register offsets/bits match the pinned local Pico SDK hardware/regs headers.
#include "pico_uart1.h"
#define REG(address) (*(volatile uint32_t*)(uintptr_t)(address))
#define UART 0x40038000u
#define RESET 0x4000c000u
#define GPIO(n) (0x40014004u+8u*(n))
#define PAD(n) (0x4001c004u+4u*(n))
#define UART1_RESET (1u<<23)
static const unsigned offsets[8]={0x24,0x28,0x2c,0x30,0x34,0x38,0x48,0x4};
uint32_t stm3_pico_uart1_micros(void*p){stm3_pico_uart1*u=p;return u->micros(u->context);}
int stm3_pico_uart1_begin(stm3_pico_uart1*u,uint32_t(*clock)(void*),void*context,uint32_t peri,uint32_t baud){
 if(!u||!clock||peri!=48000000u||baud!=2250000u)return 0;
 // Refuse an active/reserved UART or either pin already muxed to another owner.
 if(!(REG(RESET)&UART1_RESET)&&((REG(UART+0x30)&1u)||REG(UART+0x38)||REG(UART+0x48)))return 0;
 for(unsigned i=0;i<2;++i)if((REG(GPIO(8+i))&31u)!=31u)return 0;
 u->micros=clock;u->context=context;u->ready=0;u->errors=0;
 for(unsigned i=0;i<2;++i){u->gpio[i]=REG(GPIO(8+i));u->pad[i]=REG(PAD(8+i));}
 u->reset_before=REG(RESET)&UART1_RESET;
 // Atomic CLR alias avoids racing the I2C worker's reset-register updates.
 REG(RESET+0x3000)=UART1_RESET;
 const uint32_t start=clock(context);
 while(!(REG(RESET+8)&UART1_RESET))if(clock(context)-start>=1000u){
  if(u->reset_before)REG(RESET+0x2000)=UART1_RESET;
  return 0;
 }
 for(unsigned i=0;i<8;++i)u->uart[i]=REG(UART+offsets[i]);
 REG(UART+0x30)=0;REG(UART+0x38)=0;REG(UART+0x48)=0;REG(UART+0x44)=0x7ff;
 REG(UART+0x2c)=0;REG(UART+0x24)=1;REG(UART+0x28)=21;REG(UART+0x2c)=0x70;
 REG(GPIO(8))=(u->gpio[0]&~31u)|2u;REG(GPIO(9))=(u->gpio[1]&~31u)|2u;
 REG(PAD(8))=(u->pad[0]&~0x8cu)|0x40u;
 REG(PAD(9))=(u->pad[1]&~0x84u)|0x48u;
 REG(UART+0x30)=0x301;u->actual_baud=192000000u/85u;u->ready=1;return 1;
}
void stm3_pico_uart1_end(stm3_pico_uart1*u){
 if(!u||!u->ready)return;
 const uint32_t start=u->micros(u->context);
 while(REG(UART+0x18)&8u)if(u->micros(u->context)-start>=10000u)break;
 REG(UART+0x30)=0;REG(UART+0x38)=0;REG(UART+0x48)=0;
 for(unsigned i=0;i<8;++i)if(i!=3&&i!=7)REG(UART+offsets[i])=u->uart[i];
 for(unsigned i=0;i<2;++i){REG(GPIO(8+i))=u->gpio[i];REG(PAD(8+i))=u->pad[i];}
 REG(UART+0x30)=u->uart[3];
 if(u->reset_before)REG(RESET+0x2000)=UART1_RESET;
 u->ready=0;
}
int stm3_pico_uart1_send(void*p,const uint8_t*data,unsigned n,uint32_t timeout){
 stm3_pico_uart1*u=p;if(!u->ready)return 0;
 const uint32_t start=u->micros(u->context);
 for(unsigned i=0;i<n;++i){
  while(REG(UART+0x18)&32u)if(u->micros(u->context)-start>=timeout)return 0;
  REG(UART)=data[i];
 }return 1;
}
int stm3_pico_uart1_read(void*p,uint32_t timeout){
 stm3_pico_uart1*u=p;if(!u->ready)return -2;
 const uint32_t start=u->micros(u->context);
 while(REG(UART+0x18)&16u)if(u->micros(u->context)-start>=timeout)return -1;
 const uint32_t value=REG(UART);
 if(value&0xf00u){++u->errors;REG(UART+4)=0;return -2;}
 return (int)(value&255u);
}
