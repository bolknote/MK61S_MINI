/* Small RP2040 timing probe. Build with Spectrum SOURCES except main.c.
 * Renderer/CPU/audio are unchanged; timings exclude OSD and serial output.
 * Core-1 counters are reset before AUDIO_OPEN and read only after CLOSE. */
#include "../examples/portable-apps/SPECTRUM/ui.h"
static const mk61_app_services* speed_services(const mk61_app_api*,uint32_t);
static bool speed_present(spectrum_ui*);
static void speed_window(spectrum_ui*,unsigned,unsigned,unsigned,const char*,const char* const*,unsigned,unsigned);
static uint32_t speed_run(spectrum*,uint32_t);
static void speed_end(spectrum*);
#define mk61_app_get_services speed_services
#define spectrum_ui_present speed_present
#define spectrum_ui_window speed_window
#define spectrum_run speed_run
#define spectrum_sound_end speed_end
#include "../examples/portable-apps/SPECTRUM/main.c"
#undef mk61_app_get_services
#undef spectrum_ui_present
#undef spectrum_ui_window
#undef spectrum_run
#undef spectrum_sound_end
static const mk61_app_services* original;
static mk61_app_services proxy;
static struct { uint32_t start,cycles,frames,run,mem,samples,audio,max,loads,writebacks;bool active; } stats;
static uint32_t timer(void) { return *(volatile uint32_t*)0x40054028; }
static void report(const char* text) { original->call(MK61_SERVICE_DEBUG_WRITE,strlen(text),0,0,(void*)text); }
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
static uint32_t sample(void* context) {
    const uint32_t start=timer(),value=spectrum_sound_render(context),elapsed=timer()-start;
    ++stats.samples;stats.audio+=elapsed;if(elapsed>stats.max) stats.max=elapsed;return value;
}
static uint32_t call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* payload) {
    if(op==MK61_SERVICE_AUDIO_STREAM && a==MK61_AUDIO_SYNTH_OPEN) {
        memset(&stats,0,sizeof(stats));stats.active=true;stats.start=timer();
        stats.frames=machine.frames;stats.cycles=(uint32_t)machine.cpu.cyc;
        stats.loads=bank_memory.loads;stats.writebacks=bank_memory.writebacks;
        mk61_service_audio_synth request=*(mk61_service_audio_synth*)payload;request.sample=sample;
        return original->call(op,a,b,c,&request);
    }
    const uint32_t before=op==MK61_SERVICE_BUFFER?timer():0;
    const uint32_t value=original->call(op,a,b,c,payload);
    if(stats.active && op==MK61_SERVICE_BUFFER) stats.mem+=timer()-before;
    return value;
}
static const mk61_app_services* speed_services(const mk61_app_api* api,uint32_t caps) {
    original=mk61_app_get_services(api,caps);if(!original) return NULL;
    proxy=*original;proxy.call=call;return &proxy;
}
static bool speed_present(spectrum_ui* ui) {
    if(!spectrum_ui_present(ui)) return false;
    report("SPBEGIN UI\nSPEND\n");return true;
}
static void speed_window(spectrum_ui* u,unsigned x,unsigned y,unsigned width,const char* title,
                         const char* const* labels,unsigned count,unsigned selected) {
    char line[112];
    mk61_app_snprintf(services,line,sizeof(line),"SPMENU %s %u/%u xip=%u [%s]\n",
        title,selected,count,mapped_roms,count?labels[selected<count?selected:0]:"");report(line);
    spectrum_ui_window(u,x,y,width,title,labels,count,selected);
}
static uint32_t speed_run(spectrum* s,uint32_t cycles) {
    if(!stats.run) report("SPRUN\n");
    const uint32_t before=timer(),value=spectrum_run(s,cycles);stats.run+=timer()-before;return value;
}
static void speed_end(spectrum* s) {
    const uint32_t wall=timer()-stats.start;stats.active=false;char line[128];
    mk61_app_snprintf(services,line,sizeof(line),"SPTIME frames=%lu cycles=%lu wall=%lu xip=%u starved=%lu\n",
        (unsigned long)(s->frames-stats.frames),(unsigned long)((uint32_t)s->cpu.cyc-stats.cycles),
        (unsigned long)wall,mapped_roms,(unsigned long)atomic_load(&s->sound.starved));report(line);
    mk61_app_snprintf(services,line,sizeof(line),"SPIO run=%lu mem=%lu\n",
        (unsigned long)stats.run,(unsigned long)stats.mem);report(line);
    mk61_app_snprintf(services,line,sizeof(line),"SPAUDIO count=%lu busy=%lu max=%lu loads=%lu wb=%lu\n",
        (unsigned long)stats.samples,(unsigned long)stats.audio,(unsigned long)stats.max,
        (unsigned long)(bank_memory.loads-stats.loads),(unsigned long)(bank_memory.writebacks-stats.writebacks));report(line);
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
