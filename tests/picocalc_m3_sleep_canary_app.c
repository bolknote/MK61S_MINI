/* Finite sleep/resume probe: automatic stack/global/PSRAM validation.
 * The first normal wake intentionally omits resident service for 2.5 s to
 * exercise expiry of the M3 lease. It does not power off or reset either MCU. */
#include "mk61_app.h"
#include "stm3_client.h"
#include "pico_uart1.h"
#include "rtc_probe_package.h"
#include "sleep_probe_config.h"
#include <string.h>
#define MAGIC 0x31435452u
static const mk61_app_services *svc;
static stm3_client client;
static stm3_pico_uart1 uart;
static unsigned owned;
static uint32_t module_id;
static uint8_t request[256],answer[256];
static volatile uint32_t globals[256];
typedef struct { uint32_t waits,us,expired; } Counters;
static uint8_t pattern(unsigned at) { return (uint8_t)(at*37u^(at>>8)*0x5bu^0x6du); }
static uint32_t micros(void *unused) { (void)unused;return *(const volatile uint32_t *)0x40054028u; }
static void line(const char *text) {
    while(*text) { unsigned n=(unsigned)strlen(text);if(n>128)n=128;
        svc->call(MK61_SERVICE_DEBUG_WRITE,n,0,0,(void *)text);text+=n; }
}
static int cmd(unsigned op,const void *data,unsigned n,unsigned *used) {
    *used=sizeof(answer);return stm3_client_request(&client,op,data,n,answer,used,1000000);
}
static int load(void) {
    if(owned) return 0;
    if(!stm3_pico_uart1_begin(&uart,micros,0,48000000,2250000))return -1;
    const stm3_client_io io={&uart,stm3_pico_uart1_micros,stm3_pico_uart1_send,stm3_pico_uart1_read};
    stm3_client_init(&client,&io);unsigned used;
    int e=cmd(S3_HELLO,0,0,&used);if(e)return e;
    if(used!=36 || stm3_get32(answer+16)!=0 || stm3_get32(answer+28)!=2250000)return -2;
    stm3_put32(request,sizeof(rtc_probe_package));e=cmd(S3_LOAD_BEGIN,request,4,&used);if(e)return e;owned=1;
    for(unsigned at=0;at<sizeof(rtc_probe_package);) {
        unsigned n=sizeof(rtc_probe_package)-at;if(n>252)n=252;
        stm3_put32(request,at);memcpy(request+4,rtc_probe_package+at,n);
        e=cmd(S3_LOAD_CHUNK,request,n+4,&used);if(e)return e;at+=n;
        if(used!=4 || stm3_get32(answer)!=at)return -3;
    }
    e=cmd(S3_LOAD_COMMIT,0,0,&used);if(e)return e;if(used!=4)return -4;
    module_id=stm3_get32(answer);return 0;
}
static int unload(void) {
    int e=0;unsigned used;if(owned)e=cmd(S3_UNLOAD,0,0,&used);
    owned=0;stm3_pico_uart1_end(&uart);return e;
}
static int counters(Counters *out) {
    int e=load();if(e)return e;
    stm3_put32(request,module_id);stm3_put32(request+4,20);stm3_put32(request+8,800);stm3_put32(request+12,32);
    stm3_put32(request+16,MAGIC);stm3_put32(request+20,2);
    stm3_put32(request+24,SLEEP_STATS_ADDRESS);stm3_put32(request+28,SLEEP_STATS_ADDRESS+4);
    stm3_put32(request+32,SLEEP_STATS_ADDRESS+8);unsigned used;
    e=cmd(S3_START_RESULT_INPUT,request,36,&used);if(e)return e;
    if(used!=40 || stm3_get32(answer+8)!=MAGIC || stm3_get32(answer+12)!=2)return -5;
    out->expired=stm3_get32(answer+28);out->waits=stm3_get32(answer+32);out->us=stm3_get32(answer+36);
    return SLEEP_KEEP_MODULE?0:unload();
}
static int run(void) {
    volatile uint32_t stack[128];uint8_t bytes[128];mk61_service_buffer external;
    for(unsigned i=0;i<128;++i) stack[i]=i*0x9e3779b9u^0xc61a5aa5u;
    for(unsigned i=0;i<256;++i) globals[i]=~(i*0x9e3779b9u^0xc61a5aa5u);
    if(!mk61_app_buffer_acquire(svc,4096,MK61_BUFFER_EXTERNAL,&external) || external.storage!=MK61_BUFFER_PSRAM)return -6;
    for(unsigned at=0;at<4096;at+=sizeof(bytes)) {
        for(unsigned i=0;i<sizeof(bytes);++i) bytes[i]=pattern(at+i);
        if(!mk61_app_buffer_write(svc,external.handle,at,bytes,sizeof(bytes)))return -7;
    }
    Counters initial;int error=counters(&initial);if(error)return error;
    char text[240];mk61_app_snprintf(svc,text,sizeof(text),
        "SLEEPCAN READY hold=%u stack=512 globals=1024 psram=4096 waits=%lu us=%lu expired=%lu\n",
        SLEEP_KEEP_MODULE,(unsigned long)initial.waits,(unsigned long)initial.us,(unsigned long)initial.expired);line(text);
    const uint32_t start=micros(0);uint32_t checkpoint=start;unsigned cycles=0;
    while((uint32_t)(micros(0)-start)<45000000u && cycles<2) {
        mk61_api->service();const uint32_t now=micros(0),gap=now-checkpoint;
        if(gap>700000u) {
            Counters awake,expired;error=counters(&awake);if(error)return error;
            expired=awake;
            /* No API/service/I2C heartbeat before the second counter read. */
            if(!SLEEP_KEEP_MODULE && cycles==0) {
                const uint32_t begin=micros(0);
                while((uint32_t)(micros(0)-begin)<2500000u) { __asm volatile("" ::: "memory"); }
                error=counters(&expired);if(error)return error;
                if(expired.expired<=awake.expired)return -8;
            }
            for(unsigned i=0;i<128;++i) if(stack[i]!=(i*0x9e3779b9u^0xc61a5aa5u))return -9;
            for(unsigned i=0;i<256;++i) if(globals[i]!=~(i*0x9e3779b9u^0xc61a5aa5u))return -9;
            for(unsigned at=0;at<4096;at+=sizeof(bytes)) {
                if(!mk61_app_buffer_read(svc,external.handle,at,bytes,sizeof(bytes)))return -10;
                for(unsigned i=0;i<sizeof(bytes);++i) if(bytes[i]!=pattern(at+i))return -11;
            }
            if(SLEEP_KEEP_MODULE && awake.waits!=initial.waits)return -12;
            if(!SLEEP_KEEP_MODULE && awake.us-initial.us<50000u)return -13;
            ++cycles;
            mk61_app_snprintf(svc,text,sizeof(text),
                "SLEEPCAN RESUME n=%u hold=%u gap_us=%lu waits=%lu us=%lu expired_before=%lu expired_after=%lu memory=PASS\n",
                cycles,SLEEP_KEEP_MODULE,(unsigned long)gap,(unsigned long)awake.waits,(unsigned long)awake.us,
                (unsigned long)awake.expired,(unsigned long)expired.expired);line(text);
        }
        checkpoint=micros(0);
    }
    if(!mk61_app_buffer_release(svc,external.handle))return -14;
    return cycles==2?0:-15;
}
int main(void) {
    svc=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FORMAT|MK61_SERVICE_CAP_DEBUG_IO|
        MK61_SERVICE_CAP_BUFFERS|MK61_SERVICE_CAP_EXTERNAL_BUFFERS);
    if(!svc)return MK61_APP_RUNTIME_ERROR;
    int error=run();const int cleanup=unload();if(!error)error=cleanup;
    char text[96];mk61_app_snprintf(svc,text,sizeof(text),"SLEEPCAN %s code=%d hold=%u uart_errors=%lu\n",
        error?"FAIL":"PASS",error,SLEEP_KEEP_MODULE,(unsigned long)uart.errors);line(text);
    return error?MK61_APP_RUNTIME_ERROR:MK61_APP_OK;
}
