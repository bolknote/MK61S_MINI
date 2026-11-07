/* Finite LCD-only diagnostic. No files, game state, settings or RTC writes. */
#include "mk61_app.h"
#include <string.h>
static const mk61_app_services* svc;
static uint8_t pixels[10240],tiles[2560];
static uint16_t palette[64];
static uint32_t micros(void){return svc->call(MK61_SERVICE_MICROS,0,0,0,0);}
static void line(const char* s){while(*s){unsigned n=(unsigned)strlen(s);if(n>128)n=128;svc->call(MK61_SERVICE_DEBUG_WRITE,n,0,0,(void*)s);s+=n;}}
static int key(void){uint8_t keys[32]={0};if(!svc->call(MK61_SERVICE_KEYBOARD,MK61_SERVICE_KEY_BITMAP,sizeof(keys),0,keys))return -1;for(unsigned i=1;i<256;++i)if(keys[i/8]&(1U<<(i&7)))return (int)i;return -1;}
static int wait_next(unsigned cap_us){uint32_t start=micros();while((uint32_t)(micros()-start)<cap_us){int k=key();if(k==27||k==0xB1||k==0x90)return 0;if(k=='n'||k=='N')return 1;mk61_api->delay_ms(1);}return 0;}
static uint32_t crc(uint32_t value,const uint8_t* p,unsigned n){while(n--){value^=*p++;for(unsigned k=0;k<8;++k)value=(value>>1)^(0xEDB88320U&-(value&1));}return value;}
static int palette_set(void){uint32_t start=micros();for(;;){uint32_t r=svc->call(MK61_SERVICE_COLOR_DISPLAY,MK61_COLOR_PALETTE64,0,sizeof(palette),palette);if(r==1)return 1;if(r!=2||(uint32_t)(micros()-start)>2000000)return 0;mk61_api->delay_ms(1);}}
static int present(mk61_service_color_frame* f){uint32_t start=micros();for(;;){uint32_t r=svc->call(MK61_SERVICE_COLOR_DISPLAY,MK61_COLOR_PRESENT,0,sizeof(*f),f);if(r==1)return 1;if(r!=2||(uint32_t)(micros()-start)>2000000)return 0;mk61_api->delay_ms(1);}}
int main(void){
 svc=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FORMAT|MK61_SERVICE_CAP_DEBUG_IO|MK61_SERVICE_CAP_COLOR_DISPLAY);
 if(!svc)return 1;
 mk61_api->display_clear();mk61_api->display_write_m8(0,0,"LCD diagnostic",14);
 line("LCDPROBE READY v=1 frames=22 wait_us=15000000\n");
 if(!wait_next(15000000)){line("LCDPROBE CANCEL ready\n");return 0;}
 mk61_service_color_frame f={0};f.pixels=pixels;f.tiles=tiles;f.format=MK61_COLOR_TILE8;
 for(unsigned step=0;step<22;++step){
  const char* kind=step<6?"full":step<12?"spectrum":step<18?"sparse":"fill";
  if(step<12){
   f.width=step<6?320:256;f.height=step<6?256:192;f.x=(320-f.width)/2;f.y=(320-f.height)/2;
   f.pixel_bytes=f.width*f.height/8;f.tile_bytes=f.width*f.height/32;
   for(unsigned i=0;i<f.pixel_bytes;++i)pixels[i]=(uint8_t)((i*73U+i/11U)^(step&1?255:0));
   for(unsigned i=0;i<f.tile_bytes;++i)tiles[i]=(uint8_t)((i*31U+i/7U)%64);
   for(unsigned i=0;i<64;++i){unsigned v=(i+(step&1?17:0))%64;palette[i]=(uint16_t)(((v>>1)<<11)|(v<<5)|(v>>1));}
   /* Keep primaries and unequal component bytes visible in the same pattern. */
   palette[0]=0xF800;palette[1]=0x07E0;palette[2]=0x001F;palette[3]=0x1234;
   if(!palette_set())return 2;
   f.background=step<6?(step&1?0xABCD:0x1234):0x1234;
  }else if(step<18){
   for(unsigned y=8;y<16;++y)pixels[y*32+2]^=255;
   for(unsigned y=176;y<184;++y)pixels[y*32+29]^=255;
  }else f.background=step&1?0xF81F:0x07E0;
  if(!present(&f)){line("LCDPROBE FAIL present\n");return 3;}
  /* Wait beyond the 12MHz full-frame transfer; snapshot stats then stay stable. */
  mk61_api->delay_ms(400);
  uint32_t expected=crc(crc(0xFFFFFFFFU,pixels,f.pixel_bytes),tiles,f.tile_bytes)^0xFFFFFFFFU;
  char out[128];mk61_app_snprintf(svc,out,sizeof(out),"LCDPROBE FRAME seq=%u kind=%s snapshot_crc=%08lX\n",step,kind,(unsigned long)expected);line(out);
  if(!wait_next(5000000)){line("LCDPROBE CANCEL frame\n");svc->call(MK61_SERVICE_COLOR_DISPLAY,MK61_COLOR_END,0,0,0);return 0;}
 }
 f.width=320;f.height=256;f.x=0;f.y=32;f.pixel_bytes=10240;f.tile_bytes=2560;f.background=0x1234;
 for(unsigned i=0;i<64;++i)palette[i]=(uint16_t)(((i>>1)<<11)|(i<<5)|(i>>1));
 palette[0]=0xF800;palette[1]=0x07E0;palette[2]=0x001F;palette[3]=0xFFFF;
 for(unsigned y=0;y<256;++y)for(unsigned x=0;x<40;++x)pixels[y*40+x]=y<128?(x&1?0xAA:0x55):0;
 for(unsigned y=0;y<32;++y)for(unsigned x=0;x<40;++x){unsigned i=(y*40+x)*2;tiles[i]=(uint8_t)((x*64/40)%64);tiles[i+1]=(uint8_t)((tiles[i]+16)%64);}
 if(!palette_set()||!present(&f))return 4;
 mk61_api->delay_ms(400);
 line("LCDPROBE VISUAL v=1 hold_us=75000000\n");
 wait_next(75000000);
 svc->call(MK61_SERVICE_COLOR_DISPLAY,MK61_COLOR_END,0,0,0);
 line("LCDPROBE DONE v=1 frames=22\n");
 return 0;
}
