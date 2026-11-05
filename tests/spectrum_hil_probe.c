#include "../examples/portable-apps/SPECTRUM/ui.h"
/* RP2040-only diagnostic APP; production has no timers or dumps.
 * Build with build_portable_app.py, --name SPTIME, this file in place of
 * main.c and the remaining build_spectrum_app.SOURCES. Keep beside ROMs.
 * Pause prints SPTIME/SPIO/SPRAM followed by framebuffer hex. Timings cover
 * only emulation, excluding OSD dumps; run includes nested memory/file I/O.
 * RP2040 SDK TIMER_BASE+TIMER_TIMERAWL_OFFSET = 0x40054028, in microseconds.
 */
static const mk61_app_services* observed_services(const mk61_app_api*,uint32_t);
#define mk61_app_get_services observed_services
static bool observed_present(spectrum_ui*);
static uint32_t observed_run(spectrum*,uint32_t);
static void observed_end(spectrum*);
#define spectrum_ui_present observed_present
#define spectrum_run observed_run
#define spectrum_sound_end observed_end
#include "../examples/portable-apps/SPECTRUM/main.c"
#undef mk61_app_get_services
#undef spectrum_ui_present
#undef spectrum_run
#undef spectrum_sound_end
static void report(const char* text) { services->call(MK61_SERVICE_DEBUG_WRITE,strlen(text),0,0,(void*)text); }
#ifndef SPECTRUM_HIL_TIMING_ONLY
static void bytes(const uint8_t* data,unsigned n,unsigned offset) {
 static const char hex[]="0123456789ABCDEF";char line[128];
 for(unsigned at=0;at<n;at+=48) {
  unsigned size=n-at<48?n-at:48;
  unsigned used=(unsigned)mk61_app_snprintf(services,line,sizeof(line),"SPDATA %u ",offset+at);
  for(unsigned i=0;i<size;++i) { line[used++]=hex[data[at+i]>>4];line[used++]=hex[data[at+i]&15]; }
  line[used++]='\n';line[used]=0;report(line);
 }
}
#endif
static bool observed_present(spectrum_ui* u) {
 bool ok=spectrum_ui_present(u);if(!ok)return false;
 report("SPBEGIN UI\n");
#ifndef SPECTRUM_HIL_TIMING_ONLY
 bytes(u->frame.pixels,8192,0);bytes(u->frame.tiles,1024,8192);bytes((const uint8_t*)u->frame.palette,32,9216);
#endif
 report("SPEND\n");return true;
}
static uint32_t ticks(void) { return *(volatile uint32_t*)0x40054028; }
static const mk61_app_services* original;
static mk61_app_services proxy;
static struct {
 uint32_t start,frame,cycles,run,mem,mem_run,file,file_run,keyboard,color,read,write,loads,wb;
 bool running,in_run;
} profile;
static uint32_t profile_call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* payload) {
 if(op==MK61_SERVICE_AUDIO_STREAM && a==MK61_AUDIO_SYNTH_OPEN) {
  memset(&profile,0,sizeof(profile));profile.running=true;profile.start=ticks();
  profile.frame=machine.frames;profile.cycles=(uint32_t)machine.cpu.cyc;
  profile.loads=bank_memory.loads;profile.wb=bank_memory.writebacks;
 }
 const uint32_t before=ticks(),result=original->call(op,a,b,c,payload),elapsed=ticks()-before;
 if(profile.running) {
  if(op==MK61_SERVICE_BUFFER) {
   profile.mem+=elapsed;if(profile.in_run) profile.mem_run+=elapsed;
   if(payload) {
    const mk61_service_buffer* r=payload;
    if(a==MK61_BUFFER_READ) profile.read+=r->size;
    else if(a==MK61_BUFFER_WRITE) profile.write+=r->size;
   }
  } else if(op==MK61_SERVICE_FILE_BYTES) { profile.file+=elapsed;if(profile.in_run) profile.file_run+=elapsed; }
  else if(op==MK61_SERVICE_KEYBOARD) profile.keyboard+=elapsed;
  else if(op==MK61_SERVICE_COLOR_DISPLAY) profile.color+=elapsed;
 }
 return result;
}
static const mk61_app_services* observed_services(const mk61_app_api* api,uint32_t caps) {
 original=mk61_app_get_services(api,caps);if(!original) return NULL;
 proxy=*original;proxy.call=profile_call;return &proxy;
}
static uint32_t observed_run(spectrum* s,uint32_t cycles) {
 if(!profile.run) report("SPRUN\n");
 const uint32_t before=ticks();profile.in_run=true;const uint32_t result=spectrum_run(s,cycles);
 profile.in_run=false;profile.run+=ticks()-before;return result;
}
static void observed_end(spectrum* s) {
 const uint32_t wall=ticks()-profile.start;profile.running=false;char line[128];
 mk61_app_snprintf(services,line,sizeof(line),"SPTIME frames=%lu cycles=%lu wall=%lu run=%lu\n",
  (unsigned long)(s->frames-profile.frame),(unsigned long)((uint32_t)s->cpu.cyc-profile.cycles),(unsigned long)wall,(unsigned long)profile.run);report(line);
 mk61_app_snprintf(services,line,sizeof(line),"SPIO mem=%lu mem_run=%lu file=%lu file_run=%lu key=%lu color=%lu\n",
  (unsigned long)profile.mem,(unsigned long)profile.mem_run,(unsigned long)profile.file,(unsigned long)profile.file_run,(unsigned long)profile.keyboard,(unsigned long)profile.color);report(line);
 mk61_app_snprintf(services,line,sizeof(line),"SPRAM loads=%lu wb=%lu read=%lu write=%lu starved=%lu pwm=%08lX\n",
  (unsigned long)(bank_memory.loads-profile.loads),(unsigned long)(bank_memory.writebacks-profile.wb),(unsigned long)profile.read,(unsigned long)profile.write,(unsigned long)atomic_load(&s->sound.starved),(unsigned long)*(volatile uint32_t*)0x40050070);report(line);
 spectrum_sound_end(s);
#ifndef SPECTRUM_HIL_TIMING_ONLY
 mk61_service_framebuffer b={0};
 if(!services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(b),0,&b))return;
 spectrum_video8(s,b.pixels,b.pixels+6144);
 uint16_t palette[64];for(unsigned i=0;i<64;++i)palette[i]=spectrum_palette(s,i);
 report("SPBEGIN GAME\n");bytes(b.pixels,7680,0);bytes((const uint8_t*)palette,128,7680);report("SPEND\n");
#else
 report("SPBEGIN GAME\nSPEND\n");
#endif
}
