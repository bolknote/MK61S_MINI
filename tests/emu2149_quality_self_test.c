#include "../third_party/emu2149/emu2149.c"
#include <assert.h>
#include <stdio.h>
static uint32_t random_state=0x5114a0b3;
static unsigned random_word(void){random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state;}
static void init(PSG* p,unsigned rate,unsigned mode){memset(p,0,sizeof(*p));PSG_setVolumeMode(p,mode);p->quality=1;p->rate=rate;PSG_setClock(p,1750000);PSG_reset(p);}
static unsigned comparisons,weighted;
static void equal_sample(PSG* a,PSG* b,unsigned scenario,unsigned sample) {
    if(a->quality && a->base_incr==(1U<<GETA_BITS) && (a->volume[0]|a->volume[1]|a->volume[2])) {
        PSG phase=*a;const unsigned n=output_ticks(&phase);
        if(weighted_eligible(a,n))++weighted;
    }
    const int16_t actual=PSG_calc(a),expected=PSG_calc_reference(b);
    if(actual!=expected || memcmp(a,b,sizeof(*a))) {
        fprintf(stderr,"AY exact quality mismatch scenario=%u sample=%u out=%d/%d freq=%u/%u/%u noise=%u env=%u\n",scenario,sample,actual,expected,a->freq[0],a->freq[1],a->freq[2],a->noise_freq,a->env_freq);abort();
    }
    ++comparisons;
}
int main(void) {
    const unsigned rates[]={1000,8000,12500,25000,44100,48000};PSG a,b;
    for(unsigned scenario=0;scenario<96;++scenario) {
        init(&a,rates[scenario%6],scenario&1?1:2);b=a;
        for(unsigned sample=0;sample<4096;++sample) {
            if(sample%(scenario%3?31:7)==0)for(unsigned reg=0;reg<14;++reg) {
                unsigned value=random_word()&255;
                if(reg==7 && scenario%4==0)value=63;
                if(reg==6 && scenario%4==1)value=scenario%32;
                if(reg>=8 && reg<=10)value=sample%127<96?(reg==8?16:15):(random_word()&31);
                PSG_writeReg(&a,reg,value);PSG_writeReg(&b,reg,value);
            }
            if(sample%128==0) {unsigned mask=random_word()&7;PSG_setMask(&a,mask);PSG_setMask(&b,mask);}
            if(sample%193==0) {unsigned div=(sample/193)&1;PSG_setClockDivider(&a,div);PSG_setClockDivider(&b,div);}
            if(scenario%3==2 && sample%257==0) {unsigned quality=(sample/257)&1;PSG_setQuality(&a,quality);PSG_setQuality(&b,quality);}
            equal_sample(&a,&b,scenario,sample);
        }
    }
    for(unsigned shape=0;shape<16;++shape) {
        init(&a,25000,2);PSG_writeReg(&a,7,0x29);PSG_writeReg(&a,0,0xb8);PSG_writeReg(&a,1,8);
        PSG_writeReg(&a,2,0xc2);PSG_writeReg(&a,3,4);PSG_writeReg(&a,6,11);PSG_writeReg(&a,8,16);
        PSG_writeReg(&a,9,5);PSG_writeReg(&a,11,70);PSG_writeReg(&a,13,shape);b=a;
        for(unsigned sample=0;sample<25000;++sample)equal_sample(&a,&b,96+shape,sample);
    }
    // Signed filter rounding and long stable DAC spans, including >31 ticks.
    for(unsigned rate=0;rate<6;++rate) {
        init(&a,rates[rate],2);PSG_writeReg(&a,7,63);PSG_writeReg(&a,8,15);PSG_writeReg(&a,9,7);a.out=-32768;b=a;
        for(unsigned sample=0;sample<4096;++sample)equal_sample(&a,&b,112+rate,sample);
    }
    assert(weighted>100000);
    printf("Weighted path eligible: %u samples\n",weighted);
    printf("AY exact quality: %u samples, %u eligible/%u fallback; full oscillator/LFSR/envelope/mixer/filter state, six rates, all16 envelopes and signed rounding PASS\n",comparisons,weighted,comparisons-weighted);
}
