#include "../examples/portable-apps/SPECTRUM/spectrum.h"
#include "../examples/portable-apps/SPECTRUM/m3_audio_protocol.h"
#include "stm3_module.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

uint32_t module_entry(uint32_t,const stm3_api*,stm3_job*);
static stm3_api api={STM3_ABI,sizeof(stm3_api),NULL,NULL};
static FILE* vectors;
static unsigned vector_count;
static unsigned output_width=2,pwm_gain;
static void vector(const uint8_t* in,unsigned n,const uint8_t* out,unsigned used) {
    if(!vectors || vector_count==32)return;
    const uint32_t sizes[2]={n,used};assert(fwrite(sizes,sizeof(sizes),1,vectors)==1);
    assert(fwrite(in,1,n,vectors)==n && fwrite(out,1,used,vectors)==used);++vector_count;
}
static uint32_t random_state=0x91ab2375;
static unsigned rnd(void) { random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state; }
static void init(spectrum* s) {
    memset(s,0,sizeof(*s));s->ay.quality=1;s->ay.rate=25000;
    PSG_setVolumeMode(&s->ay,2);PSG_setClock(&s->ay,1750000);PSG_reset(&s->ay);
    s->ay2=s->ay;spectrum_sound_reset(s);
}
static unsigned config(const spectrum* s,uint8_t* bytes) {
    memset(bytes,0,512);spectrum_m3_put32(bytes,SPECTRUM_M3_AUDIO_MAGIC);
    if(output_width==1){bytes[5]=1;bytes[6]=(uint8_t)pwm_gain;bytes[7]=(uint8_t)(pwm_gain>>8);}
    for(unsigned i=0;i<2;++i)memcpy(bytes+8+i*SPECTRUM_M3_PSG_BYTES,
        (const uint8_t*)(i?&s->ay2:&s->ay)+offsetof(PSG,reg),SPECTRUM_M3_PSG_BYTES);
    uint8_t* tail=bytes+8+2*SPECTRUM_M3_PSG_BYTES;
    spectrum_m3_put32(tail,(uint32_t)s->sound.input);spectrum_m3_put32(tail+4,(uint32_t)s->sound.output);
    tail[8]=s->sound.beeper;tail[9]=s->sound.covox;tail[10]=s->sound.specdrum;
    return SPECTRUM_M3_STATE_BYTES;
}
static void run(uint8_t* in,unsigned size,uint8_t* out,unsigned capacity,unsigned expected_samples) {
    stm3_job job={in,size,out,capacity,0,0};
    uint32_t result=module_entry(STM3_INIT,&api,&job);unsigned calls=0;
    while(result==STM3_MORE) {
        const unsigned before=job.progress;result=module_entry(STM3_STEP,&api,&job);
        assert(job.progress>before && job.progress-before<=16 && ++calls<=8);
    }
    assert(result==STM3_DONE && job.output_bytes==8+output_width*expected_samples);
    assert(spectrum_m3_get32(out)==(expected_samples && output_width==1?SPECTRUM_M3_PWM_MAGIC:SPECTRUM_M3_PCM_MAGIC) && out[4]==expected_samples && !out[5]);
    vector(in,size,out,job.output_bytes);
}
static void same_state(const spectrum* s) {
    uint8_t request[8]={0},out[512],expected[512];
    spectrum_m3_put32(request,SPECTRUM_M3_AUDIO_MAGIC);request[4]=SPECTRUM_M3_EXPORT;
    stm3_job job={request,8,out,sizeof(out),0,0};assert(module_entry(STM3_INIT,&api,&job)==STM3_DONE);
    assert(job.output_bytes==SPECTRUM_M3_STATE_BYTES);
    config(s,expected);spectrum_m3_put32(expected,SPECTRUM_M3_STATE_MAGIC);spectrum_m3_put32(expected+4,SPECTRUM_M3_PSG_BYTES);
    assert(!memcmp(out,expected,SPECTRUM_M3_STATE_BYTES));
    vector(request,8,out,job.output_bytes);
}
static void profile(uint8_t* out) {
    uint8_t request[8]={0};spectrum_m3_put32(request,SPECTRUM_M3_AUDIO_MAGIC);
    request[4]=SPECTRUM_M3_PROFILE;
    stm3_job job={request,8,out,SPECTRUM_M3_PROFILE_BYTES,0,0};
    assert(module_entry(STM3_INIT,&api,&job)==STM3_DONE && job.output_bytes==SPECTRUM_M3_PROFILE_BYTES);
    assert(spectrum_m3_get32(out)==SPECTRUM_M3_PROFILE_MAGIC);
    vector(request,8,out,job.output_bytes);
}
static uint32_t fake_time;
static uint32_t fake_micros(void* context) {(void)context;const uint32_t now=fake_time;fake_time+=7;return now;}
static void unchanged_after_bad_render(spectrum* s,const uint8_t* source,unsigned n,unsigned at,unsigned value) {
    uint8_t bad[512],out[512];memcpy(bad,source,n);bad[at]=(uint8_t)value;
    stm3_job job={bad,n,out,sizeof(out),0,0};assert(module_entry(STM3_INIT,&api,&job)==STM3_INVALID);same_state(s);
}
int main(void) {
    const char* filename=getenv("SPECTRUM_M3_VECTORS");
    if(filename){vectors=fopen(filename,"wb");assert(vectors);const uint32_t header[2]={0x31564153,0};assert(fwrite(header,sizeof(header),1,vectors)==1);}
    spectrum s;init(&s);uint8_t input[512],output[512];
    const unsigned size=config(&s,input);assert(size<=512);
    run(input,size,output,sizeof(output),0);same_state(&s);
    profile(output);for(unsigned i=4;i<SPECTRUM_M3_PROFILE_BYTES;++i)assert(!output[i]);
    /* Exact physical PWM duties, including zero and fractional software gain.
     * The internal16-bit synth/filter state must remain identical too. */
    static const unsigned gains[]={0,1,123,333,777,999,1000};
    output_width=1;
    for(unsigned g=0;g<sizeof(gains)/sizeof(gains[0]);++g) {
        pwm_gain=gains[g];init(&s);config(&s,input);run(input,size,output,sizeof(output),0);
        memset(input,0,512);spectrum_m3_put32(input,SPECTRUM_M3_AUDIO_MAGIC);
        input[4]=SPECTRUM_M3_RENDER;input[5]=96;input[6]=7;input[7]=7;
        for(unsigned i=0;i<12;++i)input[11+i]=(uint8_t)(i*29);
        for(unsigned i=0;i<96;++i){input[23+i]=(uint8_t)(i*47);input[119+i]=(uint8_t)(i*71);}
        run(input,215,output,sizeof(output),96);s.extensions=7;
        for(unsigned i=0;i<96;++i) {
            spectrum_sound_write(&s,2,0,(input[11+i/8]>>(i&7))&1);
            spectrum_sound_write(&s,3,0,input[23+i]);spectrum_sound_write(&s,4,0,input[119+i]);
            atomic_store(&s.sound.produced,s.sound.time+140);
            const int32_t sample=(int16_t)spectrum_sound_render(&s);
            assert(output[8+i]==128+(sample*(int32_t)pwm_gain)/512000);
        }
        same_state(&s);
    }
    output_width=2;init(&s);config(&s,input);run(input,size,output,sizeof(output),0);
    unsigned samples=0;
    for(unsigned block=0;block<512;++block) {
        const unsigned n=1+rnd()%120,flags=block&7;
        memset(input,0,sizeof(input));spectrum_m3_put32(input,SPECTRUM_M3_AUDIO_MAGIC);
        input[4]=SPECTRUM_M3_RENDER;input[5]=(uint8_t)n;input[6]=(uint8_t)(rnd()&7);input[7]=(uint8_t)flags;
        input[8]=(uint8_t)(rnd()&1);input[9]=(uint8_t)rnd();input[10]=(uint8_t)rnd();
        unsigned at=11;uint8_t *beep=NULL,*cv=NULL,*sd=NULL;
        if(flags&1){beep=input+at;at+=(n+7)/8;for(unsigned j=0;j<(n+7)/8;++j)beep[j]=(uint8_t)rnd();}
        if(flags&2){cv=input+at;at+=n;for(unsigned j=0;j<n;++j)cv[j]=(uint8_t)rnd();}
        if(flags&4){sd=input+at;at+=n;for(unsigned j=0;j<n;++j)sd[j]=(uint8_t)rnd();}
        const unsigned events=at;
        for(unsigned i=0;i<n;++i)if((rnd()&7)==0 && at+6<=512) {
            input[at++]=(uint8_t)i;input[at++]=(uint8_t)(rnd()&31);input[at++]=(uint8_t)rnd();
            /* A same-value reg13 write must trigger the envelope twice. */
            if((block&7)==0 && at+3<=512){input[at++]=(uint8_t)i;input[at++]=13;input[at++]=10;}
        }
        run(input,at,output,sizeof(output),n);
        unsigned e=events;s.extensions=input[6];
        for(unsigned i=0;i<n;++i) {
            while(e<at && input[e]==i){spectrum_sound_write(&s,input[e+1]>>4,input[e+1]&15,input[e+2]);e+=3;}
            spectrum_sound_write(&s,2,0,beep?((beep[i/8]>>(i&7))&1):input[8]);
            spectrum_sound_write(&s,3,0,cv?cv[i]:input[9]);spectrum_sound_write(&s,4,0,sd?sd[i]:input[10]);
            atomic_store(&s.sound.produced,s.sound.time+140);
            const uint16_t expected=(uint16_t)spectrum_sound_render(&s);
            assert(output[8+2*i]==(uint8_t)expected && output[9+2*i]==(uint8_t)(expected>>8));
        }
        samples+=n;same_state(&s);
        unchanged_after_bad_render(&s,input,at,5,0);
        unchanged_after_bad_render(&s,input,at,5,121);
        unchanged_after_bad_render(&s,input,at,6,128);
        unchanged_after_bad_render(&s,input,at,7,128);
        unchanged_after_bad_render(&s,input,at,8,2);
    }
    /* The 16-bit PCM sequence wraps in ordinary long music playback. */
    config(&s,input);run(input,size,output,sizeof(output),0);
    memset(input,0,11);spectrum_m3_put32(input,SPECTRUM_M3_AUDIO_MAGIC);
    input[4]=SPECTRUM_M3_RENDER;input[5]=1;input[9]=input[10]=128;
    for(unsigned i=0;i<65538;++i){run(input,11,output,sizeof(output),1);assert(((unsigned)output[6]|(unsigned)output[7]<<8)==(uint16_t)i);}
    /* PROFILE leaves oscillator/filter state and sample sequence untouched.
     * The timestamp wraps during the first of eight cooperative slices. */
    init(&s);config(&s,input);run(input,size,output,sizeof(output),0);
    profile(output);for(unsigned i=4;i<SPECTRUM_M3_PROFILE_BYTES;++i)assert(!output[i]);
    memset(input,0,11);spectrum_m3_put32(input,SPECTRUM_M3_AUDIO_MAGIC);
    input[4]=SPECTRUM_M3_RENDER;input[5]=120;input[9]=input[10]=128;
    fake_time=UINT32_MAX-3;api.micros=fake_micros;
    run(input,11,output,sizeof(output),120);assert(!output[6] && !output[7]);
    for(unsigned i=0;i<120;++i) {
        s.extensions=0;atomic_store(&s.sound.produced,s.sound.time+140);
        const uint16_t sample=(uint16_t)spectrum_sound_render(&s);
        assert(output[8+2*i]==(uint8_t)sample && output[9+2*i]==(uint8_t)(sample>>8));
    }
    same_state(&s);
    uint8_t measured[SPECTRUM_M3_PROFILE_BYTES];profile(measured);
    assert(spectrum_m3_get32(measured+4)==120 && spectrum_m3_get32(measured+8)==1);
#if defined(SPECTRUM_M3_FAST_INIT) && SPECTRUM_M3_FAST_INIT>=120
    /* With the synthetic 7-us clock all eight inner chunks fit in the
     * bounded INIT turn. They are one measured slice instead of eight. */
    const unsigned slices=1,max_slice=56;
#else
    const unsigned slices=8,max_slice=7;
#endif
    assert(spectrum_m3_get32(measured+12)==slices && spectrum_m3_get32(measured+16)==56);
    assert(!spectrum_m3_get32(measured+20) && spectrum_m3_get32(measured+24)==56 && spectrum_m3_get32(measured+28)==max_slice);
    uint8_t request[8]={0};spectrum_m3_put32(request,SPECTRUM_M3_AUDIO_MAGIC);request[4]=SPECTRUM_M3_PROFILE;
    stm3_job short_profile={request,8,output,SPECTRUM_M3_PROFILE_BYTES-1,0,0};
    assert(module_entry(STM3_INIT,&api,&short_profile)==STM3_INVALID);
    short_profile.input_bytes=7;short_profile.output_capacity=sizeof(output);
    assert(module_entry(STM3_INIT,&api,&short_profile)==STM3_INVALID);
    profile(output);assert(!memcmp(output,measured,sizeof(measured)));same_state(&s);
    api.micros=NULL;input[5]=1;run(input,11,output,sizeof(output),1);assert(output[6]==1 && !output[7]);
    // Envelope pointers address a32-entry table; reject corrupt state before
    // it can reach the renderer, including the old32..63 acceptance range.
    static const unsigned bad_envelopes[]={32,63,255};
    for(unsigned chip=0;chip<2;++chip)for(unsigned i=0;i<3;++i) {
        config(&s,input);
        input[8+chip*SPECTRUM_M3_PSG_BYTES+offsetof(PSG,env_ptr)-offsetof(PSG,reg)]=(uint8_t)bad_envelopes[i];
        stm3_job bad={input,size,output,sizeof(output),0,0};
        assert(module_entry(STM3_INIT,&api,&bad)==STM3_INVALID);
    }
    config(&s,input);run(input,size,output,sizeof(output),0);
    profile(output);for(unsigned i=4;i<SPECTRUM_M3_PROFILE_BYTES;++i)assert(!output[i]);
    memset(input,0,11);spectrum_m3_put32(input,SPECTRUM_M3_AUDIO_MAGIC);input[4]=SPECTRUM_M3_RENDER;input[5]=1;
    stm3_job job={input,11,output,512,0,0};assert(module_entry(STM3_CANCEL,&api,&job)==STM3_DONE);
    assert(module_entry(STM3_FINI,&api,&job)==STM3_DONE);
    assert(module_entry(STM3_INIT,&api,&job)==STM3_INVALID);
    printf("M3 sound: %u exact local PCM samples, 512 full PSG/DC/DAC state comparisons, malformed packets unchanged, cooperative slices, sequence wrap and non-invasive render timing PASS (PSG body %zu bytes)\n",samples,(size_t)SPECTRUM_M3_PSG_BYTES);
    if(vectors){assert(!fseek(vectors,4,SEEK_SET));assert(fwrite(&vector_count,sizeof(vector_count),1,vectors)==1);assert(!fclose(vectors));}
    return 0;
}
