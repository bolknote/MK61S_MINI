#ifndef MK61_SPECTRUM_MEDIA_H
#define MK61_SPECTRUM_MEDIA_H
#include "spectrum.h"
#define SPECTRUM_TRD_BYTES 655360U
enum spectrum_error spectrum_scl_unpack(const spectrum_source*,const spectrum_memory_io*,uint32_t target);
#endif
