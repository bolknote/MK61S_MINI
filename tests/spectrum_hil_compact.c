/* Compact timing probe. Menu records validate initialization; a static
 * game HUD signature verifies the scene without a full framebuffer dump. */
#include "../examples/portable-apps/SPECTRUM/ui.h"
static void observed_window(spectrum_ui*,unsigned,unsigned,unsigned,const char*,const char* const*,unsigned,unsigned);
static void observed_begin(spectrum*,void(*)(void*),void*);
static void observed_end(spectrum*);
#define spectrum_ui_window observed_window
#define spectrum_sound_begin observed_begin
#define spectrum_sound_end observed_end
#include "../examples/portable-apps/SPECTRUM/main.c"
#undef spectrum_ui_window
#undef spectrum_sound_begin
#undef spectrum_sound_end
static uint32_t started_us,started_cycles,started_frames;
static uint32_t timer(void) { return *(volatile uint32_t*)0x40054028; }
static void report(const char* text) { services->call(MK61_SERVICE_DEBUG_WRITE,strlen(text),0,0,(void*)text); }

static void observed_window(spectrum_ui* u,unsigned x,unsigned y,unsigned width,const char* title,
                            const char* const* labels,unsigned count,unsigned selected) {
    char line[112];
    mk61_app_snprintf(services,line,sizeof(line),"SPMENU %s %u/%u xip=%u [%s]\n",
        title,selected,count,mapped_roms,count?labels[selected<count?selected:0]:"");report(line);
    spectrum_ui_window(u,x,y,width,title,labels,count,selected);
}
static void observed_begin(spectrum* s,void(*yield)(void*),void* context) {
    spectrum_sound_begin(s,yield,context);started_us=timer();started_cycles=(uint32_t)s->cpu.cyc;started_frames=s->frames;
    report("SPRUN\n");
}
static void observed_end(spectrum* s) {
    const uint32_t elapsed=timer()-started_us;char line[128];
    mk61_app_snprintf(services,line,sizeof(line),"SPTIME frames=%lu cycles=%lu wall=%lu xip=%u starved=%lu\n",
        (unsigned long)(s->frames-started_frames),(unsigned long)((uint32_t)s->cpu.cyc-started_cycles),
        (unsigned long)elapsed,mapped_roms,(unsigned long)atomic_load(&s->sound.starved));report(line);
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
