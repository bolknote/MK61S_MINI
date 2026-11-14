/* Native Cortex-M3 module; no peripherals, heap, Flash writes or host pointers. */
#include "m3_audio_protocol.h"
#include "stm3_module.h"
#include "pcm_repeat.h"
#include <stdbool.h>
#include <string.h>
#if defined(__GNUC__) && !defined(__clang__)
#define M3_COLD __attribute__((optimize("Os")))
#else
#define M3_COLD
#endif
typedef struct {
    PSG chips[2];
    int32_t filter_input,filter_output,stereo[6];
    uint16_t sequence,gain;
    uint8_t beeper,covox,specdrum,pwm8,layout,chip_mode;
    bool configured,extended,second_idle;
    uint64_t render_us;
    uint32_t render_samples,render_jobs,render_slices,job_us,max_job_us,max_slice_us;
    unsigned event_cursor;
#if defined(SPECTRUM_M3_TIMING) && SPECTRUM_M3_TIMING
    uint32_t timing_end,timing_gap;
#endif
} sound_state;
static sound_state synth;
#if defined(SPECTRUM_M3_SILENT_BATCH) && SPECTRUM_M3_SILENT_BATCH
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((noinline,optimize("Os")))
#endif
static bool advance_silent_second(unsigned samples) {
    PSG* p=&synth.chips[1];
    if(synth.layout && (synth.stereo[2] || synth.stereo[3]))return false;
    if(p->out || (p->volume[0]|p->volume[1]|p->volume[2]))return false;
    // Valid phases do not wrap their narrow counters before a period edge.
    // Keep unusual imported states on the ordinary per-sample path.
    for(unsigned i=0;i<3;++i)if(p->freq[i] && p->count[i]>=p->freq[i])return false;
    if((p->noise_freq && p->noise_count>=p->noise_freq) ||
       (p->env_freq && p->env_count>=p->env_freq))return false;
    // CONFIG guarantees this clock/rate and quality=1. With zero output and
    // volumes, merging samples preserves every counter/LFSR/envelope phase.
    p->realstep=1750000u*samples;(void)PSG_calc(p);p->realstep=1750000u;return true;
}
#endif

static M3_COLD void state_export(uint8_t* out) {
    spectrum_m3_put32(out,synth.extended?SPECTRUM_M3_STATE_V2_MAGIC:SPECTRUM_M3_STATE_MAGIC);
    spectrum_m3_put32(out+4,SPECTRUM_M3_PSG_BYTES);
    for(unsigned i=0;i<2;++i)memcpy(out+8+i*SPECTRUM_M3_PSG_BYTES,
        (const uint8_t*)&synth.chips[i]+offsetof(PSG,reg),SPECTRUM_M3_PSG_BYTES);
    out+=8+2*SPECTRUM_M3_PSG_BYTES;
    spectrum_m3_put32(out,(uint32_t)synth.filter_input);spectrum_m3_put32(out+4,(uint32_t)synth.filter_output);
    out[8]=synth.beeper;out[9]=synth.covox;out[10]=synth.specdrum;
    if(synth.extended)for(unsigned i=0;i<6;++i)spectrum_m3_put32(out+11+4*i,(uint32_t)synth.stereo[i]);
}

static M3_COLD bool state_valid(const uint8_t* bytes) {
    /* Validate in-place through a byte copy into the existing BSS, before
     * publishing synth.configured. The volume table always belongs to this image. */
    for(unsigned i=0;i<2;++i) {
        memset(&synth.chips[i],0,sizeof(synth.chips[i]));PSG_setVolumeMode(&synth.chips[i],synth.chip_mode?1:2);
        memcpy((uint8_t*)&synth.chips[i]+offsetof(PSG,reg),bytes+i*SPECTRUM_M3_PSG_BYTES,SPECTRUM_M3_PSG_BYTES);
        if(synth.chips[i].clk!=1750000 || synth.chips[i].rate!=25000 || synth.chips[i].quality!=1 ||
           synth.chips[i].clk_div || synth.chips[i].base_incr!=(1u<<24) || synth.chips[i].realstep!=1750000 ||
           synth.chips[i].psgstep!=200000 || synth.chips[i].psgtime>=200000 || synth.chips[i].env_ptr>=32 ||
           synth.chips[i].out < -32768 || synth.chips[i].out>32767) return false;
    }
    return true;
}

static M3_COLD bool render_valid(const stm3_job* job) {
    const uint8_t* p=job->input;
    const unsigned n=p[5],flags=p[7];
    if(!n || n>SPECTRUM_M3_AUDIO_SAMPLES || (p[6]&~15u) || (flags&~7u) || p[8]>1)return false;
    unsigned at=11;
    if(flags&SPECTRUM_M3_BEEPER_ARRAY)at+=(n+7)/8;
    if(flags&SPECTRUM_M3_COVOX_ARRAY)at+=n;
    if(flags&SPECTRUM_M3_SPECDRUM_ARRAY)at+=n;
    if(at>job->input_bytes || (job->input_bytes-at)%3 || job->output_capacity<8+(synth.pwm8?1:2)*(synth.layout?2:1)*n)return false;
    unsigned previous=0;
    for(;at<job->input_bytes;at+=3) {
        if(p[at]>=n || p[at]<previous || p[at+1]>=32)return false;
        previous=p[at];
    }
    return true;
}

static inline uint8_t pwm_duty(int32_t sample,unsigned gain) {
    // The physical volume wheel leaves digital gain at unity. Keep exact
    // truncation toward zero, including negative PCM, for legacy gains too.
#if defined(SPECTRUM_M3_TIMING) && SPECTRUM_M3_TIMING
    return (uint8_t)(128+(sample*(int32_t)gain)/512000);
#else
    return (uint8_t)(128+(gain==1000?sample/512:(sample*(int32_t)gain)/512000));
#endif
}

static inline int32_t clamp_pcm16(int32_t value) {
#if defined(__ARM_ARCH_7M__) || defined(__ARM_ARCH_7EM__)
    __asm__ ("ssat %0, #16, %0" : "+r"(value));
    return value;
#else
    return value>32767?32767:value < -32768?-32768:value;
#endif
}


M3_COLD static uint32_t render_step(stm3_job* restrict job) {
    // Resident input/output arenas and module state are disjoint. Keeping
    // this contract explicit lets M3 retain mixer constants across stores.
    const uint8_t* restrict p=job->input;
    uint8_t* restrict output_bytes=job->output;
    const unsigned n=p[5],flags=p[7],first=job->progress;
    const uint8_t* bits=NULL;const uint8_t* cv=NULL;const uint8_t* sd=NULL;
    unsigned at=11;
    if(flags&1){bits=p+at;at+=(n+7)/8;}
    if(flags&2){cv=p+at;at+=n;}
    if(flags&4){sd=p+at;at+=n;}
    at=synth.event_cursor;
    // Cursors, fixed mixer mode and filter state belong to this slice.
    // Only the PCM and PSG register writes are needed inside the loop.
    const unsigned extensions=p[6],layout=synth.layout,pwm8=synth.pwm8,gain=synth.gain;
    const unsigned bytes=job->input_bytes;
    const unsigned stride=(pwm8?1u:2u)*(layout?2u:1u);
    const unsigned end=n-first<SPECTRUM_M3_SLICE_SAMPLES?n:first+SPECTRUM_M3_SLICE_SAMPLES;
    uint8_t* out=output_bytes+8+first*stride;
    int32_t prev_l=synth.filter_input,prev_r=synth.stereo[4];
    int32_t dc_l=synth.filter_output,dc_r=synth.stereo[5];
    uint8_t beeper=p[8],covox=p[9],specdrum=p[10];
#if defined(SPECTRUM_M3_SILENT_BATCH) && SPECTRUM_M3_SILENT_BATCH
    const unsigned span=n-first<SPECTRUM_M3_SLICE_SAMPLES?n-first:SPECTRUM_M3_SLICE_SAMPLES;
    const bool silent=(p[6]&1) && synth.second_idle && advance_silent_second(span);
#endif
    /* A bounded sample slice per cooperative turn. */
    for(unsigned i=first;i<end;++i,out+=stride) {
        while(at<bytes && p[at]==i) {
            PSG_writeReg(&synth.chips[p[at+1]>>4],p[at+1]&15,p[at+2]);at+=3;
        }
        if(bits)beeper=(bits[i/8]>>(i&7))&1u;
        if(cv)covox=cv[i];
        if(sd)specdrum=sd[i];
        int32_t left,right;
        if(layout){PSG_calcStereo(&synth.chips[0],synth.stereo,layout);left=synth.stereo[0];right=synth.stereo[1];}
        else left=right=PSG_calc(&synth.chips[0]);
        if(extensions&1u) {
#if defined(SPECTRUM_M3_SILENT_BATCH) && SPECTRUM_M3_SILENT_BATCH
            if(!silent) {
#endif
                if(layout){PSG_calcStereo(&synth.chips[1],synth.stereo+2,layout);left+=synth.stereo[2];right+=synth.stereo[3];}
                else {const int32_t value=PSG_calc(&synth.chips[1]);left+=value;right+=value;}
#if defined(SPECTRUM_M3_SILENT_BATCH) && SPECTRUM_M3_SILENT_BATCH
            }
#endif
        } else {left*=2;right*=2;}
        int32_t common=(int32_t)beeper*8192;
        if(extensions&2u)common+=((int32_t)covox-128)*64;
        if(extensions&4u)common+=((int32_t)specdrum-128)*64;
        left+=common;right+=common;
        dc_l=left-prev_l+(dc_l*255)/256;prev_l=left;
        dc_l=clamp_pcm16(dc_l);
        if(layout) {
            dc_r=right-prev_r+(dc_r*255)/256;prev_r=right;
            dc_r=clamp_pcm16(dc_r);
        }
        if(pwm8) {
            out[0]=pwm_duty(dc_l,gain);
            if(layout)out[1]=pwm_duty(dc_r,gain);
        } else {
            out[0]=(uint8_t)dc_l;out[1]=(uint8_t)((uint32_t)dc_l>>8);
            if(layout){out[2]=(uint8_t)dc_r;out[3]=(uint8_t)((uint32_t)dc_r>>8);}
        }
    }
    synth.filter_input=prev_l;synth.filter_output=dc_l;synth.stereo[4]=prev_r;synth.stereo[5]=dc_r;
    synth.beeper=beeper;synth.covox=covox;synth.specdrum=specdrum;synth.event_cursor=at;job->progress=end;
    return job->progress==n?STM3_DONE:STM3_MORE;
}

#if defined(SPECTRUM_M3_REPEAT) && SPECTRUM_M3_REPEAT
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((noinline,optimize("Os")))
#endif
static void pack_repeat(stm3_job* job) {
    const unsigned n=job->input[5];
    if(!synth.pwm8 || !synth.layout || job->output_capacity<256+2*n)return;
    const unsigned used=stm3_pcm_repeat_encode(job->output+256,job->output+8,n);
    if(used && used<2*n) {
        memcpy(job->output+8,job->output+256,used);
        spectrum_m3_put32(job->output,0x334d5750u);job->output_bytes=8+used;
    }
}
#endif

#if defined(SPECTRUM_M3_TIMING) && SPECTRUM_M3_TIMING
static M3_COLD void timing_export(stm3_job* job) {
    unsigned compute=(synth.job_us+15)/16,gap=(synth.timing_gap+15)/16;
    job->output[5]=(uint8_t)(compute>255?255:compute);
    job->output[7]=(uint8_t)(gap>255?255:gap);
}
#endif

#if defined(SPECTRUM_M3_TIMING) && SPECTRUM_M3_TIMING
#define M3_TIMING_COLD M3_COLD
#else
#define M3_TIMING_COLD
#endif
static M3_TIMING_COLD uint32_t render_measured(const stm3_api* api,stm3_job* job,bool inline_init) {
    const uint32_t begin=api->micros?api->micros(api->context):0;
#if defined(SPECTRUM_M3_TIMING) && SPECTRUM_M3_TIMING
    if(inline_init)synth.timing_gap=0;
    else synth.timing_gap+=begin-synth.timing_end;
#endif
    const unsigned first=job->progress;
    uint32_t result;
    const uint32_t budget=inline_init?SPECTRUM_M3_INIT_BUDGET_US:SPECTRUM_M3_STEP_BUDGET_US;
    do {result=render_step(job);}
    while(result==STM3_MORE && budget &&
          (api->micros?api->micros(api->context)-begin<budget:inline_init));
    const uint32_t elapsed=api->micros?api->micros(api->context)-begin:0;
#if defined(SPECTRUM_M3_TIMING) && SPECTRUM_M3_TIMING
    synth.timing_end=begin+elapsed;
#endif
    synth.render_us+=elapsed;synth.job_us+=elapsed;synth.render_samples+=job->progress-first;++synth.render_slices;
    if(elapsed>synth.max_slice_us)synth.max_slice_us=elapsed;
    if(result==STM3_DONE){++synth.render_jobs;if(synth.job_us>synth.max_job_us)synth.max_job_us=synth.job_us;}
#if defined(SPECTRUM_M3_TIMING) && SPECTRUM_M3_TIMING
    if(result==STM3_DONE)timing_export(job);
#endif
#if defined(SPECTRUM_M3_REPEAT) && SPECTRUM_M3_REPEAT
    if(result==STM3_DONE)pack_repeat(job);
#endif
    return result;
}

static M3_COLD void profile_export(uint8_t* out) {
    spectrum_m3_put32(out,SPECTRUM_M3_PROFILE_MAGIC);
    spectrum_m3_put32(out+4,synth.render_samples);spectrum_m3_put32(out+8,synth.render_jobs);
    spectrum_m3_put32(out+12,synth.render_slices);
    spectrum_m3_put32(out+16,(uint32_t)synth.render_us);spectrum_m3_put32(out+20,(uint32_t)(synth.render_us>>32));
    spectrum_m3_put32(out+24,synth.max_job_us);spectrum_m3_put32(out+28,synth.max_slice_us);
}

#if defined(__arm__) || defined(__thumb__)
__attribute__((section(".text.module_entry"),used))
#endif
M3_COLD uint32_t module_entry(uint32_t op,const stm3_api* api,stm3_job* job) {
    if(!api || api->abi!=STM3_ABI || api->size!=sizeof(*api) || !job)return STM3_INVALID;
    if(op==STM3_FINI){synth.configured=false;return STM3_DONE;}
    if(op==STM3_CANCEL)return STM3_DONE;
    if(!job->input || job->input_bytes<8 || job->input_bytes>SPECTRUM_M3_AUDIO_IO ||
       !job->output || (spectrum_m3_get32(job->input)!=SPECTRUM_M3_AUDIO_MAGIC &&
                       spectrum_m3_get32(job->input)!=SPECTRUM_M3_AUDIO_V2_MAGIC))return STM3_INVALID;
    const unsigned command=job->input[4];
    if(op==STM3_INIT) {
        job->output_bytes=job->progress=0;
        if(command==SPECTRUM_M3_CONFIG) {
            synth.configured=false;
            synth.extended=spectrum_m3_get32(job->input)==SPECTRUM_M3_AUDIO_V2_MAGIC;
            const unsigned format=job->input[5];
            synth.layout=synth.extended?((format>>1)&3):0;synth.chip_mode=synth.extended?((format>>3)&1):0;
            const unsigned requested_gain=(unsigned)job->input[6]|(unsigned)job->input[7]<<8;
            if(job->input_bytes!=(synth.extended?SPECTRUM_M3_STATE_V2_BYTES:SPECTRUM_M3_STATE_BYTES) ||
               format>(synth.extended?15u:1u) || synth.layout>2 || requested_gain>1000 ||
               job->output_capacity<8 || !state_valid(job->input+8))return STM3_INVALID;
            const uint8_t* tail=job->input+8+2*SPECTRUM_M3_PSG_BYTES;
            synth.filter_input=(int32_t)spectrum_m3_get32(tail);synth.filter_output=(int32_t)spectrum_m3_get32(tail+4);
            if(synth.filter_input < -131072 || synth.filter_input>131072 ||
               synth.filter_output < -32768 || synth.filter_output>32767 || tail[8]>1)return STM3_INVALID;
            synth.beeper=tail[8];synth.covox=tail[9];synth.specdrum=tail[10];synth.sequence=0;
            memset(synth.stereo,0,sizeof(synth.stereo));
            if(synth.extended)for(unsigned i=0;i<6;++i) {
                synth.stereo[i]=(int32_t)spectrum_m3_get32(tail+11+4*i);
                const int32_t limit=i==4?131072:32768;
                if(synth.stereo[i]<-limit || synth.stereo[i]>=limit)return STM3_INVALID;
            }
            synth.pwm8=format&1;synth.gain=(uint16_t)requested_gain;synth.configured=true;
            synth.render_us=0;synth.render_samples=synth.render_jobs=synth.render_slices=synth.job_us=synth.max_job_us=synth.max_slice_us=0;
            spectrum_m3_put32(job->output,SPECTRUM_M3_PCM_MAGIC);spectrum_m3_put32(job->output+4,0);
            job->output[7]=10;
#if defined(SPECTRUM_M3_REPEAT) && SPECTRUM_M3_REPEAT
            job->output[7]|=128;
#endif
#if defined(SPECTRUM_M3_TIMING) && SPECTRUM_M3_TIMING
            job->output[7]|=64;
#endif
            if(synth.extended)job->output[7]|=32;
#if SPECTRUM_M3_STEP_BUDGET_US
            job->output[7]|=16;
#endif
#if defined(SPECTRUM_M3_FAST_INIT) && SPECTRUM_M3_FAST_INIT
            job->output[6]=SPECTRUM_M3_FAST_INIT;job->output[7]|=5;
#endif
            job->output_bytes=8;return STM3_DONE;
        }
        if(!synth.configured || (spectrum_m3_get32(job->input)==SPECTRUM_M3_AUDIO_V2_MAGIC)!=synth.extended)return STM3_INVALID;
        if(command==SPECTRUM_M3_EXPORT) {
            const unsigned size=synth.extended?SPECTRUM_M3_STATE_V2_BYTES:SPECTRUM_M3_STATE_BYTES;
            if(job->input_bytes!=8 || job->output_capacity<size)return STM3_INVALID;
            state_export(job->output);job->output_bytes=size;return STM3_DONE;
        }
        if(command==SPECTRUM_M3_PROFILE) {
            if(job->input_bytes!=8 || job->output_capacity<SPECTRUM_M3_PROFILE_BYTES)return STM3_INVALID;
            profile_export(job->output);job->output_bytes=SPECTRUM_M3_PROFILE_BYTES;return STM3_DONE;
        }
        if(command!=SPECTRUM_M3_RENDER || job->input_bytes<11 || !render_valid(job))return STM3_INVALID;
        spectrum_m3_put32(job->output,synth.layout?(synth.pwm8?SPECTRUM_M3_STEREO_PWM_MAGIC:SPECTRUM_M3_STEREO_PCM_MAGIC):
                                                     (synth.pwm8?SPECTRUM_M3_PWM_MAGIC:SPECTRUM_M3_PCM_MAGIC));
        job->output[4]=job->input[5];job->output[5]=0;job->output[6]=(uint8_t)synth.sequence;job->output[7]=(uint8_t)(synth.sequence>>8);++synth.sequence;
        job->output_bytes=8+(synth.pwm8?1:2)*(synth.layout?2:1)*job->input[5];
        synth.event_cursor=11;
        if(job->input[7]&1)synth.event_cursor+=(job->input[5]+7)/8;
        if(job->input[7]&2)synth.event_cursor+=job->input[5];
        if(job->input[7]&4)synth.event_cursor+=job->input[5];
#if defined(SPECTRUM_M3_SILENT_BATCH) && SPECTRUM_M3_SILENT_BATCH
        synth.second_idle=true;
        for(unsigned at=synth.event_cursor;at<job->input_bytes;at+=3)
            if(job->input[at+1]>=16){synth.second_idle=false;break;}
#endif
        synth.job_us=0;
#if defined(SPECTRUM_M3_TIMING) && SPECTRUM_M3_TIMING
        synth.timing_gap=0;synth.timing_end=api->micros?api->micros(api->context):0;
#endif
#if defined(SPECTRUM_M3_FAST_INIT) && SPECTRUM_M3_FAST_INIT
        if(job->input[5]<=SPECTRUM_M3_FAST_INIT)return render_measured(api,job,true);
#endif
        return STM3_MORE;
    }
    if(op!=STM3_STEP || command!=SPECTRUM_M3_RENDER || !synth.configured ||
       (spectrum_m3_get32(job->input)==SPECTRUM_M3_AUDIO_V2_MAGIC)!=synth.extended ||
       !render_valid(job) || job->progress>=job->input[5])return STM3_INVALID;
    return render_measured(api,job,false);
}
