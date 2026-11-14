#include <stdint.h>
static uint32_t read_register(uint32_t);
#define SPAUD_READ32 read_register
#define main probe_main
#include "main.c"
#undef main
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
static uint32_t clock_us,cc,master;static bool active,force_disabled,stall;
static unsigned opens,closes,getters;static mk61_service_audio_synth generator;
static char output[4096];static unsigned used;
static void service(void) {}
static uint32_t read_register(uint32_t address) {
    if(address==PWM5_CC)return cc;
    if(address==PWM5_CSR)return active && !force_disabled;
    assert(address==GPIO26_CTRL || address==GPIO27_CTRL);return active?4:5;
}
static uint32_t call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* data) {
    if(op==MK61_SERVICE_SETTINGS) {assert(a==MK61_SERVICE_VOLUME && !b && !c && !data);++getters;return master;}
    if(op==MK61_SERVICE_AUDIO_STREAM) {
        if(a==MK61_AUDIO_SYNTH_OPEN) {
            assert(!b && c==sizeof(generator) && data);generator=*(mk61_service_audio_synth*)data;assert(generator.rate==25000 && generator.volume==100);++opens;active=true;cc=128|(128U<<16);return 1;
        }
        assert(a==MK61_AUDIO_CLOSE);++closes;active=false;generator.sample=NULL;return 1;
    }
    if(op==MK61_SERVICE_MICROS) {
        assert(!a && !b && !c && !data);clock_us+=40;
        if(active && !stall) {
            const uint32_t value=generator.sample(generator.context);
            const int32_t l=128+((int16_t)value*(int32_t)(master*100))/512000;
            const int32_t r=128+((int16_t)(value>>16)*(int32_t)(master*100))/512000;
            cc=(uint32_t)l|((uint32_t)r<<16);
        }
        return clock_us;
    }
    assert(op==MK61_SERVICE_DEBUG_WRITE && !b && !c && used+a<sizeof(output));memcpy(output+used,data,a);used+=a;output[used]=0;return a;
}
static int format(char* out,uint32_t n,const char* f,va_list args) {return vsnprintf(out,n,f,args);}
static const mk61_app_services services={MK61_APP_SERVICES_MAGIC,MK61_APP_SERVICES_VERSION,sizeof(mk61_app_services),NULL,call,NULL,format,NULL};
static const void* query(uint32_t id,uint32_t version) {(void)id;(void)version;return &services;}
static const mk61_app_api api={.magic=MK61_APP_API_MAGIC,.version=MK61_APP_API_VERSION,.struct_size=sizeof(mk61_app_api),.service=service,.query_service=query};
const mk61_app_api* mk61_api=&api;
static void scenario(unsigned volume,bool disabled,bool stopped,bool wrap) {
    master=volume;force_disabled=disabled;stall=stopped;opens=closes=getters=used=0;clock_us=wrap?UINT32_MAX-100000:0;active=false;
    const int result=probe_main();assert(opens==1 && closes==1 && getters==1 && !active && !generator.sample && master==volume);
    if(disabled || stopped) {assert(result==3 && strstr(output,"SPAUD result=0"));return;}
    assert(result==0 && strstr(output,"SPAUD result=1"));
    if(!volume) {assert(strstr(output,"master=0 mute=1"));assert(strstr(output,"L=128/128 R=128/128"));}
    else {
        char* p=strstr(output,"SPPWM phase=1");assert(p && strstr(p,"L=96/160 R=128/128"));
        p=strstr(output,"SPPWM phase=2");assert(p && strstr(p,"L=128/128 R=96/160"));
        p=strstr(output,"SPPWM phase=3");assert(p && strstr(p,"L=96/160 R=96/160"));
    }
}
int main(void) {
    scenario(10,false,false,false);scenario(10,false,false,true);scenario(0,false,false,false);
    scenario(10,true,false,false);scenario(10,false,true,false);
    puts("Audio check actual APP: correct signed stereo/PWM, master-zero remains muted, left/right/both phases, CSR disable/stalled callbacks detected, wrapping clock, one close/quiescent context, no settings writes PASS; no physical audibility claim");
}
