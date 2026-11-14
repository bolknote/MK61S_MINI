#ifndef MK61_SPECTRUM_INFLATE_H
#define MK61_SPECTRUM_INFLATE_H

#include "spectrum.h"

/* A stream can use two direct spans or seekable external storage. */
typedef struct {
    uint8_t* first;
    uint8_t* second;
    unsigned split,limit;
    void* context;
    bool (*read)(void*,uint32_t,uint8_t*);
    bool (*write)(void*,uint32_t,uint8_t);
} spectrum_inflate_output;
enum spectrum_error spectrum_inflate(const spectrum_source*,uint32_t offset,uint32_t bytes,
    const spectrum_inflate_output*,unsigned* used);

#endif
