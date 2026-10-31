/* Physical memchr timing. No runtime ABI extension: the indirect column uses
 * an APP-local 27-entry table and the same veneer as ISO-C runtime functions. */
#include "mk61_app.h"
#include <stddef.h>
#include <stdint.h>
#ifdef BENCH_RUNTIME_MATRIX
#include <string.h>
#endif
#if defined(__ARM_ARCH_6M__)
#if defined(BENCH_RUNTIME_MATRIX)
#define FUNCTIONS 8U
#else
#define FUNCTIONS 7U
#endif
#define WARMUP 200000U
static uint32_t tick(void) { __asm__ volatile("":::"memory");return *(volatile uint32_t*)0x40054028u; }
#else
#define FUNCTIONS 8U
#define WARMUP 19200000U
static uint32_t tick(void) { __asm__ volatile("":::"memory");return *(volatile uint32_t*)0xE0001004u; }
#endif
#define ROUNDS 7U
#ifdef BENCH_WIDE_MATRIX
#undef FUNCTIONS
#if defined(__ARM_ARCH_6M__)
#define FUNCTIONS 15U
#else
#define FUNCTIONS 16U
#endif
#define ROWS 7U
#define FP_BASE 36U
#define SDK_INDEX (FUNCTIONS-3U)
#define RUNTIME_INDEX (FUNCTIONS-1U)
#define REPORT_VERSION 4U
#else
#define ROWS 12U
#define FP_BASE 16U
#define SDK_INDEX 6U
#define RUNTIME_INDEX 7U
#define REPORT_VERSION 3U
#endif
#define LIMIT 4096U
typedef void* (*Search)(const void*,int,size_t);
extern void *baseline(const void*,int,size_t),*libc_search(const void*,int,size_t);
extern void *byte_search(const void*,int,size_t),*own4(const void*,int,size_t);
extern void *own16(const void*,int,size_t),*own64(const void*,int,size_t);
extern void *indirect_search(const void*,int,size_t),*control_search(const void*,int,size_t);
#if !defined(__ARM_ARCH_6M__)
extern void* swar16(const void*,int,size_t);
#endif
#ifdef BENCH_RUNTIME_MATRIX
extern void *pair16(const void*,int,size_t),*pair64(const void*,int,size_t);
extern void *fast16(const void*,int,size_t),*fast64(const void*,int,size_t);
#ifdef BENCH_WIDE_MATRIX
extern void *balanced16(const void*,int,size_t),*balanced64(const void*,int,size_t);
#if !defined(__ARM_ARCH_6M__)
extern void* compact8(const void*,int,size_t);
#endif
#endif
#if !defined(__ARM_ARCH_6M__)
extern void *dsp16(const void*,int,size_t),*dsp32(const void*,int,size_t);
#endif
#ifdef MK61_APP_SHARED_RUNTIME
extern Search mk61_optional_memchr;
#endif
#endif
#ifdef BENCH_FLASH_HEADER
#include BENCH_FLASH_HEADER
#endif
const mk61_service_runtime_function* bench_search_runtime;
#ifndef BENCH_RUNTIME_MATRIX
static mk61_service_runtime_function selected_runtime[27];
#endif
static uint8_t buffer[LIMIT+80] __attribute__((aligned(16)));
static volatile uintptr_t sink;
/* mode: absent, first, byte 4, middle, last. Flash rows use the frozen payload
 * bytes and the requested value; mode is descriptive and never changes Flash. */
typedef struct { uint32_t size,offset,value,loops,source,mode; } Input;
typedef struct { Input input;uint32_t control[ROUNDS],time[FUNCTIONS][ROUNDS]; } Row;
static struct { uint32_t h[64];Row rows[ROWS]; } report;
_Static_assert(sizeof(report)<=4096,"Bounded result file");
#ifndef BENCH_RUNTIME_MATRIX
_Static_assert(MK61_RUNTIME_COUNT==26,"No public memchr slot in this experiment");
#endif
static const uint8_t* data(Input c) {
#ifdef BENCH_FLASH_HEADER
    if(c.source) return (const uint8_t*)PAYLOAD_DATA+c.offset;
#endif
    return buffer+32+c.offset;
}
static unsigned hit(Input c) {
    return !c.mode?c.size:c.mode==1?0:c.mode==2?(c.size>4?4:c.size-1):c.mode==3?c.size/2:c.size-1;
}
static uint8_t wanted(Input c,unsigned j) {
    unsigned first=32+c.offset;
    uint8_t value=(uint8_t)(j*13+(j>>8)*7);
    if(j>=first && j-first<c.size) {
        unsigned at=j-first;
        value=(uint8_t)c.value^(at&1?128:1);
        if(at==hit(c)) value=(uint8_t)c.value;
    }
    return value;
}
static void prepare(Input c) {
    for(unsigned i=0;i<c.size+64;++i) buffer[i]=wanted(c,i);
}
static __attribute__((noipa)) void* reference(const void* input,int value,size_t n) {
    const uint8_t* p=input;
    for(size_t i=0;i<n;++i) if(p[i]==(uint8_t)value) return (void*)(p+i);
    return NULL;
}
static __attribute__((noipa)) uint32_t measure(Search fn,Input c) {
    const uint8_t* p=data(c);uint32_t begin=tick();
    for(unsigned i=0;i<c.loops;++i) sink=(uintptr_t)fn(p,(int)c.value,c.size);
    return tick()-begin;
}
static int check(Search fn,unsigned f,Input c) {
    prepare(c);void* expected=reference(data(c),(int)c.value,c.size);
    void* actual=fn(data(c),(int)c.value,c.size);int good=actual==expected;
    for(unsigned j=0;j<c.size+64;++j) if(buffer[j]!=wanted(c,j)) good=0;
    ++report.h[5];
    if(!good) {
        ++report.h[6];report.h[7]=f;report.h[8]=c.size;report.h[9]=c.offset;
        report.h[10]=c.value;report.h[28]=c.source;report.h[29]=c.mode;
        report.h[30]=(uintptr_t)expected;report.h[31]=(uintptr_t)actual;
    }
    if(c.size>=512 || !(report.h[5]&31)) mk61_api->service();
    return good;
}
static uint32_t read_byte_at(uintptr_t address) {
    uint32_t value;__asm__ volatile("ldrb %0,[%1]":"=l"(value):"l"(address):"memory");return value;
}
static uint32_t crc(const void* data,unsigned n) {
    uint32_t c=~0u;
    for(unsigned i=0;i<n;++i) {
        c^=read_byte_at((uintptr_t)data+i);
        for(unsigned b=0;b<8;++b)c=(c>>1)^(0xEDB88320u&(0u-(c&1u)));
    }
    return ~c;
}
int main(void) {
#ifdef BENCH_RUNTIME_MATRIX
    memset(&report,0,sizeof(report));
#endif
    const mk61_app_services* s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
    if(!s || !s->runtime) return MK61_APP_RUNTIME_ERROR;
#ifdef BENCH_RUNTIME_MATRIX
    /* Guard this exact provider contract before any optional dispatch. */
    if(s->struct_size!=BENCH_EXPECT_SERVICES_SIZE ||
       mk61_app_runtime_count(s)!=BENCH_EXPECT_RUNTIME_COUNT) return MK61_APP_RUNTIME_ERROR;
#if BENCH_EXPECT_RUNTIME_COUNT > 26
    if(!s->runtime[MK61_RUNTIME_SLOT_memchr]) return MK61_APP_RUNTIME_ERROR;
#endif
#endif
    mk61_service_file file={0};
    if(s->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_MK61_BINARY,
        (uint32_t)(uintptr_t)(BENCH_ROOT "/INPUT.bin"),&file)) return MK61_APP_IO_ERROR;
    struct { uint32_t h[4];Input rows[ROWS]; } input;
    if(mk61_api->file_read(file.id,0,(uint8_t*)&input,sizeof(input))!=sizeof(input) ||
       input.h[0]!=0x4D434852 || input.h[1]!=1 || !input.h[2] || input.h[2]>ROWS) return MK61_APP_INVALID_FILE;
    for(unsigned i=0;i<input.h[2];++i)
        if(input.rows[i].size>LIMIT || input.rows[i].offset>7 || input.rows[i].source>1 ||
           input.rows[i].mode>4 || !input.rows[i].loops || input.rows[i].loops>65536) return MK61_APP_INVALID_FILE;
#ifndef BENCH_FLASH_HEADER
    for(unsigned i=0;i<input.h[2];++i) if(input.rows[i].source) return MK61_APP_INVALID_FILE;
#endif
    report.h[0]=0x4D435250;report.h[1]=REPORT_VERSION;report.h[2]=FUNCTIONS;report.h[3]=input.h[2];report.h[4]=ROUNDS;
#ifdef BENCH_RUNTIME_MATRIX
#ifdef BENCH_WIDE_MATRIX
    Search functions[FUNCTIONS]={baseline,libc_search,byte_search,own4,own16,own64,
        pair16,balanced16,pair64,balanced64,
#if defined(__ARM_ARCH_6M__)
        fast16,fast64,
#else
        dsp16,dsp32,compact8,
#endif
        memchr,byte_search,byte_search};
#else
    Search functions[FUNCTIONS]={baseline,libc_search,
#if defined(__ARM_ARCH_6M__)
        pair16,fast16,pair64,fast64,
#else
        dsp16,pair64,fast64,dsp32,
#endif
        memchr,byte_search};
#endif
#else
    Search functions[FUNCTIONS]={baseline,libc_search,byte_search,own4,own16,own64,indirect_search
#if !defined(__ARM_ARCH_6M__)
        ,swar16
#endif
    };
#endif
#if defined(__ARM_ARCH_6M__)
    report.h[11]=read_byte_at(0x13u);report.h[15]=125000000;
    report.h[24]=crc((const void*)0,16384);
    if(report.h[11]!=3 || report.h[24]!=0x0A428502u) return MK61_APP_RUNTIME_ERROR;
#else
    uint32_t demcr=*(volatile uint32_t*)0xE000EDFCu,dwt=*(volatile uint32_t*)0xE0001000u;
    *(volatile uint32_t*)0xE000EDFCu=demcr|0x1000000u;
    *(volatile uint32_t*)0xE0001000u=dwt|1u;
    report.h[11]=*(volatile uint32_t*)0x40023C00u;report.h[15]=96000000;
    report.h[24]=crc((const void*)0x1FFF0000,0x7800);
    if(report.h[24]!=0x9F8F7DEDu) { ++report.h[6];goto finished; }
#endif
#ifdef BENCH_WIDE_MATRIX
    report.h[54]=1;
#endif
#ifdef BENCH_FLASH_HEADER
    report.h[25]=crc((const void*)PAYLOAD_BASE,PAYLOAD_BYTES);
    if(report.h[25]!=PAYLOAD_CRC) { ++report.h[6];goto finished; }
#ifndef BENCH_FLASH_DATA_ONLY
#ifdef BENCH_RUNTIME_MATRIX
#ifdef BENCH_WIDE_MATRIX
    functions[0]=(Search)FLASH_BASELINE;functions[1]=(Search)FLASH_LIBC_SEARCH;
    functions[2]=(Search)FLASH_BYTE_SEARCH;functions[3]=(Search)FLASH_OWN4;
    functions[4]=(Search)FLASH_OWN16;functions[5]=(Search)FLASH_OWN64;
    functions[6]=(Search)FLASH_PAIR16;functions[7]=(Search)FLASH_BALANCED16;
    functions[8]=(Search)FLASH_PAIR64;functions[9]=(Search)FLASH_BALANCED64;
#if defined(__ARM_ARCH_6M__)
    functions[10]=(Search)FLASH_FAST16;functions[11]=(Search)FLASH_FAST64;
#else
    functions[10]=(Search)FLASH_DSP16;functions[11]=(Search)FLASH_DSP32;
    functions[12]=(Search)FLASH_COMPACT8;
#endif
#else
    functions[0]=(Search)FLASH_BASELINE;functions[1]=(Search)FLASH_LIBC_SEARCH;
    functions[2]=(Search)FLASH_MATRIX_2;functions[3]=(Search)FLASH_MATRIX_3;
    functions[4]=(Search)FLASH_MATRIX_4;functions[5]=(Search)FLASH_MATRIX_5;
#endif
#else
    functions[0]=(Search)FLASH_BASELINE;functions[1]=(Search)FLASH_LIBC_SEARCH;
    functions[2]=(Search)FLASH_BYTE_SEARCH;functions[3]=(Search)FLASH_OWN4;
    functions[4]=(Search)FLASH_OWN16;functions[5]=(Search)FLASH_OWN64;
#if !defined(__ARM_ARCH_6M__)
    functions[7]=(Search)FLASH_SWAR16;
#endif
#endif
#endif
#endif
#ifdef BENCH_RUNTIME_MATRIX
#ifdef BENCH_WIDE_MATRIX
    report.h[26]=4;report.h[54]=2;
#else
    report.h[26]=3;
#endif
    report.h[27]=mk61_app_runtime_count(s);
    report.h[34]=s->struct_size;
#ifdef BENCH_WIDE_MATRIX
    report.h[35]=(uintptr_t)s->runtime;
#endif
    if(report.h[27]>MK61_RUNTIME_SLOT_memchr && s->runtime[MK61_RUNTIME_SLOT_memchr]) {
        bench_search_runtime=s->runtime;functions[RUNTIME_INDEX]=indirect_search;
#ifdef BENCH_WIDE_MATRIX
        functions[FUNCTIONS-2U]=(Search)s->runtime[MK61_RUNTIME_SLOT_memchr];
#endif
        report.h[13]=(uintptr_t)s->runtime[MK61_RUNTIME_SLOT_memchr];
    }
    for(unsigned f=0;f<FUNCTIONS;++f) report.h[FP_BASE+f]=(uintptr_t)functions[f];
#ifdef BENCH_WIDE_MATRIX
    report.h[54]=3;
#endif
    uint32_t cold=tick();sink=(uintptr_t)functions[SDK_INDEX](NULL,-1,0);report.h[32]=tick()-cold;
#ifdef MK61_APP_SHARED_RUNTIME
    report.h[33]=(uintptr_t)mk61_optional_memchr;
#else
    report.h[33]=(uintptr_t)functions[SDK_INDEX];
#endif
    if(sink) { ++report.h[6];report.h[7]=SDK_INDEX;goto finished; }
#ifdef BENCH_WIDE_MATRIX
    report.h[54]=4;
#endif
#else
    for(unsigned i=0;i<26;++i) selected_runtime[i]=s->runtime[i];
    selected_runtime[26]=(mk61_service_runtime_function)functions[5];
    bench_search_runtime=selected_runtime;report.h[13]=(uintptr_t)functions[5];
    /* h26 distinguishes a local synthetic slot from the public runtime API. */
    report.h[26]=1;
#endif
    for(unsigned f=0;f<FUNCTIONS;++f) report.h[FP_BASE+f]=(uintptr_t)functions[f];
    for(unsigned f=0;f<FUNCTIONS;++f) {
        ++report.h[5];
        if(functions[f](NULL,-1,0)!=NULL) { ++report.h[6];report.h[7]=f;goto finished; }
        if(input.h[3]) {
            const unsigned values[]={0,1,127,128,255,0xffffffffu,256,511,0x123400a5u};
            for(unsigned n=0;n<=65;++n) for(unsigned a=0;a<4;++a)
                for(unsigned v=0;v<sizeof(values)/sizeof(values[0]);++v) for(unsigned mode=0;mode<5;++mode)
                    if(!check(functions[f],f,(Input){n,a,values[v],1,0,mode})) goto finished;
            const unsigned sizes[]={127,128,129,255,256,257,511,512,513,1024,4096};
            for(unsigned n=0;n<sizeof(sizes)/sizeof(sizes[0]);++n) for(unsigned a=0;a<4;++a)
                for(unsigned mode=0;mode<5;++mode)
                    if(!check(functions[f],f,(Input){sizes[n],a,0xa5,1,0,mode})) goto finished;
        }
        for(unsigned c=0;c<input.h[2];++c) if(!check(functions[f],f,input.rows[c])) goto finished;
    }
    Input warm={1024,0,0,1,0,0};prepare(warm);uint32_t begin=tick();
    do {
        for(unsigned f=0;f<FUNCTIONS;++f) sink=(uintptr_t)functions[f](data(warm),0,warm.size);
        mk61_api->service();
    } while((report.h[14]=tick()-begin)<WARMUP);
#ifdef BENCH_WIDE_MATRIX
    report.h[54]=5;
#endif
    for(unsigned c=0;c<input.h[2];++c) {
        Input row=input.rows[c];report.rows[c].input=row;prepare(row);
        for(unsigned r=0;r<ROUNDS;++r) {
            mk61_api->service();report.rows[c].control[r]=measure(control_search,row);
            for(unsigned order=0;order<FUNCTIONS;++order) {
                unsigned f=(order+r+c)%FUNCTIONS;
                mk61_api->service();report.rows[c].time[f][r]=measure(functions[f],row);
            }
        }
    }
#ifdef BENCH_WIDE_MATRIX
    report.h[54]=6;
#endif
finished:;
#if !defined(__ARM_ARCH_6M__)
    *(volatile uint32_t*)0xE0001000u=dwt;*(volatile uint32_t*)0xE000EDFCu=demcr;
#endif
    mk61_service_write out={"RESULT",(const uint8_t*)&report,(uint32_t)(256+input.h[2]*sizeof(Row)),MK61_SERVICE_INVALID_ID};
    return s->call(MK61_SERVICE_FILE_WRITE,file.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&out)?MK61_APP_OK:MK61_APP_IO_ERROR;
}
