#ifndef MK61_SPECTRUM_INFLATE_H
#define MK61_SPECTRUM_INFLATE_H

#include "spectrum.h"

/* One zlib stream with a caller-supplied maximum output. */
typedef struct {
    uint8_t* first;
    uint8_t* second;
    unsigned split,limit;
} spectrum_inflate_output;
enum spectrum_error spectrum_inflate(const spectrum_source*,uint32_t offset,uint32_t bytes,
    const spectrum_inflate_output*,unsigned* used);

#endif
