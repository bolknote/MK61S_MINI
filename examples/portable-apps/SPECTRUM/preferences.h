#ifndef MK61_SPECTRUM_PREFERENCES_H
#define MK61_SPECTRUM_PREFERENCES_H

#include "spectrum.h"

enum { SPECTRUM_PREFERENCES_BYTES=16 };
typedef struct {
    uint8_t model,extensions,joystick,chip,layout,raster,write_protect;
} spectrum_preferences;

void spectrum_preferences_encode(const spectrum_preferences*,uint8_t output[SPECTRUM_PREFERENCES_BYTES]);
bool spectrum_preferences_decode(spectrum_preferences*,const uint8_t input[SPECTRUM_PREFERENCES_BYTES]);

#endif
