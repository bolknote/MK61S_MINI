#include <stdint.h>
static uint32_t test_clock;
#define SPECTRUM_HIL_CLOCK() test_clock
#define SPECTRUM_HIL_PACED_SELF_TEST
#define main probe_app_main
#include "spectrum_hil_paced.c"
#undef main
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>

static char output[32768];
static unsigned used,escape_key;
static uint32_t keyboard_cost=37,service_cost=7,service_calls;
static uint8_t ram[49152],rom[16384];
static spectrum test_machine;
static void service(void) { test_clock+=service_cost;++service_calls; }
static void millisecond_delay(uint32_t n) { (void)n;assert(!"Frame pacing must not call the millisecond delay"); }
static const mk61_app_api api={.service=service,.delay_ms=millisecond_delay};
const mk61_app_api* mk61_api=&api;
static uint32_t call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* p) {
    if(op==MK61_SERVICE_MICROS) return test_clock++;
    if(op==MK61_SERVICE_DISPLAY) return 0;
    if(op==MK61_SERVICE_KEYBOARD) {
        assert(a==MK61_SERVICE_KEY_BITMAP && b==32 && !c);memset(p,0,32);test_clock+=keyboard_cost;
        if(escape_key)((uint8_t*)p)[escape_key/8]|=1U<<(escape_key&7);
        return 1;
    }
    assert(op==MK61_SERVICE_DEBUG_WRITE && !b && !c && a<=192 && used+a<sizeof(output));
    memcpy(output+used,p,a);used+=a;output[used]=0;return a;
}
static int format(char* out,uint32_t n,const char* f,va_list args) { return vsnprintf(out,n,f,args); }
static const mk61_app_services fake={MK61_APP_SERVICES_MAGIC,MK61_APP_SERVICES_VERSION,sizeof(mk61_app_services),NULL,call,NULL,format,NULL};

static void begin(paced_trace* state,uint32_t clock_start,unsigned long cycle_start) {
    active_machine=&test_machine;
    spectrum_init(&machine,ram,rom);machine.pentagon=true;machine.cpu.cyc=cycle_start;
    services=&fake;trace=state;test_clock=clock_start;used=escape_key=0;mapped_roms=true;
    memset(keys,0,32);memset(previous_keys,0,32);observed_begin(&machine,NULL,NULL);
}
static void scheduled_frames(uint32_t clock_start,uint32_t cycle_start,unsigned resume_phase,bool pentagon) {
    paced_trace state;begin(&state,clock_start,cycle_start);
    machine.pentagon=pentagon;
    const uint32_t frame_cycles=spectrum_frame_cycles(&machine),frame_us=frame_cycles*2/7;
    uint8_t blocked[32]={0};uint32_t keyboard_deadline=clock_start,deadline=clock_start-resume_phase*2/7;
    const uint32_t origin=deadline;
    for(unsigned frame=1;frame<=PACED_WARMUP+PACED_WINDOW*PACED_WINDOWS;++frame) {
        machine.frames=frame;machine.frame_tstates=(frame*137)%2048;
        machine.cpu.cyc=(uint32_t)(cycle_start+frame*frame_cycles+machine.frame_tstates-resume_phase);
        test_clock+=4000+(frame%5)*137;
        const uint32_t target=origin+frame*frame_us+machine.frame_tstates*2/7;
        assert(pace_frame(blocked,&keyboard_deadline,&deadline));
        assert((int32_t)(test_clock-target)>=0 && (uint32_t)(test_clock-target)<=1);
    }
    assert(state.started && state.done && state.count==10 && !state.resyncs && state.max_late==0);
    assert(steady.frames==3000 && steady.cycles==3000U*frame_cycles+steady.phase-steady.first_phase);
    uint32_t cycles=0,wall=0;
    for(unsigned i=0;i<10;++i) {
        const paced_window* w=&state.windows[i];assert(w->frames==300);
        assert(w->cycles==300U*frame_cycles+w->last_phase-w->first_phase);cycles+=w->cycles;wall+=w->wall;
        if(i)assert(state.windows[i-1].last_phase==w->first_phase);
    }
    assert(cycles==steady.cycles && wall==steady.last_us-steady.first_us);
    observed_end(&machine);assert(strstr(output,"SPPACING count=10"));
}
static void zero_timestamps(bool end_zero) {
    paced_trace state;begin(&state,123,0);
    const uint32_t start=end_zero?0U-3000U*20480:0;
    for(unsigned i=0;i<=10;++i) {
        machine.frames=100+i*300;machine.frame_tstates=0;machine.cpu.cyc=machine.frames*71680UL;
        const uint32_t now=start+i*300U*20480;
        paced_boundary(&machine,now,now,now-100,false);
    }
    assert(state.done && steady.last_us-steady.first_us==61440000U);
    if(end_zero)assert(steady.last_us==0);else assert(steady.first_us==0);
    observed_end(&machine);assert(strstr(output,"wall=61440000 phase=0/0"));
}
static void delayed_window_is_not_discarded(void) {
    paced_trace state;begin(&state,0,0);
    for(unsigned i=0;i<=10;++i) {
        machine.frames=100+i*300;machine.frame_tstates=0;machine.cpu.cyc=machine.frames*71680UL;
        const uint32_t target=i*300U*20480,now=target+(i==1?100:0);
        paced_boundary(&machine,target,now,now-100,false);
    }
    assert(state.count==10 && state.windows[0].wall==6144100 && state.windows[1].wall==6143900);
    assert(steady.last_us-steady.first_us==61440000 && state.max_late==100);
}
static void escape_and_resync(void) {
    for(unsigned key=27;key<=0x90;key+=0x90-27) {
        paced_trace state;begin(&state,1000000,0);machine.frame_tstates=0;started=true;escape_key=key;
        uint8_t blocked[32]={0};uint32_t keyboard_deadline=test_clock,deadline=test_clock;
        assert(!pace_frame(blocked,&keyboard_deadline,&deadline));assert(started==(key==27));
    }
    paced_trace state;begin(&state,2000000,0);machine.frames=100;machine.frame_tstates=141;
    uint8_t blocked[32]={0};uint32_t keyboard_deadline=test_clock,deadline=test_clock-20480-100001;
    assert(pace_frame(blocked,&keyboard_deadline,&deadline));assert(state.resyncs==0);
    deadline=test_clock-20480-100002-machine.frame_tstates*2/7;
    assert(pace_frame(blocked,&keyboard_deadline,&deadline));assert(state.resyncs==1);
}
static void bounded_native_turns(uint32_t start) {
    paced_trace state;begin(&state,start,0);machine.pentagon=true;machine.frame_tstates=0;
    uint8_t blocked[32]={0};uint32_t keyboard_deadline=start;
    uint32_t deadline=start-20480+2050,target=start+2050;
    keyboard_cost=service_cost=1800;service_calls=0;
    assert(pace_frame(blocked,&keyboard_deadline,&deadline));
    // The key read used almost all the available time. An additional
    // service turn based on the old timestamp would overrun by >1.5ms.
    assert(service_calls==0 && test_clock-target<=1);
    keyboard_cost=37;service_cost=7;
}
int main(int argc,char** argv) {
    scheduled_frames(1000000,0,0,true);
    if(argc==2) { FILE* f=fopen(argv[1],"wb");assert(f);assert(fwrite(output,1,used,f)==used);assert(!fclose(f)); }
    scheduled_frames(UINT32_MAX-100000,UINT32_MAX-12345,779,true);
    scheduled_frames(1000000,0,0,false);
    scheduled_frames(UINT32_MAX-100000,UINT32_MAX-12345,779,false);
    zero_timestamps(false);zero_timestamps(true);delayed_window_is_not_discarded();escape_and_resync();
    bounded_native_turns(1000000);bounded_native_turns(UINT32_MAX-1000);
    puts("Actual APP pacing: microsecond boundaries, resumed phase, late reset, Esc/F10, ten adjacent windows, zero/wrapping timestamps and cycle wrap PASS");
}
