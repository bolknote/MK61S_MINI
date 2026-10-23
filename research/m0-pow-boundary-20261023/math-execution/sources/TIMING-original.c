/* Private HIL APP. Calls typed soft-float entries in one identified diagnostic
 * firmware; both the owned implementation and Qfplib execute from flash.
 * Input addresses are generated from that ELF and checked by the host runner.
 */
#include "mk61_app.h"
#include <stdint.h>
#include <stddef.h>
#ifndef MK61_MATH_COMPARE_ROOT
#define MK61_MATH_COMPARE_ROOT "/MK61S-M0-TIMING"
#endif
#define CASES 512U
#define ROUNDS 12U
#ifndef MK61_M0_TIMING_WARMUP_US
#define MK61_M0_TIMING_WARMUP_US 1000000U
#endif
#ifdef MK61_M0_TIMING_CACHE
#define REPORT_VERSION 4U
#define RESULTS_OFFSET (40U+48U*ROUNDS)
static uint32_t last_hits,last_accesses;
#else
#define REPORT_VERSION 3U
#define RESULTS_OFFSET (40U+16U*ROUNDS)
#endif

typedef union { uint64_t bits;double number; } D;
typedef union { uint32_t bits;float number; } F;
typedef struct { uint64_t a,b,expected; } Vector;
enum { BINARY,UNARY,I32_D,U32_D,I64_D,U64_D,D_I32,D_U32,D_I64,D_U64,F_D,D_F,COMPARE };
static struct {
    uint32_t magic,version,group,kind,cases,loops,rounds,failures,first,warmup_us;
    uint32_t raw[2][ROUNDS],control[2][ROUNDS];
#ifdef MK61_M0_TIMING_CACHE
    uint32_t hits[2][ROUNDS],accesses[2][ROUNDS];
    uint32_t control_hits[2][ROUNDS],control_accesses[2][ROUNDS];
#endif
    uint64_t results[CASES][2];
} output;
_Static_assert(offsetof(__typeof__(output),results)==RESULTS_OFFSET,"Timing report wire layout");
static volatile uint64_t sink;
#define LEAF __attribute__((noipa))
#define NO_TABLES __attribute__((optimize("no-jump-tables")))
static LEAF double control_binary(double a,double b) { (void)b;return a; }
static LEAF double control_unary(double a) { return a; }
static LEAF double control_i32(int32_t a) { D r={.bits=(uint32_t)a};return r.number; }
static LEAF double control_u32(uint32_t a) { D r={.bits=a};return r.number; }
static LEAF double control_i64(int64_t a) { D r={.bits=(uint64_t)a};return r.number; }
static LEAF double control_u64(uint64_t a) { D r={.bits=a};return r.number; }
static LEAF int32_t control_di(double a) { D r={.number=a};return (int32_t)r.bits; }
static LEAF uint32_t control_du(double a) { D r={.number=a};return (uint32_t)r.bits; }
static LEAF int64_t control_dl(double a) { D r={.number=a};return (int64_t)r.bits; }
static LEAF uint64_t control_dul(double a) { D r={.number=a};return r.bits; }
static LEAF double control_fd(float a) { F f={.number=a};D r={.bits=f.bits};return r.number; }
static LEAF float control_df(double a) { D d={.number=a};F r={.bits=(uint32_t)d.bits};return r.number; }
static LEAF int control_compare(double a,double b) { (void)b;D r={.number=a};return (int)r.bits; }
static const uintptr_t controls[]={
    (uintptr_t)control_binary,(uintptr_t)control_unary,(uintptr_t)control_i32,
    (uintptr_t)control_u32,(uintptr_t)control_i64,(uintptr_t)control_u64,
    (uintptr_t)control_di,(uintptr_t)control_du,(uintptr_t)control_dl,
    (uintptr_t)control_dul,(uintptr_t)control_fd,(uintptr_t)control_df,
    (uintptr_t)control_compare
};
static __attribute__((always_inline)) inline uint64_t invoke(uintptr_t address,unsigned kind,Vector v) {
    D a={.bits=v.a},b={.bits=v.b},r;F f;
    switch(kind) {
    case BINARY:r.number=((double(*)(double,double))address)(a.number,b.number);return r.bits;
    case UNARY:r.number=((double(*)(double))address)(a.number);return r.bits;
    case I32_D:r.number=((double(*)(int32_t))address)((int32_t)v.a);return r.bits;
    case U32_D:r.number=((double(*)(uint32_t))address)((uint32_t)v.a);return r.bits;
    case I64_D:r.number=((double(*)(int64_t))address)((int64_t)v.a);return r.bits;
    case U64_D:r.number=((double(*)(uint64_t))address)(v.a);return r.bits;
    case D_I32:return (uint32_t)((int32_t(*)(double))address)(a.number);
    case D_U32:return ((uint32_t(*)(double))address)(a.number);
    case D_I64:return (uint64_t)((int64_t(*)(double))address)(a.number);
    case D_U64:return ((uint64_t(*)(double))address)(a.number);
    case F_D:f.bits=(uint32_t)v.a;r.number=((double(*)(float))address)(f.number);return r.bits;
    case D_F:f.number=((float(*)(double))address)(a.number);return f.bits;
    default:return (uint32_t)((int(*)(double,double))address)(a.number,b.number);
    }
}
static uint32_t micros(void) {
    __asm__ volatile("":::"memory");return *(volatile uint32_t*)UINT32_C(0x40054028);
}
static LEAF NO_TABLES uint32_t measure(uintptr_t address,unsigned kind,const Vector* inputs,unsigned count,unsigned loops) {
#ifdef MK61_M0_TIMING_CACHE
    /* RP2040 XIP counters saturate; any write clears them. Both cores
     * contribute. Accesses must enclose hits: reset accesses first and
     * read them last, including traffic between the non-atomic operations.
     * All counter operations stay outside the measured interval. */
    *(volatile uint32_t*)UINT32_C(0x14000010)=0;
    *(volatile uint32_t*)UINT32_C(0x1400000C)=0;
#endif
    const uint32_t begin=micros();
    for(unsigned pass=0;pass<loops;++pass)
        for(unsigned i=0;i<count;++i) sink=invoke(address,kind,inputs[i]);
    const uint32_t elapsed=micros()-begin;
#ifdef MK61_M0_TIMING_CACHE
    last_hits=*(volatile uint32_t*)UINT32_C(0x1400000C);
    last_accesses=*(volatile uint32_t*)UINT32_C(0x14000010);
#endif
    return elapsed;
}
static int same(uint64_t a,uint64_t b,unsigned kind) {
    if(a==b) return 1;
    if(kind==D_F) return (a&UINT32_C(0x7FFFFFFF))>UINT32_C(0x7F800000) &&
                           (b&UINT32_C(0x7FFFFFFF))>UINT32_C(0x7F800000);
    if(kind<=U64_D || kind==F_D) return (a&UINT64_C(0x7FFFFFFFFFFFFFFF))>UINT64_C(0x7FF0000000000000) &&
                                     (b&UINT64_C(0x7FFFFFFFFFFFFFFF))>UINT64_C(0x7FF0000000000000);
    return 0;
}
NO_TABLES int main(void) {
    const mk61_app_services* s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES);
    if(!s || !mk61_api->file_read) return MK61_APP_RUNTIME_ERROR;
    mk61_service_file file={0};
    if(s->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_MK61_BINARY,
        (uint32_t)(uintptr_t)(MK61_MATH_COMPARE_ROOT "/INPUT.bin"),&file)) return MK61_APP_IO_ERROR;
    uint32_t h[8];
    if(mk61_api->file_read(file.id,0,(uint8_t*)h,sizeof(h))!=sizeof(h) ||
       h[0]!=UINT32_C(0x4D304246) || h[1]!=1 || h[3]>COMPARE || !h[4] || h[4]>CASES ||
       !h[5] || h[5]>4096 || h[4]*h[5]>65536 ||
       mk61_api->file_size(file.id)!=sizeof(h)+h[4]*sizeof(Vector)) return MK61_APP_INVALID_FILE;
    for(unsigned i=6;i<8;++i)
        if(h[i]<UINT32_C(0x10000001) || h[i]>=UINT32_C(0x10200000) || !(h[i]&1)) return MK61_APP_INVALID_FILE;
    Vector inputs[CASES];
    if(mk61_api->file_read(file.id,sizeof(h),(uint8_t*)inputs,h[4]*sizeof(Vector))!=h[4]*sizeof(Vector)) return MK61_APP_IO_ERROR;
    output.magic=UINT32_C(0x4D305250);output.version=REPORT_VERSION;output.group=h[2];output.kind=h[3];
    output.cases=h[4];output.loops=h[5];output.rounds=ROUNDS;output.failures=0;output.first=UINT32_MAX;output.warmup_us=0;
    for(unsigned i=0;i<h[4];++i) {
        output.results[i][0]=invoke(h[6],h[3],inputs[i]);
        output.results[i][1]=invoke(h[7],h[3],inputs[i]);
        if(!same(output.results[i][0],inputs[i].expected,h[3])) {
            if(!output.failures) output.first=i;
            ++output.failures;
        }
        if(!(i&31)) mk61_api->service();
    }
    /* Opening the APP can start background display work. Exercise both
     * libraries before timing so short groups do not measure that transient.
     * The former reserved header word records the actual untimed duration. */
    const uint32_t warmup_begin=micros();
    while((output.warmup_us=micros()-warmup_begin)<MK61_M0_TIMING_WARMUP_US) {
        for(unsigned i=0;i<h[4];++i) {
            sink=invoke(h[6],h[3],inputs[i]);
            sink=invoke(h[7],h[3],inputs[i]);
            if(!(i&31)) mk61_api->service();
        }
    }
    for(unsigned round=0;round<ROUNDS;++round) {
        /* Each consecutive pair contains both library orders. Keep the
         * number of rounds even so neither library gets an extra first run. */
        for(unsigned order=0;order<2;++order) {
            const unsigned which=order^(round&1);
            mk61_api->service();
            output.control[which][round]=measure(controls[h[3]],h[3],inputs,h[4],h[5]);
#ifdef MK61_M0_TIMING_CACHE
            output.control_hits[which][round]=last_hits;output.control_accesses[which][round]=last_accesses;
#endif
            mk61_api->service();
            output.raw[which][round]=measure(h[6+which],h[3],inputs,h[4],h[5]);
#ifdef MK61_M0_TIMING_CACHE
            output.hits[which][round]=last_hits;output.accesses[which][round]=last_accesses;
#endif
        }
    }
    mk61_service_write out={"RESULT",(const uint8_t*)&output,
        (uint32_t)(offsetof(__typeof__(output),results)+h[4]*sizeof(output.results[0])),MK61_SERVICE_INVALID_ID};
    return s->call(MK61_SERVICE_FILE_WRITE,file.parent,MK61_SERVICE_INVALID_ID,
        MK61_SERVICE_FILE_MK61_BINARY,&out)?MK61_APP_OK:MK61_APP_IO_ERROR;
}
