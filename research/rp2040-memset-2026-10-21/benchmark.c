/* Private SRAM APP: no firmware writes, clock changes or disabled interrupts.
 * TIMERAWL counts real microseconds; paired empty-call batches remove loop
 * overhead. ROM is resolved once through its public table, outside timing. */
#include "mk61_app.h"
#include <stdint.h>
#include <stddef.h>
#ifndef BENCH_ROOT
#define BENCH_ROOT "/MK61S-MEMSET"
#endif
#define FUNCTIONS 9U
#define ROUNDS 7U
#define ROWS 12U
#define LIMIT 8192U
typedef void* (*Fill)(void*,int,size_t);
extern void *own16(void*,int,size_t), *own64(void*,int,size_t);
extern void *own_fast(void*,int,size_t), *memset(void*,int,size_t);
extern void *runtime_old(void*,int,size_t), *runtime_r3(void*,int,size_t);
extern void *rom_cached(void*,int,size_t), *control_fill(void*,int,size_t);
const mk61_service_runtime_function* bench_runtime;
Fill bench_rom;
static uint8_t rom_sram[120] __attribute__((aligned(4)));
static uint8_t buffer[LIMIT+80] __attribute__((aligned(16)));
static volatile uintptr_t sink;
/* Frozen previous standalone SDK implementation. */
__attribute__((noipa)) void* byte_fill(void* destination,int value,size_t size) {
    if(!size) return destination;
    unsigned char* out=destination;
    unsigned char* end=out+size;
    while(out!=end) *out++=(unsigned char)value;
    return destination;
}
typedef struct { uint32_t size,offset,value,loops; } Input;
typedef struct { Input input; uint32_t control[ROUNDS],time[FUNCTIONS][ROUNDS]; } Row;
static struct { uint32_t h[64];Row rows[ROWS]; } report;
_Static_assert(sizeof(report)<=4096,"Bounded result file");
_Static_assert(MK61_RUNTIME_SLOT_memset==23,"Assembly runtime slot");
static uint32_t micros(void) {
    __asm__ volatile("":::"memory");
    return *(volatile uint32_t*)UINT32_C(0x40054028);
}
static __attribute__((noipa)) uint32_t measure(Fill fn,Input c) {
    uint8_t* out=buffer+32+c.offset;
    uint32_t begin=micros();
    for(unsigned i=0;i<c.loops;++i) sink=(uintptr_t)fn(out,(int)c.value,c.size);
    return micros()-begin;
}
static int check(Fill fn,unsigned index,unsigned n,unsigned offset,int value) {
    for(unsigned j=0;j<n+80;++j) buffer[j]=0x5A;
    void* dest=buffer+32+offset;
    int good=fn(dest,value,n)==dest;
    for(unsigned j=0;j<n+80;++j)
        if(buffer[j]!=((j>=32+offset && j<32+offset+n)?(uint8_t)value:0x5A)) good=0;
    ++report.h[5];
    if(!good) {
        ++report.h[6];report.h[7]=index;report.h[8]=n;
        report.h[9]=offset;report.h[10]=(uint32_t)value;
    }
    if(!(report.h[5]&31)) mk61_api->service();
    return good;
}
static uint16_t rom_half(unsigned address) {
    uint32_t value;
    __asm__ volatile("ldrh %0,[%1]":"=r"(value):"r"(address):"memory");
    return (uint16_t)value;
}
int main(void) {
    const mk61_app_services* s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
    if(!s || !s->runtime) return MK61_APP_RUNTIME_ERROR;
    mk61_service_file file={0};
    if(s->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_MK61_BINARY,
        (uint32_t)(uintptr_t)(BENCH_ROOT "/INPUT.bin"),&file)) return MK61_APP_IO_ERROR;
    struct { uint32_t h[4];Input rows[ROWS]; } input;
    if(mk61_api->file_read(file.id,0,(uint8_t*)&input,sizeof(input))!=sizeof(input) ||
       input.h[0]!=0x4D534554 || input.h[1]!=1 || !input.h[2] || input.h[2]>ROWS) return MK61_APP_INVALID_FILE;
    for(unsigned i=0;i<input.h[2];++i)
        if(input.rows[i].size>LIMIT || input.rows[i].offset>7 ||
           !input.rows[i].loops || input.rows[i].loops>65536) return MK61_APP_INVALID_FILE;
    typedef void* (*Lookup)(const uint16_t*,uint32_t);
    Lookup lookup=(Lookup)(uintptr_t)rom_half(0x18);
    bench_rom=(Fill)lookup((const uint16_t*)(uintptr_t)rom_half(0x14),0x534D);
    bench_runtime=s->runtime;
    report.h[11]=rom_half(0x12)>>8;
    report.h[12]=(uintptr_t)bench_rom;
    report.h[13]=(uintptr_t)s->runtime[MK61_RUNTIME_SLOT_memset];
    /* Only this captured ROM revision has a verified position-independent
     * 120-byte MS body. This restriction belongs to the experiment alone. */
    if(report.h[11]!=3 || (uintptr_t)bench_rom!=0x26B9) return MK61_APP_RUNTIME_ERROR;
    for(unsigned i=0;i<sizeof(rom_sram);++i) rom_sram[i]=((const uint8_t*)0x26B8)[i];
    for(unsigned i=0;i<30;++i) report.h[32+i]=((const uint32_t*)rom_sram)[i];
    Fill functions[FUNCTIONS]={byte_fill,bench_rom,(Fill)s->runtime[MK61_RUNTIME_SLOT_memset],
        runtime_old,runtime_r3,rom_cached,(Fill)((uintptr_t)rom_sram|1),
#if defined(BENCH_SDK)
        memset,
#elif defined(BENCH_FAST)
        own_fast,
#else
        own16,
#endif
        own64};
    report.h[0]=0x4D535250;report.h[1]=1;report.h[2]=FUNCTIONS;
    report.h[3]=input.h[2];report.h[4]=ROUNDS;
    for(unsigned f=0;f<FUNCTIONS;++f) report.h[16+f]=(uintptr_t)functions[f];
    for(unsigned f=0;f<FUNCTIONS;++f) {
        if(functions[f](NULL,0x1234,0)!=NULL) { ++report.h[6];report.h[7]=f; }
        ++report.h[5];
        if(input.h[3]) {
            const int values[]={0,1,0x1234,-1};
            for(unsigned n=0;n<=257;++n) for(unsigned a=0;a<8;++a) for(unsigned v=0;v<4;++v)
                if(!check(functions[f],f,n,a,values[v])) goto finished;
            const unsigned sizes[]={511,512,513,1023,1024,1025,4095,4096,4097,8192};
            for(unsigned n=0;n<sizeof(sizes)/sizeof(sizes[0]);++n) for(unsigned a=0;a<8;++a)
                if(!check(functions[f],f,sizes[n],a,0xA5)) goto finished;
        }
        for(unsigned c=0;c<input.h[2];++c)
            if(!check(functions[f],f,input.rows[c].size,input.rows[c].offset,(int)input.rows[c].value)) goto finished;
    }
    uint32_t begin=micros();
    do {
        for(unsigned f=0;f<FUNCTIONS;++f) sink=(uintptr_t)functions[f](buffer+32,0xA5,1024);
        mk61_api->service();
    } while((report.h[14]=micros()-begin)<1000000U);
    for(unsigned c=0;c<input.h[2];++c) {
        Input row=input.rows[c];report.rows[c].input=row;
        for(unsigned r=0;r<ROUNDS;++r) {
            mk61_api->service();report.rows[c].control[r]=measure(control_fill,row);
            for(unsigned order=0;order<FUNCTIONS;++order) {
                unsigned f=(order+r+c)%FUNCTIONS;
                mk61_api->service();report.rows[c].time[f][r]=measure(functions[f],row);
            }
        }
    }
finished:;
    mk61_service_write out={"RESULT",(const uint8_t*)&report,
        (uint32_t)(256+input.h[2]*sizeof(Row)),MK61_SERVICE_INVALID_ID};
    return s->call(MK61_SERVICE_FILE_WRITE,file.parent,MK61_SERVICE_INVALID_ID,
        MK61_SERVICE_FILE_MK61_BINARY,&out)?MK61_APP_OK:MK61_APP_IO_ERROR;
}
