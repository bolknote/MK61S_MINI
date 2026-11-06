/* Observe every pacing boundary, with a fixed 100-frame warmup and ten
 * consecutive 300-frame windows. No UART/USB report inside measured windows. */
#include "../examples/portable-apps/SPECTRUM/ui.h"
enum { PACED_WARMUP=100, PACED_WINDOW=300, PACED_WINDOWS=10 };
typedef struct {
    uint32_t frames,cycles,wall,first_phase,last_phase,first_late,last_late;
} paced_window;
typedef struct {
    paced_window windows[PACED_WINDOWS];
    uint32_t first_late,window_us,window_cycles,window_frames,window_phase,window_late;
    uint32_t sum_wait,min_wait,max_late,late_frames,resyncs,count;
    bool started,done;
} paced_trace;
static paced_trace* trace;
static void paced_begin(void);
static void paced_end(void);
static void paced_boundary(spectrum*,uint32_t,uint32_t,uint32_t,bool);
#define SPECTRUM_HIL_EXTERNAL_PACED
#define SPECTRUM_HIL_SNAPSHOT_ONLY
#define SPECTRUM_HIL_PACED paced_boundary
#define SPECTRUM_HIL_BEGIN paced_begin
#define SPECTRUM_HIL_END paced_end
#define SPECTRUM_HIL_STEADY_WALL() (trace->started?steady.last_us-steady.first_us:0)
#ifndef SPECTRUM_HIL_PACED_SELF_TEST
#define main paced_app_main
#endif
#include "spectrum_hil_games.c"
#ifndef SPECTRUM_HIL_PACED_SELF_TEST
#undef main
int main(void) { paced_trace state;trace=&state;return paced_app_main(); }
#endif

static void paced_begin(void) {
    memset(trace,0,sizeof(*trace));trace->min_wait=UINT32_MAX;
}
static void paced_boundary(spectrum* s,uint32_t target,uint32_t now,uint32_t ready,bool resynced) {
    if(trace->done || s->frames<PACED_WARMUP) return;
    const uint32_t late=now-target;
    const uint32_t wait=(int32_t)(target-ready)>0?now-ready:0;
    if(!trace->started) {
        trace->started=true;
        steady.first_us=now;steady.first_cycles=(uint32_t)s->cpu.cyc;steady.first_frames=s->frames;
        steady.first_phase=s->frame_tstates;steady.first_starved=(uint32_t)atomic_load(&s->sound.starved);
        trace->first_late=late;trace->window_us=now;trace->window_cycles=(uint32_t)s->cpu.cyc;
        trace->window_frames=s->frames;trace->window_phase=s->frame_tstates;trace->window_late=late;
        steady.last_us=now;steady.phase=s->frame_tstates;
        trace->max_late=late;trace->resyncs=resynced?1:0;
        return;
    }
    steady.last_us=now;steady.cycles=(uint32_t)s->cpu.cyc-steady.first_cycles;
    steady.frames=s->frames-steady.first_frames;steady.phase=s->frame_tstates;
    steady.starved=(uint32_t)atomic_load(&s->sound.starved)-steady.first_starved;
    trace->sum_wait+=wait;if(wait<trace->min_wait)trace->min_wait=wait;
    if(late>trace->max_late)trace->max_late=late;
    if((int32_t)(ready-target)>0)++trace->late_frames;
    if(resynced)++trace->resyncs;
    if(s->frames-trace->window_frames==PACED_WINDOW) {
        paced_window* w=&trace->windows[trace->count++];
        *w=(paced_window){s->frames-trace->window_frames,(uint32_t)s->cpu.cyc-trace->window_cycles,
            now-trace->window_us,trace->window_phase,s->frame_tstates,trace->window_late,late};
        trace->window_us=now;trace->window_cycles=(uint32_t)s->cpu.cyc;trace->window_frames=s->frames;
        trace->window_phase=s->frame_tstates;trace->window_late=late;
        if(trace->count==PACED_WINDOWS) { trace->done=true;report("SPPACING_DONE\n"); }
    }
}
static void paced_end(void) {
    char line[176];
    for(unsigned i=0;i<trace->count;++i) {
        const paced_window* w=&trace->windows[i];
        mk61_app_snprintf(services,line,sizeof(line),"SPWIN n=%u frames=%lu cycles=%lu wall=%lu phase=%lu/%lu late=%lu/%lu\n",i,
            (unsigned long)w->frames,(unsigned long)w->cycles,(unsigned long)w->wall,
            (unsigned long)w->first_phase,(unsigned long)w->last_phase,
            (unsigned long)w->first_late,(unsigned long)w->last_late);report(line);
    }
    mk61_app_snprintf(services,line,sizeof(line),"SPPACING count=%lu firstlate=%lu maxlate=%lu wait=%lu minwait=%lu lateframes=%lu resets=%lu done=%u\n",
        (unsigned long)trace->count,(unsigned long)trace->first_late,(unsigned long)trace->max_late,
        (unsigned long)trace->sum_wait,(unsigned long)trace->min_wait,
        (unsigned long)trace->late_frames,(unsigned long)trace->resyncs,trace->done);report(line);
}
