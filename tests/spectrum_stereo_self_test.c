#include "../examples/portable-apps/SPECTRUM/spectrum.h"
#include "../examples/portable-apps/SPECTRUM/m3_audio_protocol.h"
#include "stm3_module.h"
#include "pcm_repeat.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
uint32_t module_entry(uint32_t,const stm3_api*,stm3_job*);
static stm3_api api={STM3_ABI,sizeof(stm3_api),NULL,NULL};
static unsigned seed=0x1234abcdu;
static unsigned rnd(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static FILE* vectors;
static unsigned vector_count;
static bool recording;
static void vector(const uint8_t* in,unsigned n,const uint8_t* out,unsigned used) {
    if(!vectors || !recording || vector_count==32)return;
    const uint32_t sizes[2]={n,used};assert(fwrite(sizes,sizeof(sizes),1,vectors)==1);
    assert(fwrite(in,1,n,vectors)==n && fwrite(out,1,used,vectors)==used);++vector_count;
}
static void init(spectrum* s,unsigned chip,unsigned layout) {
    memset(s,0,sizeof(*s));s->ay.quality=1;s->ay.rate=25000;
    PSG_setVolumeMode(&s->ay,2);PSG_setClock(&s->ay,1750000);PSG_reset(&s->ay);
    s->ay2=s->ay;spectrum_sound_reset(s);spectrum_sound_configure(s,chip,layout);
    spectrum_sound_begin(s,NULL,NULL);
}
static unsigned config(const spectrum* s,uint8_t* bytes,bool pwm,unsigned gain) {
    memset(bytes,0,512);spectrum_m3_put32(bytes,SPECTRUM_M3_AUDIO_V2_MAGIC);
    bytes[5]=(uint8_t)(pwm|(s->sound_layout<<1)|(s->sound_chip<<3));
    bytes[6]=(uint8_t)gain;bytes[7]=(uint8_t)(gain>>8);
    for(unsigned i=0;i<2;++i)memcpy(bytes+8+i*SPECTRUM_M3_PSG_BYTES,
        (const uint8_t*)(i?&s->ay2:&s->ay)+offsetof(PSG,reg),SPECTRUM_M3_PSG_BYTES);
    uint8_t* tail=bytes+8+2*SPECTRUM_M3_PSG_BYTES;
    spectrum_m3_put32(tail,(uint32_t)s->sound.input);spectrum_m3_put32(tail+4,(uint32_t)s->sound.output);
    tail[8]=s->sound.beeper;tail[9]=s->sound.covox;tail[10]=s->sound.specdrum;
    for(unsigned i=0;i<6;++i)spectrum_m3_put32(tail+11+4*i,(uint32_t)s->sound.stereo[i]);
    return SPECTRUM_M3_STATE_V2_BYTES;
}
static unsigned run(uint8_t* in,unsigned n,uint8_t* out) {
    stm3_job job={in,n,out,512,0,0};uint32_t result=module_entry(STM3_INIT,&api,&job);unsigned turns=0;
    while(result==STM3_MORE){result=module_entry(STM3_STEP,&api,&job);assert(++turns<=8);}
    assert(result==STM3_DONE);
    if(in[4]==SPECTRUM_M3_RENDER && spectrum_m3_get32(out)==0x334d5750u) {
        const unsigned count=out[4];uint8_t decoded[240];const uint8_t* cursor=out+8;stm3_pcm_repeat_state previous={0x8080,0};
        for(unsigned i=0;i<count;++i){assert(stm3_pcm_repeat_next(&cursor,out+job.output_bytes,&previous));decoded[2*i]=(uint8_t)previous.previous;decoded[2*i+1]=(uint8_t)(previous.previous>>8);}
        assert(cursor==out+job.output_bytes && !previous.remaining);memcpy(out+8,decoded,2*count);spectrum_m3_put32(out,SPECTRUM_M3_STEREO_PWM_MAGIC);job.output_bytes=8+2*count;
    }
    vector(in,n,out,job.output_bytes);return job.output_bytes;
}
static void same_state(spectrum* s) {
    uint8_t in[512],actual[512],expected[512];config(s,expected,true,1000);
    spectrum_m3_put32(expected,SPECTRUM_M3_STATE_V2_MAGIC);spectrum_m3_put32(expected+4,SPECTRUM_M3_PSG_BYTES);
    memset(in,0,8);spectrum_m3_put32(in,SPECTRUM_M3_AUDIO_V2_MAGIC);in[4]=SPECTRUM_M3_EXPORT;
    assert(run(in,8,actual)==SPECTRUM_M3_STATE_V2_BYTES);
    assert(!memcmp(actual,expected,SPECTRUM_M3_STATE_V2_BYTES));
}
int main(void) {
    const char* filename=getenv("SPECTRUM_M3_VECTORS");
    if(filename){vectors=fopen(filename,"wb");assert(vectors);const uint32_t h[2]={0x31564153,0};assert(fwrite(h,sizeof(h),1,vectors)==1);}
    uint8_t input[512],output[512];unsigned samples=0,states=0;
    for(unsigned chip=0;chip<2;++chip)for(unsigned layout=0;layout<3;++layout)for(unsigned pwm=0;pwm<2;++pwm) {
        spectrum s;init(&s,chip,layout);unsigned gain=layout==2?731:1000;
        recording=layout!=0;
        // Cover all CONFIG variants in relocated ARM vectors, not just the first stream.
        const unsigned n=config(&s,input,pwm,gain);
        assert(run(input,n,output)==8 && (output[7]&32));
        for(unsigned block=0;block<128;++block) {
            if(block>1)recording=false;
            if(pwm && block>1 && block%8==0){gain=rnd()%1001;config(&s,input,true,gain);run(input,n,output);}
            const unsigned count=112,flags=7;memset(input,0,11);spectrum_m3_put32(input,SPECTRUM_M3_AUDIO_V2_MAGIC);
            input[4]=SPECTRUM_M3_RENDER;input[5]=count;s.extensions=(uint8_t)(block&15);input[6]=s.extensions;input[7]=flags;
            uint8_t* beep=input+11;memset(beep,0,14);uint8_t* covox=beep+14,*specdrum=covox+count;
            unsigned at=11+14+2*count;uint32_t expected[112];
            for(unsigned i=0;i<count;++i) {
                const uint32_t edge=s.sound.time+1;s.cpu.cyc=edge;
                const unsigned b=rnd()&1,cv=rnd()&255,sd=rnd()&255;
                beep[i/8]|=(uint8_t)(b<<(i&7));covox[i]=(uint8_t)cv;specdrum[i]=(uint8_t)sd;
                spectrum_sound_write(&s,2,0,b);spectrum_sound_write(&s,3,0,cv);spectrum_sound_write(&s,4,0,sd);
                if(!(i%4)) {
                    const unsigned device=(block>>1)&1,reg=rnd()%14,value=rnd()&255;
                    input[at++]=(uint8_t)i;input[at++]=(uint8_t)(16*device+reg);input[at++]=(uint8_t)value;
                    spectrum_sound_write(&s,device,reg,value);
                }
                s.cpu.cyc=edge+139;spectrum_sound_publish(&s);expected[i]=spectrum_sound_render(&s);
            }
            const unsigned channels=layout?2:1,width=pwm?1:2;
            assert(run(input,at,output)==8+width*channels*count);
            assert(spectrum_m3_get32(output)==(layout?(pwm?SPECTRUM_M3_STEREO_PWM_MAGIC:SPECTRUM_M3_STEREO_PCM_MAGIC):
                                                                   (pwm?SPECTRUM_M3_PWM_MAGIC:SPECTRUM_M3_PCM_MAGIC)));
            for(unsigned i=0;i<count;++i)for(unsigned c=0;c<channels;++c) {
                const int16_t pcm=(int16_t)(expected[i]>>(16*c));const unsigned offset=8+width*(i*channels+c);
                if(pwm)assert(output[offset]==(uint8_t)(128+((int32_t)pcm*(int32_t)gain)/512000));
                else assert(output[offset]==(uint8_t)pcm && output[offset+1]==(uint8_t)((uint16_t)pcm>>8));
            }
            ++states;samples+=count;
            // Limit vectors to one block and full export per configuration.
            if(block==0)same_state(&s);
            else {recording=false;same_state(&s);}
        }
        spectrum_sound_end(&s);
    }
    // Reject invalid chip/layout flags and filter values before rendering.
    spectrum s;init(&s,0,1);config(&s,input,true,1000);input[5]=7;
    stm3_job bad={input,SPECTRUM_M3_STATE_V2_BYTES,output,512,0,0};assert(module_entry(STM3_INIT,&api,&bad)==STM3_INVALID);
    config(&s,input,true,1000);spectrum_m3_put32(input+SPECTRUM_M3_STATE_BYTES,32768);
    assert(module_entry(STM3_INIT,&api,&bad)==STM3_INVALID);
    if(vectors){assert(vector_count==32 && !fseek(vectors,4,SEEK_SET));assert(fwrite(&vector_count,4,1,vectors)==1);assert(!fclose(vectors));}
    printf("Stereo module: %u exact local/native frames, %u complete state exports, AY/YM, mono/ABC/ACB, PCM16/PWM8, TurboSound and changing DACs PASS\n",samples,states);
}
