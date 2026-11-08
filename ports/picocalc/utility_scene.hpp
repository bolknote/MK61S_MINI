#ifndef MK61_PICOCALC_UTILITY_SCENE_HPP
#define MK61_PICOCALC_UTILITY_SCENE_HPP
#include "utility_art.hpp"
#include "zx0.hpp"
#include <cstring>

namespace picocalc { namespace utility {
enum class Mode : u8 { NONE, USB, EJECTED, UF2_CONFIRM, UF2_ENTERING, UF2_READY };

// Only time and transfer counters live here; no timer/IRQ or additional raster.
class Animation {
public:
    void tick(u32 now,u32 reads,u32 writes) {
        now_=now;
        if(seen_ && (reads!=reads_ || writes!=writes_)) {
            traffic_=true;changed_=now;writing_=writes!=writes_;
        }
        seen_=true;reads_=reads;writes_=writes;
    }
    void begin_bootloader(u32 now) { if(!boot_) {now_=started_=now;boot_=true;} }
    bool bootloader_pending() const { return boot_; }
    bool ready() const { return boot_ && elapsed()>=960; }
    bool timed_out() const { return boot_ && elapsed()>=2400; }
    Mode boot_mode() const { return ready()?Mode::UF2_READY:Mode::UF2_ENTERING; }
    unsigned frame(Mode mode) const {
        if(mode==Mode::UF2_ENTERING) return elapsed()/120;
        if(mode==Mode::UF2_CONFIRM) return (now_/600)&1U;
        if(mode!=Mode::USB) return 0;
        const bool active=traffic_ && (u32)(now_-changed_)<700;
        return (now_%4000>=3600 && now_%4000<3760 ? 16U:0U) |
            (active?1U+(now_/140)%5+(writing_?32U:0U):0U);
    }
private:
    u32 elapsed() const {
        const u32 difference=now_-started_;
        // A stale loop timestamp must not look like a 49-day timeout.
        return difference<0x80000000U?difference:0;
    }
    u32 now_=0,started_=0,reads_=0,writes_=0,changed_=0;
    bool seen_=false,traffic_=false,writing_=false,boot_=false;
};

inline bool unpack(const u8* source,unsigned size,u8* out,unsigned capacity) {
    struct Reader { const u8* at;const u8* end; } reader{source,source+size};
    u32 written=0;
    return zx0::decode({&reader,[](void* p,u8& byte) {
        auto& r=*(Reader*)p;if(r.at==r.end)return false;byte=*r.at++;return true;
    }},size,out,capacity,written) && written==capacity;
}
struct Packed { const u8* data;unsigned bytes; };
inline void rectangle(u8* frame,int x,int y,unsigned w,unsigned h,bool on=true);
template<unsigned N> constexpr Packed asset(const u8 (&bytes)[N]) { return {bytes,N}; }
inline Packed title(Mode mode,bool russian) {
    switch(mode) {
    case Mode::USB:return russian?asset(utility_art::title_usb_ru):asset(utility_art::title_usb_en);
    case Mode::EJECTED:return russian?asset(utility_art::title_ejected_ru):asset(utility_art::title_ejected_en);
    case Mode::UF2_READY:return russian?asset(utility_art::title_ready_ru):asset(utility_art::title_ready_en);
    default:return russian?asset(utility_art::title_uf2_ru):asset(utility_art::title_uf2_en);
    }
}
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((noinline,optimize("Os")))
#else
__attribute__((noinline))
#endif
inline bool letters(u8* frame,const u8* glyphs,Packed label,unsigned top,unsigned advance) {
    unsigned left=12;
    for(unsigned i=0;i<label.bytes;++i) {
        const unsigned index=label.data[i];
        if(index==255) {left+=10;continue;}
        if(index>=utility_art::GLYPH_COUNT)return false;
        for(unsigned y=0;y<9;++y) for(unsigned x=0;x<7;++x)
            if(glyphs[index*9+y]&(64U>>x)) rectangle(frame,left+2*x,top+2*y,3,3);
        left+=advance;
    }
    return true;
}
inline bool draw_label(u8* frame,Packed label,unsigned top,unsigned advance) {
    u8 glyphs[utility_art::GLYPH_BYTES];
    return unpack(utility_art::glyphs,sizeof(utility_art::glyphs),glyphs,sizeof(glyphs)) &&
        letters(frame,glyphs,label,top,advance);
}
inline bool draw_headers(u8* frame,Mode mode,bool russian) {
    u8 glyphs[utility_art::GLYPH_BYTES];
    return unpack(utility_art::glyphs,sizeof(utility_art::glyphs),glyphs,sizeof(glyphs)) &&
        letters(frame,glyphs,asset(utility_art::brand),5,16) && letters(frame,glyphs,title(mode,russian),34,20);
}
inline void rectangle(u8* frame,int x,int y,unsigned w,unsigned h,bool on) {
    for(unsigned dy=0;dy<h;++dy) for(unsigned dx=0;dx<w;++dx) {
        const int px=x+dx,py=y+dy;
        if(px<0 || py<0 || px>=320 || py>=320) continue;
        auto& byte=frame[py*40+px/8];const u8 mask=128U>>(px&7);
        if(on)byte|=mask;else byte&=(u8)~mask;
    }
}
inline void eye(u8* out,int x,int y,bool closed) {
    if(closed) {rectangle(out,x,y+6,16,3);return;}
    rectangle(out,x,y+6,3,3);rectangle(out,x+3,y+3,3,3);rectangle(out,x+6,y,4,3);
    rectangle(out,x+10,y+3,3,3);rectangle(out,x+13,y+6,3,3);
}
// Output is the existing row-major MSB framebuffer. Decoder history lives in
// that framebuffer too. Only the moving 80x72 cartridge borrows 720 stack bytes.
inline bool draw(u8* frame,Mode mode,unsigned phase) {
    const bool usb=mode==Mode::USB || mode==Mode::EJECTED;
    const u8* packed=usb?utility_art::usb:utility_art::chip;
    const unsigned bytes=usb?sizeof(utility_art::usb):sizeof(utility_art::chip);
    if(!unpack(packed,bytes,frame+64*40,160*40)) return false;
    if(usb) {
        const bool wink=mode==Mode::USB && (phase&16);
        eye(frame,52,118,wink);eye(frame,90,118,wink);
        rectangle(frame,71,138,18,3);rectangle(frame,74,141,12,3);rectangle(frame,77,144,6,2);
        if(mode==Mode::EJECTED) {
            // A static check in the gap: the host actually ejected the card.
            rectangle(frame,168,146,4,8);rectangle(frame,172,150,4,8);
            rectangle(frame,176,146,4,8);rectangle(frame,180,142,4,8);
        } else if(phase&7U) {
            const unsigned step=(phase&7U)-1;
            const unsigned x=(phase&32U)?142+step*5:162-step*5;
            for(unsigned n=0;n<3;++n)rectangle(frame,x+16*n,142,7,7);
        }
    } else {
        u8 card[720];
        if(!unpack(utility_art::cartridge,sizeof(utility_art::cartridge),card,sizeof(card))) return false;
        const int top=mode==Mode::UF2_READY?96:mode==Mode::UF2_ENTERING?68+(int)(phase>7?7:phase)*4:68+(phase&1U)*2;
        // The cartridge slides into the socket, behind the front of the chip.
        for(unsigned y=0;y<72 && top+(int)y<154;++y) for(unsigned x=0;x<80;++x)
            if(card[y*10+x/8]&(128U>>(x&7))) rectangle(frame,120+x,top+y,1,1);
        if(mode==Mode::UF2_CONFIRM) {
            rectangle(frame,158,143,4,4);
            for(unsigned y=0;y<6;++y) rectangle(frame,154+y,146+y,12-2*y,1);
        }
    }
    return true;
}
} }
#endif
