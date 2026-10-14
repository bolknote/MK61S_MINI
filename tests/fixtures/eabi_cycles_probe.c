#include "mk61_app.h"
#include <stdint.h>
typedef double Binary(double,double) __attribute__((pcs("aapcs")));
typedef union {double d;uint64_t u;} Bits;
#include "eabi_cycles_pairs.inc"
enum {SAMPLES=1024,ROUNDS=9,CASES=sizeof(pairs)/sizeof(*pairs)};
struct Row {uint32_t operation,reserved;uint64_t a,b,result;uint32_t raw,control;};
static struct {uint32_t magic,cases,samples,rounds;struct Row rows[4*CASES];} output;
static volatile uint64_t input_a,input_b,sink;
static __attribute__((noipa,pcs("aapcs"))) double identity(double a,double b) {(void)b;return a;}
static uint32_t cycles(void) {__asm__ volatile("":::"memory");return *(volatile uint32_t*)0xE0001004;}
static uint32_t time_function(Binary* function) {
 uint32_t samples[ROUNDS];
 for(unsigned r=0;r<ROUNDS;++r) {
  mk61_api->service();uint32_t begin=cycles();
  for(unsigned i=0;i<SAMPLES;++i) {Bits a,b,y;a.u=input_a;b.u=input_b;y.d=function(a.d,b.d);sink=y.u;}
  samples[r]=cycles()-begin;
 }
 for(unsigned i=1;i<ROUNDS;++i)for(unsigned j=i;j&&samples[j]<samples[j-1];--j) {uint32_t x=samples[j];samples[j]=samples[j-1];samples[j-1]=x;}
 return samples[ROUNDS/2];
}
int main(void) {
 const mk61_app_services* s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
 if(!s||!s->runtime||!(*(volatile uint32_t*)0xE0001000&1))return MK61_APP_RUNTIME_ERROR;
 output.magic=0x554C4142;output.cases=CASES;output.samples=SAMPLES;output.rounds=ROUNDS;
 for(unsigned op=0;op<4;++op)for(unsigned i=0;i<CASES;++i) {
  struct Row* row=&output.rows[op*CASES+i];Binary* f=(Binary*)s->runtime[op];Bits a,b,y;a.u=pairs[i].a;b.u=pairs[i].b;input_a=a.u;input_b=b.u;
  y.d=f(a.d,b.d);row->operation=op;row->a=a.u;row->b=b.u;row->result=y.u;
  row->control=time_function(identity);row->raw=time_function(f);
 }
 mk61_service_write file={"ALUOUT",(const uint8_t*)&output,sizeof(output),MK61_SERVICE_INVALID_ID};
 return s->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&file)?MK61_APP_OK:MK61_APP_IO_ERROR;
}
