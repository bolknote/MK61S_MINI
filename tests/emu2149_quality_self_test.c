#include "../third_party/emu2149/emu2149.c"
#include <assert.h>
#include <stdio.h>
static uint32_t random_state=0x5114a0b3;
static unsigned random_word(void){random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state;}
static void init(PSG* p,unsigned rate,unsigned mode){memset(p,0,sizeof(*p));PSG_setVolumeMode(p,mode);p->quality=1;p->rate=rate;PSG_setClock(p,1750000);PSG_reset(p);}
static unsigned comparisons,weighted;
static void stereo_quality(void) {
    PSG a,b;unsigned checked=0;
    for(unsigned mode=1;mode<=2;++mode)for(unsigned layout=1;layout<=2;++layout)
    for(unsigned scenario=0;scenario<32;++scenario) {
        init(&a,25000,mode);b=a;int32_t actual[2]={0,0},expected[2]={0,0};
        for(unsigned sample=0;sample<4096;++sample) {
            if(!(sample%19))for(unsigned reg=0;reg<14;++reg) {
                unsigned value=random_word()&255;
                if(reg==6)value=scenario&31;
                if(reg>=8 && reg<=10)value=scenario%3?16:random_word()&15;
                if(reg==11)value=scenario%4?0:value;
                PSG_writeReg(&a,reg,value);PSG_writeReg(&b,reg,value);
            }
            if(!(sample%83)){unsigned mask=random_word()&7;PSG_setMask(&a,mask);PSG_setMask(&b,mask);}
            PSG_calcStereo(&a,actual,layout);PSG_calcStereo_reference(&b,expected,layout);
            assert(!memcmp(&a,&b,sizeof(a)) && !memcmp(actual,expected,sizeof(actual)));++checked;
        }
        // Independent constant-channel routing oracle, beyond the serial DSP reference.
        for(unsigned channel=0;channel<3;++channel) {
            init(&a,25000,mode);PSG_writeReg(&a,7,63);PSG_writeReg(&a,8+channel,15);
            actual[0]=actual[1]=0;for(unsigned i=0;i<8;++i)PSG_calcStereo(&a,actual,layout);
            const int32_t amplitude=(int32_t)(a.voltbl[31]<<4);
            const unsigned centre=layout==2?2:1;
            if(!channel){assert(actual[0]>=2*amplitude-1 && !actual[1]);}
            else if(channel==centre){assert(actual[0]>=amplitude-1 && actual[0]==actual[1]);}
            else {assert(!actual[0] && actual[1]>=2*amplitude-1);}
        }
    }
    printf("AY/YM stereo: %u exact stereo samples, ABC/ACB isolated A/centre/right, changing envelopes/noise and complete mono PSG states PASS\n",checked);
}
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
    stereo_quality();
#if defined(EMU2149_M3_FIXED_RATE) && EMU2149_M3_FIXED_RATE
    // CONFIG accepts every sub-tick phase below200000, including imported
    // phases outside the usual four positions of the fixed-rate stream.
    for(unsigned mode=1;mode<=2;++mode)for(unsigned layout=1;layout<=2;++layout)
    for(unsigned phase=0;phase<200000;++phase) {
        PSG a,b;init(&a,25000,mode);a.psgtime=phase;
        for(unsigned reg=0;reg<14;++reg)PSG_writeReg(&a,reg,(phase+13*reg)&255);
        b=a;int32_t out[2]={123,-456},reference[2]={123,-456};
        PSG_calcStereo(&a,out,layout);PSG_calcStereo_reference(&b,reference,layout);
        assert(!memcmp(&a,&b,sizeof(a)) && !memcmp(out,reference,sizeof(out)));
    }
    puts("M3 fixed rate: all200000 accepted phases, both chips/layouts and exact full states PASS");
    return 0;
#endif
#if defined(EMU2149_M3_AUDIO) && EMU2149_M3_AUDIO
    /* Independent serial LFSR reference, every 17-bit state, all bulk sizes. */
    for(uint32_t seed=0;seed<(1u<<17);++seed) {
        uint32_t serial=seed;
        for(unsigned steps=0;steps<=8;++steps) {
            assert(advance_noise(seed,steps)==serial);
            if(serial&1)serial^=0x24000;serial>>=1;
        }
    }
#endif
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
    // Every short tone/noise period, both initial gate phases, all shapes
    // and minimum envelope period. These hit the M3 mask fast paths.
    for(unsigned period=0;period<32;++period)for(unsigned shape=0;shape<16;++shape) {
        init(&a,25000,2);PSG_writeReg(&a,7,0);PSG_writeReg(&a,6,period);
        for(unsigned i=0;i<3;++i){PSG_writeReg(&a,i*2,period);PSG_writeReg(&a,8+i,16);a.edge[i]=(uint8_t)(i&1);}
        PSG_writeReg(&a,11,0);PSG_writeReg(&a,13,shape);a.noise_scaler=shape&1;b=a;
        for(unsigned sample=0;sample<256;++sample)equal_sample(&a,&b,128+period*16+shape,sample);
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
