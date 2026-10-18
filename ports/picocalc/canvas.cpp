#include "canvas.hpp"
#include "mk8_codec.hpp"
namespace picocalc { namespace canvas {
namespace { u8 pixels[BYTES]{}; }
u8* frame() { return pixels; }
void clear() { std::memset(pixels,0,sizeof(pixels)); }
unsigned glyph(u8* out,const Settings& font,u16 cp,int x,int top,bool inverse) {
    mk61_service_ui_glyph g{};if(!fonts::glyph(font,cp,g)) return 0;
    const int baseline=top+fonts::info(font).ascent;
    for(unsigned gy=0;gy<g.height;++gy) for(unsigned gx=0;gx<g.width;++gx)
        if(g.pixels[gy*((g.width+7)/8)+gx/8]&(0x80U>>(gx&7)))
            pixel(out,x+g.bearing_x+gx,baseline-g.bearing_y+gy,!inverse);
    return g.advance;
}
unsigned text(u8* out,const Settings& font,const char* value,int x,int top,unsigned right) {
    const int start=x;
    for(;*value;++value) {
        mk61_service_ui_glyph g{};if(!fonts::glyph(font,mk8::codepoint((u8)*value),g)) continue;
        if(x+g.advance>(int)right) break;
        x+=glyph(out,font,mk8::codepoint((u8)*value),x,top);
    }
    return x-start;
}
} }
