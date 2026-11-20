#ifndef MK61_PICOCALC_LCD_COLOR_HPP
#define MK61_PICOCALC_LCD_COLOR_HPP
#include "loadable_app_services.h"
#include "lcd_update.hpp"
#if defined(PICO_ON_DEVICE) && defined(__GNUC__)
#define MK61_LCD_COLOR_CODE(name) __attribute__((noinline,section(".lcd_color_code." #name)))
#else
#define MK61_LCD_COLOR_CODE(name)
#endif

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
    } else if(format==MK61_COLOR_RGB565) {
        pixels=2U*f.width*f.height;
        if(f.tiles || f.tile_bytes) return false;
    } else if(format==MK61_COLOR_TILE1 || format==MK61_COLOR_TILE8) {
        if((f.width|f.height)&7U || !f.tiles) return false;
        pixels=f.width*f.height/8;tiles=f.width*f.height/64*(format==MK61_COLOR_TILE8?2:1);
    } else if(format==MK61_COLOR_CELL565) {
        if((f.width&7U) || !f.tiles) return false;
        pixels=f.width*f.height/8;tiles=pixels*4;
    } else return false;
    if(f.pixel_bytes!=pixels || f.tile_bytes!=tiles || pixels+tiles>MK61_COLOR_SNAPSHOT_BYTES) return false;
    if(format==MK61_COLOR_TILE8) for(unsigned i=0;i<tiles;++i) if(f.tiles[i]>=64) return false;
    return true;
}
inline bool same_color_view(const mk61_service_color_frame& a,const mk61_service_color_frame& b) {
    return a.x==b.x && a.y==b.y && a.width==b.width && a.height==b.height &&
           a.format==b.format;
}
inline uint16_t cell_color(const uint8_t* colors) {
    return static_cast<uint16_t>(colors[0]|(colors[1]<<8));
}
MK61_LCD_COLOR_CODE(scanline) inline void cell565_scanline(const mk61_service_color_frame& f,const Rect& r,
                                               unsigned row,uint16_t* out) {
    unsigned x=r.x-f.x,left=r.width;
    const unsigned first=(r.y-f.y+row)*(f.width/8);
    while(left) {
        const unsigned cell=first+x/8,bit=x&7,span=left<8-bit?left:8-bit;
        const uint8_t bits=f.pixels[cell];const auto* colors=f.tiles+4*cell;
        const uint16_t paper=cell_color(colors),ink=cell_color(colors+2);
        for(unsigned i=bit;i<bit+span;++i)*out++=(bits&(128U>>i))?ink:paper;
        x+=span;left-=span;
    }
}
MK61_LCD_COLOR_CODE(dirty) inline bool cell565_dirty(const mk61_service_color_frame& old,const mk61_service_color_frame& next,
                                           unsigned x,unsigned y,unsigned rows) {
    const unsigned stride=next.width/8;
    for(unsigned row=0;row<rows;++row) {
        const unsigned cell=(y+row)*stride+x/8;
        if(old.pixels[cell]!=next.pixels[cell] || std::memcmp(old.tiles+4*cell,next.tiles+4*cell,4)!=0) return true;
    }
    return false;
}
inline uint16_t color_pixel(const mk61_service_color_frame& f,unsigned x,unsigned y,const uint16_t* palette64=nullptr) {
    unsigned index;const unsigned format=f.format&~MK61_COLOR_PRESERVE_OUTSIDE;
    if(format==MK61_COLOR_RGB565) return cell_color(f.pixels+2*(y*f.width+x));
    if(format==MK61_COLOR_CELL565) {
        const unsigned cell=y*(f.width/8)+x/8;
        return cell_color(f.tiles+cell*4+(f.pixels[cell]&(128U>>(x&7))?2:0));
    }
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
#if defined(PICO_ON_DEVICE) && defined(__GNUC__)
__attribute__((always_inline))
#endif
inline void color_scanline(const mk61_service_color_frame& f,const Rect& r,unsigned row,uint16_t* out,
                           const uint16_t* palette64=nullptr,void (*progress)()=nullptr) {
    const unsigned format=f.format&~MK61_COLOR_PRESERVE_OUTSIDE;
    if(format==MK61_COLOR_RGB565) {
        const auto* pixels=f.pixels+2*((r.y-f.y+row)*f.width+r.x-f.x);
        for(unsigned x=0;x<r.width;) {
            const unsigned n=progress && r.width-x>64?64:r.width-x;
            for(unsigned i=0;i<n;++i) out[x+i]=cell_color(pixels+2*(x+i));
            x+=n;
            if(progress) progress();
        }
        return;
    }
    if(format==MK61_COLOR_CELL565) {
        if(!progress) cell565_scanline(f,r,row,out);
        else for(unsigned x=0;x<r.width;x+=64) {
            const unsigned width=r.width-x<64?r.width-x:64;
            cell565_scanline(f,Rect{(uint16_t)(r.x+x),r.y,(uint16_t)width,r.height},row,out+x);
            progress();
        }
        return;
    }
    if(format==MK61_COLOR_TILE1 || format==MK61_COLOR_TILE8) {
        const unsigned stride=f.width/8,y=r.y-f.y+row;
        const uint8_t* pixels=f.pixels+y*stride;
        const uint8_t* tiles=f.tiles+(y/8)*stride*(format==MK61_COLOR_TILE8?2:1);
        // Load the bitmap/attributes and select two colors once per tile,
        // rather than repeating view arithmetic for every output pixel.
        unsigned x=r.x-f.x,left=r.width;
        while(left) {
            const unsigned tile=x/8,bit=x&7,span=left<8-bit?left:8-bit;
            const uint8_t bits=pixels[tile];uint16_t paper,ink;
            if(format==MK61_COLOR_TILE8) {
                paper=palette64?palette64[tiles[2*tile]]:0;
                ink=palette64?palette64[tiles[2*tile+1]]:0;
            } else {const uint8_t pair=tiles[tile];paper=f.palette[pair>>4];ink=f.palette[pair&15];}
            for(unsigned i=bit;i<bit+span;++i)*out++=(bits&(0x80U>>i))?ink:paper;
            x+=span;left-=span;
            if(progress && !(x&63))progress();
        }
        return;
    }
    unsigned x=r.x-f.x;
    const unsigned end=x+r.width;
    const uint8_t* pixels=f.pixels+(r.y-f.y+row)*((f.width+1U)/2)+x/2;
    if(x&1U) {
        *out++=f.palette[*pixels++&15];++x;
        if(progress && !(x&63))progress();
    }
    for(;x+1<end;x+=2) {
        const unsigned pair=*pixels++;
        *out++=f.palette[pair>>4];*out++=f.palette[pair&15];
        if(progress && !((x+2)&63))progress();
    }
    if(x<end)*out=f.palette[*pixels>>4];
}
inline void append_color_rect(Update& u,const Rect& next) {
    // Search all live windows: two distant sprites can each continue down
    // the next band without joining the unchanged pixels between them.
    for(unsigned i=0;i<u.count;++i) {
        auto& r=u.rectangles[i];
        if(r.x==next.x && r.width==next.width && r.y+r.height==next.y) {
            r.height+=next.height;return;
        }
    }
    if(u.count<Update::CAPACITY) { u.rectangles[u.count++]=next;return; }
    // Retain the fixed window budget. Expanding the cheapest existing
    // window covers this run without dropping updates or allocating a map.
    unsigned best=0,extra=UINT32_MAX;Rect expanded{};
    for(unsigned i=0;i<u.count;++i) {
        const auto& r=u.rectangles[i];
        const unsigned x=r.x<next.x?r.x:next.x,y=r.y<next.y?r.y:next.y;
        const unsigned right=r.x+r.width>next.x+next.width?r.x+r.width:next.x+next.width;
        const unsigned bottom=r.y+r.height>next.y+next.height?r.y+r.height:next.y+next.height;
        const unsigned cost=(right-x)*(bottom-y)-r.width*r.height;
        if(cost<extra) {
            best=i;extra=cost;
            expanded={(uint16_t)x,(uint16_t)y,(uint16_t)(right-x),(uint16_t)(bottom-y)};
        }
    }
    u.rectangles[best]=expanded;
}
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((optimize("O2")))
#endif
MK61_LCD_COLOR_CODE(plan) inline void plan_color(Update& u,const mk61_service_color_frame& old,const mk61_service_color_frame& next,bool force) {
    u.count=u.bytes=0;
    // Use the same conservative window charge as the monochrome planner:
    // commands, DMA setup and row service cost about 2048 pixel-data bytes.
    constexpr unsigned WINDOW_BYTES=2048;
    const unsigned format=next.format&~MK61_COLOR_PRESERVE_OUTSIDE;
    if(force || !same_color_view(old,next) ||
       (format!=MK61_COLOR_RGB565 && std::memcmp(old.palette,next.palette,sizeof(old.palette)))) {
        u.rectangles[0]={next.x,next.y,next.width,next.height};u.count=1;
    } else {
        // An unchanged frame needs no tile walk. The bulk comparison also
        // avoids thousands of tiny memcmp calls for idle/held game frames.
        if(!std::memcmp(old.pixels,next.pixels,next.pixel_bytes) &&
           (!next.tile_bytes || !std::memcmp(old.tiles,next.tiles,next.tile_bytes)))return;
        // Compare each tile once. Keep distant dirty runs separate; bridge
        // short gaps only when their pixel data costs less than a new window.
        for(unsigned y=0;y<next.height;y+=8) {
            unsigned first=next.width,last=0;
            const unsigned rows=next.height-y<8?next.height-y:8;
            const bool tiled=format==MK61_COLOR_TILE1 || format==MK61_COLOR_TILE8;
            alignas(uint32_t) uint8_t changed[WIDTH/8]{};
            if(tiled) {
                // Walk the bitmap in row order and accumulate one byte per
                // tile. No per-tile memcmp, division or strided inner walk.
                const unsigned stride=next.width/8;
                const auto* before=old.pixels+y*stride;const auto* after=next.pixels+y*stride;
                if(!((uintptr_t(before)|uintptr_t(after)|stride)&3U)) {
                    // Four tile columns per load on aligned bitmaps. Builtin
                    // copies preserve byte-buffer aliasing; unaligned APP
                    // buffers retain the byte path below on Cortex-M0+.
                    for(unsigned row=0;row<rows;++row) {
                        for(unsigned column=0;column<stride;column+=4) {
                            uint32_t a,b,c;
                            __builtin_memcpy(&a,__builtin_assume_aligned(before+column,4),4);
                            __builtin_memcpy(&b,__builtin_assume_aligned(after+column,4),4);
                            __builtin_memcpy(&c,changed+column,4);c|=a^b;
                            __builtin_memcpy(changed+column,&c,4);
                        }
                        before+=stride;after+=stride;
                    }
                } else for(unsigned row=0;row<rows;++row) {
                    for(unsigned column=0;column<stride;++column)changed[column]|=before[column]^after[column];
                    before+=stride;after+=stride;
                }
                const unsigned bytes=format==MK61_COLOR_TILE8?2:1;
                before=old.tiles+(y/8)*stride*bytes;after=next.tiles+(y/8)*stride*bytes;
                for(unsigned column=0;column<stride;++column) {
                    changed[column]|=before[column*bytes]^after[column*bytes];
                    if(bytes==2)changed[column]|=before[column*2+1]^after[column*2+1];
                }
            }
            for(unsigned x=0;x<next.width;x+=8) {
                bool dirty=false;
                if(tiled) {
                    dirty=changed[x/8]!=0;
                } else if(format==MK61_COLOR_CELL565) {
                    dirty=cell565_dirty(old,next,x,y,rows);
                } else {
                    const bool rgb=format==MK61_COLOR_RGB565;
                    const unsigned stride=rgb?2U*next.width:(next.width+1U)/2;
                    const unsigned column=rgb?2*x:x/2;
                    const unsigned width=next.width-x<8?next.width-x:8;
                    const unsigned bytes=rgb?2*width:(width+1U)/2;
                    for(unsigned row=0;row<rows && !dirty;++row)
                        dirty=std::memcmp(old.pixels+(y+row)*stride+column,next.pixels+(y+row)*stride+column,bytes)!=0;
                }
                if(dirty) {
                    if(first!=next.width && (x-last)*rows*2>WINDOW_BYTES) {
                        append_color_rect(u,{(uint16_t)(next.x+first),(uint16_t)(next.y+y),
                            (uint16_t)(last-first),(uint16_t)rows});
                        first=next.width;
                    }
                    if(first==next.width) first=x;
                    last=x+8<next.width?x+8:next.width;
                }
            }
            if(first==next.width) continue;
            append_color_rect(u,{(uint16_t)(next.x+first),(uint16_t)(next.y+y),
                (uint16_t)(last-first),(uint16_t)rows});
        }
    }
    for(unsigned i=0;i<u.count;++i) u.bytes+=u.rectangles[i].width*u.rectangles[i].height*2;
    const unsigned full_bytes=next.width*next.height*2;
    if(u.count && u.bytes+u.count*WINDOW_BYTES>=full_bytes+WINDOW_BYTES) {
        u.rectangles[0]={next.x,next.y,next.width,next.height};u.count=1;u.bytes=full_bytes;
    }
}
inline void copy_color(mk61_service_color_frame& out,const mk61_service_color_frame& in,uint8_t* storage) {
    std::memcpy(storage,in.pixels,in.pixel_bytes);
    if(in.tile_bytes) std::memcpy(storage+in.pixel_bytes,in.tiles,in.tile_bytes);
    out=in;out.pixels=storage;out.tiles=in.tile_bytes?storage+in.pixel_bytes:nullptr;
}
} // namespace picocalc::lcd
#undef MK61_LCD_COLOR_CODE
#endif
