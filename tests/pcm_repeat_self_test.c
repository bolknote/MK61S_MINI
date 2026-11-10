#include "../sdk/coproc/pcm_repeat.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned seed=0x12345678;
static unsigned random_word(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static unsigned long frames_checked,raw_fallbacks;
static unsigned check(const uint8_t* input,unsigned frames) {
    uint8_t coded[256],decoded[240];memset(coded,0xa5,sizeof(coded));
    const unsigned used=stm3_pcm_repeat_encode(coded+8,input,frames);
    assert(used<=frames*2);
    for(unsigned i=0;i<8;++i)assert(coded[i]==0xa5);
    for(unsigned i=8+frames*2;i<sizeof(coded);++i)assert(coded[i]==0xa5);
    if(used) {
        const uint8_t* cursor=coded+8;stm3_pcm_repeat_state previous={0x8080,0};
        for(unsigned i=0;i<frames;++i) {
            assert(stm3_pcm_repeat_next(&cursor,coded+8+used,&previous));
            decoded[2*i]=(uint8_t)previous.previous;decoded[2*i+1]=(uint8_t)(previous.previous>>8);
        }
        assert(cursor==coded+8+used && !previous.remaining);
        uint16_t guarded[130];for(unsigned i=0;i<130;++i)guarded[i]=0xa55a;
        const unsigned start=random_word();
        assert(stm3_pcm_repeat_decode_ring(guarded+1,128,start,coded+8,used,frames));
        assert(guarded[0]==0xa55a && guarded[129]==0xa55a);
        for(unsigned i=0;i<frames;++i)assert(guarded[1+((start+i)&127)]==
            (uint16_t)((unsigned)input[2*i]|(unsigned)input[2*i+1]<<8));
    } else {memcpy(decoded,input,frames*2);++raw_fallbacks;}
    assert(!memcmp(decoded,input,frames*2));frames_checked+=frames;return used;
}
int main(void) {
    uint8_t input[240];
    for(unsigned left=0;left<256;++left)for(unsigned right=0;right<256;++right) {
        for(unsigned i=0;i<120;++i){input[2*i]=(uint8_t)left;input[2*i+1]=(uint8_t)right;}
        check(input,1);assert(check(input,118)>0);check(input,120);
    }
    for(unsigned n=0;n<=120;++n)for(unsigned trial=0;trial<64;++trial) {
        for(unsigned i=0;i<n;++i) {
            if(i && (trial&1) && (random_word()&3)){input[2*i]=input[2*i-2];input[2*i+1]=input[2*i-1];}
            else {input[2*i]=(uint8_t)random_word();input[2*i+1]=(uint8_t)random_word();}
        }
        check(input,n);
    }
    for(unsigned i=0;i<120;++i){input[2*i]=(uint8_t)(i&1);input[2*i+1]=(uint8_t)i;}
    assert(check(input,118)==0); /* Escapes must select raw, without growth. */
    const uint8_t full_then_repeat[]={0,0,1,0,1,0};
    assert(check(full_then_repeat,3)==0);
    for(unsigned n=1;n<=120;++n)for(unsigned trial=0;trial<128;++trial) {
        for(unsigned i=0;i<n;++i){input[2*i]=(uint8_t)(random_word()&1);input[2*i+1]=(uint8_t)(random_word()%3);}
        check(input,n);
    }
    const uint8_t malformed[][3]={{1,0,0},{64,0,0},{255,0,0}};
    for(unsigned i=0;i<3;++i) {
        const unsigned needed=i?2:3;
        for(unsigned n=0;n<needed;++n){const uint8_t* p=malformed[i];stm3_pcm_repeat_state previous={0xbeef,0};assert(!stm3_pcm_repeat_next(&p,p+n,&previous));assert(p==malformed[i] && previous.previous==0xbeef && !previous.remaining);}
    }
    const uint8_t oversized_run[]={63};const uint8_t* run_cursor=oversized_run;
    stm3_pcm_repeat_state state={0x8080,0};assert(stm3_pcm_repeat_next(&run_cursor,oversized_run+1,&state));
    assert(run_cursor==oversized_run+1 && state.remaining==62); /* Caller must reject excess output. */
    /* Exercise arbitrary/truncated encodings with a fixed frame bound. */
    for(unsigned trial=0;trial<100000;++trial) {
        uint8_t bytes[240];const unsigned n=random_word()%241;
        for(unsigned i=0;i<n;++i)bytes[i]=(uint8_t)random_word();
        const uint8_t* cursor=bytes;stm3_pcm_repeat_state previous={0x8080,0};
        uint16_t expected[118],guarded[514];int valid=1;
        for(unsigned frames=0;frames<118;++frames){if(!stm3_pcm_repeat_next(&cursor,bytes+n,&previous)){valid=0;break;}expected[frames]=previous.previous;assert(cursor<=bytes+n);}
        valid=valid && cursor==bytes+n && !previous.remaining;
        const unsigned start=random_word();guarded[0]=0xbeef;guarded[513]=0xface;
        assert(stm3_pcm_repeat_decode_ring(guarded+1,512,start,bytes,n,118)==valid);
        assert(guarded[0]==0xbeef && guarded[513]==0xface);
        if(valid)for(unsigned i=0;i<118;++i)assert(guarded[1+((start+i)&511)]==expected[i]);
    }
    uint16_t ring[128];const uint8_t one_run[]={63};
    assert(!stm3_pcm_repeat_decode_ring(ring,0,0,one_run,1,1));
    assert(!stm3_pcm_repeat_decode_ring(ring,3,0,one_run,1,1));
    assert(!stm3_pcm_repeat_decode_ring(ring,128,0,one_run,1,129));
    assert(!stm3_pcm_repeat_decode_ring(ring,128,0,one_run,1,62));
    assert(!stm3_pcm_repeat_decode_ring(ring,128,0,one_run,1,64));
    assert(stm3_pcm_repeat_decode_ring(ring,128,127,one_run,1,63));
    assert(stm3_pcm_repeat_decode_ring(ring,128,0,one_run,0,0));
    assert(!stm3_pcm_repeat_decode_ring(ring,128,0,one_run,1,0));
    printf("Repeat codec: %lu exact stereo frames, all65536 pairs,0..120/118 boundaries, raw fallback=%lu, canaries/truncation/bounded fuzz PASS\n",frames_checked,raw_fallbacks);
}
