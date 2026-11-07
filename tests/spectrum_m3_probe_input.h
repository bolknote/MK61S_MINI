#ifndef MK61_SPECTRUM_M3_PROBE_INPUT_H
#define MK61_SPECTRUM_M3_PROBE_INPUT_H
#include <stdint.h>
#define M3_SOUND_BLOCKS 64u
#ifndef M3_SOUND_FRAMES
#define M3_SOUND_FRAMES 120u
#endif
#if defined(S3_SOUND_PWM8) && S3_SOUND_PWM8
#define M3_SOUND_OUTPUT_BYTES (8u+M3_SOUND_FRAMES)
#define M3_SOUND_OUTPUT_MAGIC 0x314d5750u
#else
#define M3_SOUND_OUTPUT_BYTES (8u+2u*M3_SOUND_FRAMES)
#define M3_SOUND_OUTPUT_MAGIC 0x314d4350u
#endif
static unsigned m3_sound_probe_packet(unsigned mode,unsigned block,uint8_t* out) {
    out[0]='S';out[1]='A';out[2]='Y';out[3]='1';out[4]=1;out[5]=M3_SOUND_FRAMES;
    out[6]=(uint8_t)(mode?7:0);out[7]=(uint8_t)(mode==2?7:0);out[8]=0;out[9]=out[10]=128;
    if(mode==2) {
        const unsigned bits=(M3_SOUND_FRAMES+7)/8;
        for(unsigned i=0;i<bits;++i)out[11+i]=0;
        for(unsigned i=0;i<M3_SOUND_FRAMES;++i) {
            const unsigned t=block*M3_SOUND_FRAMES+i;
            out[11+i/8]|=(uint8_t)(((t/3)&1)<<(i&7));out[11+bits+i]=(uint8_t)(t*29);out[11+bits+M3_SOUND_FRAMES+i]=(uint8_t)(t*47);
        }
        return 11+bits+2*M3_SOUND_FRAMES;
    }
    out[11]=0;out[12]=(uint8_t)(mode?13:0);out[13]=(uint8_t)(mode?10:0xa2+block*13);
    out[14]=M3_SOUND_FRAMES/2;out[15]=(uint8_t)(mode?29:9);out[16]=(uint8_t)(mode?10:block&15);
    return 17;
}
#endif
