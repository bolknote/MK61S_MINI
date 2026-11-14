/* Fixed, read-only game fixture. Same emulator/optimization as production;
 * only the start path, finite stop and timing observer differ. */
#include "../examples/portable-apps/SPECTRUM/ui.h"
static const mk61_app_services* observed_services(const mk61_app_api*,uint32_t);
static uint32_t observed_run(spectrum*,uint32_t);
static void observed_end(spectrum*);
static enum spectrum_error observed_load(spectrum*,const spectrum_source*);
static void observed_paced(spectrum*,uint32_t,uint32_t,uint32_t,bool);
#define SPECTRUM_HIL_PACED observed_paced
#if defined(S3_PRODUCER_PROFILE) && S3_PRODUCER_PROFILE
static void observed_video(const spectrum*,uint8_t*,uint8_t*);
#define spectrum_video8 observed_video
#endif
#define mk61_app_get_services observed_services
#define spectrum_run observed_run
#define spectrum_sound_end observed_end
#define spectrum_load_z80 observed_load
#define SPECTRUM_HIL_AFTER_FILE() goto done
#define main ordinary_main
#include "../examples/portable-apps/SPECTRUM/main.c"
#undef main
#undef mk61_app_get_services
#undef spectrum_run
#undef spectrum_sound_end
#undef spectrum_load_z80
#undef spectrum_video8
#undef SPECTRUM_HIL_PACED
#ifndef S3_GAME_FRAMES
#define S3_GAME_FRAMES 600u
#endif
#ifndef S3_GAME_FOLDER
#define S3_GAME_FOLDER "/Spectrum"
#endif
#ifndef S3_GAME_SNAPSHOT
#define S3_GAME_SNAPSHOT "COSMIC.Z80"
#define S3_GAME_PALETTE "COSMIC.ULP"
#endif
static const mk61_app_services* original;
static mk61_app_services proxy;
static uint32_t mode,seen,first_us,last_us,first_cycles,last_cycles,first_frame,last_frame,start_frame;
static uint32_t previous_us,min_frame_us=UINT32_MAX,max_frame_us,late_frames,max_lag_us,run_epoch;
static bool first_set,last_set,measured,strict_fault,fault_reported;
static uint32_t raw_seen,first_run_us,last_run_us;
static bool first_run_set,boundary_mismatch;
#if !defined(S3_FORCE_LOCAL) || !S3_FORCE_LOCAL
static void (*original_recover)(void*);
#endif
static uint32_t clock_us(void){return *(volatile uint32_t*)(uintptr_t)0x40054028;}
static void report(const char* line){original->call(MK61_SERVICE_DEBUG_WRITE,strlen(line),0,0,(void*)line);}
static void capture_frame(spectrum* s,uint32_t now) {
    // This is the real MICROS value already sampled by production pacing,
    // not its target. Do not charge our own trace/return/branch work to the
    // emulated interval by sampling a second clock in observed_run().
    if(s->frames==seen)return;
    seen=s->frames;
    if(!first_set){first_set=true;first_us=now;first_cycles=(uint32_t)s->cpu.cyc;first_frame=s->frames;}
    else {
        const uint32_t delta=now-previous_us,period=spectrum_frame_cycles(s)*2/7;
        if(delta<min_frame_us)min_frame_us=delta;
        if(delta>max_frame_us)max_frame_us=delta;
        if(delta>period+1000)++late_frames;
        const int32_t lag=(int32_t)((now-first_us)-(s->frames-first_frame)*period);
        if(lag>0 && (uint32_t)lag>max_lag_us)max_lag_us=(uint32_t)lag;
        last_us=now;last_cycles=(uint32_t)s->cpu.cyc;last_frame=s->frames;last_set=true;
    }
    previous_us=now;
}
#if defined(S3_FRAME_TRACE) && S3_FRAME_TRACE
#ifndef S3_FRAME_TRACE_LIMIT
#define S3_FRAME_TRACE_LIMIT 64u
#endif
static struct { uint32_t target,now;int32_t ready;uint16_t frame,phase; } frame_trace[S3_FRAME_TRACE_LIMIT];
static unsigned frame_trace_count;
static bool first_slice_pending;
static uint32_t paced_count,paced_previous,paced_min=UINT32_MAX,paced_max,paced_late,paced_max_late,paced_resyncs;
static void observed_paced(spectrum* s,uint32_t target,uint32_t now,uint32_t ready,bool resynced) {
    capture_frame(s,now);
    first_slice_pending=true;
    if(paced_count++) {
        const uint32_t delta=now-paced_previous;
        if(delta<paced_min)paced_min=delta;
        if(delta>paced_max)paced_max=delta;
    }
    paced_previous=now;const uint32_t late=now-target;
    if(late>paced_max_late)paced_max_late=late;
    if(late>1000)++paced_late;
    if(resynced)++paced_resyncs;
    if(frame_trace_count<sizeof(frame_trace)/sizeof(frame_trace[0])) {
        const unsigned i=frame_trace_count++;
        frame_trace[i].target=target;frame_trace[i].now=now;frame_trace[i].ready=(int32_t)(ready-target);
        frame_trace[i].frame=(uint16_t)s->frames;frame_trace[i].phase=(uint16_t)s->frame_tstates;
    }
}
static void frame_report(void) {
    char line[144];
    mk61_app_snprintf(original,line,sizeof(line),"SP3 PACING frames=%lu min_us=%lu max_us=%lu late_1ms=%lu max_late_us=%lu resyncs=%lu\n",
        (unsigned long)paced_count,(unsigned long)(paced_count>1?paced_min:0),(unsigned long)paced_max,
        (unsigned long)paced_late,(unsigned long)paced_max_late,(unsigned long)paced_resyncs);report(line);
    for(unsigned i=0;i<frame_trace_count;++i) {
        mk61_app_snprintf(original,line,sizeof(line),"SP3 DEADLINE frame=%u target_us=%lu ready_us=%ld late_us=%lu phase=%u\n",
            frame_trace[i].frame,(unsigned long)(frame_trace[i].target-frame_trace[0].target),(long)frame_trace[i].ready,
            (unsigned long)(frame_trace[i].now-frame_trace[i].target),frame_trace[i].phase);report(line);
    }
}
#else
static void observed_paced(spectrum* s,uint32_t target,uint32_t now,uint32_t ready,bool resynced) {
    (void)target;(void)ready;(void)resynced;capture_frame(s,now);
}
#endif
#if defined(S3_PRODUCER_PROFILE) && S3_PRODUCER_PROFILE
enum { PROF_CPU,PROF_SERVICE,PROF_KEYS,PROF_BUFFER,PROF_COLOR,PROF_PRESENT,PROF_PALETTE,PROF_MICROS,PROF_VIDEO,PROF_OTHER,PROF_COUNT };
static struct { uint32_t calls,us,max; } profile[PROF_COUNT];
static uint32_t cpu_end,cpu_gap,cpu_first,cpu_cycles;
static bool inside_cpu;
static uint32_t cpu_service_calls,cpu_service_us;
#if defined(S3_PRODUCER_TRACE) && S3_PRODUCER_TRACE
static struct { uint16_t at,us,produced,consumed; } trace[192];
static unsigned trace_count;
static uint32_t trace_epoch;
#endif
static const mk61_app_api* original_api;
static mk61_app_api timed_api;
static void profile_add(unsigned slot,uint32_t begin) {
    const uint32_t us=clock_us()-begin;
    ++profile[slot].calls;profile[slot].us+=us;if(us>profile[slot].max)profile[slot].max=us;
}
static void profiled_service(void) {
    const uint32_t begin=clock_us();original_api->service();
    if(mode && !measured)profile_add(PROF_SERVICE,begin);
    if(inside_cpu){++cpu_service_calls;cpu_service_us+=clock_us()-begin;}
}
static void observed_video(const spectrum* s,uint8_t* bitmap,uint8_t* tiles) {
    const uint32_t begin=clock_us();spectrum_video8(s,bitmap,tiles);
    if(mode && !measured)profile_add(PROF_VIDEO,begin);
}
static void profile_report(void) {
    static const char*const names[]={"CPU","SERVICE","KEYS","BUFFER","COLOR","PRESENT","PALETTE","MICROS","VIDEO","OTHER"};
    char line[144];
    mk61_app_snprintf(original,line,sizeof(line),"SP3 PRODUCER wall_us=%lu cycles=%lu max_gap_us=%lu loads=%lu writebacks=%lu\n",
        (unsigned long)(clock_us()-cpu_first),(unsigned long)cpu_cycles,(unsigned long)cpu_gap,
        (unsigned long)(machine.memory?machine.memory->loads:0),(unsigned long)(machine.memory?machine.memory->writebacks:0));report(line);
    for(unsigned i=0;i<PROF_COUNT;++i) {
        mk61_app_snprintf(original,line,sizeof(line),"SP3 PROF %s calls=%lu us=%lu max_us=%lu\n",names[i],
            (unsigned long)profile[i].calls,(unsigned long)profile[i].us,(unsigned long)profile[i].max);report(line);
    }
    mk61_app_snprintf(original,line,sizeof(line),"SP3 CPU_SERVICE calls=%lu us=%lu\n",
        (unsigned long)cpu_service_calls,(unsigned long)cpu_service_us);report(line);
#if defined(S3_PRODUCER_TRACE) && S3_PRODUCER_TRACE
    for(unsigned i=0;i<trace_count;++i) {
        mk61_app_snprintf(original,line,sizeof(line),"SP3 TRACE at_us=%u cpu_us=%u produced=%u consumed=%u\n",
            trace[i].at,trace[i].us,trace[i].produced,trace[i].consumed);report(line);
    }
#endif
}
#endif
static void measurement(void) {
    if(measured)return;
    measured=true;
    const uint32_t frames=last_set?last_frame-first_frame:0;
    char line[144];mk61_app_snprintf(original,line,sizeof(line),
        "SP3 RESULT mode=%lu frames=%lu cycles=%lu us=%lu starved=%lu\n",
        (unsigned long)mode,(unsigned long)frames,
        (unsigned long)(last_set?last_cycles-first_cycles:0),(unsigned long)(last_set?last_us-first_us:0),
        (unsigned long)atomic_load(&machine.sound.starved));report(line);
    mk61_app_snprintf(original,line,sizeof(line),
        "SP3 TIMER_PAIR first=%lu last=%lu run_first=%lu run_last=%lu complete=%u same_cycles=%u\n",
        (unsigned long)first_us,(unsigned long)last_us,(unsigned long)first_run_us,(unsigned long)last_run_us,
        first_run_set && last_set && raw_seen==last_frame,!boundary_mismatch);report(line);
    mk61_app_snprintf(original,line,sizeof(line),
        "SP3 FRAME min_us=%lu max_us=%lu late_1ms=%lu max_lag_us=%lu strict_fault=%u\n",
        (unsigned long)(frames?min_frame_us:0),(unsigned long)max_frame_us,
        (unsigned long)late_frames,(unsigned long)max_lag_us,strict_fault);report(line);
#if defined(S3_PRODUCER_PROFILE) && S3_PRODUCER_PROFILE
    profile_report();
#endif
#if defined(S3_FRAME_TRACE) && S3_FRAME_TRACE
    frame_report();
#endif
}
#if !defined(S3_FORCE_LOCAL) || !S3_FORCE_LOCAL
static void strict_recover(void* context) {
    /* Core0, only after native consumers stop. Leave no producer waiting for
     * a remote ring that this diagnostic deliberately will not replace. */
    original_recover(context);
    spectrum* s=context;s->sound.asynchronous=false;spectrum_sound_clock(s,false);
    strict_fault=true;
}
#endif
static uint32_t observed_call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* payload) {
    if(op==MK61_SERVICE_FILE_BYTES && a==MK61_FILE_BYTES_PATH) {
        mk61_service_file_bytes* r=payload;const char path[]=S3_GAME_FOLDER "/" S3_GAME_SNAPSHOT;
        if(r->size<sizeof(path))return 0;
        memcpy(r->data,path,sizeof(path));return 1;
    }
#if defined(S3_FORCE_LOCAL) && S3_FORCE_LOCAL
    if(op==MK61_SERVICE_AUDIO_STREAM && (a==MK61_AUDIO_PSG_OPEN || a==MK61_AUDIO_PSG_CONFIG_OPEN))return 0;
#else
    if(op==MK61_SERVICE_AUDIO_STREAM && a==MK61_AUDIO_SYNTH_OPEN){strict_fault=true;return 0;}
    if(op==MK61_SERVICE_AUDIO_STREAM && (a==MK61_AUDIO_PSG_OPEN || a==MK61_AUDIO_PSG_CONFIG_OPEN)) {
        mk61_service_audio_psg* request=payload;
#ifdef S3_GAME_MODULE
        request->module_path=S3_GAME_MODULE;
#endif
        original_recover=request->recover;request->recover=strict_recover;
        a=a==MK61_AUDIO_PSG_CONFIG_OPEN?MK61_AUDIO_PSG_CONFIG_ONLY_OPEN:MK61_AUDIO_PSG_ONLY_OPEN;run_epoch=clock_us();
    }
#endif
    if(op==MK61_SERVICE_AUDIO_STREAM && a==MK61_AUDIO_CLOSE && mode) {
        measurement();
        /* USB sends64-byte packets; finish the short final packet before
         * AUDIO_CLOSE re-enumerates it while returning200MHz to125MHz. */
        mk61_api->delay_ms(25);
    }
#if defined(S3_PRODUCER_PROFILE) && S3_PRODUCER_PROFILE
    const uint32_t begin=clock_us();
#endif
    const uint32_t result=original->call(op,a,b,c,payload);
#if defined(S3_PRODUCER_PROFILE) && S3_PRODUCER_PROFILE
    if(mode && !measured) {
        const unsigned slot=op==MK61_SERVICE_KEYBOARD?PROF_KEYS:op==MK61_SERVICE_BUFFER?PROF_BUFFER:
            op==MK61_SERVICE_COLOR_DISPLAY?(a==MK61_COLOR_PRESENT?PROF_PRESENT:a==MK61_COLOR_PALETTE64?PROF_PALETTE:PROF_COLOR):
            op==MK61_SERVICE_MICROS?PROF_MICROS:PROF_OTHER;
        profile_add(slot,begin);
    }
#endif
    if(op==MK61_SERVICE_AUDIO_STREAM && (a==MK61_AUDIO_PSG_ONLY_OPEN || a==MK61_AUDIO_PSG_CONFIG_ONLY_OPEN) && result!=2)strict_fault=true;
    if(op==MK61_SERVICE_AUDIO_STREAM && (a==MK61_AUDIO_SYNTH_OPEN || a==MK61_AUDIO_PSG_OPEN || a==MK61_AUDIO_PSG_ONLY_OPEN ||
        a==MK61_AUDIO_PSG_CONFIG_OPEN || a==MK61_AUDIO_PSG_CONFIG_ONLY_OPEN) && result) {
        mode=result;raw_seen=seen=start_frame=machine.frames;first_us=last_us=0;
        first_run_us=last_run_us=0;first_run_set=boundary_mismatch=false;
        first_set=last_set=measured=false;run_epoch=clock_us();
        report(mode==2?"SP3 MODE=M3\n":"SP3 MODE=LOCAL\n");
    }
    if(op==MK61_SERVICE_KEYBOARD && a==MK61_SERVICE_KEY_BITMAP) {
#if defined(S3_FRAME_TRACE) && S3_FRAME_TRACE
        // Exercise the actual production loop: input scanning must not take
        // the first CPU/audio slice immediately after a pacing boundary.
        if(first_slice_pending)strict_fault=true;
#endif
        const uint32_t deadline=S3_GAME_FRAMES>1200u?S3_GAME_FRAMES*22000u+5000000u:35000000u;
        if(mode && (uint32_t)(clock_us()-run_epoch)>deadline)strict_fault=true;
        if(strict_fault && !fault_reported){report("SP3 FAULT remote_or_deadline\n");fault_reported=true;}
        if(strict_fault || (mode && machine.frames-start_frame>=S3_GAME_FRAMES))((uint8_t*)payload)[27/8]|=1u<<(27&7);
    }
    return result;
}
static const mk61_app_services* observed_services(const mk61_app_api* api,uint32_t caps) {
    original=mk61_app_get_services(api,caps);if(!original)return NULL;
    proxy=*original;proxy.call=observed_call;
#if defined(S3_FORCE_LOCAL) && S3_FORCE_LOCAL
    report("SP3 POLICY remote_only=0\n");
#else
    report("SP3 POLICY remote_only=1\n");
#endif
    return &proxy;
}
static uint32_t observed_run(spectrum* s,uint32_t cycles) {
#if defined(S3_FRAME_TRACE) && S3_FRAME_TRACE
    first_slice_pending=false;
#endif
    if(first_set && s->frames!=raw_seen) {
        raw_seen=s->frames;const uint32_t now=clock_us();
        if(!first_run_set){first_run_set=true;first_run_us=now;}
        last_run_us=now;
        if((uint32_t)s->cpu.cyc!=(last_set?last_cycles:first_cycles))boundary_mismatch=true;
    }
#if defined(S3_PRODUCER_PROFILE) && S3_PRODUCER_PROFILE
    const uint32_t begin=clock_us();
    if(!profile[PROF_CPU].calls) {
        cpu_first=begin;
#if defined(S3_PRODUCER_TRACE) && S3_PRODUCER_TRACE
        trace_epoch=atomic_load(&s->sound.produced);
#endif
    }
    else if(begin-cpu_end>cpu_gap)cpu_gap=begin-cpu_end;
    inside_cpu=true;const uint32_t result=spectrum_run(s,cycles);inside_cpu=false;
    cpu_cycles+=result;profile_add(PROF_CPU,begin);cpu_end=clock_us();
#if defined(S3_PRODUCER_TRACE) && S3_PRODUCER_TRACE
    if(trace_count<sizeof(trace)/sizeof(trace[0]) && begin-cpu_first<=UINT16_MAX) {
        trace[trace_count].at=(uint16_t)(begin-cpu_first);trace[trace_count].us=(uint16_t)(cpu_end-begin);
        trace[trace_count].produced=(uint16_t)((atomic_load(&s->sound.produced)-trace_epoch)/140);
        trace[trace_count].consumed=(uint16_t)((s->sound.time-trace_epoch)/140);++trace_count;
    }
#endif
    return result;
#else
    return spectrum_run(s,cycles);
#endif
}
static void observed_end(spectrum* s) {
    spectrum_sound_end(s);
    if(strict_fault && !measured){measurement();mk61_api->delay_ms(25);}
}
static enum spectrum_error observed_load(spectrum* s,const spectrum_source* source) {
    const enum spectrum_error error=spectrum_load_z80(s,source);if(error)return error;
#ifdef S3_SOUND_LAYOUT
    spectrum_sound_configure(s,S3_SOUND_CHIP,S3_SOUND_LAYOUT);
    char line[80];mk61_app_snprintf(original,line,sizeof(line),"SP3 SOUND chip=%s layout=%s\n",
        s->sound_chip==SPECTRUM_YM?"YM":"AY",s->sound_layout==SPECTRUM_ABC?"ABC":s->sound_layout==SPECTRUM_ACB?"ACB":"MONO");report(line);
#endif
#ifdef S3_GAME_PALETTE
    uint8_t palette[65];mk61_service_file_bytes r={S3_GAME_FOLDER "/" S3_GAME_PALETTE,palette,0,sizeof(palette)};
    if(!original->call(MK61_SERVICE_FILE_BYTES,MK61_FILE_BYTES_READ,0,sizeof(r),&r) || palette[0]>1)return SPECTRUM_IO;
    s->ulaplus_mode=palette[0];memcpy(s->ulaplus_palette,palette+1,64);
#endif
    return SPECTRUM_OK;
}
int main(void){
#if defined(S3_PRODUCER_PROFILE) && S3_PRODUCER_PROFILE
    original_api=mk61_api;timed_api=*mk61_api;timed_api.service=profiled_service;mk61_api=&timed_api;
#endif
    return run_app(0);
}
