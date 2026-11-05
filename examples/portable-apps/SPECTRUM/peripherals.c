#include "spectrum.h"
#include <string.h>
static void apply(spectrum* s,unsigned device,unsigned reg,unsigned value) {
    if(device<2) PSG_writeReg(device?&s->ay2:&s->ay,reg,value);
    else if(device==2) s->sound.beeper=(uint8_t)value;
    else if(device==3) s->sound.covox=(uint8_t)value;
    else if(device==4) s->sound.specdrum=(uint8_t)value;
}
void spectrum_sound_reset(spectrum* s) {
    memset(&s->sound,0,sizeof(s->sound));
    atomic_init(&s->sound.read,0);atomic_init(&s->sound.write,0);
    atomic_init(&s->sound.produced,0);atomic_init(&s->sound.starved,0);
    s->sound.covox=s->sound.specdrum=128;
}
void spectrum_sound_write(spectrum* s,unsigned device,unsigned reg,unsigned value) {
    spectrum_sound* q=&s->sound;
    if(device<2) {
        static const uint8_t masks[]={255,15,255,15,255,15,31,255,31,31,31,255,255,15,255,255};
        q->regs[device][reg&15]=(uint8_t)(value&masks[reg&15]);
    }
    if(!q->asynchronous) { apply(s,device,reg,value);return; }
    const uint32_t w=atomic_load_explicit(&q->write,memory_order_relaxed);
    while(w-atomic_load_explicit(&q->read,memory_order_acquire)==SPECTRUM_SOUND_QUEUE_EVENTS) {
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
    for(unsigned chip=0;chip<2;++chip) memcpy(q->regs[chip],chip?s->ay2.reg:s->ay.reg,16);
    q->yield=yield;q->yield_context=context;q->asynchronous=true;
}
void spectrum_sound_end(spectrum* s) {
    spectrum_sound* q=&s->sound;
    if(!q->asynchronous) return;
    const uint32_t produced=atomic_load_explicit(&q->produced,memory_order_acquire);
    while((int32_t)(produced-(q->time+140))>=0) (void)spectrum_sound_render(s);
    uint32_t r=atomic_load_explicit(&q->read,memory_order_relaxed),w=atomic_load_explicit(&q->write,memory_order_acquire);
    while(r!=w) { const spectrum_sound_event e=q->events[r&(SPECTRUM_SOUND_QUEUE_EVENTS-1)];apply(s,e.device,e.reg,e.value);++r; }
    atomic_store_explicit(&q->read,r,memory_order_release);q->asynchronous=false;
}
uint32_t spectrum_sound_render(void* context) {
    spectrum* s=context;spectrum_sound* q=&s->sound;
    const uint32_t next=q->time+140,available=atomic_load_explicit(&q->produced,memory_order_acquire);
    if((int32_t)(available-next)<0) {
        const uint32_t n=atomic_load_explicit(&q->starved,memory_order_relaxed);
        atomic_store_explicit(&q->starved,n+1,memory_order_relaxed);
        return (uint16_t)q->output|((uint32_t)(uint16_t)q->output<<16);
    }
    uint32_t r=atomic_load_explicit(&q->read,memory_order_relaxed);
    const uint32_t w=atomic_load_explicit(&q->write,memory_order_acquire);
    while(r!=w && (int32_t)(q->events[r&(SPECTRUM_SOUND_QUEUE_EVENTS-1)].time-next)<=0) {
        const spectrum_sound_event e=q->events[r&(SPECTRUM_SOUND_QUEUE_EVENTS-1)];apply(s,e.device,e.reg,e.value);++r;
    }
    atomic_store_explicit(&q->read,r,memory_order_release);q->time=next;
    int32_t sample=PSG_calc(&s->ay);
    if(s->extensions&SPECTRUM_TURBOSOUND) sample+=PSG_calc(&s->ay2);
    else sample*=2;
    sample+=q->beeper?8192:0;
    if(s->extensions&SPECTRUM_COVOX) sample+=((int32_t)q->covox-128)*64;
    if(s->extensions&SPECTRUM_SPECDRUM) sample+=((int32_t)q->specdrum-128)*64;
    int32_t output=sample-q->input+(q->output*255)/256;q->input=sample;
    if(output>32767) output=32767;else if(output < -32768) output=-32768;
    q->output=output;return (uint16_t)output|((uint32_t)(uint16_t)output<<16);
}
