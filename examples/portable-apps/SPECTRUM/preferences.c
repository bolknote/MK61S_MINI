#include "preferences.h"
#include <string.h>

static uint32_t checksum(const uint8_t* bytes) {
    uint32_t value=2166136261u;
    for(unsigned i=0;i<12;++i) value=(value^bytes[i])*16777619u;
    return value;
}

void spectrum_preferences_encode(const spectrum_preferences* settings,uint8_t output[SPECTRUM_PREFERENCES_BYTES]) {
    memcpy(output,"SPCF\1",5);
    output[5]=settings->model;output[6]=settings->extensions;output[7]=settings->joystick;
    output[8]=settings->chip;output[9]=settings->layout;output[10]=settings->raster;
    output[11]=settings->write_protect;
    const uint32_t sum=checksum(output);
    for(unsigned i=0;i<4;++i) output[12+i]=(uint8_t)(sum>>(8*i));
}

bool spectrum_preferences_decode(spectrum_preferences* settings,const uint8_t input[SPECTRUM_PREFERENCES_BYTES]) {
    if(memcmp(input,"SPCF\1",5) || input[5]>SPECTRUM_128 || (input[6]&~15u) ||
       input[7]>2 || input[8]>SPECTRUM_YM || input[9]>SPECTRUM_ACB || input[10]>1 || input[11]>3) return false;
    const uint32_t sum=checksum(input);
    for(unsigned i=0;i<4;++i) if(input[12+i]!=(uint8_t)(sum>>(8*i))) return false;
    *settings=(spectrum_preferences){input[5],input[6],input[7],input[8],input[9],input[10],input[11]};
    return true;
}
