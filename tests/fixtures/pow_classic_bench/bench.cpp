#include <stdint.h>
#include <string.h>
#if POW_BENCH_PICO
#include "compact_math.hpp"
#include "hardware/clocks.h"
#include "hardware/watchdog.h"
#include "pico/stdlib.h"
#include <stdio.h>
namespace classic_reference { double pow(double,double); }
#else
#include "mk61_app.h"
static const mk61_app_services *services;
#endif

namespace {
struct Pair { double x,y; };
constexpr Pair pairs[]={
    {1.3,.7},{.7,1.3},{10,1.125},{1.001,20},{1.2,3},{1.2,4},
    {1.2,2},{1.2,-1},{2,.5},{1.2,-.5},{.5,-3},{-1.2,5},{-2,.5},
    {0,-1.5},{-0.,3},{1,4.2},{1.2,-0.},{1.2,1},{2,64},{1e200,1e-20},
    {0x1.fffffffffffffp-1,0x1p52},{2,-1074.5},{2,1023.75},
    {0x0.0000000000001p-1022,0.25}
};
constexpr unsigned count=sizeof(pairs)/sizeof(*pairs), samples=128, rounds=7;
struct Row { uint64_t bits; uint32_t ticks,control; };
struct Report { uint32_t magic,case_count,batch_size,batches; Row rows[count]; };
static volatile double operand_x,operand_y,sink;
using Call=double(*)(double,double);
__attribute__((noipa)) double identity(double x,double) { return x; }
#if !POW_BENCH_PICO
__attribute__((noipa)) double resident(double x,double y) { return services->math(MK61_SERVICE_POW,x,y); }
#endif
uint32_t now() {
    asm volatile ("":::"memory");
#if POW_BENCH_PICO
    return 0xffffffU-*reinterpret_cast<volatile uint32_t*>(0xe000e018);
#else
    return *reinterpret_cast<volatile uint32_t*>(0xe0001004);
#endif
}
uint32_t median(Call f) {
    uint32_t elapsed[rounds];
    for(unsigned r=0;r<rounds;++r) {
#if POW_BENCH_PICO
        watchdog_update();
#else
        mk61_api->service();
#endif
        uint32_t start=now();
        for(unsigned i=0;i<samples;++i) sink=f(operand_x,operand_y);
        uint32_t ticks=(now()-start)&0xffffffU;
        unsigned j=r;
        while(j && elapsed[j-1]>ticks) {elapsed[j]=elapsed[j-1];--j;}
        elapsed[j]=ticks;
    }
    return elapsed[rounds/2];
}
Row measure(Call f,const Pair& p) {
    operand_x=p.x; operand_y=p.y;
    const double value=f(operand_x,operand_y);
    Row row;
    memcpy(&row.bits,&value,sizeof(value));
    row.control=median(identity);
    row.ticks=median(f);
    return row;
}
}

int main() {
#if POW_BENCH_PICO
    watchdog_enable(8000,false);
    stdio_init_all();
    if(clock_get_hz(clk_sys)==125000000 && getchar_timeout_us(5500000)=='g') {
        *reinterpret_cast<volatile uint32_t*>(0xe000e014)=0xffffffU;
        *reinterpret_cast<volatile uint32_t*>(0xe000e018)=0;
        *reinterpret_cast<volatile uint32_t*>(0xe000e010)=5; // core clock, no interrupt
        printf("POW1 %u %u %u 125000000\n",count,samples,rounds);
        for(unsigned i=0;i<count;++i) {
            const Row pico=measure(compact_math::pow,pairs[i]);
            const Row ref=measure(classic_reference::pow,pairs[i]);
            printf("%u %08lx%08lx %lu %lu %08lx%08lx %lu %lu\n",i,
                (unsigned long)(pico.bits>>32),(unsigned long)pico.bits,
                (unsigned long)pico.ticks,(unsigned long)pico.control,
                (unsigned long)(ref.bits>>32),(unsigned long)ref.bits,
                (unsigned long)ref.ticks,(unsigned long)ref.control);
        }
        puts("END POW1"); stdio_flush(); sleep_ms(200);
    }
    watchdog_reboot(0,0,0);
    for(;;) tight_loop_contents();
#else
    services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_MATH);
    if(!services || !services->math || !(*reinterpret_cast<volatile uint32_t*>(0xe0001000)&1))
        return MK61_APP_RUNTIME_ERROR;
    // The installed firmware maintains a 1 ms tick. Check the DWT counter
    // over 32 tick edges before using the 96 MHz scale for the report.
    const uint32_t start_ms=mk61_api->millis_ms(), start_ticks=now();
    while(mk61_api->millis_ms()==start_ms)
        if(now()-start_ticks>2000000) return MK61_APP_RUNTIME_ERROR;
    const uint32_t first=now(), first_ms=mk61_api->millis_ms();
    while(mk61_api->millis_ms()-first_ms<32)
        if(now()-first>4000000) return MK61_APP_RUNTIME_ERROR;
    const uint32_t elapsed=now()-first;
    if(elapsed<3040000 || elapsed>3104000) return MK61_APP_RUNTIME_ERROR;
    static Report report={0x31574f50,count,samples,rounds,{}};
    for(unsigned i=0;i<count;++i) report.rows[i]=measure(resident,pairs[i]);
    mk61_service_write file={"POWCLASS",reinterpret_cast<const uint8_t*>(&report),
                             sizeof(report),MK61_SERVICE_INVALID_ID};
    return services->call(MK61_SERVICE_FILE_WRITE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_INVALID_ID,
                          MK61_SERVICE_FILE_MK61_BINARY,&file)?MK61_APP_OK:MK61_APP_IO_ERROR;
#endif
}
