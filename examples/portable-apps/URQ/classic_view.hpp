#ifndef URQ_CLASSIC_VIEW_HPP
#define URQ_CLASSIC_VIEW_HPP
#include "mk61_app.h"
#include "mk8_codec.hpp"
#include "mk8_literal.hpp"
#include <string.h>

// The Classic has enough pixels for four 12px story lines and an 8px hint.
// Only this transient page bitmap uses the stack; no second game arena.
namespace classic_view {
constexpr unsigned WIDTH=192, HEIGHT=64, BYTES=1536, PITCH=14;
inline bool available(const mk61_app_services* services) {
  return mk61_api->graphics_available && mk61_api->graphics_available() &&
      mk61_api->graphics_width()==WIDTH && mk61_api->graphics_height()==HEIGHT &&
      (services->call(MK61_SERVICE_CAPABILITIES,0,0,0,nullptr)&
       (MK61_SERVICE_CAP_FONT|MK61_SERVICE_CAP_UI_FONT))==(MK61_SERVICE_CAP_FONT|MK61_SERVICE_CAP_UI_FONT);
}
struct Canvas {
  const mk61_app_services* services;
  uint8_t* pixels;
  void pixel(unsigned x,unsigned y,bool ink=true) {
    if(x>=WIDTH || y>=HEIGHT) return;
    const uint8_t mask=uint8_t(1U<<(y&7));
    auto& byte=pixels[y/8*WIDTH+x];
    if(ink) byte|=mask; else byte&=uint8_t(~mask);
  }
  void box(unsigned x,unsigned y,unsigned w,unsigned h,bool fill=true) {
    for(unsigned dy=0;dy<h;++dy) for(unsigned dx=0;dx<w;++dx)
      if(fill || !dy || dy+1==h || !dx || dx+1==w) pixel(x+dx,y+dy);
  }
  mk61_service_ui_glyph glyph(uint8_t ch) const {
    mk61_service_ui_glyph g{};g.family=1;g.size=12;
    // The compact strike uses an ASCII dash for the M8 en/em dash variants.
    const unsigned cp=(ch==0x96 || ch==0x97)?unsigned('-'):mk8::codepoint(ch);
    services->call(MK61_SERVICE_UI_FONT,MK61_UI_FONT_GLYPH,cp,sizeof(g),&g);
    return g;
  }
  unsigned advance(uint8_t ch) const { return glyph(ch).advance; }
  void text(unsigned x,unsigned y,const char* value,bool inverse=false,bool small=false,unsigned right=WIDTH-3) {
    for(;*value;++value) {
      mk61_service_ui_glyph g{};
      if(small) {
        mk61_service_glyph source{};
        services->call(MK61_SERVICE_FONT,0,mk8::codepoint(uint8_t(*value)),0,&source);
        g.width=uint8_t(source.width);g.height=uint8_t(source.height);g.advance=6;g.bearing_y=8;
        memcpy(g.pixels,source.pixels,8);
      } else g=glyph(uint8_t(*value));
      if(!g.advance || x+g.advance>right) break;
      for(unsigned gy=0;gy<g.height;++gy) for(unsigned gx=0;gx<g.width;++gx)
        if(g.pixels[gy*((g.width+7)/8)+gx/8]&(0x80U>>(gx&7)))
          pixel(x+g.bearing_x+gx,y+(small?8:10)-g.bearing_y+gy,!inverse);
      x+=g.advance;
    }
  }
  void hint(const char* value) { box(0,55,WIDTH,1);text(3,56,value,false,true,WIDTH); }
  // Both selected captions and story text wrap by the resident glyph advance.
  unsigned wrap(const char* text,unsigned at,char* out,unsigned width) const {
    unsigned n=0,used=0,space=0;
    while(text[at+n] && text[at+n]!='\n' && n<126) {
      const unsigned step=advance(uint8_t(text[at+n]));
      if(n && used+step>width) break;
      if(text[at+n]==' ') space=n;
      used+=step;++n;
    }
    if(text[at+n] && text[at+n]!=' ' && text[at+n]!='\n' && space) n=space;
    memcpy(out,text+at,n);out[n]=0;at+=n;
    while(text[at]==' ' || text[at]=='\r') ++at;
    if(text[at]=='\n') ++at;
    return at;
  }
};
inline int menu(const mk61_app_services* services,mk61_service_menu_source& source) {
  if(!source.count || !mk61_api->graphics_begin()) return -1;
  for(;;) {
    uint8_t pixels[BYTES]{};Canvas canvas{services,pixels};
    canvas.box(0,0,WIDTH,8);canvas.text(4,0,source.title,true,true,150);
    char position[16];mk61_app_snprintf(services,position,sizeof(position),"%u/%u",unsigned(source.selected+1),unsigned(source.count));
    canvas.text(WIDTH-6*strlen(position)-3,0,position,true,true,WIDTH);
    const unsigned top=source.selected/3*3;
    for(unsigned row=0;row<3 && top+row<source.count;++row) {
      char label[128]{};
      if(!source.label(source.context,top+row,label,sizeof(label))) return -1;
      const unsigned y=10+row*PITCH;const bool active=top+row==source.selected;
      if(active) canvas.box(2,y,184,PITCH);
      canvas.text(6,y+1,label,active,false,184);
    }
    canvas.box(189,10,1,42);canvas.box(188,10+source.selected*36/source.count,3,6);
    canvas.hint(M8("←→:пункт OK:выбор ESC:назад"));
    mk61_api->graphics_present(pixels,sizeof(pixels));
    const uint32_t revision=mk61_api->graphics_revision?mk61_api->graphics_revision():0;
    int key;
    do {
      key=mk61_api->key_poll();
      if(key>=0 || (mk61_api->graphics_revision && mk61_api->graphics_revision()!=revision)) break;
      mk61_api->delay_ms(1);
    } while(true);
    if(key==MK61_APP_KEY_OK) return int(source.selected);
    if(key==MK61_APP_KEY_ESC || key==MK61_APP_KEY_USER) return -1;
    if((key==MK61_APP_KEY_LEFT || key==MK61_APP_KEY_SHIFT_LEFT || key==MK61_APP_KEY_BACKWARD) && source.selected) --source.selected;
    if((key==MK61_APP_KEY_RIGHT || key==MK61_APP_KEY_SHIFT_RIGHT || key==MK61_APP_KEY_FORWARD) && source.selected+1<source.count) ++source.selected;
  }
}
}
#endif
