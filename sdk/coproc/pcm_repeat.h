#ifndef MK61_STM3_PCM_REPEAT_H
#define MK61_STM3_PCM_REPEAT_H
#include <stdint.h>
/* Lossless unsigned8 stereo. Byte0 repeats once; bytes2..63 repeat that
 * many frames; byte1 escapes a complete pair; bytes64..255 begin a plain
 * two-byte pair. Initial pair128/128; no cross-block state. All65536
 * literal pairs supported. Disjoint buffers hold2*frames bytes. Return0
 * selects raw fallback if escapes would grow the block. At most2*frames
 * pair comparisons; output never exceeds raw. */
static inline unsigned stm3_pcm_repeat_encode(uint8_t* out,const uint8_t* in,unsigned frames) {
    uint16_t previous=0x8080;unsigned used=0,i=0;
    while(i<frames) {
        const unsigned left=in[2*i];const uint16_t pair=(uint16_t)(left|(unsigned)in[2*i+1]<<8);
        if(pair==previous) {
            unsigned run=1;
            while(run<63 && i+run<frames && in[2*(i+run)]==(uint8_t)pair && in[2*(i+run)+1]==(uint8_t)(pair>>8))++run;
            if(used==2*frames)return 0;
            out[used++]=(uint8_t)(run==1?0:run);i+=run;
        } else {
            const unsigned need=left<64?3:2;if(need>2*frames-used)return 0;
            if(left<64)out[used++]=1;
            out[used++]=(uint8_t)left;out[used++]=in[2*i+1];previous=pair;++i;
        }
    }
    return used;
}
typedef struct {uint16_t previous;uint8_t remaining;} stm3_pcm_repeat_state;
/* One bounded output frame per call, at most3 input bytes. Caller checks
 * the exact frame count, cursor==end and remaining==0 before publishing. */
static inline int stm3_pcm_repeat_next(const uint8_t** cursor,const uint8_t* end,stm3_pcm_repeat_state* state) {
    if(state->remaining){--state->remaining;return 1;}
    const uint8_t* p=*cursor;if(p==end)return 0;
    const unsigned left=*p++;
    if(left==1) {
        if(end-p<2)return 0;
        state->previous=(uint16_t)((unsigned)p[0]|(unsigned)p[1]<<8);p+=2;
    } else if(left<64)state->remaining=(uint8_t)(left?left-1:0);
    else {
        if(p==end)return 0;
        state->previous=(uint16_t)(left|(unsigned)*p++<<8);
    }
    *cursor=p;return 1;
}

/* Decode exactly one independently seeded block directly into a power-of-two
 * duty ring. Repeated pairs cost one parse per run; partial output remains
 * unpublished when malformed input is rejected. No heap or temporary block. */
static inline int stm3_pcm_repeat_decode_ring(uint16_t* ring,unsigned capacity,unsigned start,
                                              const uint8_t* input,unsigned bytes,unsigned frames) {
    if(!capacity || (capacity&(capacity-1)) || frames>capacity)return 0;
    const uint8_t* p=input;const uint8_t* end=input+bytes;
    uint16_t previous=0x8080;unsigned remaining=frames;
    while(remaining) {
        if(p==end)return 0;
        const unsigned left=*p++;
        if(left>=64) {
            if(p==end)return 0;
            previous=(uint16_t)(left|(unsigned)*p++<<8);
        } else if(left==1) {
            if(end-p<2)return 0;
            previous=(uint16_t)((unsigned)p[0]|(unsigned)p[1]<<8);p+=2;
        } else {
            unsigned run=left?left:1;
            if(run>remaining)return 0;
            remaining-=run;
            do {ring[start++&(capacity-1)]=previous;}while(--run);
            continue;
        }
        ring[start++&(capacity-1)]=previous;--remaining;
    }
    return p==end;
}

#endif
