#ifndef MK61_SPECTRUM_SZX_H
#define MK61_SPECTRUM_SZX_H

#include "spectrum.h"

typedef struct {
    uint8_t header[170];
    const spectrum* machine;
    unsigned banks, prefix;
} spectrum_szx_writer;

/* Start a random-access SZX writer after stopping the sound consumer. */
uint32_t spectrum_szx_save(spectrum_szx_writer*,const spectrum*);
int spectrum_szx_read(void*,uint32_t offset,uint8_t* output,uint32_t size);
/* Compressed bank workspace: first 12 KiB and final 4 KiB of one bank. */
enum spectrum_error spectrum_load_szx(spectrum*,const spectrum_source*,uint8_t* low,uint8_t* high);
enum spectrum_error spectrum_szx_model(const spectrum_source*,unsigned*);

#endif
