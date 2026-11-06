#ifndef MK61_SPECTRUM_PERIPHERALS_H
#define MK61_SPECTRUM_PERIPHERALS_H
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
struct spectrum;
enum { SPECTRUM_TURBOSOUND=1, SPECTRUM_COVOX=2, SPECTRUM_SPECDRUM=4, SPECTRUM_ULAPLUS=8 };
#define SPECTRUM_SOUND_QUEUE_EVENTS 256U
#define SPECTRUM_SOUND_START_SAMPLES 50U /* 2 ms at the native 25 kHz rate. */
typedef struct { uint32_t time;uint8_t device,reg,value,reserved; } spectrum_sound_event;
typedef struct {
    spectrum_sound_event events[SPECTRUM_SOUND_QUEUE_EVENTS];
    _Atomic uint32_t read,write,produced,starved;
    _Atomic bool clock_running;
    uint32_t startup_samples;
    uint32_t time;
    uint8_t regs[2][16],selected,selected_reg[2],beeper,covox,specdrum;
    bool asynchronous;
    int32_t input,output;
    void (*yield)(void*);
    void* yield_context;
} spectrum_sound;
void spectrum_sound_reset(struct spectrum*);
void spectrum_sound_write(struct spectrum*,unsigned device,unsigned reg,unsigned value);
void spectrum_sound_begin(struct spectrum*,void (*yield)(void*),void*);
void spectrum_sound_clock(struct spectrum*,bool running);
void spectrum_sound_end(struct spectrum*);
uint32_t spectrum_sound_render(void*);
void spectrum_sound_publish(struct spectrum*);
#endif
