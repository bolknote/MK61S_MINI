#include <stdint.h>
static uint32_t test_clock;
#define SPECTRUM_HIL_CLOCK() test_clock
#define main probe_app_main
#include "spectrum_hil_steady.c"
#undef main
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
static uint8_t test_ram[49152],test_rom[16384];
static char output[4096];
static unsigned used;
static uint32_t log_call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* payload) {
    if(op==MK61_SERVICE_DISPLAY) return 0;
    assert(op==MK61_SERVICE_DEBUG_WRITE && !b && !c && a<=128 && used+a<sizeof(output));
    memcpy(output+used,payload,a);used+=a;output[used]=0;return a;
}
static int format_output(char* out,uint32_t n,const char* f,va_list args) { return vsnprintf(out,n,f,args); }
static const mk61_app_services fake={MK61_APP_SERVICES_MAGIC,MK61_APP_SERVICES_VERSION,sizeof(mk61_app_services),NULL,log_call,NULL,format_output,NULL};
const mk61_app_api* mk61_api;
static void exercise(uint32_t clock_start,unsigned long cycle_start) {
    spectrum_init(&machine,test_ram,test_rom);machine.cpu.cyc=cycle_start;
    services=&fake;used=0;test_clock=clock_start;observed_begin(&machine,NULL,NULL);
    test_clock+=300000; // Audio/UI start barrier is outside the steady interval.
    const uint32_t first=test_clock;
    for(unsigned frame=1;frame<=301;++frame) {
        test_clock=first+(frame-1)*20480U;
        machine.frames=frame;machine.frame_tstates=100;machine.cpu.cyc=cycle_start+frame*71680UL+100;
        atomic_store(&machine.sound.starved,frame==1?1:21);
        assert(observed_run(&machine,0)==0);
        // Calls within the same emulated frame cannot move the endpoints.
        test_clock+=500;assert(observed_run(&machine,0)==0);
    }
    test_clock=first+300*20480U+400000; // Audio/LCD drain is outside too.
    observed_end(&machine);
    assert(strstr(output,"SPSTEADY frames=300 cycles=21504000 wall=6144000 phase=100/100 starved=20\n"));
    assert(strstr(output,"wall=6844000 xip="));
}
int main(void) {
    exercise(1000000,0);exercise(UINT32_MAX-200000,UINT32_MAX-40000UL);
    puts("Actual HIL timing probe excludes start/drain barriers, samples frame boundaries and handles timer/cycle wrap: PASS");
}
