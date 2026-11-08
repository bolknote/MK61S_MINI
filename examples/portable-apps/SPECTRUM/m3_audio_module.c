/* Native Cortex-M3 module; no peripherals, heap, Flash writes or host pointers. */
#include "m3_audio_protocol.h"
#include "stm3_module.h"
#include <stdbool.h>
#include <string.h>

static PSG chips[2];
static int32_t filter_input,filter_output;
static uint8_t beeper,covox,specdrum;
static uint16_t sequence;
static uint16_t gain;
static uint8_t pwm8;
static bool configured;
static uint64_t render_us;
static uint32_t render_samples,render_jobs,render_slices,job_us,max_job_us,max_slice_us;
static unsigned event_cursor;
#if defined(SPECTRUM_M3_SILENT_BATCH) && SPECTRUM_M3_SILENT_BATCH
static bool second_idle;
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((noinline,optimize("Os")))
#endif
static bool advance_silent_second(unsigned samples) {
    PSG* p=&chips[1];
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

static void state_export(uint8_t* out) {
    spectrum_m3_put32(out,SPECTRUM_M3_STATE_MAGIC);
    spectrum_m3_put32(out+4,SPECTRUM_M3_PSG_BYTES);
    for(unsigned i=0;i<2;++i)memcpy(out+8+i*SPECTRUM_M3_PSG_BYTES,
        (const uint8_t*)&chips[i]+offsetof(PSG,reg),SPECTRUM_M3_PSG_BYTES);
    out+=8+2*SPECTRUM_M3_PSG_BYTES;
    spectrum_m3_put32(out,(uint32_t)filter_input);spectrum_m3_put32(out+4,(uint32_t)filter_output);
    out[8]=beeper;out[9]=covox;out[10]=specdrum;
}

static bool state_valid(const uint8_t* bytes) {
    /* Validate in-place through a byte copy into the existing BSS, before
     * publishing configured. The volume table always belongs to this image. */
    for(unsigned i=0;i<2;++i) {
        memset(&chips[i],0,sizeof(chips[i]));PSG_setVolumeMode(&chips[i],2);
        memcpy((uint8_t*)&chips[i]+offsetof(PSG,reg),bytes+i*SPECTRUM_M3_PSG_BYTES,SPECTRUM_M3_PSG_BYTES);
        if(chips[i].clk!=1750000 || chips[i].rate!=25000 || chips[i].quality!=1 ||
           chips[i].clk_div || chips[i].base_incr!=(1u<<24) || chips[i].realstep!=1750000 ||
           chips[i].psgstep!=200000 || chips[i].psgtime>=200000 || chips[i].env_ptr>=32 ||
           chips[i].out < -32768 || chips[i].out>32767) return false;
    }
    return true;
}

static bool render_valid(const stm3_job* job) {
    const uint8_t* p=job->input;
    const unsigned n=p[5],flags=p[7];
    if(!n || n>SPECTRUM_M3_AUDIO_SAMPLES || (p[6]&~15u) || (flags&~7u) || p[8]>1)return false;
    unsigned at=11;
    if(flags&SPECTRUM_M3_BEEPER_ARRAY)at+=(n+7)/8;
    if(flags&SPECTRUM_M3_COVOX_ARRAY)at+=n;
    if(flags&SPECTRUM_M3_SPECDRUM_ARRAY)at+=n;
    if(at>job->input_bytes || (job->input_bytes-at)%3 || job->output_capacity<8+(pwm8?1:2)*n)return false;
    unsigned previous=0;
    for(;at<job->input_bytes;at+=3) {
        if(p[at]>=n || p[at]<previous || p[at+1]>=32)return false;
        previous=p[at];
    }
    return true;
}

static uint32_t render_step(stm3_job* job) {
    const uint8_t* p=job->input;
    const unsigned n=p[5],flags=p[7],first=job->progress;
    const uint8_t* bits=NULL;const uint8_t* cv=NULL;const uint8_t* sd=NULL;
    unsigned at=11;
    if(flags&1){bits=p+at;at+=(n+7)/8;}
    if(flags&2){cv=p+at;at+=n;}
    if(flags&4){sd=p+at;at+=n;}
    at=event_cursor;
#if defined(SPECTRUM_M3_SILENT_BATCH) && SPECTRUM_M3_SILENT_BATCH
    const unsigned span=n-first<SPECTRUM_M3_SLICE_SAMPLES?n-first:SPECTRUM_M3_SLICE_SAMPLES;
    const bool silent=(p[6]&1) && second_idle && advance_silent_second(span);
#endif
    /* A bounded sample slice per cooperative turn. No state changes while
     * validating a render packet, and no callbacks into the loaded APP. */
    for(unsigned i=first;i<n && i<first+SPECTRUM_M3_SLICE_SAMPLES;++i) {
        while(at<job->input_bytes && p[at]<i)at+=3;
        while(at<job->input_bytes && p[at]==i) {
            PSG_writeReg(&chips[p[at+1]>>4],p[at+1]&15,p[at+2]);at+=3;
        }
        beeper=bits?((bits[i/8]>>(i&7))&1):p[8];covox=cv?cv[i]:p[9];specdrum=sd?sd[i]:p[10];
        int32_t sample=PSG_calc(&chips[0]);
        if(p[6]&1) {
#if defined(SPECTRUM_M3_SILENT_BATCH) && SPECTRUM_M3_SILENT_BATCH
            if(!silent)
#endif
            sample+=PSG_calc(&chips[1]);
        } else sample*=2;
        sample+=beeper?8192:0;
        if(p[6]&2)sample+=((int32_t)covox-128)*64;
        if(p[6]&4)sample+=((int32_t)specdrum-128)*64;
        int32_t output=sample-filter_input+(filter_output*255)/256;filter_input=sample;
        if(output>32767)output=32767;else if(output < -32768)output=-32768;
        filter_output=output;
        if(pwm8)job->output[8+i]=(uint8_t)(128+(output*gain)/512000);
        else {job->output[8+2*i]=(uint8_t)output;job->output[9+2*i]=(uint8_t)((uint32_t)output>>8);}
        job->progress=i+1;
    }
    event_cursor=at;
    return job->progress==n?STM3_DONE:STM3_MORE;
}

static uint32_t render_measured(const stm3_api* api,stm3_job* job,bool inline_init) {
    const uint32_t begin=api->micros?api->micros(api->context):0;
    const unsigned first=job->progress;
    uint32_t result;
    const uint32_t budget=inline_init?SPECTRUM_M3_INIT_BUDGET_US:SPECTRUM_M3_STEP_BUDGET_US;
    do {result=render_step(job);}
    while(result==STM3_MORE && budget &&
          (api->micros?api->micros(api->context)-begin<budget:inline_init));
    const uint32_t elapsed=api->micros?api->micros(api->context)-begin:0;
    render_us+=elapsed;job_us+=elapsed;render_samples+=job->progress-first;++render_slices;
    if(elapsed>max_slice_us)max_slice_us=elapsed;
    if(result==STM3_DONE){++render_jobs;if(job_us>max_job_us)max_job_us=job_us;}
    return result;
}

static void profile_export(uint8_t* out) {
    spectrum_m3_put32(out,SPECTRUM_M3_PROFILE_MAGIC);
    spectrum_m3_put32(out+4,render_samples);spectrum_m3_put32(out+8,render_jobs);
    spectrum_m3_put32(out+12,render_slices);
    spectrum_m3_put32(out+16,(uint32_t)render_us);spectrum_m3_put32(out+20,(uint32_t)(render_us>>32));
    spectrum_m3_put32(out+24,max_job_us);spectrum_m3_put32(out+28,max_slice_us);
}

#if defined(__arm__) || defined(__thumb__)
__attribute__((section(".text.module_entry"),used))
#endif
uint32_t module_entry(uint32_t op,const stm3_api* api,stm3_job* job) {
    if(!api || api->abi!=STM3_ABI || api->size!=sizeof(*api) || !job)return STM3_INVALID;
    if(op==STM3_FINI){configured=false;return STM3_DONE;}
    if(op==STM3_CANCEL)return STM3_DONE;
    if(!job->input || job->input_bytes<8 || job->input_bytes>SPECTRUM_M3_AUDIO_IO ||
       !job->output || spectrum_m3_get32(job->input)!=SPECTRUM_M3_AUDIO_MAGIC)return STM3_INVALID;
    const unsigned command=job->input[4];
    if(op==STM3_INIT) {
        job->output_bytes=job->progress=0;
        if(command==SPECTRUM_M3_CONFIG) {
            configured=false;
            const unsigned requested_gain=(unsigned)job->input[6]|(unsigned)job->input[7]<<8;
            if(job->input_bytes!=SPECTRUM_M3_STATE_BYTES || job->input[5]>1 || requested_gain>1000 ||
               job->output_capacity<8 || !state_valid(job->input+8))return STM3_INVALID;
            const uint8_t* tail=job->input+8+2*SPECTRUM_M3_PSG_BYTES;
            filter_input=(int32_t)spectrum_m3_get32(tail);filter_output=(int32_t)spectrum_m3_get32(tail+4);
            if(filter_input < -131072 || filter_input>131072 ||
               filter_output < -32768 || filter_output>32767 || tail[8]>1)return STM3_INVALID;
            beeper=tail[8];covox=tail[9];specdrum=tail[10];sequence=0;
            pwm8=job->input[5];gain=(uint16_t)requested_gain;configured=true;
            render_us=0;render_samples=render_jobs=render_slices=job_us=max_job_us=max_slice_us=0;
            spectrum_m3_put32(job->output,SPECTRUM_M3_PCM_MAGIC);spectrum_m3_put32(job->output+4,0);
            job->output[7]=10;
#if SPECTRUM_M3_STEP_BUDGET_US
            job->output[7]|=16;
#endif
#if defined(SPECTRUM_M3_FAST_INIT) && SPECTRUM_M3_FAST_INIT
            job->output[6]=SPECTRUM_M3_FAST_INIT;job->output[7]|=5;
#endif
            job->output_bytes=8;return STM3_DONE;
        }
        if(!configured)return STM3_INVALID;
        if(command==SPECTRUM_M3_EXPORT) {
            if(job->input_bytes!=8 || job->output_capacity<SPECTRUM_M3_STATE_BYTES)return STM3_INVALID;
            state_export(job->output);job->output_bytes=SPECTRUM_M3_STATE_BYTES;return STM3_DONE;
        }
        if(command==SPECTRUM_M3_PROFILE) {
            if(job->input_bytes!=8 || job->output_capacity<SPECTRUM_M3_PROFILE_BYTES)return STM3_INVALID;
            profile_export(job->output);job->output_bytes=SPECTRUM_M3_PROFILE_BYTES;return STM3_DONE;
        }
        if(command!=SPECTRUM_M3_RENDER || job->input_bytes<11 || !render_valid(job))return STM3_INVALID;
        spectrum_m3_put32(job->output,pwm8?SPECTRUM_M3_PWM_MAGIC:SPECTRUM_M3_PCM_MAGIC);
        job->output[4]=job->input[5];job->output[5]=0;job->output[6]=(uint8_t)sequence;job->output[7]=(uint8_t)(sequence>>8);++sequence;
        job->output_bytes=8+(pwm8?1:2)*job->input[5];
        event_cursor=11;
        if(job->input[7]&1)event_cursor+=(job->input[5]+7)/8;
        if(job->input[7]&2)event_cursor+=job->input[5];
        if(job->input[7]&4)event_cursor+=job->input[5];
#if defined(SPECTRUM_M3_SILENT_BATCH) && SPECTRUM_M3_SILENT_BATCH
        second_idle=true;
        for(unsigned at=event_cursor;at<job->input_bytes;at+=3)
            if(job->input[at+1]>=16){second_idle=false;break;}
#endif
        job_us=0;
#if defined(SPECTRUM_M3_FAST_INIT) && SPECTRUM_M3_FAST_INIT
        if(job->input[5]<=SPECTRUM_M3_FAST_INIT)return render_measured(api,job,true);
#endif
        return STM3_MORE;
    }
    if(op!=STM3_STEP || command!=SPECTRUM_M3_RENDER || !configured ||
       !render_valid(job) || job->progress>=job->input[5])return STM3_INVALID;
    return render_measured(api,job,false);
}
