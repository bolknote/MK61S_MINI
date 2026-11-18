/* Finite RTC/body verification and foreground-service benchmark; no settings writes. */
#include "mk61_app.h"
#include "stm3_client.h"
#include "pico_uart1.h"
#include "rtc_probe_package.h"
#include <string.h>
#define MAGIC 0x31435452u
static const mk61_app_services *svc;
static stm3_client client;
static stm3_pico_uart1 uart;
static uint8_t request[256], answer[256];
static uint32_t module_id;
static int owned;
static uint32_t micros(void *unused) { (void)unused; return *(const volatile uint32_t *)0x40054028u; }
static void line(const char *text) {
    while (*text) {
        unsigned n=(unsigned)strlen(text); if(n>128)n=128;
        svc->call(MK61_SERVICE_DEBUG_WRITE,n,0,0,(void *)text); text+=n;
    }
}
static int cmd(uint8_t op, const void *data, unsigned n, unsigned *used) {
    *used=sizeof(answer);
    return stm3_client_request(&client,op,data,n,answer,used,1000000);
}
static int upload(void) {
    unsigned used; int error=cmd(S3_HELLO,0,0,&used); if(error)return error;
    if (used!=36 || stm3_get32(answer)!=1 || stm3_get32(answer+4)!=0x70301 ||
        stm3_get32(answer+16)!=0 || stm3_get32(answer+28)!=2250000 ||
        (stm3_get32(answer+32)&(8u|32u))!=(8u|32u)) return -10;
    stm3_put32(request,sizeof(rtc_probe_package));
    error=cmd(S3_LOAD_BEGIN,request,4,&used); if(error)return error; owned=1;
    for(unsigned at=0;at<sizeof(rtc_probe_package);) {
        unsigned n=sizeof(rtc_probe_package)-at; if(n>252)n=252;
        stm3_put32(request,at); memcpy(request+4,rtc_probe_package+at,n);
        error=cmd(S3_LOAD_CHUNK,request,n+4,&used); if(error)return error;
        at+=n; if(used!=4 || stm3_get32(answer)!=at)return -11;
    }
    error=cmd(S3_LOAD_COMMIT,0,0,&used); if(error)return error;
    if(used!=4)return -12;
    module_id=stm3_get32(answer);
    return 0;
}
static int job(unsigned n, unsigned count, unsigned *slice) {
    /* The caller assembles job input at request+16. The first four words
     * are the fused START_RESULT_INPUT header; no WRITE round trip. */
    stm3_put32(request,module_id); stm3_put32(request+4,n);
    stm3_put32(request+8,800); stm3_put32(request+12,count);
    unsigned used; int error=cmd(S3_START_RESULT_INPUT,request,n+16,&used); if(error)return error;
    if(used!=8+count || !stm3_get32(answer) || stm3_get32(answer+8)!=MAGIC)return -13;
    *slice=stm3_get32(answer+4); if(*slice>2000)return -14;
    return 0;
}
#if RTC_PROBE_VERIFY
#include "rtc_probe_expected.h"
static int run(void) {
    unsigned slice, checked=0;
    for(unsigned region=0;region<3;++region) {
        const uint8_t *data=region==0?expected_boot:region==1?expected_bios:expected_metadata;
        const unsigned size=region==0?sizeof(expected_boot):region==1?sizeof(expected_bios):sizeof(expected_metadata);
        const unsigned base=region==0?0:region==1?0x2000:0xf400;
        for(unsigned at=0;at<size;) {
            unsigned n=size-at; if(n>224)n=224;
            stm3_put32(request+16,MAGIC); stm3_put32(request+20,0);
            stm3_put32(request+24,base+at); stm3_put32(request+28,n);
            memcpy(request+32,data+at,n);
            int e=job(16+n,20,&slice); if(e)return e;
            if(stm3_get32(answer+12)!=0 || stm3_get32(answer+16)!=base+at ||
               stm3_get32(answer+20)!=n || stm3_get32(answer+24)!=1)return -20;
            at+=n; checked+=n;
            mk61_api->service();
        }
    }
    char text[160]; mk61_app_snprintf(svc,text,sizeof(text),
        "RTCPROBE IDENTITY role=%s boot=%u bios=%u metadata=%u checked=%u matched=1\n",
        RTC_PROBE_ROLE,(unsigned)sizeof(expected_boot),(unsigned)sizeof(expected_bios),
        (unsigned)sizeof(expected_metadata),checked); line(text);
    unsigned equal=0;
    for(unsigned i=0;i<13;++i) {
        stm3_put32(request+16,MAGIC); stm3_put32(request+20,2);
        stm3_put32(request+24,RTC_DATE_ADDRESS); stm3_put32(request+28,RTC_TIME_ADDRESS);
        stm3_put32(request+32,RTC_CALENDAR_ADDRESS);
        int e=job(20,32,&slice); if(e)return e;
        const uint32_t crh=stm3_get32(answer+16), crl=stm3_get32(answer+20), seconds=stm3_get32(answer+24);
        const uint32_t date=stm3_get32(answer+32), time=stm3_get32(answer+36);
        const unsigned cached=(time&255u)*3600u+((time>>8)&255u)*60u+((time>>16)&255u);
        if((crh&1u) || (seconds%86400u+86400u-cached)%86400u>1u)return -21;
        if(seconds%86400u==cached)++equal;
        mk61_app_snprintf(svc,text,sizeof(text),
            "RTCPROBE CLOCK role=%s n=%u seconds=%lu cached=%u date=%08lX crh=%08lX crl=%08lX\n",
            RTC_PROBE_ROLE,i,(unsigned long)seconds,cached,(unsigned long)date,(unsigned long)crh,(unsigned long)crl); line(text);
        mk61_api->service(); mk61_api->delay_ms(173+(i*17)%61);
    }
    mk61_app_snprintf(svc,text,sizeof(text),
        "RTCPROBE CLOCK_SUMMARY role=%s equal=%u total=13\n",RTC_PROBE_ROLE,equal); line(text);
    if(equal<10)return -24;
    return 0;
}
#else
static int run(void) {
    static const unsigned counts[3]={8192,4096,256}, work[3]={0,64,4096};
    for(unsigned repetition=0;repetition<7;++repetition)for(unsigned j=0;j<3;++j) {
        const unsigned mode=(repetition&1)?2-j:j;
        stm3_put32(request+16,MAGIC); stm3_put32(request+20,1);
        stm3_put32(request+24,counts[mode]); stm3_put32(request+28,work[mode]);
        stm3_put32(request+32,0x12345678); stm3_put32(request+36,0);
        const uint32_t begin=micros(0); unsigned slice;
        int e=job(24,28,&slice); if(e)return e;
        if(stm3_get32(answer+12)!=1 || stm3_get32(answer+16)!=counts[mode] ||
           stm3_get32(answer+20)!=work[mode] || stm3_get32(answer+24)!=0x12345678 ||
           stm3_get32(answer+28)!=rtc_probe_checksums[mode])return -22;
        const uint32_t elapsed=stm3_get32(answer+32);
        if(!elapsed || elapsed>=800000u)return -23;
        char text[192]; mk61_app_snprintf(svc,text,sizeof(text),
            "RTCBENCH rep=%u mode=%u steps=%u work=%u m3_us=%lu rtt_us=%lu checksum=%08lX max_slice_us=%u\n",
            repetition,mode,counts[mode],work[mode],(unsigned long)elapsed,
            (unsigned long)(micros(0)-begin),(unsigned long)stm3_get32(answer+28),slice); line(text);
        mk61_api->service();
    }
    return 0;
}
#endif
int main(void) {
    svc=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FORMAT|MK61_SERVICE_CAP_DEBUG_IO);
    if(!svc)return MK61_APP_RUNTIME_ERROR;
    line("RTCPROBE BEGIN v=1\n");
    if(!stm3_pico_uart1_begin(&uart,micros,0,48000000,2250000)) { line("RTCPROBE FAIL code=-30\n");return MK61_APP_OK; }
    const stm3_client_io io={&uart,stm3_pico_uart1_micros,stm3_pico_uart1_send,stm3_pico_uart1_read};
    stm3_client_init(&client,&io);
    int error=upload(); if(!error)error=run();
    if(owned) { unsigned used; int e=cmd(S3_UNLOAD,0,0,&used); if(!error && e)error=e; }
    stm3_pico_uart1_end(&uart);
    char text[144]; mk61_app_snprintf(svc,text,sizeof(text),
        "RTCPROBE %s code=%d requests=%lu uart_errors=%lu\n",error?"FAIL":"PASS",error,
        (unsigned long)client.requests,(unsigned long)uart.errors); line(text);
    return MK61_APP_OK;
}
