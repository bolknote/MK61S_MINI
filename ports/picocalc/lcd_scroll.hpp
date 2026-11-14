#ifndef MK61_PICOCALC_LCD_SCROLL_HPP
#define MK61_PICOCALC_LCD_SCROLL_HPP
#include "lcd_update.hpp"
#include "loadable_app_services.h"
namespace picocalc::lcd {
struct Region {
    uint16_t top=0,height=0;
    bool valid() const { return height>=32 && top<HEIGHT && height<=HEIGHT-top; }
    bool operator==(Region other) const { return top==other.top && height==other.height; }
    bool operator!=(Region other) const { return !(*this==other); }
};
struct Scroll {
    Region region;
    unsigned offset=0;
    unsigned map(unsigned y) const {
        if(!region.valid() || y<region.top || y>=region.top+region.height) return y;
        return region.top+(y-region.top+offset)%region.height;
    }
    unsigned run(unsigned y,unsigned count) const {
        unsigned rows=1;
        while(rows<count && map(y+rows)==map(y)+rows) ++rows;
        return rows;
    }
    static int find(const uint8_t* previous,const uint8_t* next,Region region) {
        if(!region.valid()) return 0;
        const auto* before=previous+region.top*STRIDE;
        const auto* after=next+region.top*STRIDE;
        if(!std::memcmp(before,after,region.height*STRIDE)) return 0;
        const unsigned limit=region.height/2<64?region.height/2:64;
        for(unsigned delta=1;delta<=limit;++delta) {
            const unsigned bytes=(region.height-delta)*STRIDE;
            const unsigned probe=bytes<8*STRIDE?bytes:8*STRIDE;
            if(!std::memcmp(before+delta*STRIDE,after,probe) && !std::memcmp(before+delta*STRIDE,after,bytes)) return (int)delta;
            if(!std::memcmp(before,after+delta*STRIDE,probe) && !std::memcmp(before,after+delta*STRIDE,bytes)) return -(int)delta;
        }
        return 0;
    }
    void rotate(uint8_t* frame,int delta) {
        const unsigned shift=(delta%(int)region.height+region.height)%region.height;
        if(!shift) return;
        unsigned a=region.height,b=shift;
        while(b) { const unsigned rest=a%b;a=b;b=rest; }
        uint8_t saved[STRIDE];auto* body=frame+region.top*STRIDE;
        for(unsigned start=0;start<a;++start) {
            std::memcpy(saved,body+start*STRIDE,STRIDE);
            unsigned current=start;
            for(;;) {
                const unsigned next=(current+shift)%region.height;
                if(next==start) break;
                std::memcpy(body+current*STRIDE,body+next*STRIDE,STRIDE);current=next;
            }
            std::memcpy(body+current*STRIDE,saved,STRIDE);
        }
        offset=(offset+shift)%region.height;
    }
};
// A color strip is copied before DMA; the complete RGB565 image stays in
// GRAM. Keep a mapping transaction, not a second color framebuffer. The new
// origin is published only after every exposed/changed strip has completed.
struct ColorScroll {
    bool open=false,valid=false,failed=false;
    unsigned rows=0;
    static bool accepts(const mk61_service_color_scroll& r) {
        return Region{r.top,r.height}.valid() && r.previous<r.height && r.offset<r.height;
    }
    unsigned begin(Scroll& mapping,const mk61_service_color_scroll& r) {
        if(open || !accepts(r)) return 0;
        const Region region{r.top,r.height};
        const bool reuse=valid && mapping.region==region && mapping.offset==r.previous;
        const unsigned distance=(r.offset+r.height-r.previous)%r.height;
        rows=reuse?(distance<r.height-distance?distance:r.height-distance):0;
        mapping={region,r.offset};open=true;valid=false;failed=false;
        return reuse?1:3;
    }
    void fault() { valid=false;if(open) failed=true; }
    bool ready() {
        if(!open) return false;
        if(failed) {failed=false;return false;}
        return true;
    }
    void committed() { open=false;valid=true; }
    void reset() { *this={}; }
};
}
#endif
