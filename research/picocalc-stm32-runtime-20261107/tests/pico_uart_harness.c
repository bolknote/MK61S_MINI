#include "pico_uart1.h"
static stm3_pico_uart1 port;
static uint32_t ticks;
static uint32_t micros(void*p){(void)p;return ++ticks;}
void harness_init(void){}
int harness_begin(uint32_t peri,uint32_t baud){return stm3_pico_uart1_begin(&port,micros,0,peri,baud);}
void harness_end(void){stm3_pico_uart1_end(&port);}
int harness_send(const uint8_t*p,unsigned n,uint32_t timeout){return stm3_pico_uart1_send(&port,p,n,timeout);}
int harness_read(uint32_t timeout){return stm3_pico_uart1_read(&port,timeout);}
uint32_t harness_baud(void){return port.actual_baud;}
uint32_t harness_errors(void){return port.errors;}
