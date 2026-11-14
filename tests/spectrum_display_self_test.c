/* Exercise the actual OSD against old/new color hosts. Drawing primitives
 * receive a fixed font/palette here; the clock contract is the boundary. */
#include <assert.h>
#include <stdio.h>
#define spectrum_color display_test_color
#define spectrum_video display_test_video
#include "../examples/portable-apps/SPECTRUM/ui.c"
#undef spectrum_color
#undef spectrum_video
static uint8_t canvas[12800],rom[16384];
static bool supported;
static unsigned clocks,presents,delays;
static uint32_t hz;
uint16_t display_test_color(unsigned color) { return (uint16_t)(color*17); }
void display_test_video(const spectrum* s,uint8_t* bits,uint8_t* tiles) { (void)s;(void)bits;(void)tiles; }
static uint32_t begin(void) { return 1; }
static void delay(uint32_t ms) { assert(ms==1);++delays; }
static uint32_t call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* p) {
    if(op==MK61_SERVICE_FILE_BYTES) {
        const mk61_service_file_bytes* r=p;
        assert(a==MK61_FILE_BYTES_READ && !b && c==sizeof(*r) && !strcmp(r->path,"48.rom") && r->offset==0x3D00 && r->size==768);
        memcpy(r->data,rom+0x3D00,768);return 1;
    }
    if(op==MK61_SERVICE_DISPLAY) {
        assert(a==MK61_SERVICE_DISPLAY_FRAMEBUFFER && b==sizeof(mk61_service_framebuffer) && !c);
        *(mk61_service_framebuffer*)p=(mk61_service_framebuffer){canvas,sizeof(canvas),320,320};return 1;
    }
    assert(op==MK61_SERVICE_COLOR_DISPLAY && !b);
    if(a==MK61_COLOR_SPI_HZ) {
        assert(c==sizeof(uint32_t) && p && *(uint32_t*)p==24000000);++clocks;
        if(!supported)return 0;
        return hz=24000000;
    }
    assert(a==MK61_COLOR_PRESENT && c==sizeof(mk61_service_color_frame) && clocks);
    assert(hz==(supported?24000000:12000000));
    const mk61_service_color_frame* f=p;
    assert(f->width==256 && f->height==256 && f->format==MK61_COLOR_TILE1);
    return ++presents%2?2:1;
}
static const mk61_app_services common={.call=call};
static const mk61_app_api api={.graphics_begin=begin,.delay_ms=delay};
const mk61_app_api* mk61_api=&api;
int main(int argc,char** argv) {
    assert(argc==1 || argc==2);
    if(argc==2) { FILE* f=fopen(argv[1],"rb");assert(f && fread(rom,1,sizeof(rom),f)==sizeof(rom));fclose(f); }
    for(unsigned mode=0;mode<2;++mode) {
        supported=mode;clocks=presents=delays=0;hz=12000000;
        spectrum_ui u;spectrum s={0};
        assert(spectrum_ui_begin(&u,&common,&s,false));
        const char* labels[]={"Start machine","Snapshot...","Beta Disk...","DivMMC...","Machine...","Options...","TR-DOS","Reset","Help","Exit"};
        spectrum_ui_window(&u,8,8,224,"Spectrum",labels,10,0);
        spectrum_ui_footer(&u,"Enter: select    Esc: back");
        assert(spectrum_ui_present(&u) && presents==2 && delays==1 && clocks==1);
        if(mode && argc==2) {
            uint32_t crc=UINT32_MAX;
            for(unsigned i=0;i<9216;++i) { crc^=canvas[i];for(unsigned bit=0;bit<8;++bit)crc=(crc>>1)^((crc&1)?0xEDB88320U:0); }
            printf("Spectrum ordinary root menu snapshot CRC=%08lX\n",(unsigned long)(crc^UINT32_MAX));
        }
        assert(spectrum_ui_begin(&u,&common,&s,true) && clocks==2);
        assert(spectrum_ui_present(&u));
    }
    puts("Actual Spectrum OSD: LCD24 requested before presentation; unsupported old host still renders; busy retry PASS");
}
