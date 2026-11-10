/* Finite, M3-only speaker routing check at the resident's stock clock.
 * Three isolated tones: A440Hz, B~555Hz, C~660Hz; no guest RAM or SD writes. */
#include "mk61_app.h"
#include "../examples/portable-apps/SPECTRUM/spectrum.h"
#include <string.h>
#ifndef S3_PAN_CHIP
#define S3_PAN_CHIP SPECTRUM_AY
#endif
#ifndef S3_PAN_LAYOUT
#define S3_PAN_LAYOUT SPECTRUM_ABC
#endif
static spectrum machine;
static const mk61_app_services* services;
static void yield(void* unused){(void)unused;mk61_api->service();}
static uint32_t micros(void){return services->call(MK61_SERVICE_MICROS,0,0,0,NULL);}
static void line(const char* s){services->call(MK61_SERVICE_DEBUG_WRITE,strlen(s),0,0,(void*)s);}
int main(void) {
    services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_AUDIO_STREAM|MK61_SERVICE_CAP_DEBUG_IO);
    if(!services)return MK61_APP_RUNTIME_ERROR;
    memset(&machine,0,sizeof(machine));machine.ay.quality=1;machine.ay.rate=25000;
    PSG_setVolumeMode(&machine.ay,2);PSG_setClock(&machine.ay,1750000);PSG_reset(&machine.ay);
    machine.ay2=machine.ay;spectrum_sound_reset(&machine);
    spectrum_sound_configure(&machine,S3_PAN_CHIP,S3_PAN_LAYOUT);
    static const unsigned periods[]={249,197,166};
    for(unsigned c=0;c<3;++c){spectrum_sound_write(&machine,0,2*c,periods[c]&255);spectrum_sound_write(&machine,0,2*c+1,periods[c]>>8);}
    spectrum_sound_write(&machine,0,7,0x38);
    const char* header=S3_PAN_LAYOUT==SPECTRUM_ABC?"ABC: A=L B=C C=R":"ACB: A=L B=R C=C";
    mk61_api->display_clear();mk61_api->display_write_m8(0,0,header,strlen(header));
    const char* tones="Low / mid / high";mk61_api->display_write_m8(0,2,tones,strlen(tones));
    spectrum_sound_begin(&machine,yield,NULL);spectrum_sound_clock(&machine,false);
    spectrum_sound* q=&machine.sound;mk61_service_audio_psg_config config={0};mk61_service_audio_psg* r=&config.psg;
    r->local=(mk61_service_audio_synth){spectrum_sound_render,&machine,25000,100};r->module_path="AY.S3M";
    r->psg[0]=(uint8_t*)&machine.ay.reg;r->psg[1]=(uint8_t*)&machine.ay2.reg;r->psg_bytes=132;
    r->events=(const uint8_t*)q->events;r->event_capacity=SPECTRUM_SOUND_QUEUE_EVENTS;
    r->read=(volatile uint32_t*)&q->read;r->write=(const volatile uint32_t*)&q->write;r->produced=(const volatile uint32_t*)&q->produced;
    r->time=&q->time;r->running=(const volatile uint8_t*)&q->clock_running;r->dac=&q->beeper;
    r->dc_input=&q->input;r->dc_output=&q->output;r->recover=spectrum_sound_recover;
    config.chip=S3_PAN_CHIP;config.layout=S3_PAN_LAYOUT;config.stereo=q->stereo;
    if(services->call(MK61_SERVICE_AUDIO_STREAM,MK61_AUDIO_PSG_CONFIG_ONLY_OPEN,0,sizeof(config),&config)!=2) {
        spectrum_sound_end(&machine);line("S3PAN FAIL remote_unavailable\n");return MK61_APP_OK;
    }
    line("S3PAN BEGIN isolated=A,B,C\n");
    unsigned lo[3][2]={{255,255},{255,255},{255,255}},hi[3][2]={{0}},observations[3]={0},different[3]={0};
    unsigned edge=0;const uint32_t epoch=micros();spectrum_sound_clock(&machine,true);bool cancelled=false;
    while(micros()-epoch<12000000) {
        const uint32_t target=(micros()-epoch)/40+600;
        while(edge<6) {
            const unsigned channel=edge/2,sample=channel*100000+(edge&1?75000:0);
            if(sample>=target)break;
            machine.cpu.cyc=sample*140+1;spectrum_sound_write(&machine,0,8+channel,edge&1?0:15);++edge;
        }
        machine.cpu.cyc=target*140;spectrum_sound_publish(&machine);
        // RP2040 PWM slice5 CC: GPIO26=A, GPIO27=B. Observe the atomic
        // duty pair after the filters settle; no writes or extra USB I/O.
        const uint32_t elapsed=micros()-epoch,within=elapsed%4000000u;
        const unsigned tone=elapsed/4000000u;
        if(tone<3 && within>=250000u && within<2750000u) {
            const uint32_t cc=*(const volatile uint32_t*)0x40050070u;
            const unsigned levels[2]={cc&65535u,cc>>16};
            for(unsigned c=0;c<2;++c){if(levels[c]<lo[tone][c])lo[tone][c]=levels[c];if(levels[c]>hi[tone][c])hi[tone][c]=levels[c];}
            ++observations[tone];if(levels[0]!=levels[1])++different[tone];
        }
        if(mk61_api->key_poll()==MK61_APP_KEY_ESC){cancelled=true;break;}
        mk61_api->service();mk61_api->delay_ms(1);
    }
    spectrum_sound_clock(&machine,false);services->call(MK61_SERVICE_AUDIO_STREAM,MK61_AUDIO_CLOSE,0,0,NULL);
    spectrum_sound_end(&machine);
    bool routed=true;
    for(unsigned tone=0;tone<3;++tone) {
        const unsigned centre=S3_PAN_LAYOUT==SPECTRUM_ACB?2:1;
        const bool left=tone==0 || tone==centre,right=tone!=0;
        if(!observations[tone] || (left?lo[tone][0]==hi[tone][0]:lo[tone][0]!=128 || hi[tone][0]!=128) ||
           (right?lo[tone][1]==hi[tone][1]:lo[tone][1]!=128 || hi[tone][1]!=128) ||
           (tone==centre && different[tone]))routed=false;
        char text[128];mk61_app_snprintf(services,text,sizeof(text),"S3PAN PWM tone=%u L=%u..%u R=%u..%u n=%u different=%u\n",
            tone,lo[tone][0],hi[tone][0],lo[tone][1],hi[tone][1],observations[tone],different[tone]);line(text);
    }
    line(cancelled?"S3PAN CANCELLED\n":routed?"S3PAN DONE\n":"S3PAN FAIL pwm_routing\n");return MK61_APP_OK;
}
