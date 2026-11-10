#include "spectrum.h"
#include <string.h>
static void apply(spectrum* s,unsigned device,unsigned reg,unsigned value) {
    if(device<2) PSG_writeReg(device?&s->ay2:&s->ay,reg,value);
    else if(device==2) s->sound.beeper=(uint8_t)value;
    else if(device==3) s->sound.covox=(uint8_t)value;
    else if(device==4) s->sound.specdrum=(uint8_t)value;
}
void spectrum_sound_configure(spectrum* s,unsigned chip,unsigned layout) {
    if(chip>SPECTRUM_YM || layout>SPECTRUM_ACB || s->sound.asynchronous)return;
    if(s->sound_chip==chip && s->sound_layout==layout)return;
    s->sound_chip=(uint8_t)chip;s->sound_layout=(uint8_t)layout;
    PSG_setVolumeMode(&s->ay,chip==SPECTRUM_YM?1:2);
    PSG_setVolumeMode(&s->ay2,chip==SPECTRUM_YM?1:2);
    /* Filter histories belong to the previous mix/table. Oscillator phases,
     * envelopes, RAM and guest registers are intentionally preserved. */
    s->ay.out=s->ay2.out=0;s->sound.input=s->sound.output=0;
    memset(s->sound.stereo,0,sizeof(s->sound.stereo));
}
void spectrum_sound_reset(spectrum* s) {
    memset(&s->sound,0,sizeof(s->sound));
    atomic_init(&s->sound.read,0);atomic_init(&s->sound.write,0);
    atomic_init(&s->sound.produced,0);atomic_init(&s->sound.starved,0);
    atomic_init(&s->sound.clock_running,true);
    s->sound.covox=s->sound.specdrum=128;
    s->sound.latest_dac[1]=s->sound.latest_dac[2]=128;
}
void spectrum_sound_write(spectrum* s,unsigned device,unsigned reg,unsigned value) {
    spectrum_sound* q=&s->sound;
    if(device<2) {
        static const uint8_t masks[]={255,15,255,15,255,15,31,255,31,31,31,255,255,15,255,255};
        q->regs[device][reg&15]=(uint8_t)(value&masks[reg&15]);
    } else if(device<=4)q->latest_dac[device-2]=(uint8_t)value;
    if(!q->asynchronous) { apply(s,device,reg,value);return; }
    uint32_t w;
    for(;;) {
        w=atomic_load_explicit(&q->write,memory_order_relaxed);
        if(w-atomic_load_explicit(&q->read,memory_order_acquire)<SPECTRUM_SOUND_QUEUE_EVENTS)break;
        atomic_store_explicit(&q->produced,(uint32_t)s->cpu.cyc,memory_order_release);
        if(q->yield) q->yield(q->yield_context);
    }
    q->events[w&(SPECTRUM_SOUND_QUEUE_EVENTS-1)]=(spectrum_sound_event){(uint32_t)s->cpu.cyc,(uint8_t)device,(uint8_t)reg,(uint8_t)value,0};
    atomic_store_explicit(&q->write,w+1,memory_order_release);
}
void spectrum_sound_publish(spectrum* s) {
    if(s->sound.asynchronous) atomic_store_explicit(&s->sound.produced,(uint32_t)s->cpu.cyc,memory_order_release);
}
void spectrum_sound_begin(spectrum* s,void (*yield)(void*),void* context) {
    spectrum_sound* q=&s->sound;
    atomic_store_explicit(&q->read,0,memory_order_relaxed);atomic_store_explicit(&q->write,0,memory_order_relaxed);
    atomic_store_explicit(&q->starved,0,memory_order_relaxed);
    q->time=(uint32_t)s->cpu.cyc;atomic_store_explicit(&q->produced,q->time,memory_order_release);
    q->latest_dac[0]=q->beeper;q->latest_dac[1]=q->covox;q->latest_dac[2]=q->specdrum;
    for(unsigned chip=0;chip<2;++chip) memcpy(q->regs[chip],chip?s->ay2.reg:s->ay.reg,16);
    q->yield=yield;q->yield_context=context;q->asynchronous=true;
    q->startup_samples=0;
    atomic_store_explicit(&q->clock_running,true,memory_order_release);
}
void spectrum_sound_clock(spectrum* s,bool running) {
    // Arm only while the device is gated (or after its callback has stopped).
    if(running) s->sound.startup_samples=SPECTRUM_SOUND_START_SAMPLES;
    atomic_store_explicit(&s->sound.clock_running,running,memory_order_release);
}
void spectrum_sound_recover(void* context) {
    spectrum* s=context;spectrum_sound* q=&s->sound;
    /* Called on core0 only after the remote consumer and PWM IRQ stop.
     * A lost link cannot export oscillator phase; restart from the current
     * producer registers, discard its stale queue, then resume locally. */
    for(unsigned i=0;i<2;++i) {
        PSG* p=i?&s->ay2:&s->ay;memset(p,0,sizeof(*p));p->quality=1;p->rate=25000;
        PSG_setVolumeMode(p,s->sound_chip==SPECTRUM_YM?1:2);PSG_setClock(p,1750000);PSG_reset(p);
        for(unsigned reg=0;reg<16;++reg)PSG_writeReg(p,reg,q->regs[i][reg]);
    }
    q->beeper=q->latest_dac[0];q->covox=q->latest_dac[1];q->specdrum=q->latest_dac[2];
    q->input=q->output=0;memset(q->stereo,0,sizeof(q->stereo));
    q->time=(uint32_t)s->cpu.cyc;q->startup_samples=SPECTRUM_SOUND_START_SAMPLES;
    atomic_store_explicit(&q->read,0,memory_order_relaxed);atomic_store_explicit(&q->write,0,memory_order_relaxed);
    atomic_store_explicit(&q->produced,q->time,memory_order_release);
}
void spectrum_sound_end(spectrum* s) {
    spectrum_sound* q=&s->sound;
    if(!q->asynchronous) return;
    atomic_store_explicit(&q->clock_running,true,memory_order_release);
    const uint32_t produced=atomic_load_explicit(&q->produced,memory_order_acquire);
    while((int32_t)(produced-(q->time+140))>=0) (void)spectrum_sound_render(s);
    uint32_t r=atomic_load_explicit(&q->read,memory_order_relaxed),w=atomic_load_explicit(&q->write,memory_order_acquire);
    while(r!=w) { const spectrum_sound_event e=q->events[r&(SPECTRUM_SOUND_QUEUE_EVENTS-1)];apply(s,e.device,e.reg,e.value);++r; }
    atomic_store_explicit(&q->read,r,memory_order_release);q->asynchronous=false;spectrum_sound_clock(s,false);
}
uint32_t spectrum_sound_render(void* context) {
    spectrum* s=context;spectrum_sound* q=&s->sound;
    if(!atomic_load_explicit(&q->clock_running,memory_order_acquire)) return 0;
    if(q->startup_samples) { --q->startup_samples;return 0; }
    const uint32_t next=q->time+140,available=atomic_load_explicit(&q->produced,memory_order_acquire);
    const bool underrun=(int32_t)(available-next)<0;
    const uint32_t until=underrun?available:next;
    if(underrun) {
        const uint32_t n=atomic_load_explicit(&q->starved,memory_order_relaxed);
        atomic_store_explicit(&q->starved,n+1,memory_order_relaxed);
    }
    uint32_t r=atomic_load_explicit(&q->read,memory_order_relaxed);
    const uint32_t w=atomic_load_explicit(&q->write,memory_order_acquire);
    /* The sample clock keeps running even when the producer is late. Drain
     * only published events, including past events behind that clock, so a
     * full queue can never wait for the producer to catch up to itself. */
    while(r!=w && (int32_t)(q->events[r&(SPECTRUM_SOUND_QUEUE_EVENTS-1)].time-until)<=0) {
        const spectrum_sound_event e=q->events[r&(SPECTRUM_SOUND_QUEUE_EVENTS-1)];apply(s,e.device,e.reg,e.value);++r;
    }
    atomic_store_explicit(&q->read,r,memory_order_release);q->time=next;
    int32_t left,right;
    if(s->sound_layout) {
        PSG_calcStereo(&s->ay,q->stereo,s->sound_layout);
        left=q->stereo[0];right=q->stereo[1];
        if(s->extensions&SPECTRUM_TURBOSOUND) {
            PSG_calcStereo(&s->ay2,q->stereo+2,s->sound_layout);left+=q->stereo[2];right+=q->stereo[3];
        } else {left*=2;right*=2;}
    } else {
        left=PSG_calc(&s->ay);
        if(s->extensions&SPECTRUM_TURBOSOUND)left+=PSG_calc(&s->ay2);else left*=2;
        right=left;
    }
    int32_t common=q->beeper?8192:0;
    if(s->extensions&SPECTRUM_COVOX)common+=((int32_t)q->covox-128)*64;
    if(s->extensions&SPECTRUM_SPECDRUM)common+=((int32_t)q->specdrum-128)*64;
    left+=common;right+=common;
    int32_t l=left-q->input+(q->output*255)/256;q->input=left;
    if(l>32767)l=32767;else if(l < -32768)l=-32768;q->output=l;
    int32_t right_output=l;
    if(s->sound_layout) {
        right_output=right-q->stereo[4]+(q->stereo[5]*255)/256;q->stereo[4]=right;
        if(right_output>32767)right_output=32767;else if(right_output < -32768)right_output=-32768;q->stereo[5]=right_output;
    }
    return (uint16_t)l|((uint32_t)(uint16_t)right_output<<16);
}
