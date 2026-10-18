#ifndef MK61_PICOCALC_CANVAS_HPP
#define MK61_PICOCALC_CANVAS_HPP
#include "fonts.hpp"
#include <cstring>
namespace picocalc { namespace canvas {
constexpr unsigned WIDTH=320, HEIGHT=320, BYTES=WIDTH*HEIGHT/8;
// The foreground owner borrows this page-major bitmap. The panel has its own
// row-major buffer, which also serves as the stable USB Screen snapshot.
u8* frame();
void clear();
inline void pixel(u8* out,int x,int y,bool on=true,unsigned width=WIDTH,unsigned height=HEIGHT) {
    if(!out || x<0 || y<0 || (unsigned)x>=width || (unsigned)y>=height) return;
    auto& byte=out[(unsigned)y/8*width+(unsigned)x];const u8 bit=1U<<(y&7);
    if(on) byte|=bit;else byte&=(u8)~bit;
}
inline void rect(u8* out,int x,int y,unsigned w,unsigned h,bool on=false) {
    for(unsigned dy=0;dy<h;++dy) for(unsigned dx=0;dx<w;++dx) pixel(out,x+dx,y+dy,on);
}
unsigned glyph(u8* out,const Settings& font,u16 cp,int x,int top,bool inverse=false);
unsigned text(u8* out,const Settings& font,const char* value,int x,int top,unsigned right=WIDTH);
} }
#endif
