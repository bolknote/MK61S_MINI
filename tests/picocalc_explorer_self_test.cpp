#include "services.hpp"
#include "screen.hpp"
#include "script.hpp"
#include "m61_text.hpp"
#include "mk8_literal.hpp"
#include "shared_memory_buffer.hpp"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

extern u64 picocalc_host_read_count();
namespace {
using namespace picocalc;
unsigned find(const Services& service,const char* name) {
    for(unsigned i=0;i<service.browser_count();++i) {
        char label[64];if(service.browser_label(i,label) && !std::strcmp(label,name)) return i;
    }
    assert(false);return 0;
}
void select(Services& service,unsigned index) {
    while(service.browser_selection()<index) assert(service.input(0xB7));
    while(service.browser_selection()>index) assert(service.input(0xB4));
}
void preview(const Screen& screen) {
    const char* prefix=std::getenv("MK61_LAYOUT_PREVIEW_PREFIX");if(!prefix) return;
    const std::string path=std::string(prefix)+"-explorer.pbm";
    FILE* output=std::fopen(path.c_str(),"wb");assert(output);
    std::fprintf(output,"P4\n320 320\n");
    assert(std::fwrite(screen.data(),1,Screen::BYTES,output)==Screen::BYTES);std::fclose(output);
}
}
void picocalc_explorer_test() {
    using namespace picocalc;
    assert(files::mkdir("/ExplorerNative"));
    for(const char* name:{"/ExplorerNative/IconOnly","/ExplorerNative/Bad","/ExplorerNative/Launcher"}) assert(files::mkdir(name));
    for(unsigned i=0;i<12;++i) {
        char path[80];std::snprintf(path,sizeof(path),"/ExplorerNative/File%02u.txt",i);
        assert(files::write_text(path,"fixture",7));
    }
    u8 bytes[132];std::memset(bytes,0xFF,sizeof(bytes));
    bytes[0]=bytes[1]=0;bytes[2]=bytes[3]=32;bytes[4]=0x7F;
    assert(files::write("/ExplorerNative/IconOnly/autoexec.wbmp",bytes,sizeof(bytes)));
    bytes[2]=31;assert(files::write("/ExplorerNative/Bad/autoexec.wbmp",bytes,sizeof(bytes)));bytes[2]=32;
    assert(files::write_text("/ExplorerNative/Launcher/autoexec.m61","invalid on purpose",18));
    Calculator calculator;calculator.init();Ui ui;ui.init(Settings{});
    static constexpr usize external_bytes=8192;
    static std::vector<u8> external(external_bytes);
    const bool own_backend=shared_memory::buffer_statistics().external_capacity==0;
    if(own_backend) assert(shared_memory::configure_buffer_backend({external_bytes,
        [] {return true;},
        [](u32 at,void* out,usize size) {if(at>external.size() || size>external.size()-at) return false;std::memcpy(out,external.data()+at,size);return true;},
        [](u32 at,const void* in,usize size) {if(at>external.size() || size>external.size()-at) return false;std::memcpy(external.data()+at,in,size);return true;},
        [] {return true;}}));
    const auto before=shared_memory::buffer_statistics();
    {
        Services service;service.set_ui(ui);service.open(Action::EXPLORER,true,calculator);
        assert(service.enter_directory("/ExplorerNative",false));
        assert(service.browser_count()==9 && service.browser_more() && service.browser_selection()==0);
        const unsigned good=find(service,"IconOnly"),bad=find(service,"Bad"),launcher=find(service,"Launcher");
        explorer_view::Icon icon{};
        assert(service.browser_icon(good,icon));assert(icon.pixels[0]==0x80);
        assert(!service.browser_icon(bad,icon));
        Screen screen;screen.render(calculator.snapshot(),true,&ui,&service);
        select(service,good);
        const auto reads=picocalc_host_read_count();
        for(unsigned i=0;i<12;++i) {
            service.input(0xB7);screen.render(calculator.snapshot(),true,&ui,&service);
            service.input(0xB4);screen.render(calculator.snapshot(),true,&ui,&service);
        }
        assert(picocalc_host_read_count()==reads); // real FatFs, no SD read per highlight/frame
        if(own_backend) {
            shared_memory::Buffer required;
            assert(required.acquire(shared_memory::Owner::APPLICATION,external.size(),shared_memory::BufferAccess::EXTERNAL_ONLY));
            assert(!service.browser_icon(good,icon)); // eviction revokes the optional cache safely
            // Match the device: VM/SD leases occupy all PSRAM and cannot be
            // reclaimed. Icons still load into a temporary 1152-byte SRAM lease.
            service.filter_directory("");
            assert(service.browser_icon(good,icon) && icon.pixels[0]==0x80);
            assert(shared_memory::buffer_statistics().internal_used>=9*explorer_view::ICON_BYTES);
            const auto full_reads=picocalc_host_read_count();
            service.input(0xB7);screen.render(calculator.snapshot(),true,&ui,&service);
            service.input(0xB4);screen.render(calculator.snapshot(),true,&ui,&service);
            assert(picocalc_host_read_count()==full_reads);
            u8 shipped[132];FILE* asset=std::fopen("programs/games/Turochamp/autoexec.wbmp","rb");assert(asset);
            assert(std::fread(shipped,1,sizeof(shipped),asset)==sizeof(shipped));std::fclose(asset);
            assert(files::write("/ExplorerNative/IconOnly/autoexec.wbmp",shipped,sizeof(shipped)));
            service.tick();explorer_view::Icon expected{};
            assert(explorer_view::decode_icon(shipped,sizeof(shipped),expected));
            assert(service.browser_icon(good,icon) && !std::memcmp(icon.pixels,expected.pixels,sizeof(icon.pixels)));
            select(service,8);service.input(0xB7);assert(service.browser_offset()==9);
            service.input(0xB4);assert(service.browser_offset()==0);
            assert(service.browser_icon(good,icon) && !std::memcmp(icon.pixels,expected.pixels,sizeof(icon.pixels)));
            const auto full=shared_memory::buffer_statistics();
            assert(full.external_used==external_bytes);
            assert(full.internal_used==before.internal_used+sizeof(files::Entry)*9+9*explorer_view::ICON_BYTES);
            service.input(0x1B);service.input(0x1B);service.tick();assert(!service.active());
            assert(shared_memory::buffer_statistics().internal_used==before.internal_used);
            assert(required.reset());service.open(Action::EXPLORER,true,calculator);
            assert(service.enter_directory("/ExplorerNative",false));
            assert(service.browser_icon(good,icon));
        }
        bytes[4]=0xBF;assert(files::write("/ExplorerNative/IconOnly/autoexec.wbmp",bytes,sizeof(bytes)));
        service.tick();assert(service.browser_icon(good,icon));assert(icon.pixels[0]==0x40);
        bytes[2]=1;assert(files::write("/ExplorerNative/IconOnly/autoexec.wbmp",bytes,sizeof(bytes)));
        service.tick();assert(!service.browser_icon(good,icon));bytes[2]=32;
        assert(files::remove("/ExplorerNative/IconOnly/autoexec.wbmp"));service.tick();assert(!service.browser_icon(good,icon));
        // An ordinary icon folder does not run anything. Actions can enter a
        // launcher folder without parsing/executing its deliberately bad script.
        assert(service.enter_directory("/ExplorerNative/IconOnly"));
        assert(!std::strcmp(service.page_name(),"BROWSER") && !m61_text::active());
        service.input('\r');assert(!std::strcmp(service.page_name(),"PROMPT"));
        service.input(0x1B);assert(!std::strcmp(service.page_name(),"BROWSER"));
        assert(service.enter_directory("/ExplorerNative",false));select(service,launcher);
        service.input(0x81);for(unsigned i=0;i<5;++i) service.input(0xB6);service.input('\r');
        assert(!std::strcmp(service.page_name(),"BROWSER") && !m61_text::active());
        assert(service.browser_count()==1);
        assert(service.enter_directory("/ExplorerNative",false));
        select(service,8);service.input(0xB7);
        assert(service.browser_offset()==9 && service.browser_selection()==0);
        service.input(0xB4);assert(service.browser_offset()==0 && service.browser_selection()==8);
        service.input(0x88);assert(service.browser_mode()==explorer_view::Mode::LIST);
        assert(screen.render(calculator.snapshot(),true,&ui,&service));
        assert(!screen.render(calculator.snapshot(),true,&ui,&service));
        service.input(0x88);assert(service.browser_mode()==explorer_view::Mode::ICONS);
        assert(screen.render(calculator.snapshot(),true,&ui,&service));
        // Supply the shipped artwork through the same FAT reader and cache.
        FILE* asset=std::fopen("programs/games/Turochamp/autoexec.wbmp","rb");assert(asset);
        assert(std::fread(bytes,1,sizeof(bytes),asset)==sizeof(bytes));std::fclose(asset);
        assert(files::write("/ExplorerNative/IconOnly/autoexec.wbmp",bytes,sizeof(bytes)));
        service.tick();select(service,good);screen.render(calculator.snapshot(),true,&ui,&service);preview(screen);
        service.input(0x1B);service.input(0x1B);service.tick();assert(!service.active());
    }
    const auto after=shared_memory::buffer_statistics();
    assert(after.internal_used==before.internal_used && after.active==before.active);
    if(own_backend) assert(shared_memory::configure_buffer_backend({}));
    std::puts("Pico Explorer: 9 native tiles, zero SD reads on selection, revision/invalid icon fallback, paging, folder bypass and buffer lifetime PASS");
}
