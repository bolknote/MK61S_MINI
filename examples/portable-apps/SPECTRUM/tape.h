#ifndef MK61_SPECTRUM_TAPE_H
#define MK61_SPECTRUM_TAPE_H

#include "spectrum.h"

typedef struct {
    uint32_t data, bytes;
    uint32_t items, data_items, pilot_stream, data_table, data_stream;
    uint16_t pause, pilot, sync1, sync2, zero, one, count;
    uint8_t type, bits;
    uint32_t rate;
} spectrum_tape_block;

typedef struct {
    uint32_t file, decoded, bytes;
} spectrum_tape_index;

#define SPECTRUM_TAPE_INDEX_BYTES (4096u * sizeof(spectrum_tape_index))
#define SPECTRUM_TAPE_CSW_BYTES (2u * 1024u * 1024u)
#define SPECTRUM_TAPE_SLOT_BYTES (SPECTRUM_TAPE_INDEX_BYTES+SPECTRUM_TAPE_CSW_BYTES)
#define SPECTRUM_TAPE_DECODE_SCRATCH 1024u
typedef struct {
    spectrum_source source;
    spectrum_tape_block block;
    uint32_t next, deadline, byte, cache_at[2], cache_bytes[2];
    uint32_t loop_start[4];
    uint16_t loop_block[4];
    uint32_t call_offsets,call_block;
    uint32_t fraction, symbol_at;
    uint16_t loop_left[4], pulses;
    uint16_t index_count,index_block,call_next,call_count;
    void* index_context;
    bool (*index_read)(void*,uint32_t,uint8_t*,uint32_t);
    bool (*index_write)(void*,uint32_t,const uint8_t*,uint32_t);
    uint8_t cache[2][256], depth, bit, phase, half, value;
    uint8_t choices;
    bool tzx, level, playing, timed, fault, cached_decoded;
    /* The CSW area follows the index in this callback's logical address space. */
    uint32_t decoded_bytes;
    uint8_t* decode_scratch; /* SPECTRUM_TAPE_DECODE_SCRATCH bytes during open. */
} spectrum_tape;

/* Initializes a candidate tape. On error the candidate must be discarded. */
enum spectrum_error spectrum_tape_open(spectrum_tape*,const spectrum_source*,bool tzx);
void spectrum_tape_rewind(spectrum_tape*);
void spectrum_tape_toggle(spectrum_tape*,uint32_t cycles);
bool spectrum_tape_ear(void*,const z80*);
bool spectrum_tape_choice(spectrum_tape*,unsigned option,char* label,unsigned capacity);
bool spectrum_tape_choose(spectrum_tape*,unsigned option,uint32_t cycles);

#if SPECTRUM_HAS_TAPE_RECORD
typedef struct {
    void* context;
    bool (*write)(void*,uint32_t,const uint8_t*,uint32_t);
    uint32_t capacity,size,edge,bytes;
    uint16_t pilot;
    uint8_t stage,half,bits,value,checksum;
    bool have_edge,level,fault;
    uint8_t data[128];
} spectrum_tape_recorder;
void spectrum_tape_mic(void*,uint32_t cycles,bool level);
void spectrum_tape_record_finish(spectrum_tape_recorder*);
#endif

#endif
