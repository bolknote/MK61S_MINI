// Varied addition streams, with all operands/results exported for host checks.
#include "mk61_app.h"
#include <stdint.h>
#ifndef M0_BENCH_MIXED_STREAMS
#define M0_BENCH_MIXED_STREAMS 0
#endif
typedef double Binary(double,double);
typedef union {double d;uint64_t u;} Bits;
#if M0_BENCH_QFPLIB
extern double qfp_dadd(double,double);
#define LOCAL_ADD qfp_dadd
#elif !M0_BENCH_RESIDENT
extern double __aeabi_dadd(double,double);
#define LOCAL_ADD __aeabi_dadd
#endif
enum {CASES=32,GROUPS=6,SAMPLES=1024,ROUNDS=9};
typedef struct {uint64_t a,b,result;} Pair;
static struct {
 uint32_t magic,version,cases,samples,rounds,groups;
 struct {Pair pairs[CASES];uint32_t raw[ROUNDS],control[ROUNDS];} rows[GROUPS];
} output;
static volatile uint64_t sink;
static uint32_t state=0xADD06140;
static uint32_t random32(void) {state^=state<<13;state^=state>>17;state^=state<<5;return state;}
static uint64_t fraction(void) {return ((uint64_t)(random32()&0xFFFFF)<<32)|random32();}
static __attribute__((noipa)) double identity(double a,double b) {(void)b;return a;}
static uint32_t micros(void) {__asm__ volatile("":::"memory");return *(volatile uint32_t*)0x40054028;}
static uint32_t time_function(Binary* f,const Pair* pairs) {
 const uint32_t begin=micros();
 for(unsigned i=0;i<SAMPLES;++i) {
  Bits a,b,r;a.u=pairs[i&(CASES-1)].a;b.u=pairs[i&(CASES-1)].b;
  r.d=f(a.d,b.d);sink=r.u;
 }
 return micros()-begin;
}
int main(void) {
 const mk61_app_services* s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
 if(!s || !s->runtime)return MK61_APP_RUNTIME_ERROR;
 mk61_service_file marker={0};
 if(s->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_MK61_BINARY,
      (uint32_t)(uintptr_t)M0_BENCH_MARKER,&marker)!=0)return MK61_APP_IO_ERROR;
#if M0_BENCH_RESIDENT
 Binary* f=(Binary*)s->runtime[0];
#else
 Binary* f=LOCAL_ADD;
#endif
 output.magic=0x30414C55;output.version=M0_BENCH_MIXED_STREAMS?3:2;output.cases=CASES;
 output.samples=SAMPLES;output.rounds=ROUNDS;output.groups=GROUPS;
 for(unsigned group=0;group<GROUPS;++group) {
  for(unsigned i=0;i<CASES;++i) {
   unsigned ea=1015+(random32()&15),eb=ea-(random32()&7);
   uint64_t sa=0,sb=0;
#if M0_BENCH_MIXED_STREAMS
   uint64_t af=fraction(),bf=fraction();
   sa=(uint64_t)((i>>1)&1)<<63;sb=sa^(UINT64_C(1)<<63);
   eb=ea;
   if(group==1)eb=ea-1;
   if(group==2) {af&=~UINT64_C(1);bf=af+1;}
   if(group==3) {eb=ea-1;af=random32()&3;bf=UINT64_C(0xFFFFFFFFFFFFF)-(random32()&15);}
   if(group==4)bf=af;
   if(group==5) {eb=ea-1;af=(UINT64_C(1)<<51)+(UINT64_C(1)<<32)+((i&4)?UINT64_C(0xFFFFFFFF):0);bf=i&3;}
   Pair* p=&output.rows[group].pairs[i];
   p->a=sa|((uint64_t)ea<<52)|af;p->b=sb|((uint64_t)eb<<52)|bf;
#else
   if(group==1)sa=sb=UINT64_C(1)<<63;
   if(group==2) {eb=ea-(random32()&1);sb=UINT64_C(1)<<63;}
   if(group==3) {eb=ea-32-(random32()&31);sb=(uint64_t)(random32()&1)<<63;}
   if(group==4) {eb=ea;sa=sb=(uint64_t)(random32()&1)<<63;}
   if(group==5) {
    ea=1+random32()%2046;eb=1+random32()%2046;
    sa=(uint64_t)(random32()&1)<<63;sb=(uint64_t)(random32()&1)<<63;
   }
   Pair* p=&output.rows[group].pairs[i];
   p->a=sa|((uint64_t)ea<<52)|fraction();p->b=sb|((uint64_t)eb<<52)|fraction();
#endif
   // Both alignment directions occur in every stream.
   if(i&1) {uint64_t swap=p->a;p->a=p->b;p->b=swap;}
   Bits a,b,r;a.u=p->a;b.u=p->b;r.d=f(a.d,b.d);p->result=r.u;
  }
  for(unsigned round=0;round<ROUNDS;++round) {
   mk61_api->service();output.rows[group].control[round]=time_function(identity,output.rows[group].pairs);
   mk61_api->service();output.rows[group].raw[round]=time_function(f,output.rows[group].pairs);
  }
 }
 mk61_service_write file={M0_BENCH_OUTPUT,(const uint8_t*)&output,sizeof(output),MK61_SERVICE_INVALID_ID};
 return s->call(MK61_SERVICE_FILE_WRITE,marker.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&file)?MK61_APP_OK:MK61_APP_IO_ERROR;
}
