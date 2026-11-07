#include <assert.h>
#include <stdio.h>
#include <stdarg.h>
#define main lcdprobe_main
#include "picocalc_lcd_color_probe.c"
#undef main
static uint32_t now;
static unsigned frames,ended,attempts,palettes;
static int scenario;
static char output[8192];static unsigned used;
static void pump(void){}
static void delay(uint32_t ms){now+=ms*1000;}
static uint32_t clear(void){return 1;}
static uint32_t text(uint32_t x,uint32_t y,const char* s,uint32_t n){assert(!x&&!y&&strlen(s)==n);return 1;}
static int format(char* out,uint32_t n,const char* f,va_list args){return vsnprintf(out,n,f,args);}
static uint32_t call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* p){
 (void)b;
 if(op==MK61_SERVICE_CAPABILITIES)return MK61_SERVICE_CAP_FORMAT|MK61_SERVICE_CAP_DEBUG_IO|MK61_SERVICE_CAP_COLOR_DISPLAY;
 if(op==MK61_SERVICE_MICROS)return now;
 if(op==MK61_SERVICE_DEBUG_WRITE){assert(a<=128&&used+a<sizeof(output));memcpy(output+used,p,a);used+=a;output[used]=0;return 1;}
 if(op==MK61_SERVICE_KEYBOARD){assert(a==MK61_SERVICE_KEY_BITMAP);memset(p,0,32);if(scenario==1)return 1;int k=scenario==2&&frames?27:'n';((uint8_t*)p)[k/8]|=1U<<(k&7);return 1;}
 assert(op==MK61_SERVICE_COLOR_DISPLAY);
 if(a==MK61_COLOR_END){assert(!c&&!p);++ended;return 1;}
 if(a==MK61_COLOR_PALETTE64){assert(c==128);++palettes;return palettes%3==1?2:1;}
 assert(a==MK61_COLOR_PRESENT&&c==sizeof(mk61_service_color_frame));
 const mk61_service_color_frame* f=p;assert(f->pixel_bytes+f->tile_bytes<=12800&&f->x+f->width<=320&&f->y+f->height<=320);
 if(scenario==3)return 2;
 if(++attempts%2)return 2;
 ++frames;return 1;
}
static const mk61_app_services common={MK61_APP_SERVICES_MAGIC,MK61_APP_SERVICES_VERSION,sizeof(mk61_app_services),NULL,call,NULL,format,NULL};
static const void* query(uint32_t id,uint32_t version){assert(id==MK61_APP_SERVICE_COMMON&&version==MK61_APP_SERVICES_VERSION);return &common;}
static const mk61_app_api api={.magic=MK61_APP_API_MAGIC,.version=MK61_APP_API_VERSION,.struct_size=sizeof(mk61_app_api),.service=pump,.delay_ms=delay,.display_clear=clear,.display_write_m8=text,.query_service=query};
const mk61_app_api* mk61_api=&api;
int main(void){
 assert((crc(0xFFFFFFFFU,(const uint8_t*)"123456789",9)^0xFFFFFFFFU)==0xCBF43926U);
 for(scenario=0;scenario<4;++scenario){now=UINT32_MAX-1000000;frames=ended=attempts=palettes=used=0;output[0]=0;
  int rc=lcdprobe_main();
  if(scenario==0){assert(!rc&&frames==23&&ended==1&&strstr(output,"DONE v=1 frames=22"));for(unsigned n=0;n<22;++n){char s[48];snprintf(s,sizeof(s),"FRAME seq=%u kind=",n);assert(strstr(output,s));}}
  if(scenario==1)assert(!rc&&!frames&&!ended&&strstr(output,"CANCEL ready"));
  if(scenario==2)assert(!rc&&frames==1&&ended==1&&strstr(output,"CANCEL frame"));
  if(scenario==3)assert(rc==3&&!frames&&strstr(output,"FAIL present"));
 }
 puts("LCDPROBE HOST: 22 exact frame markers plus visual pattern, busy retries, Esc, ready/present bounds, uint32 wrap and no file/settings/RTC calls PASS");
}
