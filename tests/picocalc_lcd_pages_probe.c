/* Finite optical qualification of the compensated 480-row page mapping.
 * No game data, files, settings, or calculator state are written. */
#include "mk61_app.h"
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
    const uint32_t value=page;
    return control(MK61_COLOR_PAGE_SHOW,&value,sizeof(value));
}
static void hold(const char *stage) {line(stage);mk61_api->delay_ms(4000);}
int main(void) {
    services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_COLOR_DISPLAY|MK61_SERVICE_CAP_DEBUG_IO);
    if(!services || !mk61_api->graphics_begin())return 1;
    bool ok=false;
    const mk61_service_color_pages config={60,200};
    if(!control(MK61_COLOR_PAGES_BEGIN_V2,&config,sizeof(config)) || !draw(0) || !show(0))goto done;
    hold("AWPAGES PAGE0\n");
    line("AWPAGES WRITE1\n");
    if(!draw(1))goto done;
    hold("AWPAGES PAGE0_STILL\n");
    if(!show(1))goto done;
    hold("AWPAGES PAGE1\n");
    if(!show(0))goto done;
    hold("AWPAGES PAGE0_AGAIN\n");
    if(!control(MK61_COLOR_PAGES_END,NULL,0))goto done;
    ok=true;
 done:
    services->call(MK61_SERVICE_COLOR_DISPLAY,MK61_COLOR_END,0,0,NULL);
    mk61_api->graphics_end();line(ok?"AWPAGES PASS\n":"AWPAGES FAIL\n");
    return ok?0:2;
}
