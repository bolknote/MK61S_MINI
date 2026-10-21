#ifndef MK61_PICOCALC_LCD_UPDATE_HPP
#define MK61_PICOCALC_LCD_UPDATE_HPP

#include <cstdint>
#include <array>
#include <cstring>

namespace picocalc::lcd {
constexpr unsigned WIDTH=320, HEIGHT=320, STRIDE=WIDTH/8, BYTES=STRIDE*HEIGHT;
struct Rect { uint16_t x,y,width,height; };

// Bound RAM while retaining sparse updates. When the rectangle budget is
// full, expand the cheapest existing window instead of sending the screen.
// The input is the immutable, horizontal MSB-first LCD bitmap.
struct Update {
    static constexpr unsigned CAPACITY=32;
    Rect rectangles[CAPACITY]{};
    unsigned count=0,bytes=0;
    void full() {
        count=1;bytes=WIDTH*HEIGHT*2;
        rectangles[0]={0,0,WIDTH,HEIGHT};
    }
    void plan(const uint8_t* previous,const uint8_t* next,bool force=false) {
        count=bytes=0;
        if(force) { full();return; }
        for(unsigned y=0;y<HEIGHT;y+=8) {
            // One dirty tile is eight pixels by eight pixels. This preserves
            // separate windows for distant cursors rather than their bounding box.
            bool dirty[STRIDE]{};
            for(unsigned row=y;row<y+8;++row)
                for(unsigned x=0;x<STRIDE;++x)
                    dirty[x]|=previous[row*STRIDE+x]!=next[row*STRIDE+x];
            for(unsigned x=0;x<STRIDE;) {
                if(!dirty[x]) { ++x;continue; }
                const unsigned first=x;
                while(x<STRIDE && dirty[x]) ++x;
                const unsigned left=first*8,width=(x-first)*8;
                unsigned index=0;
                while(index<count && !(rectangles[index].x==left &&
                      rectangles[index].width==width &&
                      rectangles[index].y+rectangles[index].height==y)) ++index;
                if(index<count) rectangles[index].height+=8;
                else {
                    if(count<CAPACITY) rectangles[count++]={(uint16_t)left,(uint16_t)y,(uint16_t)width,8};
                    else {
                        unsigned best=0,best_extra=WIDTH*HEIGHT;
                        Rect expanded{};
                        for(unsigned i=0;i<count;++i) {
                            const auto& r=rectangles[i];
                            const unsigned x0=r.x<left?r.x:left,y0=r.y<y?r.y:y;
                            const unsigned x1=r.x+r.width>left+width?r.x+r.width:left+width;
                            const unsigned y1=r.y+r.height>y+8?r.y+r.height:y+8;
                            const unsigned extra=(x1-x0)*(y1-y0)-r.width*r.height;
                            if(extra<best_extra) {
                                best=i;best_extra=extra;
                                expanded={(uint16_t)x0,(uint16_t)y0,(uint16_t)(x1-x0),(uint16_t)(y1-y0)};
                            }
                        }
                        rectangles[best]=expanded;
                    }
                }
            }
        }
        for(unsigned i=0;i<count;++i) bytes+=rectangles[i].width*rectangles[i].height*2;
        // Windows also cost commands, DMA setup and I/O service between
        // short rows. On Pico H a near-full checkerboard split into 32
        // windows takes longer than one full window despite fewer pixels.
        // Charge about 1.3 ms/window at 12.5 MHz, while sparse cursors remain
        // comfortably below a full transfer even at the rectangle limit.
        if(bytes+count*2048>=WIDTH*HEIGHT*2) full();
    }
};

inline void scanline(const uint8_t* frame,const Rect& rect,unsigned row,uint8_t* output) {
    // Dirty rectangles are tile-aligned. Four pixels at once remove the
    // per-pixel branch, mask and pair of byte stores; the small table remains
    // in flash and both SRAM scanline buffers retain their original size.
    static constexpr auto expanded=[] {
        std::array<std::array<uint8_t,8>,16> table{};
        for(unsigned n=0;n<16;++n)
            for(unsigned x=0;x<4;++x)
                table[n][x*2]=table[n][x*2+1]=(n&(8U>>x))?0xFF:0;
        return table;
    }();
    if(!((rect.x|rect.width)&7)) {
        const auto* source=frame+(rect.y+row)*STRIDE+rect.x/8;
        for(unsigned x=0;x<rect.width/8;++x) {
            std::memcpy(output+x*16,expanded[source[x]>>4].data(),8);
            std::memcpy(output+x*16+8,expanded[source[x]&15].data(),8);
        }
        return;
    }
    for(unsigned x=0;x<rect.width;++x) {
        const unsigned source_x=rect.x+x;
        const uint8_t value=frame[(rect.y+row)*STRIDE+source_x/8] & (0x80U>>(source_x%8)) ? 0xFF : 0;
        output[x*2]=output[x*2+1]=value;
    }
}
} // namespace picocalc::lcd
#endif
