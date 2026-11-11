#include "stm3_runtime.h"
static stm3_runtime runtime;
static uint32_t ticks;
static uint32_t micros(void*p){(void)p;return ++ticks;}
static uint32_t address(void*c,const void*p){(void)c;return (uint32_t)(uintptr_t)p;}
static uint32_t invoke(void*c,uint32_t entry,uint32_t op,const stm3_api*api,stm3_job*job){(void)c;return ((stm3_entry)(uintptr_t)entry)(op,api,job);}
__attribute__((used)) void harness_init(void){const stm3_backend b={0,micros,address,invoke,2250000,3};stm3_init(&runtime,&b);}
__attribute__((used)) void harness_feed(uint32_t value){stm3_feed(&runtime,(uint8_t)value);}
__attribute__((used)) unsigned harness_transmit(uint8_t*p,unsigned n){return stm3_transmit(&runtime,p,n);}
__attribute__((used)) void harness_tick(void){stm3_tick(&runtime);}
__attribute__((used)) uint32_t harness_state(void){return runtime.state;}
__attribute__((used)) uint32_t harness_max_slice(void){return runtime.max_slice_us;}
__attribute__((used)) uint32_t harness_module_base(void){return (uint32_t)(uintptr_t)runtime.arena.bytes;}
__attribute__((used)) uint32_t harness_set_clock(uint32_t value){ticks=value;return ticks;}
__attribute__((used)) uint32_t harness_empty(void){for(unsigned i=0;i<sizeof(runtime.arena.bytes);++i)if(runtime.arena.bytes[i])return 0;return 1;}
void*memcpy(void*d,const void*s,size_t n){volatile uint8_t*p=d;const uint8_t*q=s;while(n--)*p++=*q++;return d;}
void*memset(void*d,int value,size_t n){volatile uint8_t*p=d;while(n--)*p++=(uint8_t)value;return d;}
void*memmove(void*d,const void*s,size_t n){uint8_t*p=d;const uint8_t*q=s;if(p<q){for(size_t i=0;i<n;++i)p[i]=q[i];}else{while(n){--n;p[n]=q[n];}}return d;}
