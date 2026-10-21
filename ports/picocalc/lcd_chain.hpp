#ifndef MK61_PICOCALC_LCD_CHAIN_HPP
#define MK61_PICOCALC_LCD_CHAIN_HPP
#include "lcd_update.hpp"
#include <cstdint>
namespace picocalc::lcd {
constexpr unsigned STRIP_ROWS=3;
struct Segment { uint32_t count; uintptr_t source; };
// Zero source is a quiet null trigger: if the producer is late, DMA stops
// at this descriptor rather than reusing either strip. Descriptors remain
// alive until RX drains the whole window and the terminal null is consumed.
struct Stream {
    static constexpr unsigned CAPACITY=(HEIGHT+STRIP_ROWS-1)/STRIP_ROWS;
    Segment segments[CAPACITY+1]{};
    unsigned count=0;
    void reset(const Rect& rect) {
        count=(rect.height+STRIP_ROWS-1)/STRIP_ROWS;
        for(unsigned i=0;i<=count;++i) segments[i]={0,0};
    }
    static Segment prepare(const uint8_t* frame,const Rect& rect,unsigned index,uint16_t* output) {
        const unsigned first=index*STRIP_ROWS;
        const unsigned rows=rect.height-first<STRIP_ROWS?rect.height-first:STRIP_ROWS;
        for(unsigned row=0;row<rows;++row)
            scanline(frame,rect,first+row,(uint8_t*)(output+row*rect.width));
        return {rows*rect.width,(uintptr_t)output};
    }
    // Called only after SPI and its RX FIFO are drained. A stalled control
    // descriptor may be retried from this wire position, never from a guessed
    // descriptor index which could duplicate a short completed strip.
    static unsigned next(unsigned pixels,unsigned width) {
        return (pixels+width*STRIP_ROWS-1)/(width*STRIP_ROWS);
    }
};
}
#endif
