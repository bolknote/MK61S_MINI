#include <Arduino.h>
#include "stm3_runtime.h"
#include "stm3_uart_dma.h"
// Resident keyboard firmware owns USART3/DMA. Modules only see job buffers.
static stm3_runtime coproc;
static bool coproc_ready=false;
static uint32_t last_uart_errors;
static uint32_t time_us(void*){return micros();}
static uint32_t load_address(void*,const void* p){return (uint32_t)(uintptr_t)p;}
static uint32_t invoke(void*,uint32_t entry,uint32_t op,const stm3_api*api,stm3_job*job){
 __asm__ volatile("dsb\n\tisb":::"memory");
 return ((stm3_entry)(uintptr_t)entry)(op,api,job);
}
extern "C" void coproc_setup(){
 const stm3_backend backend={nullptr,time_us,load_address,invoke,STM3_UART_BAUD,3};stm3_init(&coproc,&backend);
 coproc_ready=stm3_uart_begin(HAL_RCC_GetPCLK1Freq())!=0;
}
extern "C" void coproc_poll(){
 if(!coproc_ready)return;
 unsigned room=0;uint8_t*tx=stm3_uart_tx_buffer(&room);
 if(tx){const unsigned n=stm3_transmit(&coproc,tx,room);if(n&&!stm3_uart_tx_start(n))++coproc.bad_frames;}
 if(coproc.tx_at==coproc.tx_bytes){
  uint8_t bytes[64];const unsigned n=stm3_uart_read(bytes,sizeof(bytes));
  const uint32_t errors=stm3_uart_errors();
  if(errors!=last_uart_errors){last_uart_errors=errors;++coproc.bad_frames;coproc.frame_overflow=1;}
  for(unsigned i=0;i<n;++i){stm3_feed(&coproc,bytes[i]);if(coproc.tx_at<coproc.tx_bytes)break;}
 }
 stm3_tick(&coproc);
}
