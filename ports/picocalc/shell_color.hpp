#ifndef MK61_PICOCALC_SHELL_COLOR_HPP
#define MK61_PICOCALC_SHELL_COLOR_HPP

#include <cstdint>

namespace picocalc::lcd {
// The shell keeps its existing one-bit framebuffer. These roles describe
// foreground pixels; zero bits remain black. Native APP color frames keep
// using their separate, unchanged presentation API.
enum class Ink : uint8_t { MONO, WHITE, SOFT, LINE, OCHRE, GREEN, GRID, GRID_CONFIG };
enum class UtilityArt : uint8_t { NONE, USB, EJECTED, UF2_CONFIRM, UF2_ENTERING, UF2_READY };

constexpr uint16_t rgb565(unsigned r,unsigned g,unsigned b) {
    return (uint16_t)((((r*31U+127U)/255U)<<11) |
                      (((g*63U+127U)/255U)<<5) | ((b*31U+127U)/255U));
}
constexpr uint16_t color(Ink ink) {
    switch(ink) {
    case Ink::MONO:  return 0xffff;
    case Ink::WHITE: return rgb565(0xf0,0xf5,0xe9);
    case Ink::SOFT:  return rgb565(0xb8,0xc9,0xc4);
    case Ink::LINE:  return rgb565(0x52,0x6c,0x70);
    case Ink::OCHRE: return rgb565(0xb3,0x9d,0x7b);
    case Ink::GREEN: return rgb565(0x00,0xd4,0x6a);
    case Ink::GRID: case Ink::GRID_CONFIG: break;
    }
    return 0xffff;
}
struct InkRegion {
    // Four nine-bit coordinates and a three-bit role occupy five bytes.
    // Keeping two theme snapshots small protects the APP/audio SRAM reserve.
    uint8_t low_x=0,low_y=0,low_width=0,low_height=0,high=0;
    InkRegion()=default;
    InkRegion(unsigned x,unsigned y,unsigned width,unsigned height,Ink ink)
      :low_x((uint8_t)x),low_y((uint8_t)y),low_width((uint8_t)width),low_height((uint8_t)height),
       high((uint8_t)((x>>8)|((y>>8)<<1)|((width>>8)<<2)|((height>>8)<<3)|((unsigned)ink<<4))) {}
    unsigned x() const { return low_x|((high&1U)<<8); }
    unsigned y() const { return low_y|((high&2U)<<7); }
    unsigned width() const { return low_width|((high&4U)<<6); }
    unsigned height() const { return low_height|((high&8U)<<5); }
    Ink ink() const { return (Ink)(high>>4); }
    bool same(const InkRegion& o) const {
        return low_x==o.low_x && low_y==o.low_y && low_width==o.low_width &&
               low_height==o.low_height && high==o.high;
    }
};
struct ShellTheme {
    // A region describes a semantic element, never a bitmap allocation.
    // Later regions take precedence where elements overlap.
    static constexpr unsigned CAPACITY=7;
    InkRegion regions[CAPACITY]{};
    unsigned count=0;
    Ink base=Ink::SOFT;
    UtilityArt utility=UtilityArt::NONE;
    uint8_t phase=0;
    const uint8_t* cartridge=nullptr; // immutable 80x72, MSB-first bitmap

    void reset(Ink value=Ink::SOFT) {
        count=0;base=value;utility=UtilityArt::NONE;phase=0;cartridge=nullptr;
    }
    bool add(unsigned x,unsigned y,unsigned width,unsigned height,Ink value) {
        if(!width || !height || x>=320 || y>=320 || count==CAPACITY) return false;
        if(width>320-x) width=320-x;
        if(height>320-y) height=320-y;
        regions[count++]=InkRegion(x,y,width,height,value);
        return true;
    }
    bool add_grid(unsigned x,unsigned y,unsigned width,unsigned height,unsigned column,unsigned row) {
        if(!column || !row || column>320 || row>320 || count+2>CAPACITY) return false;
        if(!add(x,y,width,height,Ink::GRID)) return false;
        regions[count++]=InkRegion(column,row,0,0,Ink::GRID_CONFIG);
        return true;
    }
    bool same(const ShellTheme& other) const {
        if(base!=other.base || count!=other.count || utility!=other.utility ||
           phase!=other.phase || cartridge!=other.cartridge) return false;
        for(unsigned i=0;i<count;++i) {
            const auto& a=regions[i];const auto& b=other.regions[i];
            if(!a.same(b)) return false;
        }
        return true;
    }
    bool scroll_safe(unsigned top,unsigned height) const {
        if(utility!=UtilityArt::NONE) return false;
        for(unsigned i=0;i<count;++i) {
            const auto& r=regions[i];
            if(r.ink()==Ink::GRID_CONFIG) continue;
            if(r.y()<top+height && top<r.y()+r.height() &&
               (r.ink()==Ink::GRID || !(r.y()<=top && r.y()+r.height()>=top+height))) return false;
        }
        return true;
    }
    Ink at(unsigned x,unsigned y) const {
        Ink result=base;
        for(unsigned i=0;i<count;++i) {
            const auto& r=regions[i];
            if(r.ink()==Ink::GRID && i+1<count) {
                const auto& grid=regions[++i];
                if(x<r.x() || x-r.x()>=r.width() || y<r.y() || y-r.y()>=r.height()) continue;
                for(unsigned line=r.x();line<r.x()+r.width();line+=grid.x())
                    if(x==line) {result=Ink::LINE;break;}
                for(unsigned line=r.y()+grid.y()-1;line<r.y()+r.height();line+=grid.y())
                    if(y==line && x>r.x()) {result=Ink::LINE;break;}
            } else if(r.ink()!=Ink::GRID_CONFIG && x>=r.x() && x-r.x()<r.width() && y>=r.y() && y-r.y()<r.height()) result=r.ink();
        }
        if(utility==UtilityArt::USB || utility==UtilityArt::EJECTED) {
            if(x>=210 && x<282 && y>=94 && y<200) result=Ink::OCHRE;
            // The USB packets, rather than a fixed rectangle around their
            // path, are green. The scene's cable and eyes retain their ink.
            const unsigned packet=phase&31U;
            if(utility==UtilityArt::USB && packet && y>=142 && y<149) {
                const unsigned step=packet-1>20?20:packet-1;
                const unsigned left=(phase&64U)?142+step:162-step;
                for(unsigned n=0;n<3;++n)
                    if(x>=left+16*n && x<left+16*n+7) return Ink::GREEN;
            }
        } else if(utility!=UtilityArt::NONE) {
            const unsigned top=utility==UtilityArt::UF2_READY?96:
                utility==UtilityArt::UF2_ENTERING?68+(phase>28?28:phase):68+(phase&1U)*2;
            if(cartridge && x>=120 && x<200 && y>=top && y<154 && y<top+72) {
                // Only the cartridge bitmap is ochre. Four fixed chip pins
                // cross its insertion lane and remain the chip's white.
                const unsigned cx=x-120,cy=y-top;
                const bool card=cartridge[cy*10+cx/8]&(0x80U>>(cx&7U));
                bool pin=false;
                if(y>=146 && y<154) for(unsigned px=122;px<=198;px+=19)
                    if(px!=160 && x>=px && x<px+8) pin=true;
                if(card && !pin) result=Ink::OCHRE;
            }
            // The arrow exists only in the confirmation frame. During the
            // insertion the same coordinates contain moving cartridge ink.
            if(utility==UtilityArt::UF2_CONFIRM) {
                if(x>=158 && x<162 && y>=143 && y<147) return Ink::GREEN;
                if(y>=146 && y<152) {
                    const unsigned row=y-146;
                    if(x>=154+row && x<166-row) return Ink::GREEN;
                }
            }
        }
        return result;
    }
};
} // namespace picocalc::lcd
#endif
