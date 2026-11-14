#ifndef MK61_PICOCALC_LCD_SHELL_UPDATE_HPP
#define MK61_PICOCALC_LCD_SHELL_UPDATE_HPP

#include "lcd_color.hpp"
#include "shell_color.hpp"

namespace picocalc::lcd {
// Include pixels whose ink changed while their monochrome bit stayed set.
// This matters for moving artwork and menu selection changes: comparing the
// one-bit frames alone would otherwise leave stale colors on the panel.
inline void plan_shell(Update& update,const uint8_t* previous,const uint8_t* next,
                       const ShellTheme& old_theme,const ShellTheme& new_theme,bool force) {
    update.plan(previous,next,force);
    if(force || old_theme.same(new_theme)) return;
    for(unsigned top=0;top<HEIGHT;top+=8) {
        unsigned first=STRIDE;
        for(unsigned column=0;column<=STRIDE;++column) {
            bool changed=false;
            if(column<STRIDE) {
                bool already_dirty=false;
                for(unsigned y=top;y<top+8;++y) {
                    const unsigned at=y*STRIDE+column;
                    if(previous[at]!=next[at]) { already_dirty=true;break; }
                }
                if(!already_dirty) for(unsigned y=top;y<top+8 && !changed;++y) {
                    const uint8_t bits=next[y*STRIDE+column];
                    for(unsigned b=0;b<8;++b) if(bits&(0x80U>>b)) {
                        const unsigned x=column*8+b;
                        if(old_theme.at(x,y)!=new_theme.at(x,y)) {changed=true;break;}
                    }
                }
            }
            if(changed && first==STRIDE) first=column;
            if(!changed && first!=STRIDE) {
                append_color_rect(update,{(uint16_t)(first*8),(uint16_t)top,
                                          (uint16_t)((column-first)*8),8});
                first=STRIDE;
            }
        }
    }
    update.bytes=0;
    for(unsigned i=0;i<update.count;++i)
        update.bytes+=update.rectangles[i].width*update.rectangles[i].height*2;
    if(update.bytes+update.count*2048>=WIDTH*HEIGHT*2) update.full();
}

inline void shell_scanline(const uint8_t* bitmap,const Rect& rect,unsigned row,
                           const ShellTheme& theme,uint16_t* output) {
    if(theme.base==Ink::MONO && !theme.count && theme.utility==UtilityArt::NONE) {
        scanline(bitmap,rect,row,(uint8_t*)output);return;
    }
    const unsigned y=rect.y+row;
    for(unsigned i=0;i<rect.width;++i) {
        const unsigned x=rect.x+i;
        output[i]=(bitmap[y*STRIDE+x/8]&(0x80U>>(x&7U)))?color(theme.at(x,y)):0;
    }
}
} // namespace picocalc::lcd
#endif
