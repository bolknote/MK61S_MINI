#include "screen.hpp"
#include "services.hpp"
#include "fonts.hpp"
#include "clock.hpp"
#include "ui_font_catalog.hpp"
#include "mk8_codec.hpp"
#include "mk8_literal.hpp"
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
    Text(Settings font,const char* value,unsigned size) {
        if(font.ui_font_family==1) font.ui_font_size=(u8)size;
        const auto metrics=fonts::info(font);
        width=fonts::text_width(font,value,(unsigned)std::strlen(value));height=metrics.height;
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
            }
            left+=glyph.advance;
        }
    }
    bool matches(const Screen& screen,unsigned left,unsigned top) const {
        if(left+width>312 || top+height>320) return false;
        for(unsigned y=0;y<height;++y) for(unsigned x=0;x<width;++x)
            if(screen.pixel(left+x,top+y)!=(pixels[y*width+x]!=0)) return false;
        return true;
    }
};
int find_x(const Text& text,const Screen& screen,unsigned top) {
    for(unsigned x=18;x<=96;++x) if(text.matches(screen,x,top)) return (int)x;
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
void menu(Services& services,Ui& ui,Calculator& calc,unsigned count) {
    Screen screen;int previous=-1;
    const auto metrics=fonts::info(ui.settings());
    for(unsigned i=0;i<count;++i) {
        char row[Services::COLS+1];services.row(i,row);
        require(row[0]=='>',"every menu item is selectable");
        screen.render(calc.snapshot(),true,&ui,&services);
        const Text text(ui.settings(),row,ui.settings().ui_font_size);
        const int top=find_y(text,screen);
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
    const auto before=core_values();const auto model=calc.snapshot();
    Screen screen;BatteryStatus battery;battery.decode(0x0B,73);
    screen.render(model,true,&ui,nullptr,battery);
    require(Text(ui.settings(),"X2",16).matches(screen,10,72),"large display latch is labelled X2 at readable size");
    static const stack slots[]={X,Y,Z,T,X1};static const char* labels[]={"X","Y","Z","T","X1"};
    int column=-1;
    for(unsigned i=0;i<5;++i) {
        char raw[INDICATOR_STRING_LENGTH];read_stack_register(slots[i],raw,nullptr);
        const Text number(ui.settings(),raw,16),label(ui.settings(),labels[i],16);
        const unsigned top=154+i*24;
        require(label.matches(screen,18,top),"all five stack labels are visible");
        const int left=find_x(number,screen,top);
        require(left>=0,"complete signed mantissa and exponent fit");
        if(column<0) column=left;else require(left==column,"X1 and one-character labels share the same numeric column");
        require(top+number.height<280,"stack stays clear of both footer rows");
    }
    const Text longest_label(ui.settings(),"X1",16);
    require(column>=(int)(18+longest_label.width+4) && column<=(int)(18+longest_label.width+10),"label gap remains compact and clear");
    require(!screen.scroll_region().valid(),"calculator view does not change hardware scroll region");
    ui.input(0xB6,calc);require(ui.view()==View::REGISTERS,"Down enters register view");
    bool seen[15]{};
    for(unsigned offset=0;offset<=9;++offset) {
        require(ui.offset()==offset,"PgDn advances the register window");
        screen.render(model,true,&ui,nullptr,battery);int value_column=-1;
        for(unsigned row=0;row<6;++row) {
            const unsigned index=offset+row;char label[4],raw[INDICATOR_STRING_LENGTH];
            std::snprintf(label,sizeof(label),"R%X",index);MK61Emu_ReadRegister((int)index,raw,nullptr);
            require(Text(ui.settings(),label,ui.settings().ui_font_size).matches(screen,18,154+row*20),"register label is complete");
            const int left=find_x(Text(ui.settings(),raw,ui.settings().ui_font_size),screen,154+row*20);
            require(left>=0,"register number is complete");
            if(value_column<0) value_column=left;else require(left==value_column,"register values share a column");
            seen[index]=true;
        }
        require(Text(ui.settings(),M8("Shift+↑/↓: R0-RE"),12).matches(screen,10,280),"physical register paging keys and range fit");
        require(Text(ui.settings(),ui.footer(),12).matches(screen,10,301),"Tab and view navigation hint fits without truncation");
        require(std::strstr(ui.footer(),"Tab")!=nullptr,"menu navigation stays discoverable");
        ui.input(0xD7,calc);
    }
    require(ui.offset()==9,"PgDn clamps at RE");
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
    menu(services,ui,calc,5);
    require(core_values()==before,"rendering and UI navigation preserve X2, all stack and memory registers");
}
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
    std::printf("PicoCalc focused UI layout/navigation: PASS (%u assertions; 8 font choices, EN/RU)\n",checks);
}
#if defined(MK61_LAYOUT_STANDALONE)
int main() { picocalc_layout_self_test(); }
#endif
