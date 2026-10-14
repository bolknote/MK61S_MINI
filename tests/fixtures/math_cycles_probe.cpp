/* Diagnostic SRAM APP, not resident firmware.
 * Compare identical promoted binary32 inputs with the published SEGGER table.
 * DWT batch medians subtract the matching identity-call loop.
 * Volatile operands/results prevent GCC/LTO from hoisting math out of a batch.
 * Both the local math and its arithmetic helpers execute in SRAM.
 */
#include "mk61_app.h"
#include <stdint.h>
extern "C" {float sinf(float);float cosf(float);float tanf(float);float logf(float);float expf(float);float sqrtf(float);
#if LOCAL_DOUBLE == 2
double sin(double);double cos(double);double tan(double);double log(double);double exp(double);double sqrt(double);
#endif
}
#include "compact_math.hpp"
#ifndef LOCAL_DOUBLE
#define LOCAL_DOUBLE 1
#endif
static const unsigned Samples=512,Rounds=9;
union F {float number;uint32_t bits;};
union D {double number;uint64_t bits;};
struct Case {uint32_t operation,input,expected;};
#include "segger_float_cases.inc"
struct Header {uint32_t magic,version,mode,cases,samples,rounds;};
struct Row {uint32_t operation,input,expected,rounded;uint64_t calculated;
            uint32_t ram_cycles,ram_control,flash_cycles,flash_control;};
struct Output {Header header;Row rows[sizeof(cases)/sizeof(*cases)];};
static Output output;
#if LOCAL_DOUBLE
static volatile uint64_t double_input,double_sink;
#else
static volatile uint32_t float_input,float_sink;
#endif
static const mk61_app_services* services;
extern "C" int* __errno() {static int cell;return &cell;}
static inline uint32_t cycles() {
  __asm__ volatile ("":::"memory");
  return *(volatile uint32_t*)0xE0001004;
}
static uint32_t median(uint32_t* values) {
  for (unsigned i=1;i<Rounds;++i)
    for (unsigned j=i;j && values[j]<values[j-1];--j) {
      uint32_t x=values[j];values[j]=values[j-1];values[j-1]=x;
    }
  return values[Rounds/2];
}
#if LOCAL_DOUBLE
using Function=double(*)(double);
#if LOCAL_DOUBLE == 2
static Function functions[]={::sin,::cos,::tan,nullptr,nullptr,nullptr,::log,nullptr,::exp,::sqrt};
#else
static Function functions[]={compact_math::sin,compact_math::cos,compact_math::tan,
  nullptr,nullptr,nullptr,compact_math::ln,nullptr,compact_math::exp,compact_math::sqrt};
#endif
__attribute__((noipa)) static double identity(double x) {return x;}
static uint32_t ram_time(Function f) {
  uint32_t times[Rounds];
  for (unsigned r=0;r<Rounds;++r) {
    mk61_api->service();const uint32_t begin=cycles();
    for (unsigned i=0;i<Samples;++i) {D x;x.bits=double_input;D y;y.number=f(x.number);double_sink=y.bits;}
    times[r]=cycles()-begin;
  }
  return median(times);
}
#if LOCAL_DOUBLE == 1
static uint32_t flash_time(uint32_t operation) {
  uint32_t times[Rounds];
  for (unsigned r=0;r<Rounds;++r) {
    mk61_api->service();const uint32_t begin=cycles();
    for (unsigned i=0;i<Samples;++i) {D x;x.bits=double_input;D y;y.number=services->math(operation,x.number,0.0);double_sink=y.bits;}
    times[r]=cycles()-begin;
  }
  return median(times);
}
#endif
#else
using Function=float(*)(float);
static Function functions[]={sinf,cosf,tanf,nullptr,nullptr,nullptr,logf,nullptr,expf,sqrtf};
__attribute__((noipa)) static float identity(float x) {return x;}
static uint32_t ram_time(Function f) {
  uint32_t times[Rounds];
  for (unsigned r=0;r<Rounds;++r) {
    mk61_api->service();const uint32_t begin=cycles();
    for (unsigned i=0;i<Samples;++i) {F x;x.bits=float_input;F y;y.number=f(x.number);float_sink=y.bits;}
    times[r]=cycles()-begin;
  }
  return median(times);
}
#endif
int main(void) {
  services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_MATH);
  if (!services || !services->math || !(*(volatile uint32_t*)0xE0001000&1)) return MK61_APP_RUNTIME_ERROR;
  output.header={0x42474553,1,LOCAL_DOUBLE,unsigned(sizeof(cases)/sizeof(*cases)),Samples,Rounds};
  for (unsigned i=0;i<sizeof(cases)/sizeof(*cases);++i) {
    const Case& c=cases[i];Row& row=output.rows[i];F input;input.bits=c.input;
    row.operation=c.operation;row.input=c.input;row.expected=c.expected;
#if LOCAL_DOUBLE
    D x;x.number=double(input.number);double_input=x.bits;
    D y;y.number=functions[c.operation](x.number);F rounded;rounded.number=float(y.number);
    row.calculated=y.bits;row.rounded=rounded.bits;
    row.ram_control=ram_time(identity);row.ram_cycles=ram_time(functions[c.operation]);
#if LOCAL_DOUBLE == 1
    row.flash_control=flash_time(255);row.flash_cycles=flash_time(c.operation);
#endif
#else
    float_input=c.input;F y;y.number=functions[c.operation](input.number);
    row.calculated=y.bits;row.rounded=y.bits;
    row.ram_control=ram_time(identity);row.ram_cycles=ram_time(functions[c.operation]);
#endif
  }
  mk61_service_write file={LOCAL_DOUBLE==2?"SEGGG":LOCAL_DOUBLE?"SEGGD":"SEGGF",(const uint8_t*)&output,sizeof(output),MK61_SERVICE_INVALID_ID};
  return services->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_INVALID_ID,
                       MK61_SERVICE_FILE_MK61_BINARY,&file)?MK61_APP_OK:MK61_APP_IO_ERROR;
}
