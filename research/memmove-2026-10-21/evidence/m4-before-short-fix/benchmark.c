/* Physical CPU timings. Instructions in standalone APPs reside in SRAM;
 * source 0 is SRAM, source 1 is resident Flash (warm instruction/data cache).
 * All interrupt/service time is included, except service calls between batches. */
#include "mk61_app.h"
#include "baseline-memory.h"
#define FUNCTIONS 8U
#define ROUNDS 7U
#define ROWS 12U
#define LIMIT 4096U
typedef void* (*Copy)(void*,const void*,size_t);
extern void *own16(void*,const void*,size_t), *own64(void*,const void*,size_t);
extern void *memmove(void*,const void*,size_t), *runtime_move(void*,const void*,size_t);
extern void *control_move(void*,const void*,size_t);
const mk61_service_runtime_function* bench_runtime;
#ifdef BENCH_SELECTED_RUNTIME
extern void* runtime_selected(void*,const void*,size_t);
extern const mk61_service_runtime_function* mk61_app_runtime;
const mk61_service_runtime_function* bench_selected_runtime;
static mk61_service_runtime_function selected_runtime[MK61_RUNTIME_COUNT];
#endif
static uint8_t source[LIMIT+80] __attribute__((aligned(16)));
static uint8_t buffer[LIMIT+192] __attribute__((aligned(16)));
static volatile uintptr_t sink;
__attribute__((noipa)) void* baseline(void* d,const void* s,size_t n) { return mk61_memory_move(d,s,n); }
__attribute__((noipa)) void* byte_move(void* d,const void* s,size_t n) {
    uint8_t* out=d;const uint8_t* in=s;
    if((uintptr_t)d<(uintptr_t)s) { while(n--) *out++=*in++; }
    else { while(n) { --n;out[n]=in[n]; } }
    return d;
}
/* RP2040 exports no memmove; the inspected F411 word-copy is not overlap-safe.
 * Use ROM memcpy only for disjoint spans; overlap uses a directional byte loop. */
__attribute__((noipa)) void* rom_move(void* d,const void* s,size_t n) {
    uintptr_t a=(uintptr_t)d,b=(uintptr_t)s;
    if(a==b || !n) return d;
    if((a>b?a-b:b-a)<n) return byte_move(d,s,n);
#if __ARM_ARCH_6M__
    return ((Copy)0x261Du)(d,s,n);
#else
    size_t words=n&~(size_t)3;
    if(words) ((Copy)0x1FFF0A4Du)(d,s,words);
    uint8_t* out=(uint8_t*)d+words;const uint8_t* in=(const uint8_t*)s+words;
    for(size_t i=0;i<(n&3);++i) out[i]=in[i];
    return d;
#endif
}
#if __ARM_ARCH_6M__
static uint16_t rom_half(unsigned address) {
    uint32_t value;
    __asm__ volatile("ldrh %0,[%1]":"=r"(value):"r"(address):"memory");
    return (uint16_t)value;
}
#define FLASH_SOURCE 0x10001000u
#define WARMUP 200000u
static uint32_t tick(void) { __asm__ volatile("":::"memory"); return *(volatile uint32_t*)0x40054028u; }
#else
#define FLASH_SOURCE 0x08002000u
#define WARMUP 19200000u
static uint32_t tick(void) { __asm__ volatile("":::"memory"); return *(volatile uint32_t*)0xE0001004u; }
#endif
#ifdef BENCH_FLASH_HEADER
#include BENCH_FLASH_HEADER
#endif
typedef struct { uint32_t size,src_offset,dst_offset,loops,source; } Input;
typedef struct { Input input;uint32_t control[ROUNDS],time[FUNCTIONS][ROUNDS]; } Row;
static struct { uint32_t h[64];Row rows[ROWS]; } report;
_Static_assert(sizeof(report)<=4096,"Bounded result file");
_Static_assert(MK61_RUNTIME_SLOT_memmove==24,"Assembly runtime slot");
static unsigned destination_offset(Input c) {
    if(c.source<2) return 32+c.dst_offset;
    return 32+c.src_offset+(c.source==2?c.dst_offset:0);
}
static const uint8_t* input_source(Input c) {
    if(c.source<2) return (c.source?(const uint8_t*)FLASH_SOURCE:source+32)+c.src_offset;
    return buffer+32+c.src_offset+(c.source==3?c.dst_offset:0);
}
static uint8_t pattern(unsigned j) { return (uint8_t)(j*13+(j>>8)*7); }
static __attribute__((noipa)) uint32_t measure(Copy fn,Input c) {
    void* out=buffer+destination_offset(c);const void* in=input_source(c);
    uint32_t begin=tick();
    for(unsigned i=0;i<c.loops;++i) sink=(uintptr_t)fn(out,in,c.size);
    return tick()-begin;
}
static int check(Copy fn,unsigned index,Input c) {
    for(unsigned j=0;j<c.size+160;++j) buffer[j]=pattern(j)^0xA5;
    for(unsigned j=0;j<c.size+64;++j) source[j]=pattern(j);
    unsigned off=destination_offset(c);
    void* dest=buffer+off;const uint8_t* in=input_source(c);
    int good=fn(dest,in,c.size)==dest;
    for(unsigned j=0;j<c.size+160;++j) {
        uint8_t wanted=pattern(j)^0xA5;
        if(j>=off && j<off+c.size) {
            if(c.source==1) wanted=in[j-off];
            else if(c.source==0) wanted=pattern(32+c.src_offset+j-off);
            else wanted=pattern((unsigned)(in-buffer)+j-off)^0xA5;
        }
        if(buffer[j]!=wanted) good=0;
    }
    if(c.source<2) for(unsigned j=0;j<c.size+64;++j) if(source[j]!=pattern(j)) good=0;
    ++report.h[5];
    if(!good) { ++report.h[6];report.h[7]=index;report.h[8]=c.size;report.h[9]=c.src_offset;report.h[10]=c.dst_offset;report.h[28]=c.source; }
    if(!(report.h[5]&31)) mk61_api->service();
    return good;
}
static uint32_t crc(const void* data,unsigned n) {
    const volatile uint8_t* p=data;uint32_t c=~0u;
    for(unsigned i=0;i<n;++i) { c^=p[i];for(unsigned b=0;b<8;++b)c=(c>>1)^(0xEDB88320u&(0u-(c&1u))); }
    return ~c;
}
int main(void) {
    for(unsigned i=0;i<64;++i) report.h[i]=0;
    const mk61_app_services* s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
    if(!s || !s->runtime) return MK61_APP_RUNTIME_ERROR;
    mk61_service_file file={0};
    if(s->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_MK61_BINARY,
        (uint32_t)(uintptr_t)(BENCH_ROOT "/INPUT.bin"),&file)) return MK61_APP_IO_ERROR;
    struct { uint32_t h[4];Input rows[ROWS]; } input;
    if(mk61_api->file_read(file.id,0,(uint8_t*)&input,sizeof(input))!=sizeof(input) ||
       input.h[0]!=0x4D4D4F56 || input.h[1]!=1 || !input.h[2] || input.h[2]>ROWS) return MK61_APP_INVALID_FILE;
    for(unsigned i=0;i<input.h[2];++i)
        if(input.rows[i].size>LIMIT || input.rows[i].src_offset>7 || input.rows[i].dst_offset>64 ||
           input.rows[i].source>4 || !input.rows[i].loops || input.rows[i].loops>65536) return MK61_APP_INVALID_FILE;
    bench_runtime=s->runtime;
#if __ARM_ARCH_6M__
    typedef void* (*Lookup)(const uint16_t*,uint32_t);
    Lookup lookup=(Lookup)(uintptr_t)rom_half(0x18);
    Copy rom_pointer=(Copy)lookup((const uint16_t*)(uintptr_t)rom_half(0x14),0x434D);
    report.h[11]=rom_half(0x12)>>8;
    if(report.h[11]!=3 || (uintptr_t)rom_pointer!=0x261D) return MK61_APP_RUNTIME_ERROR;
    Copy rom=rom_move,extra=byte_move;
    report.h[15]=125000000;
    report.h[24]=crc((const void*)0x2604,168);
    if(report.h[24]!=3697890341u) return MK61_APP_RUNTIME_ERROR;
#else
    report.h[24]=crc((const void*)0x1FFF0000,0x7800);
    if(report.h[24]!=0x9F8F7DEDu) return MK61_APP_RUNTIME_ERROR;
    Copy rom=rom_move,extra=byte_move;
    uint32_t demcr=*(volatile uint32_t*)0xE000EDFCu, dwt=*(volatile uint32_t*)0xE0001000u;
    *(volatile uint32_t*)0xE000EDFCu=demcr|0x1000000u;
    *(volatile uint32_t*)0xE0001000u=dwt|1u;
    report.h[11]=*(volatile uint32_t*)0x40023C00u;
    report.h[15]=96000000;
#endif
    report.h[12]=(uintptr_t)rom;report.h[13]=(uintptr_t)s->runtime[MK61_RUNTIME_SLOT_memmove];
    Copy functions[FUNCTIONS]={baseline,rom,(Copy)s->runtime[MK61_RUNTIME_SLOT_memmove],runtime_move,own16,own64,memmove,extra};
#ifdef BENCH_FLASH_HEADER
    report.h[25]=crc((const void*)PAYLOAD_BASE,PAYLOAD_BYTES);
    if(report.h[25]!=PAYLOAD_CRC) goto finished;
    functions[0]=(Copy)FLASH_BASELINE;functions[4]=(Copy)FLASH_OWN16;functions[5]=(Copy)FLASH_OWN64;
#ifndef BENCH_SELECTED_RUNTIME
    functions[6]=(Copy)FLASH_SDK;
#endif
#endif
#ifdef BENCH_SELECTED_RUNTIME
    /* Bind this APP's normal SDK trampoline to the selected, byte-identical
     * production body. The device's resident service table stays untouched.
     * This isolates the runtime calling cost without installing a new image. */
    for(unsigned i=0;i<MK61_RUNTIME_COUNT;++i) selected_runtime[i]=s->runtime[i];
#ifdef BENCH_FLASH_HEADER
    selected_runtime[24]=(mk61_service_runtime_function)FLASH_SDK;
#else
    selected_runtime[24]=(mk61_service_runtime_function)own64;
#endif
    bench_selected_runtime=selected_runtime;
    mk61_app_runtime=selected_runtime;
    functions[4]=runtime_selected;
    report.h[26]=1;report.h[27]=(uintptr_t)selected_runtime[24];
#endif
    report.h[0]=0x4D4D5250;report.h[1]=1;report.h[2]=FUNCTIONS;report.h[3]=input.h[2];report.h[4]=ROUNDS;
    for(unsigned f=0;f<FUNCTIONS;++f) report.h[16+f]=(uintptr_t)functions[f];
    /* Snapshot resident entry instructions to identify the actual wrapper. */
    for(unsigned i=0;i<64;++i) ((uint8_t*)&report.h[32])[i]=((const uint8_t*)((uintptr_t)s->runtime[24]&~1u))[i];
    for(unsigned f=0;f<FUNCTIONS;++f) {
        if(functions[f](NULL,NULL,0)!=NULL) { ++report.h[6];report.h[7]=f; }
        ++report.h[5];
        if(input.h[3]) {
            for(unsigned n=0;n<=65;++n) for(unsigned a=0;a<4;++a) {
                for(unsigned kind=2;kind<=3;++kind) for(unsigned gap=1;gap<=4;++gap)
                    if(!check(functions[f],f,(Input){n,a,gap,1,kind})) goto finished;
                if(!check(functions[f],f,(Input){n,a,0,1,4})) goto finished;
            }
            const unsigned sizes[]={127,128,129,255,256,257,511,512,513,1024,4096};
            const unsigned gaps[]={1,2,3,4,7,15,16,31,32,63,64};
            for(unsigned n=0;n<sizeof(sizes)/sizeof(sizes[0]);++n) for(unsigned a=0;a<4;++a) {
                for(unsigned kind=2;kind<=3;++kind) for(unsigned g=0;g<sizeof(gaps)/sizeof(gaps[0]);++g)
                    if(!check(functions[f],f,(Input){sizes[n],a,gaps[g],1,kind})) goto finished;
                for(unsigned kind=0;kind<=1;++kind) for(unsigned b=0;b<4;++b)
                    if(!check(functions[f],f,(Input){sizes[n],a,b,1,kind})) goto finished;
            }
        }
        for(unsigned c=0;c<input.h[2];++c) if(!check(functions[f],f,input.rows[c])) goto finished;
    }
    uint32_t begin=tick();
    do {
        for(unsigned f=0;f<FUNCTIONS;++f) sink=(uintptr_t)functions[f](buffer+32,source+32,1024);
        mk61_api->service();
    } while((report.h[14]=tick()-begin)<WARMUP);
    for(unsigned c=0;c<input.h[2];++c) {
        Input row=input.rows[c];report.rows[c].input=row;
        for(unsigned r=0;r<ROUNDS;++r) {
            mk61_api->service();report.rows[c].control[r]=measure(control_move,row);
            for(unsigned order=0;order<FUNCTIONS;++order) {
                unsigned f=(order+r+c)%FUNCTIONS;
                mk61_api->service();report.rows[c].time[f][r]=measure(functions[f],row);
            }
        }
    }
finished:;
#if !__ARM_ARCH_6M__
    *(volatile uint32_t*)0xE0001000u=dwt;
    *(volatile uint32_t*)0xE000EDFCu=demcr;
#endif
    mk61_service_write out={"RESULT",(const uint8_t*)&report,(uint32_t)(256+input.h[2]*sizeof(Row)),MK61_SERVICE_INVALID_ID};
    return s->call(MK61_SERVICE_FILE_WRITE,file.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&out)?MK61_APP_OK:MK61_APP_IO_ERROR;
}
