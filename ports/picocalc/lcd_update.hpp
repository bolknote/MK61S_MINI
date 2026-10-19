#ifndef MK61_PICOCALC_LCD_UPDATE_HPP
#define MK61_PICOCALC_LCD_UPDATE_HPP

#include <cstdint>

namespace picocalc::lcd {
constexpr unsigned WIDTH=320, HEIGHT=320, STRIDE=WIDTH/8, BYTES=STRIDE*HEIGHT;
struct Rect { uint16_t x,y,width,height; };

// Bound both RAM and command overhead. Fragmented updates fall back to one
// full window. The input is the immutable, horizontal MSB-first LCD bitmap.
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
                    if(count==CAPACITY) { full();return; }
                    rectangles[count++]={(uint16_t)left,(uint16_t)y,(uint16_t)width,8};
                }
                bytes+=width*8*2;
            }
        }
    }
};

inline void scanline(const uint8_t* frame,const Rect& rect,unsigned row,uint8_t* output) {
    for(unsigned x=0;x<rect.width;++x) {
        const unsigned source_x=rect.x+x;
        const uint8_t value=frame[(rect.y+row)*STRIDE+source_x/8] & (0x80U>>(source_x%8)) ? 0xFF : 0;
        output[x*2]=output[x*2+1]=value;
    }
}
} // namespace picocalc::lcd
#endif
