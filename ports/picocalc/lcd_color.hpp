#ifndef MK61_PICOCALC_LCD_COLOR_HPP
#define MK61_PICOCALC_LCD_COLOR_HPP
#include "loadable_app_services.h"
#include "lcd_update.hpp"

namespace picocalc::lcd {
// Color APPs borrow the panel's existing monochrome snapshot storage. No
// caller pointers remain live after submit, including palette/attribute data.
inline bool valid_color(const mk61_service_color_frame& f) {
    if(!f.pixels || !f.width || !f.height || f.width>WIDTH || f.height>HEIGHT ||
       f.x>WIDTH-f.width || f.y>HEIGHT-f.height) return false;
    unsigned pixels=0,tiles=0;const unsigned format=f.format&~MK61_COLOR_PRESERVE_OUTSIDE;
    if(format==MK61_COLOR_INDEX4) {
        pixels=((f.width+1U)/2)*f.height;
        if(f.tiles || f.tile_bytes) return false;
    } else if(format==MK61_COLOR_TILE1 || format==MK61_COLOR_TILE8) {
        if((f.width|f.height)&7U || !f.tiles) return false;
        pixels=f.width*f.height/8;tiles=f.width*f.height/64*(format==MK61_COLOR_TILE8?2:1);
    } else return false;
    if(f.pixel_bytes!=pixels || f.tile_bytes!=tiles || pixels+tiles>MK61_COLOR_SNAPSHOT_BYTES) return false;
    if(format==MK61_COLOR_TILE8) for(unsigned i=0;i<tiles;++i) if(f.tiles[i]>=64) return false;
    return true;
}
inline bool same_color_view(const mk61_service_color_frame& a,const mk61_service_color_frame& b) {
    return a.x==b.x && a.y==b.y && a.width==b.width && a.height==b.height &&
           a.format==b.format;
}
inline uint16_t color_pixel(const mk61_service_color_frame& f,unsigned x,unsigned y,const uint16_t* palette64=nullptr) {
    unsigned index;const unsigned format=f.format&~MK61_COLOR_PRESERVE_OUTSIDE;
    if(format==MK61_COLOR_INDEX4) {
        const auto pair=f.pixels[y*((f.width+1U)/2)+x/2];
        index=(x&1U)?pair&15U:pair>>4;
    } else if(format==MK61_COLOR_TILE8) {
        const unsigned tile=((y/8)*(f.width/8)+x/8)*2;
        index=f.tiles[tile+((f.pixels[y*(f.width/8)+x/8]&(0x80U>>(x&7U)))?1:0)];
        return palette64?palette64[index]:0;
    } else {
        const auto pair=f.tiles[(y/8)*(f.width/8)+x/8];
        index=(f.pixels[y*(f.width/8)+x/8]&(0x80U>>(x&7U)))?pair&15U:pair>>4;
    }
    return f.palette[index];
}
inline void color_scanline(const mk61_service_color_frame& f,const Rect& r,unsigned row,uint16_t* out,const uint16_t* palette64=nullptr) {
    for(unsigned x=0;x<r.width;++x) out[x]=color_pixel(f,r.x-f.x+x,r.y-f.y+row,palette64);
}
inline void plan_color(Update& u,const mk61_service_color_frame& old,const mk61_service_color_frame& next,bool force) {
    u.count=u.bytes=0;
    const unsigned format=next.format&~MK61_COLOR_PRESERVE_OUTSIDE;
    if(force || !same_color_view(old,next) || std::memcmp(old.palette,next.palette,sizeof(old.palette))) {
        u.rectangles[0]={next.x,next.y,next.width,next.height};u.count=1;
    } else {
        // Compare eight-row bands. Merge adjacent equal spans, bounding both
        // planning time and command overhead without allocating a dirty map.
        for(unsigned y=0;y<next.height;y+=8) {
            unsigned first=next.width,last=0;
            const unsigned rows=next.height-y<8?next.height-y:8;
            for(unsigned x=0;x<next.width;x+=8) {
                bool dirty=false;
                if(format==MK61_COLOR_TILE1 || format==MK61_COLOR_TILE8) {
                    const unsigned column=x/8,stride=next.width/8;
                    const unsigned bytes=format==MK61_COLOR_TILE8?2:1;
                    dirty=std::memcmp(old.tiles+((y/8)*stride+column)*bytes,next.tiles+((y/8)*stride+column)*bytes,bytes)!=0;
                    for(unsigned row=0;row<rows && !dirty;++row)
                        dirty=old.pixels[(y+row)*stride+column]!=next.pixels[(y+row)*stride+column];
                } else {
                    const unsigned stride=(next.width+1U)/2;
                    const unsigned bytes=(next.width-x<8?(next.width-x+1U)/2:4);
                    for(unsigned row=0;row<rows && !dirty;++row)
                        dirty=std::memcmp(old.pixels+(y+row)*stride+x/2,next.pixels+(y+row)*stride+x/2,bytes)!=0;
                }
                if(dirty) { if(first==next.width) first=x;last=x+8<next.width?x+8:next.width; }
            }
            if(first==next.width) continue;
            if(u.count && u.rectangles[u.count-1].x==next.x+first &&
               u.rectangles[u.count-1].width==last-first &&
               u.rectangles[u.count-1].y+u.rectangles[u.count-1].height==next.y+y)
                u.rectangles[u.count-1].height+=rows;
            else if(u.count<Update::CAPACITY)
                u.rectangles[u.count++]={(uint16_t)(next.x+first),(uint16_t)(next.y+y),(uint16_t)(last-first),(uint16_t)rows};
            else { u.rectangles[0]={next.x,next.y,next.width,next.height};u.count=1;break; }
        }
    }
    for(unsigned i=0;i<u.count;++i) u.bytes+=u.rectangles[i].width*u.rectangles[i].height*2;
}
inline void copy_color(mk61_service_color_frame& out,const mk61_service_color_frame& in,uint8_t* storage) {
    std::memcpy(storage,in.pixels,in.pixel_bytes);
    if(in.tile_bytes) std::memcpy(storage+in.pixel_bytes,in.tiles,in.tile_bytes);
    out=in;out.pixels=storage;out.tiles=in.tile_bytes?storage+in.pixel_bytes:nullptr;
}
} // namespace picocalc::lcd
#endif
