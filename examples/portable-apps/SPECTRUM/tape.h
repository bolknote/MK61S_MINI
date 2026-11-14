#ifndef MK61_SPECTRUM_TAPE_H
#define MK61_SPECTRUM_TAPE_H

#include "spectrum.h"

typedef struct {
    uint32_t data, bytes;
    uint16_t pause, pilot, sync1, sync2, zero, one, count;
    uint8_t type, bits;
    uint32_t rate;
} spectrum_tape_block;

#define SPECTRUM_TAPE_INDEX_BYTES 16384u
typedef struct {
    spectrum_source source;
    spectrum_tape_block block;
    uint32_t next, deadline, byte, cache_at, cache_bytes;
    uint32_t loop_start[4];
    uint16_t loop_block[4];
    uint32_t call_offsets,call_block;
    uint32_t fraction;
    uint16_t loop_left[4], pulses;
    uint16_t index_count,index_block,call_next,call_count;
    void* index_context;
    bool (*index_read)(void*,uint32_t,uint8_t*,uint32_t);
    bool (*index_write)(void*,uint32_t,const uint8_t*,uint32_t);
    uint8_t cache[512], depth, bit, phase, half, value;
    bool tzx, level, playing, timed, fault;
} spectrum_tape;

/* Initializes a candidate tape. On error the candidate must be discarded. */
enum spectrum_error spectrum_tape_open(spectrum_tape*,const spectrum_source*,bool tzx);
void spectrum_tape_rewind(spectrum_tape*);
void spectrum_tape_toggle(spectrum_tape*,uint32_t cycles);
bool spectrum_tape_ear(void*,const z80*);

#endif
