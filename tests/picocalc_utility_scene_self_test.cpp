#include "utility_scene.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
using namespace picocalc;
int main(int argc,char** argv) {
    static_assert(sizeof(utility::Animation)<=32,"animation state must stay small");
    utility::Animation animation;
    animation.tick(1000,10,20);assert(animation.frame(utility::Mode::USB)==0);
    animation.tick(1500,10,20);assert(animation.frame(utility::Mode::USB)==0);
    animation.tick(1600,11,20);assert((animation.frame(utility::Mode::USB)&7)!=0);
    assert(!(animation.frame(utility::Mode::USB)&32));
    animation.tick(1800,11,21);assert(animation.frame(utility::Mode::USB)&32);
    animation.tick(2500,11,21);assert(!(animation.frame(utility::Mode::USB)&7));
    animation.tick(3650,11,21);assert(animation.frame(utility::Mode::USB)==16);
    assert(animation.frame(utility::Mode::EJECTED)==0);
    animation.tick(4000,11,21);assert(animation.frame(utility::Mode::USB)==0);
    const u32 start=0xffffffffU-400;
    animation.begin_bootloader(start);animation.begin_bootloader(start+100);
    animation.tick(start-1,11,21);
    assert(!animation.ready() && !animation.timed_out() && animation.frame(utility::Mode::UF2_ENTERING)==0);
    for(u32 elapsed:{0U,119U,120U,959U,960U,2399U,2400U}) {
        animation.tick(start+elapsed,11,21);
        assert(animation.bootloader_pending());assert(animation.ready()==(elapsed>=960));
        assert(animation.timed_out()==(elapsed>=2400));
        assert(animation.boot_mode()==(elapsed>=960?utility::Mode::UF2_READY:utility::Mode::UF2_ENTERING));
    }
    std::array<u8,12800+32> guarded{};
    for(auto mode:{utility::Mode::USB,utility::Mode::EJECTED,utility::Mode::UF2_CONFIRM,
                  utility::Mode::UF2_ENTERING,utility::Mode::UF2_READY}) {
        for(unsigned phase=0;phase<64;++phase) {
            guarded.fill(0xa7);u8* frame=guarded.data()+16;std::memset(frame,0,12800);
            assert(utility::draw(frame,mode,phase));
            if(mode==utility::Mode::UF2_CONFIRM)
                for(unsigned y=152;y<154;++y)for(unsigned x=154;x<166;++x)
                    assert(!(frame[y*40+x/8]&(128U>>(x&7))));
            assert(utility::draw_headers(frame,mode,(phase&1)!=0));
            for(unsigned i=0;i<16;++i)assert(guarded[i]==0xa7 && guarded[12816+i]==0xa7);
            for(unsigned y=0;y<320;++y)if((y<64 || y>=224) && (y<34 || y>=58) && (y<5 || y>=27))
                for(unsigned x=0;x<40;++x)assert(frame[y*40+x]==0);
        }
    }
    if(argc==2) {
        struct Art { const char* name;const u8* bytes;unsigned size,raw; };
        #define ART(name,raw) Art{#name,utility_art::name,sizeof(utility_art::name),raw}
        for(const auto& art:{ART(usb,6400),ART(chip,6400),ART(cartridge,720),ART(glyphs,utility_art::GLYPH_BYTES)}) {
            std::array<u8,6400> raw{};assert(utility::unpack(art.bytes,art.size,raw.data(),art.raw));
            std::ofstream file(std::string(argv[1])+"/"+art.name+".raw",std::ios::binary);
            file.write((const char*)raw.data(),art.raw);assert(file.good());
        }
        #undef ART
        struct Label {const char* name;utility::Packed data;unsigned top,advance,rows;};
        #define LABEL(name,top,advance,rows) Label{#name,utility::asset(utility_art::name),top,advance,rows}
        for(const auto& label:{LABEL(brand,5,16,22),LABEL(title_usb_ru,34,20,24),LABEL(title_usb_en,34,20,24),
                LABEL(title_ejected_ru,34,20,24),LABEL(title_ejected_en,34,20,24),LABEL(title_uf2_ru,34,20,24),
                LABEL(title_uf2_en,34,20,24),LABEL(title_ready_ru,34,20,24),LABEL(title_ready_en,34,20,24)}) {
            u8 frame[12800]{};assert(utility::draw_label(frame,label.data,label.top,label.advance));
            std::ofstream file(std::string(argv[1])+"/"+label.name+".raw",std::ios::binary);
            file.write((const char*)frame+label.top*40,label.rows*40);assert(file.good());
        }
        #undef LABEL
    }
    std::puts("Pico utility scenes: guarded native raster, real-traffic animation, eject, bounded boot and timer wrap PASS");
}
