#include "ui.h"
#include <string.h>
#include "rom_cache.h"
/* The OSD shares the resident borrowed canvas and panel-owned snapshot.
 * 256x256 TILE1: 8192 bitmap + 1024 attributes, no RGB framebuffer. */
static void pixel(spectrum_ui* u,unsigned x,unsigned y,bool on) {
    if(x>=256 || y>=256) return;
    uint8_t* p=(uint8_t*)u->frame.pixels+y*32+x/8;const unsigned mask=128U>>(x&7);
    if(on) *p|=mask;else *p&=(uint8_t)~mask;
}
static void fill(spectrum_ui* u,unsigned x,unsigned y,unsigned width,unsigned height,unsigned paper,unsigned ink) {
    for(unsigned row=y;row<y+height && row<256;++row)
        memset((uint8_t*)u->frame.pixels+row*32+x/8,0,width/8);
    for(unsigned row=y/8;row<(y+height)/8 && row<32;++row)
        memset((uint8_t*)u->frame.tiles+row*32+x/8,(paper<<4)|ink,width/8);
}
static void label(spectrum_ui* u,unsigned x,unsigned y,unsigned max,const char* value) {
    for(unsigned i=0;value[i] && i<max;++i) {
        const unsigned c=(unsigned char)value[i];const uint8_t* glyph=u->font+((c>=32 && c<128)?c-32:31)*8;
        for(unsigned row=0;row<8;++row) for(unsigned bit=0;bit<8;++bit)
            pixel(u,x+i*8+bit,y+row,(glyph[row]&(128U>>bit))!=0);
    }
}
bool spectrum_ui_begin(spectrum_ui* u,const mk61_app_services* api,const spectrum* s,bool running) {
    u->api=api;
    if(!mk61_api->graphics_begin()) return false;
    mk61_service_framebuffer buffer={0};
    if(!api->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(buffer),0,&buffer) || !buffer.pixels || buffer.bytes<9984) return false;
    const uint8_t* rom=spectrum_rom_cache_find(SPECTRUM_ROM_48,NULL);
    if(rom) u->font=rom+0x3D00;
    else {
        mk61_service_file_bytes request={"48.rom",buffer.pixels+9216,0x3D00,768};
        if(!api->call(MK61_SERVICE_FILE_BYTES,MK61_FILE_BYTES_READ,0,sizeof(request),&request)) return false;
        u->font=buffer.pixels+9216;
    }
    memset(&u->frame,0,sizeof(u->frame));u->frame.pixels=buffer.pixels;u->frame.tiles=buffer.pixels+8192;
    u->frame.pixel_bytes=8192;u->frame.tile_bytes=1024;u->frame.width=u->frame.height=256;
    u->frame.x=u->frame.y=32;u->frame.format=MK61_COLOR_TILE1;
    for(unsigned i=0;i<16;++i) u->frame.palette[i]=spectrum_color(i);
    u->frame.background=spectrum_color(7);fill(u,0,0,256,256,7,0);
    if(running) spectrum_video(s,buffer.pixels+1024,buffer.pixels+8192+128);
    spectrum_display_fast(api);
    return true;
}
void spectrum_ui_window(spectrum_ui* u,unsigned x,unsigned y,unsigned width,const char* title,
                        const char* const* labels,unsigned count,unsigned selected) {
    const unsigned visible=count>12?12:count,top=selected<count && selected>=visible?selected-visible+1:0,height=16+16*visible;
    fill(u,x-8,y-8,width+16,height+16,15,0);
    fill(u,x,y,width,16,0,15);label(u,x+8,y+4,(width-64)/8,title);
    static const uint8_t colors[]={0,10,14,12,13,9,0};
    for(unsigned tile=0;tile<6;++tile) {
        const unsigned left=x+width-48+tile*8;
        for(unsigned row=0;row<16;++row)
            ((uint8_t*)u->frame.pixels)[(y+row)*32+left/8]=(uint8_t)(255U>>(7-row/2));
        for(unsigned row=0;row<2;++row) ((uint8_t*)u->frame.tiles)[(y/8+row)*32+left/8]=(colors[tile]<<4)|colors[tile+1];
    }
    for(unsigned row=0;row<visible;++row) {
        const unsigned index=top+row,at=y+16+row*16;
        fill(u,x,at,width,16,index==selected?13:15,0);
        label(u,x+8,at+4,(width-16)/8,labels[index]);
    }
    for(unsigned at=x-1;at<=x+width;++at) { pixel(u,at,y-1,true);pixel(u,at,y+height,true); }
    for(unsigned at=y-1;at<=y+height;++at) { pixel(u,x-1,at,true);pixel(u,x+width,at,true); }
}
void spectrum_ui_footer(spectrum_ui* u,const char* value) {
    fill(u,0,232,256,24,7,0);label(u,0,240,32,value);
}
bool spectrum_ui_present(spectrum_ui* u) {
    for(;;) {
        const uint32_t result=u->api->call(MK61_SERVICE_COLOR_DISPLAY,MK61_COLOR_PRESENT,0,sizeof(u->frame),&u->frame);
        if(result!=2) return result==1;
        mk61_api->delay_ms(1);
    }
}
