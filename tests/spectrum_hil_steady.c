/* Compact timing probe. Menu records validate initialization; a static
 * game HUD signature verifies the scene without a full framebuffer dump. */
#include "../examples/portable-apps/SPECTRUM/ui.h"
static void observed_window(spectrum_ui*,unsigned,unsigned,unsigned,const char*,const char* const*,unsigned,unsigned);
static void observed_begin(spectrum*,void(*)(void*),void*);
static void observed_end(spectrum*);
static uint32_t observed_run(spectrum*,uint32_t);
#define spectrum_ui_window observed_window
#define spectrum_sound_begin observed_begin
#define spectrum_sound_end observed_end
#define spectrum_run observed_run
#include "../examples/portable-apps/SPECTRUM/main.c"
#undef spectrum_ui_window
#undef spectrum_sound_begin
#undef spectrum_sound_end
#undef spectrum_run
static uint32_t started_us,started_cycles,started_frames;
static struct {
    uint32_t first_us,last_us,first_cycles,cycles,first_frames,frames;
    uint32_t first_phase,phase,seen_frame,first_starved,starved;
} steady;
#ifndef SPECTRUM_HIL_CLOCK
#define SPECTRUM_HIL_CLOCK() (*(volatile uint32_t*)0x40054028)
#endif
static uint32_t timer(void) { return SPECTRUM_HIL_CLOCK(); }
static void report(const char* text) { services->call(MK61_SERVICE_DEBUG_WRITE,strlen(text),0,0,(void*)text); }

static void observed_window(spectrum_ui* u,unsigned x,unsigned y,unsigned width,const char* title,
                            const char* const* labels,unsigned count,unsigned selected) {
    char line[112];
    mk61_app_snprintf(services,line,sizeof(line),"SPMENU %s %u/%u rom_psram=%u [%s]\n",
        title,selected,count,bank_memory.paged_rom,count?labels[selected<count?selected:0]:"");report(line);
    spectrum_ui_window(u,x,y,width,title,labels,count,selected);
}
/* Observe the first CPU call after each frame's pacing wait. Both endpoints
 * stay inside active emulation, excluding audio/UI start and drain barriers. */
static uint32_t observed_run(spectrum* s,uint32_t cycles) {
    if(s->frames!=steady.seen_frame) {
        steady.seen_frame=s->frames;const uint32_t now=timer();
        const uint32_t starved=(uint32_t)atomic_load(&s->sound.starved);
        if(!steady.first_us) {
            steady.first_us=now;steady.first_cycles=(uint32_t)s->cpu.cyc;
            steady.first_frames=s->frames;steady.first_phase=s->frame_tstates;steady.first_starved=starved;
        } else {
            steady.last_us=now;steady.cycles=(uint32_t)s->cpu.cyc-steady.first_cycles;
            steady.frames=s->frames-steady.first_frames;steady.phase=s->frame_tstates;steady.starved=starved-steady.first_starved;
        }
    }
    return spectrum_run(s,cycles);
}
static void observed_begin(spectrum* s,void(*yield)(void*),void* context) {
    memset(&steady,0,sizeof(steady));steady.seen_frame=s->frames;
    spectrum_sound_begin(s,yield,context);started_us=timer();started_cycles=(uint32_t)s->cpu.cyc;started_frames=s->frames;
    report("SPRUN\n");
}
static void observed_end(spectrum* s) {
    const uint32_t elapsed=timer()-started_us;char line[128];
    mk61_app_snprintf(services,line,sizeof(line),"SPTIME frames=%lu cycles=%lu wall=%lu rom_psram=%u starved=%lu\n",
        (unsigned long)(s->frames-started_frames),(unsigned long)((uint32_t)s->cpu.cyc-started_cycles),
        (unsigned long)elapsed,bank_memory.paged_rom,(unsigned long)atomic_load(&s->sound.starved));report(line);
    mk61_app_snprintf(services,line,sizeof(line),"SPSTEADY frames=%lu cycles=%lu wall=%lu phase=%lu/%lu starved=%lu\n",
        (unsigned long)steady.frames,(unsigned long)steady.cycles,
        (unsigned long)(steady.last_us?steady.last_us-steady.first_us:0),
        (unsigned long)steady.first_phase,(unsigned long)steady.phase,(unsigned long)steady.starved);report(line);
    spectrum_sound_end(s);report("SPBEGIN GAME\n");
    mk61_service_framebuffer buffer={0};
    if(services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(buffer),0,&buffer)) {
        spectrum_video8(s,buffer.pixels,buffer.pixels+6144);
        uint32_t hash=2166136261U;
        /* Static DIZZY HUD glyphs, 112x16 at x=64,y=0. */
        for(unsigned row=0;row<16;++row) for(unsigned col=8;col<22;++col)
            hash=(hash^buffer.pixels[row*32+col])*16777619U;
        mk61_app_snprintf(services,line,sizeof(line),"SPVIDEO sig=%08lX pc=%04X\n",(unsigned long)hash,s->cpu.pc);report(line);
    }

    report("SPEND\n");
}
