/* Diagnostic only: write two page patterns and read the complemented RGB565
 * back over PicoCalc SPI1 MISO. Writes only the display's volatile memory. */
#include "mk61_app.h"
#include "picocalc_lcd_readback.h"
#include <string.h>

static const mk61_app_services *services;
static uint8_t pixels[12800];
static uint32_t micros(void) { return services->call(MK61_SERVICE_MICROS,0,0,0,NULL); }
static void line(const char *text) {
    services->call(MK61_SERVICE_DEBUG_WRITE,(uint32_t)strlen(text),0,0,(void *)text);
}
static bool control(unsigned operation,const void *payload,unsigned size) {
    const uint32_t started=micros();
    for(;;) {
        const unsigned result=services->call(MK61_SERVICE_COLOR_DISPLAY,operation,0,size,(void *)payload);
        if(result==1)return true;
        if(result!=2 || (uint32_t)(micros()-started)>2000000u)return false;
        mk61_api->service();
    }
}
static bool draw(unsigned page) {
    const uint32_t selected=page;
    if(!control(MK61_COLOR_PAGE_SELECT,&selected,sizeof(selected)))return false;
    const uint16_t palette[2][4]={{0xf800,0x07e0,0x001f,0xffff},{0x07ff,0xf81f,0xffe0,0x8410}};
    for(unsigned y=0;y<200;y+=80) {
        const unsigned rows=200-y<80?200-y:80;
        for(unsigned row=0;row<rows;++row)for(unsigned x=0;x<160;++x) {
            const unsigned index=((y+row)>=100?2:0)+(x>=80?1:0);
            pixels[row*160+x]=(uint8_t)((index<<4)|index);
        }
        mk61_service_color_frame f={0};f.pixels=pixels;f.pixel_bytes=rows*160;
        f.x=0;f.y=(uint16_t)(60+y);f.width=320;f.height=(uint16_t)rows;
        f.format=MK61_COLOR_INDEX4|MK61_COLOR_PRESERVE_OUTSIDE;
        memcpy(f.palette,palette[page],sizeof(palette[page]));
        if(!control(MK61_COLOR_PRESENT,&f,sizeof(f)))return false;
    }
    return true;
}
static bool show(unsigned page) {
    const uint32_t value=page;return control(MK61_COLOR_PAGE_SHOW,&value,sizeof(value));
}

#include "picocalc_lcd_spi1_readback.h"

static bool capture(unsigned stage,unsigned page) {
    const uint32_t normal=0;
    if(!control(MK61_COLOR_INVERT,&normal,sizeof(normal)) || !hw_begin())return false;
    picocalc_lcd_read_bus bus={NULL,hw_lines,hw_transfer};uint8_t rgb[4][3];bool ok=true;
    for(unsigned q=0;q<4 && ok;++q)
        ok=picocalc_lcd_read_pixel(&bus,(q&1)?240:80,60+page*200+((q&2)?150:50),rgb[q]);
    if(!hw_end())ok=false;
    if(!ok)return false;
    for(unsigned q=0;q<4;++q) {
        char output[80];
        mk61_app_snprintf(services,output,sizeof(output),"AWREAD S=%u P=%u Q=%u RGB=%02X%02X%02X\n",
                           stage,page,q,rgb[q][0],rgb[q][1],rgb[q][2]);
        line(output);
    }
    return true;
}
int main(void) {
    services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_COLOR_DISPLAY|MK61_SERVICE_CAP_DEBUG_IO|MK61_SERVICE_CAP_FORMAT);
    if(!services || !mk61_api->graphics_begin())return 1;
    bool ok=false;
    const mk61_service_color_pages config={60,200};
    if(!control(MK61_COLOR_PAGES_BEGIN_V2,&config,sizeof(config)) || !draw(0) || !show(0) || !capture(0,0))goto done;
    if(!draw(1) || !capture(1,0) || !capture(1,1))goto done;
    if(!show(1) || !capture(2,1) || !show(0) || !capture(3,0))goto done;
    if(!control(MK61_COLOR_PAGES_END,NULL,0))goto done;
    ok=true;
 done:
    services->call(MK61_SERVICE_COLOR_DISPLAY,MK61_COLOR_END,0,0,NULL);
    mk61_api->graphics_end();line(ok?"AWREAD DONE\n":"AWREAD FAIL\n");
    return ok?0:2;
}
