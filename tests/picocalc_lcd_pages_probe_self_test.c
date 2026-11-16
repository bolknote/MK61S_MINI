#include "mk61_app.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static uint16_t gram[2][320*200];
static unsigned selected,visible,begins,shows,ends,graphics,fail_show;
static uint32_t clock_us;
static char output[1024];static unsigned output_size;
const mk61_app_api *mk61_api;
uint32_t mk61_app_image_crc,mk61_app_current_kind;
int lcd_pages_probe_main(void);
static void service(void){clock_us+=100;}
static void delay(uint32_t ms){clock_us+=ms*1000;}
static uint32_t begin(void){++graphics;return 1;}
static void end(void){assert(graphics);--graphics;}
static void check(unsigned page) {
    const uint16_t expected[2][4]={{0xf800,0x07e0,0x001f,0xffff},{0x07ff,0xf81f,0xffe0,0x8410}};
    for(unsigned y=0;y<200;++y)for(unsigned x=0;x<320;++x)
        assert(gram[page][y*320+x]==expected[page][(y>=100?2:0)+(x>=160?1:0)]);
}
static uint32_t call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void *payload) {
    (void)b;
    if(op==MK61_SERVICE_CAPABILITIES)return ~0u;
    if(op==MK61_SERVICE_MICROS)return ++clock_us;
    if(op==MK61_SERVICE_DEBUG_WRITE) {
        assert(output_size+a<sizeof(output));memcpy(output+output_size,payload,a);output_size+=a;output[output_size]=0;
        if(a==20 && !memcmp(payload,"AWPAGES PAGE0_STILL\n",20)) {assert(visible==0);check(0);check(1);}
        return 1;
    }
    if(op!=MK61_SERVICE_COLOR_DISPLAY)return 0;
    if(a==MK61_COLOR_PAGES_BEGIN_V2) {
        assert(c==sizeof(mk61_service_color_pages));const mk61_service_color_pages *p=payload;
        assert(p->top==60 && p->height==200);if(!begins++)return 2;return 1;
    }
    if(a==MK61_COLOR_PAGE_SELECT){assert(c==4);memcpy(&selected,payload,4);assert(selected<2);return 1;}
    if(a==MK61_COLOR_PAGE_SHOW){
        uint32_t page;assert(c==4);memcpy(&page,payload,4);assert(page<2);
        if(fail_show)return 0;visible=page;++shows;check(page);return 1;
    }
    if(a==MK61_COLOR_PAGES_END || a==MK61_COLOR_END){++ends;return 1;}
    if(a==MK61_COLOR_PRESENT) {
        const mk61_service_color_frame *f=payload;assert(c==sizeof(*f) && selected<2);
        assert(f->x==0 && f->y>=60 && f->y+f->height<=260 && f->width==320 && f->pixel_bytes==160u*f->height);
        assert(f->format==(MK61_COLOR_INDEX4|MK61_COLOR_PRESERVE_OUTSIDE));
        for(unsigned y=0;y<f->height;++y)for(unsigned x=0;x<320;++x) {
            uint8_t pair=f->pixels[y*160+x/2];unsigned index=(pair>>((x&1)?0:4))&15;
            gram[selected][(f->y-60+y)*320+x]=f->palette[index];
        }
        return 1;
    }
    return 0;
}
static const mk61_app_services services={MK61_APP_SERVICES_MAGIC,MK61_APP_SERVICES_VERSION,sizeof(services),NULL,call,NULL,NULL,NULL};
static const void *query(uint32_t id,uint32_t version){return id==MK61_APP_SERVICE_COMMON && version==MK61_APP_SERVICES_VERSION?&services:NULL;}
int main(void){
    mk61_app_api api={0};api.magic=MK61_APP_API_MAGIC;api.version=MK61_APP_API_VERSION;api.struct_size=sizeof(api);
    api.service=service;api.delay_ms=delay;api.graphics_begin=begin;api.graphics_end=end;api.query_service=query;mk61_api=&api;
    selected=visible=2;assert(lcd_pages_probe_main()==0);assert(!graphics && begins==2 && shows==3 && ends==2);
    assert(strstr(output,"AWPAGES PAGE0_STILL\n") && strstr(output,"AWPAGES PASS\n"));
    begins=shows=ends=graphics=output_size=0;clock_us=0;selected=visible=2;fail_show=1;
    assert(lcd_pages_probe_main()==2 && !graphics && ends==1 && strstr(output,"AWPAGES FAIL\n"));
    puts("LCD page probe: full color patterns, hidden write and failure cleanup passed");return 0;
}
