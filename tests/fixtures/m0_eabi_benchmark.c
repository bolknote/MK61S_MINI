// RP2040 SRAM benchmark; runtime implementations are linked separately.
#include "mk61_app.h"
#include <stdint.h>
#ifndef M0_BENCH_OUTPUT
#define M0_BENCH_OUTPUT "M0ALU.OUT"
#endif
#ifndef M0_BENCH_MARKER
#define M0_BENCH_MARKER "/M0ALU.bin"
#endif
typedef double Binary(double,double);
typedef union {double d;uint64_t u;} Bits;
#if M0_BENCH_QFPLIB
extern double qfp_dadd(double,double),qfp_dsub(double,double),qfp_dmul(double,double),qfp_ddiv(double,double);
static Binary* const functions[]={qfp_dadd,qfp_dsub,qfp_dmul,qfp_ddiv};
#elif !M0_BENCH_RESIDENT
extern double __aeabi_dadd(double,double),__aeabi_dsub(double,double),__aeabi_dmul(double,double),__aeabi_ddiv(double,double);
static Binary* const functions[]={__aeabi_dadd,__aeabi_dsub,__aeabi_dmul,__aeabi_ddiv};
#endif
// Normal values with exact integers, nearby values, different signs and scales.
// IEEE boundary cases are assessed separately, without timing FTZ as if it
// implemented gradual underflow.
static const struct {uint64_t a,b;} pairs[]={
 {UINT64_C(0x3FE6666666666666),UINT64_C(0x3FF4CCCCCCCCCCCD)},
 {UINT64_C(0x3FF0000000000000),UINT64_C(0x4000000000000000)},
 {UINT64_C(0x3FF0000000000001),UINT64_C(0x3FF0000000000000)},
 {UINT64_C(0x400921FB54442D18),UINT64_C(0x4005BF0A8B145769)},
 {UINT64_C(0xBFF4CCCCCCCCCCCD),UINT64_C(0x3FE6666666666666)},
 {UINT64_C(0x4031000000000000),UINT64_C(0xC027000000000000)},
 {UINT64_C(0x3FEFFFFFFFFFFFFF),UINT64_C(0x3FEFFFFFFFFFFFFE)},
 {UINT64_C(0x3FC999999999999A),UINT64_C(0x4024000000000000)},
 {UINT64_C(0x42F123456789ABCD),UINT64_C(0x439FEDCBA9876543)},
 {UINT64_C(0x350FEDCBA9876543),UINT64_C(0x347123456789ABCD)},
 {UINT64_C(0x4000000000000000),UINT64_C(0x3FF0000000000000)},
 {UINT64_C(0x3FF0000000000000),UINT64_C(0x3C90000000000000)},
};
enum {SAMPLES=1024,ROUNDS=9,CASES=sizeof(pairs)/sizeof(*pairs)};
static struct {
 uint32_t magic,version,cases,samples,rounds;
 struct {uint64_t a,b,result;uint32_t raw[ROUNDS],control[ROUNDS];} rows[4*CASES];
} output;
static volatile uint64_t input_a,input_b,sink;
static __attribute__((noipa)) double identity(double a,double b) {(void)b;return a;}
static uint32_t micros(void) {__asm__ volatile("":::"memory");return *(volatile uint32_t*)0x40054028;}
static uint32_t time_function(Binary* f) {
 const uint32_t begin=micros();
 for(unsigned i=0;i<SAMPLES;++i) {Bits a,b,r;a.u=input_a;b.u=input_b;r.d=f(a.d,b.d);sink=r.u;}
 return micros()-begin;
}
int main(void) {
 const mk61_app_services* s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
 if(!s || !s->runtime)return MK61_APP_RUNTIME_ERROR;
 mk61_service_file marker={0};
 if(s->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_MK61_BINARY,
      (uint32_t)(uintptr_t)M0_BENCH_MARKER,&marker)!=0)return MK61_APP_IO_ERROR;
 output.magic=0x30414C55;output.version=1;output.cases=CASES;output.samples=SAMPLES;output.rounds=ROUNDS;
 for(unsigned op=0;op<4;++op)for(unsigned i=0;i<CASES;++i) {
#if M0_BENCH_RESIDENT
  Binary* f=(Binary*)s->runtime[op];
#else
  Binary* f=functions[op];
#endif
  Bits a,b,r;a.u=pairs[i].a;b.u=pairs[i].b;input_a=a.u;input_b=b.u;
  output.rows[op*CASES+i].a=a.u;output.rows[op*CASES+i].b=b.u;r.d=f(a.d,b.d);output.rows[op*CASES+i].result=r.u;
  for(unsigned round=0;round<ROUNDS;++round) {
   mk61_api->service();output.rows[op*CASES+i].control[round]=time_function(identity);
   mk61_api->service();output.rows[op*CASES+i].raw[round]=time_function(f);
  }
 }
 mk61_service_write file={M0_BENCH_OUTPUT,(const uint8_t*)&output,sizeof(output),MK61_SERVICE_INVALID_ID};
 return s->call(MK61_SERVICE_FILE_WRITE,marker.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&file)?MK61_APP_OK:MK61_APP_IO_ERROR;
}
