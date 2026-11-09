#include "screen.hpp"
#include "services.hpp"
#include "fonts.hpp"
#include "clock.hpp"
#include "ui_font_catalog.hpp"
#include "mk8_codec.hpp"
#include "mk8_literal.hpp"
#include "display_symbols.hpp"
#include "rtc_idle_clock_core.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace {
using namespace picocalc;
unsigned checks=0;
void require(bool value,const char* why) {
    ++checks;
    if(!value) { std::fprintf(stderr,"PicoCalc UI layout: %s\n",why);std::abort(); }
}
struct Text {
    unsigned width,height;
    std::vector<u8> pixels;
    Text(Settings font,const char* value,unsigned size,unsigned tracking=0,bool bold=false) {
        if(font.ui_font_family==1) font.ui_font_size=(u8)size;
        const auto metrics=fonts::info(font);
        width=fonts::text_width(font,value,(unsigned)std::strlen(value))+tracking*std::strlen(value);height=metrics.height+(bold?1:0);
        pixels.resize(width*height);
        unsigned left=0;
        for(;*value;++value) {
            mk61_service_ui_glyph glyph{};
            require(fonts::glyph(font,mk8::codepoint((u8)*value),glyph),"fixture glyph");
            for(unsigned y=0;y<glyph.height;++y) for(unsigned x=0;x<glyph.width;++x) {
                if(!(glyph.pixels[y*((glyph.width+7)/8)+x/8]&(0x80U>>(x&7)))) continue;
                const int px=(int)left+glyph.bearing_x+x,py=(int)metrics.ascent-glyph.bearing_y+y;
                require(px>=0 && (unsigned)px<width && py>=0 && (unsigned)py<height,"glyph stays in its line box");
                pixels[(unsigned)py*width+(unsigned)px]=1;
                if(bold) {
                    require((unsigned)px+1<width && (unsigned)py+1<height,"bold native glyph stays in its line box");
                    pixels[(unsigned)py*width+(unsigned)px+1]=1;
                    pixels[((unsigned)py+1)*width+(unsigned)px]=1;
                    pixels[((unsigned)py+1)*width+(unsigned)px+1]=1;
                }
            }
            left+=glyph.advance+tracking;
        }
    }
    bool matches(const Screen& screen,unsigned left,unsigned top,bool inverse=false) const {
        if(left+width>312 || top+height>320) return false;
        for(unsigned y=0;y<height;++y) for(unsigned x=0;x<width;++x)
            if(screen.pixel(left+x,top+y)!=((pixels[y*width+x]!=0)!=inverse)) return false;
        return true;
    }
};
int find_x(const Text& text,const Screen& screen,unsigned top,unsigned first=18,unsigned last=96) {
    for(unsigned x=first;x<=last;++x) if(text.matches(screen,x,top)) return (int)x;
    return -1;
}
int find_y(const Text& text,const Screen& screen) {
    for(unsigned y=40;y+text.height<282;++y) if(text.matches(screen,10,y)) return (int)y;
    return -1;
}
std::string core_values() {
    char raw[INDICATOR_STRING_LENGTH];std::string result=MK61Emu_GetIndicatorStr(nullptr);
    for(int s=X1;s<=T;++s) result+=read_stack_register((stack)s,raw,nullptr);
    for(int r=0;r<15;++r) { MK61Emu_ReadRegister(r,raw,nullptr);result+=raw; }
    return result;
}
void fixture(Calculator& calc) {
    calc.init();
    for(const char* p="1.2345678ne99";*p;++p) require(calc.input((u8)*p),"X2 input");
    for(unsigned i=0;i<4096;++i) { calc.tick();if(calc.idle()&&!core_61::is_RUN()) break; }
    require(calc.idle()&&!core_61::is_RUN(),"fixture settles");
    require(std::strstr(calc.snapshot().indicator,"Err")==nullptr,"finite X2 fixture");
    require(write_stack_register(X1,'-',"12345678",-99),"negative long X1");
    require(write_stack_register(X,' ',"98765432",99),"X differs from X2");
    require(write_stack_register(Y,' ',"12345678",-12),"Y fixture");
    require(write_stack_register(Z,'-',"87654321",23),"Z fixture");
    require(write_stack_register(T,' ',"31415926",0),"T fixture");
    for(unsigned i=0;i<15;++i) {
        const u8 packed[]={(u8)(4U|(i&1?0x80:0)),(u8)(((i+1)/10)*16+(i+1)%10),0x12,0x34,0x56,0x78};
        require(MK61Emu_UnpackRegster((u8)i,packed)!=nullptr,"memory fixture");
    }
}
void preview(const Screen& screen,const char* suffix) {
    const char* prefix=std::getenv("MK61_LAYOUT_PREVIEW_PREFIX");if(!prefix) return;
    const std::string path=std::string(prefix)+suffix+".pbm";
    FILE* file=std::fopen(path.c_str(),"wb");require(file,"preview output");
    std::fprintf(file,"P4\n320 320\n");
    require(std::fwrite(screen.data(),1,Screen::BYTES,file)==Screen::BYTES,"preview raster");
    std::fclose(file);
}
void menu(Services& services,Ui& ui,Calculator& calc,unsigned count) {
    Screen screen;int previous=-1;
    Settings face=ui.settings();
    const bool browser=services.browser_actions();
    if(browser) {face.ui_font_family=1;face.ui_font_size=16;face.ui_font_key=0;}
    const auto metrics=fonts::info(face);
    for(unsigned i=0;i<count;++i) {
        char row[Services::COLS+1];services.row(i,row);
        require(row[0]=='>',"every menu item is selectable");
        screen.render(calc.snapshot(),true,&ui,&services);
        const Text text(face,browser?row+2:row,face.ui_font_size);
        int top=-1;
        if(browser) {
            for(unsigned y=40;y+text.height<282;++y)
                if(text.matches(screen,16,y,true)) {top=(int)y;break;}
        } else top=find_y(text,screen);
        require(top>=40,"complete menu item fits between header and footer");
        if(previous>=0) {
            require(top-previous>=27,"selection menu has the same minimum pitch as the main menu");
            require(top-previous>=(int)(metrics.height+metrics.line_gap+8),"menu leaves breathing room after its actual line box");
        }
        previous=top;
        require(services.input(0xB6),"next menu item");
    }
    char row[Services::COLS+1];services.row(count-1,row);
    require(row[0]=='>',"selection clamps at last menu item");
    services.row(count,row);require(!row[0],"no hidden extra menu item");
    for(unsigned i=1;i<count;++i) services.input(0xB5);
}
void check_choice(const Settings& settings,Calculator& calc) {
    Ui ui;ui.init(settings);
    require(ui.settings().ui_font_family==settings.ui_font_family,"requested font remains selected");
    u8 saved_settings[SETTINGS_PAGE_BYTES];encode_settings(ui.settings(),0,saved_settings);
    const auto before=core_values();const auto model=calc.snapshot();
    Screen screen;BatteryStatus battery;battery.decode(0x0B,73);
    screen.render(model,true,&ui,nullptr,battery);
    static const stack slots[]={X,Y,Z,T,X1};static const char* labels[]={"X","Y","Z","T","X1","X2"};
    int column=-1;
    for(unsigned i=0;i<6;++i) {
        char raw[INDICATOR_STRING_LENGTH];
        if(i<5) read_stack_register(slots[i],raw,nullptr);
        else {
            std::snprintf(raw,sizeof(raw),"%s",model.face_indicator);
            for(char* p=raw;*p;++p) if(*p=='O') *p='0';
        }
        const Text number(ui.settings(),raw,16),label(ui.settings(),labels[i],16);
        const unsigned top=154+i*20;
        require(label.matches(screen,18,top),"all six X/Y/Z/T/X1/X2 labels are visible");
        const int left=find_x(number,screen,top);
        require(left>=0,"complete signed mantissa and exponent fit");
        if(column<0) column=left;else require(left==column,"X1 and one-character labels share the same numeric column");
        require(top+number.height<280,"stack stays clear of both footer rows");
    }
    const Text longest_label(ui.settings(),"X1",16);
    require(column>=(int)(18+longest_label.width+4) && column<=(int)(18+longest_label.width+10),"label gap remains compact and clear");
    require(!screen.scroll_region().valid(),"calculator view does not change hardware scroll region");
    const bool save=settings.ui_font_family==1 && settings.ui_font_size==14 && settings.russian;
    if(save) preview(screen,"-stack");
    ui.input(0xB6,calc);require(ui.view()==View::REGISTERS,"Down enters register view");
    bool seen[15]{};
    for(unsigned offset=0;offset<=3;++offset) {
        require(ui.offset()==offset,"PgDn advances the register window");
        screen.render(model,true,&ui,nullptr,battery);
        // A selected face that cannot fit the table falls back locally to a
        // native strike. Verify complete glyph rasters, not just lit pixels.
        Settings fallback;fallback.ui_font_family=1;fallback.ui_font_size=14;
        Settings font;bool found=false;
        for(const auto& candidate:{ui.settings(),fallback}) {
            char raw[INDICATOR_STRING_LENGTH];MK61Emu_ReadRegister((int)offset,raw,nullptr);
            if(find_x(Text(candidate,raw,candidate.ui_font_size),screen,154,8,64)>=0) {
                font=candidate;found=true;break;
            }
        }
        require(found,"table uses selected or native unscaled font");
        int value_columns[2]={-1,-1};
        for(unsigned cell=0;cell<12;++cell) {
            const unsigned index=offset+cell,side=cell/6,top=154+(cell%6)*20;
            const unsigned left=8+side*160,right=left+144;
            char label[4],raw[INDICATOR_STRING_LENGTH];
            std::snprintf(label,sizeof(label),"R%X",index);MK61Emu_ReadRegister((int)index,raw,nullptr);
            const Text number(font,raw,font.ui_font_size),name(font,label,font.ui_font_size);
            require(name.matches(screen,left,top),"both columns have complete register labels");
            const int value_left=find_x(number,screen,top,left,left+64);
            require(value_left>=0 && value_left+(int)number.width<=(int)right,"full signed mantissa and exponent fit their own column");
            require(value_left>=(int)(left+name.width+4),"register label and value stay apart");
            require(top+number.height<280,"both register columns stay clear of status and footer");
            if(value_columns[side]<0) value_columns[side]=value_left;
            else require(value_left==value_columns[side],"register values share a numeric column");
            seen[index]=true;
        }
        require(value_columns[1]-value_columns[0]==160,"both columns have equal width and label spacing");
        u8 current_settings[SETTINGS_PAGE_BYTES];encode_settings(ui.settings(),0,current_settings);
        require(!std::memcmp(current_settings,saved_settings,sizeof(saved_settings)),"local table font keeps saved settings unchanged");
        require(Text(ui.settings(),M8("Shift+↑/↓: R0-RE"),12).matches(screen,10,280),"physical register paging keys and range fit");
        require(Text(ui.settings(),ui.footer(),12).matches(screen,10,301),"Tab and view navigation hint fits without truncation");
        require(std::strstr(ui.footer(),"Tab")!=nullptr,"menu navigation stays discoverable");
        if(save && (offset==0 || offset==3)) preview(screen,offset?"-registers-last":"-registers");
        ui.input(0xD7,calc);
    }
    require(ui.offset()==3,"PgDn clamps when RE is in the second column");
    for(bool value:seen) require(value,"every R0-RE register is reachable");
    for(unsigned i=0;i<12;++i) ui.input(0xD6,calc);
    require(ui.offset()==0,"PgUp clamps at R0");
    ui.input(0xD7,calc);ui.input(0xB5,calc);
    require(ui.view()==View::STACK && !ui.offset(),"changing view resets register offset");
    Services services;services.set_ui(ui);services.open(Action::DEVELOPMENT,settings.russian,calc);
    menu(services,ui,calc,4);
    for(unsigned tool=1;tool<=3;++tool) {
        for(unsigned i=0;i<tool;++i) services.input(0xB6);
        services.input('\r');require(!std::strcmp(services.page_name(),"LANGUAGE"),"development item opens its language menu");
        menu(services,ui,calc,tool==1?2:4);services.input(0x1B);
    }
    services.input(0x1B);services.open(Action::EXPLORER,false,calc);
    require(services.enter_directory("/LayoutUI"),"RAM-only browser fixture");
    services.input(0xB6);services.input(0x81);
    require(!std::strcmp(services.page_name(),"FILE_ACTIONS"),"F1 opens file actions");
    menu(services,ui,calc,6);
    require(core_values()==before,"rendering and UI navigation preserve X2, all stack and memory registers");
}
Snapshot display_sequence(Calculator& calc,std::initializer_list<u8> program) {
    calc.init(true);unsigned at=0;
    for(u8 code:program) MK61Emu_SetCode((int)core_61::get_ring_address(at++),code);
    require(calc.input('r'),"start display control program");
    for(unsigned n=0;n<4096;++n) {
        calc.tick();
        if(calc.idle() && !core_61::is_RUN()) return calc.snapshot();
    }
    require(false,"display control program settles");return {};
}
void published_x2() {
    Calculator calc;Ui ui;ui.init();Screen screen;
    const unsigned left=18+Text(ui.settings(),"X1",16).width+8;
    const auto blank=[&](const Snapshot& model) {
        screen.render(model,true,&ui);
        require(Text(ui.settings(),"X2",16).matches(screen,18,254),"X2 label remains visible when its display is blank");
        for(unsigned y=254;y<274;++y) for(unsigned x=left;x<312;++x)
            require(!screen.pixel(x,y),"published clear/hold must not expose the raw indicator in X2");
    };
    // Actual expanded core repro: idle after 2F 0D 50, raw latch still 0,
    // published numeric display blank. Rendering must obey publication.
    auto model=display_sequence(calc,{0x2F,0x0D,0x50});
    require(!core_61::extended_display_auto() && !model.running && model.idle && !model.segmented,"numeric clear survives program stop");
    require(std::strspn(model.face_indicator," ")==std::strlen(model.face_indicator),"core publishes a blank numeric face");
    require(std::strspn(model.indicator," ")<std::strlen(model.indicator),"repro raw latch is still nonblank");
    blank(model);preview(screen,"-X2-clear");

    model=display_sequence(calc,{0x2F,0x50,0x07,0x50});
    require(!core_61::extended_display_auto() && !model.segmented,"numeric hold survives program stop");
    char raw[INDICATOR_STRING_LENGTH];read_stack_register(X,raw,nullptr);
    require(std::strchr(raw,'7')!=nullptr && std::strchr(model.face_indicator,'7')==nullptr,"held display differs from changed arithmetic X");
    char held[INDICATOR_STRING_LENGTH];std::snprintf(held,sizeof(held),"%s",model.face_indicator);
    for(char* p=held;*p;++p) if(*p=='O') *p='0';
    screen.render(model,true,&ui);
    require(Text(ui.settings(),held,16).matches(screen,left,254),"X2 text uses the held publication");
    preview(screen,"-X2-held");

    model=display_sequence(calc,{0x2F,0x50,0x07,0x2F,0x52,0x08,0x50});
    require(core_61::extended_display_auto() && std::strchr(model.face_indicator,'8'),"resume publishes later numeric X");
    char resumed[INDICATOR_STRING_LENGTH];std::snprintf(resumed,sizeof(resumed),"%s",model.face_indicator);
    for(char* p=resumed;*p;++p) if(*p=='O') *p='0';
    screen.render(model,true,&ui);
    require(Text(ui.settings(),resumed,16).matches(screen,left,254),"X2 follows resumed publication");

    model=display_sequence(calc,{0x2F,0x2A,0x2F,0x50,0x07,0x50});
    require(model.segmented && !core_61::extended_display_auto(),"held segment publication");
    for(u8 mask:model.segments) require(mask==0,"held segments remain blank after changed X");
    blank(model);
    model=display_sequence(calc,{0x2F,0x2A,0x07,0x2F,0x0D,0x50});
    require(model.segmented,"cleared segment publication");
    for(u8 mask:model.segments) require(mask==0,"clear removes every published segment and dot");
    blank(model);
    model=display_sequence(calc,{0x2F,0x2A,0x2F,0x50,0x07,0x2F,0x52,0x08,0x50});
    require(model.segmented && core_61::extended_display_auto(),"segment resume mode");
    bool lit=false;for(u8 mask:model.segments) lit|=mask!=0;
    require(lit,"segment resume publishes later X");

    // Every 8-bit mask in every physical slot: arbitrary bars and the dot
    // remain exact even where no digit/letter can represent their shape.
    for(unsigned value=0;value<256;++value) {
        for(unsigned slot=0;slot<12;++slot) model.segments[slot]=(u8)(value+17*slot);
        screen.render(model,true,&ui);
        for(unsigned slot=0;slot<12;++slot) for(unsigned y=0;y<13;++y) for(unsigned x=0;x<12;++x) {
            const u8 mask=model.segments[slot];
            const bool horizontal=x>=1 && x<=5;
            const bool upper=y>=1 && y<=5,lower=y>=7 && y<=11;
            const bool expected=(horizontal && ((y==0 && (mask&1)) || (y==6 && (mask&64)) || (y==12 && (mask&8)))) ||
                (x==6 && ((upper && (mask&2)) || (lower && (mask&4)))) ||
                (x==0 && ((upper && (mask&32)) || (lower && (mask&16)))) ||
                (x==9 && y>=11 && (mask&128));
            require(screen.pixel(left+slot*12+x,255+y)==expected,"exact published mask/dot at every X2 slot");
        }
    }
    preview(screen,"-X2-segments");
    model.segmented=false;std::snprintf(model.face_indicator,sizeof(model.face_indicator),"%c%c,O",display_symbol::uc1609::CYR_GHE,display_symbol::uc1609::RT_ARROW);
    screen.render(model,true,&ui);
    require(Text(ui.settings(),M8("Г→.0"),16).matches(screen,left,254),"legacy indicator tokens are converted to M8 glyphs");
    std::puts("PicoCalc X2 publication: real core clear/hold/resume and all 256 masks/dots in all 12 slots PASS");
}
void clock_during_input() {
    const auto saved=clock::get();
    require(clock::set({2026,10,31,12,34,0}),"clock entry fixture");
    Calculator calc;calc.init();Ui ui;ui.init();Services services;Screen screen;
    Settings clock_font;clock_font.ui_font_family=1;clock_font.ui_font_size=16;
    BatteryStatus battery;battery.decode(0x0B,73);
    unsigned busy=0,settled=0;
    const auto check=[&](const Snapshot& model,const char* time,unsigned hour,unsigned minute) {
        screen.render(model,true,&ui,nullptr,battery);
        const Text text(clock_font,time,16);
        require(text.matches(screen,Screen::WIDTH-44-text.width,9),"native clock remains complete during press and release");
        u8 frame[1536];screen.logical_frame(ui,services,frame);
        u32 rows[rtc_idle_clock::GRAPHIC_CLOCK_HEIGHT];
        require(rtc_idle_clock::build_graphic_clock(hour,minute,rows),"clock oracle");
        for(unsigned y=0;y<7;++y) for(unsigned x=0;x<rtc_idle_clock::GRAPHIC_CLOCK_WIDTH;++x)
            require(bool(frame[(18+y)/8*192+165+x]&(1U<<((18+y)%8)))==bool(rows[y]&(1U<<x)),"logical USB clock remains visible during input");
    };
    check(calc.snapshot(),"12:34",12,34);
    for(u8 key:{'1','2','3'}) {
        require(calc.input(key),"manual clock input key");
        for(unsigned cycle=0;cycle<4096;++cycle) {
            const auto model=calc.snapshot();
            require(!model.running && !model.programming,"ordinary digit remains manual calculator mode");
            if(model.idle) ++settled;else ++busy;
            check(model,"12:34",12,34);
            if(model.idle) break;
            calc.tick();
        }
        require(calc.idle(),"manual key settles");
    }
    require(busy && settled,"real key input covered both busy and settled phases");
    // A minute change must still invalidate the raster while a key is held.
    require(calc.input('4'),"minute rollover while input busy");
    auto held=calc.snapshot();require(!held.idle,"rollover occurs during a real queued key");
    require(clock::set({2026,10,31,12,35,0}),"advance clock minute");
    require(screen.render(held,true,&ui,nullptr,battery),"minute changes invalidate even during input");
    check(held,"12:35",12,35);
    for(bool running:{true,false}) {
        auto hidden=held;hidden.running=running;hidden.programming=!running;
        screen.render(hidden,true,&ui,nullptr,battery);
        u8 frame[1536];screen.logical_frame(ui,services,frame);
        for(unsigned y=0;y<7;++y) for(unsigned x=0;x<rtc_idle_clock::GRAPHIC_CLOCK_WIDTH;++x)
            require(!(frame[(18+y)/8*192+165+x]&(1U<<((18+y)%8))),"RUN and programming still hide the idle clock");
    }
    require(clock::set(saved),"restore HOST clock fixture");
    std::puts("PicoCalc clock during real manual press/release: native/logical surfaces, busy minute rollover and RUN/PRG policy PASS");
}
void power_indicator() {
    const auto saved=clock::get();require(clock::set({2026,11,7,12,34,0}),"power clock fixture");
    Calculator calc;fixture(calc);Settings settings;settings.russian=1;Ui ui;ui.init(settings);
    Screen screen;BatteryStatus battery;battery.decode(0x0B,73);
    require(battery.decode_power(BIOS_POWER_REG,0xB1),"battery power fixture");
    screen.render(calc.snapshot(),true,&ui,nullptr,battery);
    const Screen baseline=screen;
    const unsigned states[]={0xB7,0xBB,0xB3,0xB1,0xA0};
    const char* names[]={"-power-charging","-power-complete","-power-external","-power-battery","-power-unknown"};
    for(unsigned i=0;i<5;++i) {
        require(battery.decode_power(BIOS_POWER_REG,(u8)states[i]),"power state fixture");
        require(screen.render(calc.snapshot(),true,&ui,nullptr,battery),"power state updates without a percent change");
        require(!screen.render(calc.snapshot(),true,&ui,nullptr,battery),"stable power status does not repaint");
        for(unsigned y=0;y<33;++y) for(unsigned x=0;x<278;++x)
            require(screen.pixel(x,y)==baseline.pixel(x,y),"power badge stays clear of title and clock");
        require(screen.pixel(280,15)==battery.external_power(),"external power plug is independent of charge state");
        preview(screen,names[i]);
    }
    require(clock::set(saved),"restore power clock fixture");
}
void explorer_hints(Calculator& calc) {
    require(files::mkdir("/ExplorerHints"),"Explorer hint fixture");
    for(unsigned i=0;i<9;++i) {
        char name[48];std::snprintf(name,sizeof(name),"/ExplorerHints/File%u.txt",i);
        require(files::write_text(name,"hint",4),"Explorer hint file");
    }
    for(bool russian:{false,true}) {
        Settings face;face.russian=russian;Ui ui;ui.init(face);
        Services services;services.set_ui(ui);services.open(Action::EXPLORER,russian,calc);
        require(services.enter_directory("/ExplorerHints",false),"Explorer hint directory");
        const char* expected=russian?M8("F1: файл  F8: значки/список"):"F1: file  F8: icons/list";
        const Text hint(face,expected,12);
        require(hint.width<=300,"Explorer shortcut hint fits the native footer");
        for(unsigned mode=0;mode<2;++mode) {
            if(mode) services.input(0x88);
            require(services.browser_count()==9,"footer tested with a full page");
            while(services.browser_selection()<8) services.input(0xB7);
            Screen screen;screen.render(calc.snapshot(),true,&ui,&services);
            require(hint.matches(screen,10,303),"F8 hint is visible in icons and list, EN and RU");
            for(unsigned x=0;x<320;++x) require(screen.pixel(x,299),"Explorer footer separator");
            if(mode) {
                char name[64];require(services.browser_label(8,name),"last list entry");
                const Text label(face,name,16);
                require(label.matches(screen,16,281,true),"last selected list entry stays above footer");
            }
            preview(screen,russian?(mode?"-explorer-list-ru":"-explorer-icons-ru"):
                                   (mode?"-explorer-list-en":"-explorer-icons-en"));
        }
    }
}
}

namespace {
template<unsigned N> bool banner_matches(const picocalc::Screen& screen,const u8 (&packed)[N]) {
    u8 raw[12800]{};return picocalc::utility::draw_label(raw,picocalc::utility::asset(packed),34,20) &&
        !std::memcmp(raw+34*40,screen.data()+34*40,960);
}
}
void picocalc_utility_test() {
    using namespace picocalc;
    Calculator calc;calc.init();
    for(bool ru:{false,true}) {
        Settings settings;settings.russian=ru;
        // A deliberately different chosen UI font must not resize pixel artwork.
        settings.ui_font_family=4;settings.ui_font_size=16;
        Ui ui;ui.init(settings);Services service;service.set_ui(ui);Screen screen;
        Settings native;native.ui_font_family=1;native.ui_font_key=0;
        service.open(Action::USB_DISK,ru,calc);require(service.usb_disk(),"USB fixture exports RAM disk");
        screen.animation_tick(1000,0,0);
        require(screen.render({},true,&ui,&service),"USB native page first frame");
        require(ru?banner_matches(screen,utility_art::title_usb_ru):banner_matches(screen,utility_art::title_usb_en),"native USB banner");
        const Text caption(native,ru?M8("Карта подключена к ПК"):"Card connected to computer",16,1,true);
        require(caption.width<=296 && caption.matches(screen,(320-caption.width)/2,227),"large centered native USB instructions");
        require(!screen.render({},true,&ui,&service),"idle USB page retains raster");
        const std::vector<u8> before(screen.data(),screen.data()+Screen::BYTES);
        screen.animation_tick(1200,1,0);require(screen.render({},true,&ui,&service),"real USB read animates");
        unsigned changed=0;
        for(unsigned y=0;y<320;++y)for(unsigned x=0;x<320;++x) {
            const bool old=before[y*40+x/8]&(128U>>(x&7));
            if(old!=screen.pixel(x,y)) {++changed;require(y>=118 && y<158,"USB animation changes only tiny face/packet region");}
        }
        require(changed && changed<300,"USB dirty areas stay bounded");
        require(screen.partial_renders()==1,"USB phase reuses static raster and captions");
        const auto exact=[&]() {
            Screen reference=screen;reference.invalidate();reference.render({},true,&ui,&service);
            require(!std::memcmp(reference.data(),screen.data(),Screen::BYTES),"incremental utility raster differs from forced full render");
        };
        exact();
        const auto partial=screen.partial_renders();
        for(unsigned phase=1;phase<=80;++phase) {
            screen.animation_tick(1200+phase*32,1+phase,0);
            require(screen.render({},true,&ui,&service),"one-pixel packet animation phase");exact();
        }
        require(screen.partial_renders()==partial+80,"all moving packet/blink phases use incremental RAM rendering");
        if(ru)preview(screen,"-usb-ru");else preview(screen,"-usb-en");
        if(ru) for(unsigned step=0;step<10;++step) {
            screen.animation_tick(1200+step*140,1+(step<5?step:4),step<5?0:step-4);
            screen.render({},true,&ui,&service);
            char suffix[32];std::snprintf(suffix,sizeof(suffix),"-usb-step%u",step);preview(screen,suffix);
        }
        require(!service.input('\r') || service.usb_disk(),"Enter cannot abandon mounted host filesystem");
        files::usb_eject();screen.animation_tick(2600,5,5);
        require(screen.render({},true,&ui,&service),"safe eject changes scene");
        require(ru?banner_matches(screen,utility_art::title_ejected_ru):banner_matches(screen,utility_art::title_ejected_en),"ejected banner");
        if(ru)preview(screen,"-usb-ejected");
        require(service.input('\r') && !service.active() && files::ready(),"safe eject returns native SD ownership");
        require(ui.input('\t',calc) && ui.input('\r',calc) && ui.bootloader_confirmation(),"UF2 confirmation via actual UI");
        screen.animation_tick(3000,5,5);require(screen.render({},true,&ui,&service),"UF2 native confirmation");
        require(ru?banner_matches(screen,utility_art::title_uf2_ru):banner_matches(screen,utility_art::title_uf2_en),"UF2 banner");
        if(ru)preview(screen,"-uf2-confirm");
        require(ui.input(0x1b,calc) && !ui.bootloader_confirmation() && ui.take_action()==Action::NONE,"UF2 Esc cancels without arming ROM");
        require(ui.input('\r',calc) && ui.input('\r',calc) && ui.take_action()==Action::BOOTLOADER,"UF2 Enter requests ROM");
        screen.begin_bootloader(4000);
        const auto boot_partial=screen.partial_renders();
        for(unsigned step=0;step<28;++step) {
            screen.animation_tick(4000+step*35,5,5);
            require(screen.render({},true,&ui,&service),"cartridge insertion frame");
            exact();
            if(ru) {char suffix[32];std::snprintf(suffix,sizeof(suffix),"-uf2-step%u",step);preview(screen,suffix);}
        }
        require(screen.partial_renders()==boot_partial+27,"insertion reuses static chip/headers/captions");
        screen.animation_tick(4960,5,5);require(screen.render({},true,&ui,&service) && screen.bootloader_ready(),"final ROM instructions before handoff");
        require(ru?banner_matches(screen,utility_art::title_ready_ru):banner_matches(screen,utility_art::title_ready_en),"static ROM banner");
        if(ru)preview(screen,"-uf2-ready");
        screen.animation_tick(7000,5,5);require(!screen.render({},true,&ui,&service),"ROM last frame stays static");
    }
    std::puts("Pico USB/UF2: native EN/RU text, compressed art, dirty-only animation, safe eject, cancel and ROM final frame PASS");
}
void picocalc_layout_self_test() {
    // This translation unit is only linked to the host tests. Its FatFs disk is
    // tests/picocalc_host_disk.cpp's RAM vector; no host block device is opened.
    require(!picocalc::files::usb_active(),"RAM disk is not exported");
    require(picocalc::files::format(),"format RAM fixture");
    require(picocalc::files::mkdir("/LayoutUI"),"fixture directory");
    require(picocalc::files::write_text("/LayoutUI/check.bas","10 END\n",7),"fixture document");
    require(picocalc::files::mkdir("/Fonts"),"fixture fonts directory");
    const std::string source=__FILE__,root=source.substr(0,source.rfind("/tests/"));
    for(unsigned size:{12U,14U}) {
        const std::string name="DejaVu-"+std::to_string(size)+".FMK";
        std::ifstream file(root+"/programs/Fonts/"+name,std::ios::binary);
        std::vector<u8> data((std::istreambuf_iterator<char>(file)),{});
        require(!data.empty() && picocalc::files::write(("/Fonts/"+name).c_str(),data.data(),(unsigned)data.size()),"actual repository FMK fixture");
    }
    picocalc::clock::init();picocalc::Calculator calc;fixture(calc);
    const unsigned choices[][2]={{1,12},{1,14},{1,16},{4,16},{0,14},{5,5},{3,12},{3,14}};
    for(const auto& choice:choices) for(unsigned russian=0;russian<2;++russian) {
        picocalc::Settings settings;settings.ui_font_family=(u8)choice[0];settings.ui_font_size=(u8)choice[1];settings.russian=(u8)russian;
        if(choice[0]==3) settings.ui_font_key=ui_font_catalog::name_key(("DejaVu-"+std::to_string(choice[1])+".FMK").c_str());
        check_choice(settings,calc);
    }
    clock_during_input();published_x2();power_indicator();explorer_hints(calc);picocalc_utility_test();
    std::printf("PicoCalc focused UI layout/navigation: PASS (%u assertions; 8 font choices, EN/RU)\n",checks);
}
#if defined(MK61_LAYOUT_STANDALONE)
int main() { picocalc_layout_self_test(); }
#endif
