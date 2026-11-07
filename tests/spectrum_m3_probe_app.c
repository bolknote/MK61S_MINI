/* Finite real-DSP qualification. No PWM, firmware, RTC or settings writes. */
#include "mk61_app.h"
#include "stm3_client.h"
#include "pico_uart1.h"
#include "module_package.h"
#include "sound_vectors.h"
#include "spectrum_m3_probe_input.h"
#include <string.h>
static const mk61_app_services* svc;
static stm3_client client;
static stm3_pico_uart1 uart;
static uint8_t input[512],request[256],answer[256];
static uint32_t module_id,job_id;
static int owned;
#ifndef S3_SOUND_PUSH
#define S3_SOUND_PUSH 1
#endif
#if !S3_SOUND_PUSH
static int fast_init;
#endif
static uint32_t micros(void* p){(void)p;return *(volatile uint32_t*)(uintptr_t)0x40054028u;}
static void line(const char* p) {
    while(*p){unsigned n=(unsigned)strlen(p);if(n>128)n=128;svc->call(MK61_SERVICE_DEBUG_WRITE,n,0,0,(void*)p);p+=n;}
}
static int cmd(unsigned op,const void* in,unsigned n,unsigned* used) {
    *used=sizeof(answer);return stm3_client_request(&client,(uint8_t)op,in,n,answer,used,100000);
}
static int upload(void) {
    unsigned used;int error=cmd(S3_HELLO,NULL,0,&used);if(error)return error;
    if(used!=36 || stm3_get32(answer)!=1 || stm3_get32(answer+4)!=0x70301 ||
       stm3_get32(answer+8)!=6144 || stm3_get32(answer+12)!=512 || stm3_get32(answer+16)!=0 ||
       stm3_get32(answer+28)!=2250000 || (stm3_get32(answer+32)&(S3_SOUND_PUSH?7u:3u))!=(S3_SOUND_PUSH?7u:3u))return -10;
    stm3_put32(request,sizeof(stm3_package));error=cmd(S3_LOAD_BEGIN,request,4,&used);if(error)return error;owned=1;
    for(unsigned at=0;at<sizeof(stm3_package);) {
        unsigned n=(unsigned)sizeof(stm3_package)-at;if(n>252)n=252;
        stm3_put32(request,at);memcpy(request+4,stm3_package+at,n);error=cmd(S3_LOAD_CHUNK,request,n+4,&used);if(error)return error;
        at+=n;if(used!=4 || stm3_get32(answer)!=at)return -11;
    }
    error=cmd(S3_LOAD_COMMIT,NULL,0,&used);if(error)return error;if(used!=4)return -12;module_id=stm3_get32(answer);return 0;
}
static int job(const uint8_t* in,unsigned n,unsigned expected,unsigned* slice) {
    unsigned used;int error;const unsigned operation=in[4];
    for(unsigned at=0;at<n;) {
        unsigned count=n-at;if(count>252)count=252;stm3_put32(request,at);memcpy(request+4,in+at,count);
        error=cmd(S3_WRITE,request,count+4,&used);if(error)return error;at+=count;
    }
#if S3_SOUND_PUSH
    unsigned received=expected;if(received>S3_RESULT_LIMIT)received=S3_RESULT_LIMIT;
    stm3_put32(request,module_id);stm3_put32(request+4,n);stm3_put32(request+8,10);stm3_put32(request+12,received);
    error=cmd(S3_START_RESULT,request,16,&used);if(error)return error;
    if(used!=8+received || !stm3_get32(answer))return -13;
    job_id=stm3_get32(answer);const unsigned maximum=stm3_get32(answer+4);if(maximum>*slice)*slice=maximum;
    if(maximum>2000)return -15;
    memcpy(input,answer+8,received);
    for(unsigned at=received;at<expected;) {
        unsigned take=expected-at;if(take>252)take=252;
        stm3_put32(request,job_id);stm3_put32(request+4,at);stm3_put32(request+8,take);
        error=cmd(S3_READ,request,12,&used);if(error)return error;
        if(used!=take)return -17;
        memcpy(input+at,answer,take);at+=take;
    }
    memcpy(answer,input,expected);used=expected;
#else
    stm3_put32(request,module_id);stm3_put32(request+4,n);stm3_put32(request+8,100);
    error=cmd(S3_START,request,12,&used);if(error)return error;if(used!=4)return -13;job_id=stm3_get32(answer);
    unsigned finished=(expected!=8 && fast_init);
#if defined(S3_SOUND_DIRECT_READ) && S3_SOUND_DIRECT_READ
    finished=expected!=8 && (job_id&63)!=0;
#endif
    if(finished && (job_id&15)==0)finished=0; /* Sample timing; overrun is always enforced by resident. */
    for(unsigned polls=0;polls<100;++polls) {
        if(finished)break;
        stm3_put32(request,job_id);error=cmd(S3_STATUS,request,4,&used);if(error)return error;
        if(used!=28 || stm3_get32(answer)!=job_id)return -14;
        const unsigned state=stm3_get32(answer+4),max=stm3_get32(answer+24);if(max>*slice)*slice=max;
        if(state==4){finished=1;break;}if(state!=3)return -15;
    }
    if(!finished)return -16;
    for(unsigned tries=0;tries<64;++tries) {
        stm3_put32(request,job_id);stm3_put32(request+4,0);stm3_put32(request+8,expected);
        error=cmd(S3_READ,request,12,&used);
        if(error==2 && finished){if(tries==63)return -41;continue;}
        if(error)return error;
        break;
    }
#endif
    const uint32_t magic=operation==3?0x31504153u:(expected==8?0x314d4350u:M3_SOUND_OUTPUT_MAGIC);
    if(used!=expected || stm3_get32(answer)!=magic)return -17;
    return 0;
}
static int measure(void) {
    static const char*const names[3]={"TONE3","TURBO_ENV_NOISE","DAC_DENSE"};
    int error=upload();if(error)return error;
    for(unsigned mode=0;mode<3;++mode) {
        unsigned slice=0;error=job(sound_configs[mode],sizeof(sound_configs[mode]),8,&slice);if(error)return error;
#if !S3_SOUND_PUSH
        fast_init=(answer[7]&1) && !(answer[7]&4) && answer[6]>=M3_SOUND_FRAMES;
#endif
        const unsigned has_profile=answer[7]&8;
        uint32_t crc=~0u;const uint32_t begin=micros(NULL),tx=client.sent,rx=client.received,requests=client.requests;
        for(unsigned b=0;b<M3_SOUND_BLOCKS;++b) {
            const unsigned n=m3_sound_probe_packet(mode,b,input);error=job(input,n,M3_SOUND_OUTPUT_BYTES,&slice);if(error)return error;
            if(answer[4]!=M3_SOUND_FRAMES || answer[5] || ((unsigned)answer[6]|(unsigned)answer[7]<<8)!=b)return -18;
            for(unsigned i=0;i<M3_SOUND_OUTPUT_BYTES;++i){crc^=answer[i];for(unsigned k=0;k<8;++k)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1)));}
            if(mk61_api->key_poll()==MK61_APP_KEY_ESC)return -27;
        }
        if((~crc)!=sound_expected_crc[mode])return -19;
        char text[240];mk61_app_snprintf(svc,text,sizeof(text),
            "S3SOUND MODE=%s blocks=%u samples=%u us=%lu max_slice_us=%u requests=%lu tx=%lu rx=%lu pcm_crc=%08lX uart_errors=%lu\n",
            names[mode],M3_SOUND_BLOCKS,M3_SOUND_BLOCKS*M3_SOUND_FRAMES,(unsigned long)(micros(NULL)-begin),slice,
            (unsigned long)(client.requests-requests),(unsigned long)(client.sent-tx),(unsigned long)(client.received-rx),
            (unsigned long)(~crc),(unsigned long)uart.errors);line(text);
        if(has_profile) {
            const uint8_t profile[8]={'S','A','Y','1',3,0,0,0};
            error=job(profile,sizeof(profile),32,&slice);if(error)return error;
            mk61_app_snprintf(svc,text,sizeof(text),
                "S3DSP MODE=%s samples=%lu jobs=%lu slices=%lu render_us_lo=%lu render_us_hi=%lu max_job_us=%lu max_slice_us=%lu\n",
                names[mode],(unsigned long)stm3_get32(answer+4),(unsigned long)stm3_get32(answer+8),
                (unsigned long)stm3_get32(answer+12),(unsigned long)stm3_get32(answer+16),(unsigned long)stm3_get32(answer+20),
                (unsigned long)stm3_get32(answer+24),(unsigned long)stm3_get32(answer+28));line(text);
        }
    }
    return 0;
}
int main(void) {
    svc=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FORMAT|MK61_SERVICE_CAP_DEBUG_IO);if(!svc)return MK61_APP_RUNTIME_ERROR;
    line(S3_SOUND_PUSH?"S3SOUND BEGIN v=3 rate=25000 no_pwm=1 completion=push\n":"S3SOUND BEGIN v=3 rate=25000 no_pwm=1 completion=legacy\n");
    if(!stm3_pico_uart1_begin(&uart,micros,NULL,48000000,2250000)){line("S3SOUND FAIL code=-30\n");return MK61_APP_OK;}
    const stm3_client_io io={&uart,stm3_pico_uart1_micros,stm3_pico_uart1_send,stm3_pico_uart1_read};stm3_client_init(&client,&io);
    int error;unsigned used;
#if defined(S3_SOUND_AUDIT_ONLY) && S3_SOUND_AUDIT_ONLY
    (void)measure;
    error=cmd(S3_HELLO,NULL,0,&used);
    if(!error && (used!=36 || stm3_get32(answer)!=1 || stm3_get32(answer+4)!=0x70301 || stm3_get32(answer+16)!=0))error=-40;
    if(!error)line("S3SOUND AUDIT module=EMPTY\n");
#else
    error=measure();
#endif
    if(owned) {
        if(job_id){stm3_put32(request,job_id);(void)cmd(S3_CANCEL,request,4,&used);}
        int e=cmd(S3_UNLOAD,NULL,0,&used);if(!error && e)error=e;
        if(!e){e=cmd(S3_HELLO,NULL,0,&used);if(!error && (e || used!=36 || stm3_get32(answer+16)!=0))error=-20;}
    }
    stm3_pico_uart1_end(&uart);char text[128];mk61_app_snprintf(svc,text,sizeof(text),"S3SOUND %s code=%d requests=%lu uart_errors=%lu\n",error?"FAIL":"PASS",error,(unsigned long)client.requests,(unsigned long)uart.errors);line(text);
    return MK61_APP_OK;
}
