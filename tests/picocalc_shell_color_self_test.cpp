#include "lcd_shell_update.hpp"
#include "utility_scene.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace picocalc;
using namespace picocalc::lcd;

namespace {
using Frame=std::array<uint8_t,BYTES>;

bool covered(const Update& update,unsigned x,unsigned y) {
    for(unsigned i=0;i<update.count;++i) {
        const auto& r=update.rectangles[i];
        if(x>=r.x && x<r.x+r.width && y>=r.y && y<r.y+r.height) return true;
    }
    return false;
}
bool on(const Frame& f,unsigned x,unsigned y) {
    return f[y*STRIDE+x/8]&(0x80U>>(x&7));
}
uint16_t visible(const Frame& f,const ShellTheme& t,unsigned x,unsigned y) {
    return on(f,x,y)?color(t.at(x,y)):0;
}
void verify_update(const Frame& old_frame,const Frame& next_frame,
                   const ShellTheme& old_theme,const ShellTheme& next_theme) {
    Update update;plan_shell(update,old_frame.data(),next_frame.data(),old_theme,next_theme,false);
    for(unsigned y=0;y<HEIGHT;++y) for(unsigned x=0;x<WIDTH;++x)
        if(visible(old_frame,old_theme,x,y)!=visible(next_frame,next_theme,x,y))
            assert(covered(update,x,y));
}
ShellTheme utility_theme(UtilityArt art,unsigned phase,const uint8_t* cartridge) {
    ShellTheme theme;theme.reset();theme.add(0,64,320,160,Ink::WHITE);
    theme.utility=art;theme.phase=(uint8_t)phase;theme.cartridge=cartridge;
    return theme;
}
void color_only_changes() {
    Frame pixels{};pixels[85*STRIDE+10]=0xff;
    ShellTheme before,after;before.reset();after.reset();
    after.add(80,80,8,8,Ink::GREEN);
    Update update;plan_shell(update,pixels.data(),pixels.data(),before,after,false);
    assert(update.count && covered(update,80,85) && update.bytes<WIDTH*HEIGHT*2);
    uint16_t row[8]{};shell_scanline(pixels.data(),{80,85,8,1},0,after,row);
    for(auto pixel:row) assert(pixel==color(Ink::GREEN));
    pixels.fill(0);plan_shell(update,pixels.data(),pixels.data(),before,after,false);
    assert(!update.count); // A color change over black is invisible.

    ShellTheme mono;mono.reset(Ink::MONO);
    pixels[0]=0x81;uint16_t output[8]{};
    shell_scanline(pixels.data(),{0,0,8,1},0,mono,output);
    for(unsigned i=0;i<8;++i) assert(output[i]==((i==0 || i==7)?0xffff:0));
}
void grid_selection_changes() {
    Frame frame{};
    // Include filled selection, text, and grid pixels with unchanged bits:
    // only their ink roles change as the selection moves between cells.
    for(unsigned y=56;y<272;++y) for(unsigned x=0;x<320;++x)
        if((x+y)%3==0) frame[y*STRIDE+x/8]|=(uint8_t)(0x80U>>(x&7));
    for(unsigned cell_width:{72U,96U}) {
        ShellTheme before,after;before.reset();after.reset();
        for(auto* theme:{&before,&after}) {
            assert(theme->add(0,34,320,46,Ink::OCHRE));
            assert(theme->add(0,80,31,192,Ink::OCHRE));
            assert(theme->add_grid(31,56,289,216,cell_width,24));
        }
        assert(before.add(33,81,cell_width-2,22,Ink::OCHRE));
        assert(after.add(33+cell_width,81,cell_width-2,22,Ink::OCHRE));
        verify_update(frame,frame,before,after);
        assert(before.at(31,75)==Ink::LINE && before.at(50,79)==Ink::LINE);
        assert(before.at(40,85)==Ink::OCHRE && after.at(40,85)==Ink::SOFT);
    }
}
void utility_animations() {
    uint8_t cartridge[720]{};
    assert(utility::unpack(utility_art::cartridge,sizeof(utility_art::cartridge),cartridge,sizeof(cartridge)));
    static_assert(sizeof(utility_art::cartridge_mask)==sizeof(cartridge),"native cartridge mask size");
    assert(std::memcmp(cartridge,utility_art::cartridge_mask,sizeof(cartridge))==0);
    Frame previous{};ShellTheme previous_theme;bool have_previous=false;
    const auto verify=[&](utility::Mode mode,UtilityArt art,unsigned phase) {
        Frame next{};assert(utility::draw(next.data(),mode,phase));
        const auto theme=utility_theme(art,phase,cartridge);
        if(have_previous) verify_update(previous,next,previous_theme,theme);
        unsigned green=0;
        for(unsigned y=64;y<224;++y) for(unsigned x=0;x<320;++x) {
            if(!on(next,x,y) || theme.at(x,y)!=Ink::GREEN) continue;
            ++green;
            if(art==UtilityArt::UF2_CONFIRM) {
                const int row=(int)y-146;
                const bool arrow=(x>=158 && x<162 && y>=143 && y<147) ||
                    (row>=0 && row<6 && x>=154U+(unsigned)row && x<166U-(unsigned)row);
                assert(arrow);
            } else if(art==UtilityArt::UF2_ENTERING || art==UtilityArt::UF2_READY) assert(false);
        }
        if(art==UtilityArt::UF2_CONFIRM) assert(green==54);
        if(art==UtilityArt::UF2_ENTERING || art==UtilityArt::UF2_READY) assert(!green);
        previous=next;previous_theme=theme;have_previous=true;
    };
    verify(utility::Mode::UF2_CONFIRM,UtilityArt::UF2_CONFIRM,0);
    verify(utility::Mode::UF2_CONFIRM,UtilityArt::UF2_CONFIRM,1);
    for(unsigned phase=0;phase<=28;++phase)
        verify(utility::Mode::UF2_ENTERING,UtilityArt::UF2_ENTERING,phase);
    verify(utility::Mode::UF2_READY,UtilityArt::UF2_READY,0);
    verify(utility::Mode::USB,UtilityArt::USB,0);
    verify(utility::Mode::USB,UtilityArt::USB,utility::BLINK);
    for(unsigned phase=1;phase<=21;++phase) {
        verify(utility::Mode::USB,UtilityArt::USB,phase);
        verify(utility::Mode::USB,UtilityArt::USB,phase|utility::WRITING);
    }
    verify(utility::Mode::EJECTED,UtilityArt::EJECTED,0);
}
}

int main() {
    static_assert(color(Ink::GREEN)==rgb565(0,212,106),"mockup's emerald");
    static_assert(color(Ink::OCHRE)==rgb565(179,157,123),"chosen register color");
    color_only_changes();grid_selection_changes();utility_animations();
    std::puts("PicoCalc shell color: palette, partial updates, USB and UF2 animations PASS");
}
