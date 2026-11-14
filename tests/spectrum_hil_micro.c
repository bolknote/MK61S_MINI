/* Minimal RP2040 speed probe for the tightest SRAM layouts. */
#include "../examples/portable-apps/SPECTRUM/ui.h"
static bool observed_present(spectrum_ui*);
static void observed_window(spectrum_ui*,unsigned,unsigned,unsigned,const char*,const char* const*,unsigned,unsigned);
static void observed_begin(spectrum*,void(*)(void*),void*);
static void observed_end(spectrum*);
#define spectrum_ui_present observed_present
#define spectrum_ui_window observed_window
#define spectrum_sound_begin observed_begin
#define spectrum_sound_end observed_end
#include "../examples/portable-apps/SPECTRUM/main.c"
#undef spectrum_ui_present
#undef spectrum_ui_window
#undef spectrum_sound_begin
#undef spectrum_sound_end
static uint32_t started_us,started_cycles,started_frames;
static uint32_t timer(void) { return *(volatile uint32_t*)0x40054028; }
static void report(const char* text) { services->call(MK61_SERVICE_DEBUG_WRITE,strlen(text),0,0,(void*)text); }
#ifdef SPECTRUM_HIL_DUMP_GAME
static void dump(const uint8_t* data,unsigned n,unsigned offset) {
    static const char hex[]="0123456789ABCDEF";char line[128];
    for(unsigned at=0;at<n;at+=48) {
        const unsigned size=n-at<48?n-at:48;
        unsigned used=(unsigned)mk61_app_snprintf(services,line,sizeof(line),"SPDATA %u ",offset+at);
        for(unsigned i=0;i<size;++i) { line[used++]=hex[data[at+i]>>4];line[used++]=hex[data[at+i]&15]; }
        line[used++]='\n';line[used]=0;report(line);
    }
}
#endif
static void observed_window(spectrum_ui* u,unsigned x,unsigned y,unsigned width,const char* title,
                            const char* const* labels,unsigned count,unsigned selected) {
    char line[112];
    mk61_app_snprintf(services,line,sizeof(line),"SPMENU %s %u/%u rom_psram=%u [%s]\n",
        title,selected,count,bank_memory.paged_rom,count?labels[selected<count?selected:0]:"");report(line);
    spectrum_ui_window(u,x,y,width,title,labels,count,selected);
}
static bool observed_present(spectrum_ui* u) {
    if(!spectrum_ui_present(u)) return false;
    report("SPBEGIN UI\nSPEND\n");return true;
}
static void observed_begin(spectrum* s,void(*yield)(void*),void* context) {
    spectrum_sound_begin(s,yield,context);started_us=timer();started_cycles=(uint32_t)s->cpu.cyc;started_frames=s->frames;
    report("SPRUN\n");
}
static void observed_end(spectrum* s) {
    const uint32_t elapsed=timer()-started_us;char line[128];
    mk61_app_snprintf(services,line,sizeof(line),"SPTIME frames=%lu cycles=%lu wall=%lu rom_psram=%u starved=%lu\n",
        (unsigned long)(s->frames-started_frames),(unsigned long)((uint32_t)s->cpu.cyc-started_cycles),
        (unsigned long)elapsed,bank_memory.paged_rom,(unsigned long)atomic_load(&s->sound.starved));report(line);
    spectrum_sound_end(s);report("SPBEGIN GAME\n");
#ifdef SPECTRUM_HIL_DUMP_GAME
    mk61_service_framebuffer buffer={0};
    if(services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(buffer),0,&buffer)) {
        spectrum_video8(s,buffer.pixels,buffer.pixels+6144);
        uint16_t palette[64];for(unsigned i=0;i<64;++i) palette[i]=spectrum_palette(s,i);
        dump(buffer.pixels,7680,0);dump((const uint8_t*)palette,128,7680);
    }
#endif
    report("SPEND\n");
}
