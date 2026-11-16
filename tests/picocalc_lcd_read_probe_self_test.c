#include "mk61_app.h"
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

static uint16_t gram[2][320*200];
static unsigned selected,visible,begins,shows,ends,graphics,spi_active,reads,transfers;
static unsigned op,parameter,x,y;static uint8_t params[4],sample[3];
static bool cs,data_mode,fail_begin,fail_transfer,fail_end;
static uint32_t clock_us;static char output[4096];static unsigned output_size;
const mk61_app_api *mk61_api;
uint32_t mk61_app_image_crc,mk61_app_current_kind;
int lcd_read_probe_main(void);
static void service(void){clock_us+=100;}
static uint32_t begin(void){++graphics;return 1;}
static void end(void){assert(graphics);--graphics;}
bool picocalc_lcd_test_begin(void){if(fail_begin)return false;assert(!spi_active);spi_active=1;return true;}
bool picocalc_lcd_test_end(void){assert(spi_active && !cs);spi_active=0;return !fail_end;}
bool picocalc_lcd_test_lines(void *ctx,bool active,bool data){(void)ctx;assert(spi_active);cs=active;data_mode=data;return true;}
bool picocalc_lcd_test_transfer(void *ctx,uint8_t out,uint8_t *in){
    (void)ctx;assert(spi_active && cs);++transfers;
    if(fail_transfer && transfers==5)return false;
    *in=0;
    if(!data_mode){op=out;parameter=0;return true;}
    if(op==0x2a || op==0x2b){
        assert(parameter<4);params[parameter++]=out;
        if(parameter==4){unsigned start=(unsigned)params[0]*256+params[1],end=(unsigned)params[2]*256+params[3];
            assert(start==end);if(op==0x2a)x=start;else y=start;}
        return true;
    }
    assert(op==0x2e && x<320 && y>=60 && y<460);
    if(!parameter++){
        const unsigned row=y-60;
        const uint16_t color=gram[row/200][(row%200)*320+x];
        sample[0]=(uint8_t)(color>>8);sample[1]=(uint8_t)color;++reads;
    } else {assert(parameter<=3);*in=sample[parameter-2];}
    return true;
}
static uint32_t call(uint32_t op0,uint32_t a,uint32_t b,uint32_t c,void *payload){
    (void)b;
    if(op0==MK61_SERVICE_CAPABILITIES)return ~0u;
    if(op0==MK61_SERVICE_MICROS)return ++clock_us;
    if(op0==MK61_SERVICE_DEBUG_WRITE){assert(output_size+a<sizeof(output));memcpy(output+output_size,payload,a);output_size+=a;output[output_size]=0;return 1;}
    if(op0!=MK61_SERVICE_COLOR_DISPLAY)return 0;
    assert(!spi_active);
    if(a==MK61_COLOR_PAGES_BEGIN_V2){assert(c==sizeof(mk61_service_color_pages));if(!begins++)return 2;return 1;}
    if(a==MK61_COLOR_PAGE_SELECT){assert(c==4);memcpy(&selected,payload,4);assert(selected<2);return 1;}
    if(a==MK61_COLOR_PAGE_SHOW){assert(c==4);memcpy(&visible,payload,4);assert(visible<2);++shows;return 1;}
    if(a==MK61_COLOR_INVERT){assert(c==4 && *(uint32_t *)payload==0);return 1;}
    if(a==MK61_COLOR_PAGES_END || a==MK61_COLOR_END){++ends;return 1;}
    if(a==MK61_COLOR_PRESENT){
        const mk61_service_color_frame *f=payload;assert(c==sizeof(*f) && selected<2);
        assert(f->x==0 && f->y>=60 && f->y+f->height<=260 && f->width==320);
        for(unsigned row=0;row<f->height;++row)for(unsigned col=0;col<320;++col){
            const uint8_t pair=f->pixels[row*160+col/2];
            gram[selected][(f->y-60+row)*320+col]=f->palette[(pair>>((col&1)?0:4))&15]^0xffffu;
        }
        return 1;
    }
    return 0;
}
static int format(char *out,uint32_t size,const char *text,va_list args){return vsnprintf(out,size,text,args);}
static const mk61_app_services services={MK61_APP_SERVICES_MAGIC,MK61_APP_SERVICES_VERSION,sizeof(services),NULL,call,NULL,format,NULL};
static const void *query(uint32_t id,uint32_t version){return id==MK61_APP_SERVICE_COMMON && version==MK61_APP_SERVICES_VERSION?&services:NULL;}
static void reset(void){
    memset(gram,0,sizeof(gram));memset(output,0,sizeof(output));output_size=0;
    selected=visible=2;begins=shows=ends=graphics=spi_active=reads=transfers=op=parameter=x=y=0;
    cs=data_mode=fail_begin=fail_transfer=fail_end=false;clock_us=0;
}
int main(void){
    mk61_app_api api={0};api.magic=MK61_APP_API_MAGIC;api.version=MK61_APP_API_VERSION;api.struct_size=sizeof(api);
    api.service=service;api.graphics_begin=begin;api.graphics_end=end;api.query_service=query;mk61_api=&api;
    reset();assert(lcd_read_probe_main()==0 && !graphics && !spi_active && !cs);
    assert(begins==2 && shows==3 && ends==2 && reads==20 && strstr(output,"AWREAD DONE\n"));
    assert(strstr(output,"AWREAD S=0 P=0 Q=0 RGB=00FCFC\n"));
    assert(strstr(output,"AWREAD S=1 P=1 Q=1 RGB=00FC00\n"));
    assert(strstr(output,"AWREAD S=2 P=1 Q=3 RGB=787C78\n"));
    reset();fail_begin=true;assert(lcd_read_probe_main()==2 && !graphics && !spi_active && ends==1 && strstr(output,"AWREAD FAIL\n"));
    reset();fail_transfer=true;assert(lcd_read_probe_main()==2 && !graphics && !spi_active && !cs && ends==1 && strstr(output,"AWREAD FAIL\n"));
    reset();fail_end=true;assert(lcd_read_probe_main()==2 && !graphics && !spi_active && !cs && ends==1 && strstr(output,"AWREAD FAIL\n"));
    puts("LCD GRAM APP: two real page patterns, 20 reads, hidden write, SPI cleanup and failures PASS");return 0;
}
