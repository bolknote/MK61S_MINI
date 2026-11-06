/* Multi-game timing probe. Z80 fixtures keep a 65-byte ULAplus sidecar;
 * RGB565 palette and the complete screen are captured only after pause. */
#include "../examples/portable-apps/SPECTRUM/ui.h"
static void observed_window(spectrum_ui*,unsigned,unsigned,unsigned,const char*,const char* const*,unsigned,unsigned);
static void observed_begin(spectrum*,void(*)(void*),void*);
static void observed_end(spectrum*);
static uint32_t observed_run(spectrum*,uint32_t);
static enum spectrum_error observed_load(spectrum*,const spectrum_source*);
#define spectrum_ui_window observed_window
#define spectrum_sound_begin observed_begin
#define spectrum_sound_end observed_end
#define spectrum_run observed_run
#define spectrum_load_z80 observed_load
#include "../examples/portable-apps/SPECTRUM/main.c"
#undef spectrum_ui_window
#undef spectrum_sound_begin
#undef spectrum_sound_end
#undef spectrum_run
#undef spectrum_load_z80
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
    mk61_app_snprintf(services,line,sizeof(line),"SPMENU %s %u/%u xip=%u [%s]\n",
        title,selected,count,mapped_roms,count?labels[selected<count?selected:0]:"");report(line);
    spectrum_ui_window(u,x,y,width,title,labels,count,selected);
}
/* Observe the first CPU call after each frame's pacing wait. Both endpoints
 * stay inside active emulation, excluding audio/UI start and drain barriers. */
static uint32_t observed_run(spectrum* s,uint32_t cycles) {
#ifndef SPECTRUM_HIL_EXTERNAL_PACED
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
#endif
#ifdef SPECTRUM_HIL_MEASURE_RUN
    return SPECTRUM_HIL_MEASURE_RUN(s,cycles);
#else
    return spectrum_run(s,cycles);
#endif
}
static void observed_begin(spectrum* s,void(*yield)(void*),void* context) {
    memset(&steady,0,sizeof(steady));steady.seen_frame=s->frames;
    spectrum_sound_begin(s,yield,context);started_us=timer();started_cycles=(uint32_t)s->cpu.cyc;started_frames=s->frames;
#ifdef SPECTRUM_HIL_BEGIN
    SPECTRUM_HIL_BEGIN();
#endif
    report("SPRUN\n");
}
static void observed_end(spectrum* s) {
    const uint32_t elapsed=timer()-started_us;char line[128];
    mk61_app_snprintf(services,line,sizeof(line),"SPTIME frames=%lu cycles=%lu wall=%lu xip=%u starved=%lu\n",
        (unsigned long)(s->frames-started_frames),(unsigned long)((uint32_t)s->cpu.cyc-started_cycles),
        (unsigned long)elapsed,mapped_roms,(unsigned long)atomic_load(&s->sound.starved));report(line);
    mk61_app_snprintf(services,line,sizeof(line),"SPSTEADY frames=%lu cycles=%lu wall=%lu phase=%lu/%lu starved=%lu\n",
        (unsigned long)steady.frames,(unsigned long)steady.cycles,
        (unsigned long)(
#ifdef SPECTRUM_HIL_STEADY_WALL
            SPECTRUM_HIL_STEADY_WALL()
#else
            steady.last_us?steady.last_us-steady.first_us:0
#endif
        ),
        (unsigned long)steady.first_phase,(unsigned long)steady.phase,(unsigned long)steady.starved);report(line);
#ifdef SPECTRUM_HIL_END
    SPECTRUM_HIL_END();
#endif
#ifdef SPECTRUM_HIL_PROFILE_END
    SPECTRUM_HIL_PROFILE_END();
#endif
    spectrum_sound_end(s);report("SPBEGIN GAME\n");
    mk61_service_framebuffer buffer={0};
    if(services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(buffer),0,&buffer)) {
        spectrum_video8(s,buffer.pixels,buffer.pixels+6144);
        for(unsigned i=0;i<64;++i) {
            const unsigned c=spectrum_palette(s,i);
            buffer.pixels[7680+2*i]=(uint8_t)c;buffer.pixels[7681+2*i]=(uint8_t)(c>>8);
        }
        char hex[77];memcpy(hex,"SPDATA ",7);hex[11]=' ';
        static const char digits[]="0123456789ABCDEF";
        for(unsigned at=0;at<7808;at+=32) {
            for(unsigned j=0;j<4;++j) hex[7+j]=digits[(at>>(12-4*j))&15];
            for(unsigned j=0;j<32;++j) {
                const unsigned c=buffer.pixels[at+j];hex[12+2*j]=digits[c>>4];hex[13+2*j]=digits[c&15];
            }
            hex[76]='\n';services->call(MK61_SERVICE_DEBUG_WRITE,77,0,0,hex);
        }
    }

    report("SPEND\n");
}

static enum spectrum_error observed_load(spectrum* s,const spectrum_source* source) {
    if(s->disk.mode) return SPECTRUM_UNSUPPORTED;
    enum spectrum_error error=spectrum_load_z80(s,source);
    if(error) return error;
    const unsigned n=(unsigned)strlen(snapshot_path);
    if(n<4) return SPECTRUM_FORMAT;
    char saved[3];memcpy(saved,snapshot_path+n-3,3);memcpy(snapshot_path+n-3,"ULP",3);
    uint8_t state[65];
    const bool ok=file_call(MK61_FILE_BYTES_READ,snapshot_path,state,0,sizeof(state))!=0;
    memcpy(snapshot_path+n-3,saved,3);
    if(!ok) return SPECTRUM_IO;
    if(state[0]>1) return SPECTRUM_FORMAT;
    s->ulaplus_mode=state[0];memcpy(s->ulaplus_palette,state+1,64);
    char line[40];mk61_app_snprintf(services,line,sizeof(line),"SPPAL mode=%u\n",state[0]);report(line);
    return SPECTRUM_OK;
}
