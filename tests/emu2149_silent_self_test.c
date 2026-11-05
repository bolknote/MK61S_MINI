#include "../third_party/emu2149/emu2149.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned random_state=0xA710C123;
static unsigned random_word(void) { random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state; }
static void init(PSG* p,unsigned rate) { memset(p,0,sizeof(*p));PSG_setVolumeMode(p,2);p->quality=1;p->rate=rate;PSG_setClock(p,1750000);PSG_reset(p); }
int main(void) {
    PSG a,b;const unsigned rates[]={8000,12500,25000,44100,48000};
    for(unsigned rate=0;rate<sizeof(rates)/sizeof(*rates);++rate) {
        init(&a,rates[rate]);b=a;
        for(unsigned i=0;i<100000;++i) {
            if(i%31==0) for(unsigned reg=0;reg<14;++reg) {
                unsigned value=random_word()&255;
                if(reg>=8 && reg<=10 && (i%127<96)) value=0;
                PSG_writeReg(&a,reg,value);PSG_writeReg(&b,reg,value);
            }
            const int16_t actual=PSG_calc(&a),expected=PSG_calc_reference(&b);
            if(actual!=expected || memcmp(&a,&b,sizeof(a))) { fprintf(stderr,"silent state mismatch rate=%u sample=%u output=%d/%d\n",rates[rate],i,actual,expected);return 1; }
        }
    }
    init(&a,25000);PSG_writeReg(&a,7,63);PSG_writeReg(&a,8,15);
    assert(PSG_calc(&a)>0); // Disabled tone/noise is an AY amplitude DAC.
    PSG_writeReg(&a,7,62);for(unsigned i=0;i<32;++i) (void)PSG_calc(&a);
    assert(!a.ch_out[0]); // Ultrasonic tones never retain a stale DC output.
    puts("AY silent fast path: 500000 samples, exact counters/LFSR/envelope/filter; amplitude DAC: PASS");return 0;
}
