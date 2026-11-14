#include "mk61_app.h"
#include <stdatomic.h>
#include <string.h>
#ifndef SPAUD_READ32
#define SPAUD_READ32(a) (*(volatile uint32_t*)(uintptr_t)(a))
#endif
#define PWM5_CSR 0x40050064UL
#define PWM5_CC 0x40050070UL
#define GPIO26_CTRL 0x400140D4UL
#define GPIO27_CTRL 0x400140DCUL
typedef struct {_Atomic uint32_t calls;} tone_state;
typedef struct {uint32_t count,min_l,max_l,min_r,max_r;} pwm_phase;
enum {LEFT_BEGIN=50000,RIGHT_BEGIN=100000,BOTH_BEGIN=150000,SILENCE_BEGIN=200000,TOTAL_SAMPLES=212500};
static uint32_t tone(void* raw) {
    tone_state* q=raw;const uint32_t n=atomic_load_explicit(&q->calls,memory_order_relaxed);
    int16_t l=0,r=0;
    if(n>=LEFT_BEGIN && n<SILENCE_BEGIN) {
        if(n<RIGHT_BEGIN || n>=BOTH_BEGIN)l=n%50<25?16384:-16384;
        if(n>=RIGHT_BEGIN)r=n%25<12?16384:-16384;
    }
    atomic_store_explicit(&q->calls,n+1,memory_order_release);
    return (uint16_t)l|((uint32_t)(uint16_t)r<<16);
}
int main(void) {
    const mk61_app_services* s=mk61_app_get_services(mk61_api,0);if(!s)return 1;
    const uint32_t master=s->call(MK61_SERVICE_SETTINGS,MK61_SERVICE_VOLUME,0,0,NULL);
    tone_state q;atomic_init(&q.calls,0);pwm_phase stats[5];memset(stats,0,sizeof(stats));
    for(unsigned i=0;i<5;++i)stats[i].min_l=stats[i].min_r=UINT32_MAX;
    const mk61_service_audio_synth request={tone,&q,25000,100};
    uint32_t opened=s->call(MK61_SERVICE_AUDIO_STREAM,MK61_AUDIO_SYNTH_OPEN,0,sizeof(request),(void*)&request);
    if(!opened) {s->call(MK61_SERVICE_AUDIO_STREAM,MK61_AUDIO_CLOSE,0,0,NULL);return 2;}
    const uint32_t start=s->call(MK61_SERVICE_MICROS,0,0,0,NULL);
    uint32_t calls=0;
    while((calls=atomic_load_explicit(&q.calls,memory_order_acquire))<TOTAL_SAMPLES &&
          s->call(MK61_SERVICE_MICROS,0,0,0,NULL)-start<12000000) {
        const unsigned index=calls<LEFT_BEGIN?0:calls<RIGHT_BEGIN?1:calls<BOTH_BEGIN?2:calls<SILENCE_BEGIN?3:4;
        const uint32_t low[]={0,LEFT_BEGIN,RIGHT_BEGIN,BOTH_BEGIN,SILENCE_BEGIN},high[]={LEFT_BEGIN,RIGHT_BEGIN,BOTH_BEGIN,SILENCE_BEGIN,TOTAL_SAMPLES};
        if(calls>=low[index]+4 && calls<high[index]-4) {
            const uint32_t cc=SPAUD_READ32(PWM5_CC),l=cc&65535U,r=cc>>16;pwm_phase* a=&stats[index];++a->count;
            if(l<a->min_l)a->min_l=l;
            if(l>a->max_l)a->max_l=l;
            if(r<a->min_r)a->min_r=r;
            if(r>a->max_r)a->max_r=r;
        }
        mk61_api->service();
    }
    const uint32_t csr=SPAUD_READ32(PWM5_CSR),left=SPAUD_READ32(GPIO26_CTRL)&31,right=SPAUD_READ32(GPIO27_CTRL)&31;
    const uint32_t close=s->call(MK61_SERVICE_AUDIO_STREAM,MK61_AUDIO_CLOSE,0,0,NULL);
    const uint32_t closed_csr=SPAUD_READ32(PWM5_CSR);char line[192];
    const bool ok=calls>=TOTAL_SAMPLES && (csr&1) && left==4 && right==4 && close && !(closed_csr&1);
    mk61_app_snprintf(s,line,sizeof(line),"SPAUD result=%u master=%lu mute=%u calls=%lu pwm_en=%u pins=%lu/%lu closed=%u\n",ok,(unsigned long)master,master==0,(unsigned long)calls,(unsigned)(csr&1),(unsigned long)left,(unsigned long)right,!(closed_csr&1));
    s->call(MK61_SERVICE_DEBUG_WRITE,strlen(line),0,0,line);
    for(unsigned i=0;i<5;++i) {
        const pwm_phase* a=&stats[i];mk61_app_snprintf(s,line,sizeof(line),"SPPWM phase=%u count=%lu L=%lu/%lu R=%lu/%lu\n",i,(unsigned long)a->count,
            (unsigned long)a->min_l,(unsigned long)a->max_l,(unsigned long)a->min_r,(unsigned long)a->max_r);s->call(MK61_SERVICE_DEBUG_WRITE,strlen(line),0,0,line);
    }
    return ok?0:3;
}
