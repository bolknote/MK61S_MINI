#include "../cosmic-display/candidate/examples/portable-apps/SPECTRUM/spectrum.h"
static uint32_t audited_render(void*);
#define spectrum_sound_render audited_render
#define main dump_main
#include "frame_dump_driver.c"
#undef main
#undef spectrum_sound_render
#include <inttypes.h>
typedef struct {uint32_t samples,nonzero;int32_t minimum,maximum;uint64_t squared;uint32_t pwm_noncenter[11];} levels;
static levels windows[10];
static uint32_t audited_render(void* raw) {
    spectrum* m=raw;const uint32_t value=spectrum_sound_render(raw);
    if(m->sound.time<100*71680UL || m->sound.time>=3100*71680UL)return value;
    levels* a=&windows[(m->sound.time/71680-100)/300];const int32_t sample=(int16_t)value;
    ++a->samples;a->nonzero+=sample!=0;a->squared+=(uint64_t)(sample*sample);
    if(sample<a->minimum)a->minimum=sample;if(sample>a->maximum)a->maximum=sample;
    for(unsigned master=0;master<=10;++master)a->pwm_noncenter[master]+=(sample*(int32_t)(master*100))/512000!=0;
    return value;
}
int main(int argc,char** argv) {
    assert(argc==3);for(unsigned i=0;i<10;++i) {windows[i].minimum=32767;windows[i].maximum=-32768;}
    char* args[]={argv[0],argv[1],argv[2],"/dev/null",NULL};dump_main(4,args);
    puts("HOST PCM levels: complete512T, fixedP100..199; current nativePWM formula/gain for master0..10; not physical capture");
    for(unsigned i=0;i<10;++i) {
        levels* a=&windows[i];printf("LEVEL window=%u samples=%u nonzero=%u min=%d max=%d squared=%" PRIu64 " pwm_noncenter=",i,a->samples,a->nonzero,a->minimum,a->maximum,a->squared);
        for(unsigned v=0;v<=10;++v)printf("%s%u",v?",":"",a->pwm_noncenter[v]);puts("");
    }
}
