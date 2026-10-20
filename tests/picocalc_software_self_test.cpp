#include "services.hpp"
#include "builtin_font.hpp"
#include "display_symbols.hpp"
#include "../ports/picocalc/terminal.hpp"
#include "markdown.hpp"
#include "fonts.hpp"
#include "diagnostics.hpp"
#include "script.hpp"
#include "screen.hpp"
#include "m61_platform.hpp"
#include "mk61_ref.hpp"
#include "mk8_literal.hpp"
#include "ui_font_catalog.hpp"
#include "rtc_idle_clock_core.hpp"
#include "ui_font.hpp"
#include <cassert>
#include <cstring>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>
namespace {
using namespace picocalc;
u64 test_time=1000000;
u64 test_clock() { return test_time; }
void text(const char* path,const char* source) {
    assert(files::write_text(path,source,std::strlen(source)));
}
std::vector<u8> source_file(const char* path) {
    std::ifstream input(path,std::ios::binary);assert(input.good());
    return {(std::istreambuf_iterator<char>(input)),{}};
}
bool pixel(const u8* frame,unsigned x,unsigned y) { return (frame[(y/8)*192+x]>>(y%8))&1; }
void face_status(const Screen& screen,const Ui& ui,const Services& services,
                 const char* mode,const char* angle,const char* key) {
    text_screen::Grid grid;grid.reset(2);
    char status[17];std::snprintf(status,sizeof(status),"%-5.5s %-3.3s %-6.6s",mode,angle,key);
    for(const char* p=status;*p;++p) grid.writeCodepoint(mk8::codepoint((u8)*p));
    u8 expected[1536],actual[1536];calculator_face::renderFrame(grid,expected);
    screen.logical_frame(ui,services,actual);
    assert(!std::memcmp(expected,actual,192*2));
}
void native_status(const Screen& screen,const char* mode,const char* angle,const char* key) {
    // Compare LCD pixels directly with the native Ark Pixel 16 strike,
    // independently of the 192x64 calculator face and its 5/3 scale.
    const ui_font::Face font{ui_font::Family::PIXEL,ui_font::Size::PX16};
    const int baseline=40+ui_font::metrics(font).ascent;
    const char* labels[]={mode,angle,key};
    u8 expected[27][40]{};
    for(unsigned field=0;field<3;++field) {
        unsigned advance=0;
        for(const char* p=labels[field];*p;++p) advance+=ui_font::glyph(font,mk8::codepoint((u8)*p)).advance;
        assert(advance<=96);
        int pen=8+field*104+(96-advance)/2,previous_right=-1;
        for(const char* p=labels[field];*p;++p) {
            const auto glyph=ui_font::glyph(font,mk8::codepoint((u8)*p));assert(!glyph.fallback);
            int left=320,right=-1;
            for(unsigned y=0;y<glyph.height;++y) for(unsigned x=0;x<glyph.width;++x)
                if(font_glyph::pixel(glyph,x,y)) {
                    const int px=pen+glyph.bearing_x+x,py=baseline-glyph.bearing_y+y;
                    assert(px>=int(8+field*104) && px<int(104+field*104) && py>=38 && py<63);
                    expected[py-38][px/8]|=(u8)(0x80U>>(px%8));
                    if(px<left) left=px;if(px>right) right=px;
                }
            if(right>=0) { assert(previous_right<0 || left>previous_right+1);previous_right=right; }
            pen+=glyph.advance;
        }
        for(unsigned x=8+field*104;x<104+field*104;++x) expected[63-38][x/8]|=(u8)(0x80U>>(x%8));
    }
    for(unsigned y=0;y<27;++y) for(unsigned x=0;x<320;++x)
        assert(screen.pixel(x,38+y)==bool(expected[y][x/8]&(0x80U>>(x%8))));
}
void status_preview(const Screen& screen,const char* path,const char* suffix) {
    if(!path) return;
    std::ofstream out(std::string(path)+suffix,std::ios::binary);assert(out.good());
    out<<"P4\n320 320\n";out.write((const char*)screen.data(),Screen::BYTES);assert(out.good());
}
void physical_face(const Screen& screen,const picocalc::Snapshot& model,bool classic) {
    // The original strike must occupy exactly 16x35 pixels in each 26-pixel
    // slot. Check the entire indicator band, including the empty gutters.
    bool expected[35][320]{};u8 masks[12]{};u16 tokens[12]{};
    if(model.segmented) std::memcpy(masks,model.segments,12);
    else {
        unsigned slot=0;
        for(const char* p=model.face_indicator;*p;++p) {
            if(*p==',' || *p=='.') { if(slot) masks[slot-1]|=128; }
            else if(slot<12) { tokens[slot]=(u8)*p;masks[slot++]=calculator_face::sourceSegments((u8)*p); }
        }
    }
    for(unsigned slot=0;slot<12;++slot) {
        const u8 mask=masks[slot];
        const unsigned left=9+slot*26;
        const u16 token=model.segmented?calculator_face::sourceToken(mask&127):tokens[slot];
        if(token==display_symbol::uc1609::RT_ARROW) {
            const u16 columns[]={0,0x38,0x38,0x38,0x38,0x38,0x139,0xBA,0x54,0x38};
            for(unsigned x=0;x<10;++x) for(unsigned y=0;y<9;++y)
                if(columns[x]&(1U<<y)) expected[12+y][left+3+x]=true;
        } else if(classic && token) {
            const ui_font::Face font{ui_font::Family::PIXEL,ui_font::Size::PX16};
            const auto glyph=ui_font::glyph(font,token);
            const int px=left+(16-glyph.advance)/2+glyph.bearing_x;
            const int py=9+ui_font::metrics(font).ascent-glyph.bearing_y;
            for(unsigned y=0;y<glyph.height;++y) for(unsigned x=0;x<glyph.width;++x)
                if(font_glyph::pixel(glyph,x,y)) expected[py+y][px+x]=true;
            if(mask&128) for(unsigned y=0;y<2;++y) for(unsigned x=0;x<2;++x) expected[23+y][left+18+x]=true;
        } else for(unsigned y=0;y<35;++y) {
            const auto bits=calculator_face::sourceRow(mask,y);
            for(unsigned x=0;x<16;++x) if(bits&(0x8000U>>x)) expected[y][left+x]=true;
        }
    }
    for(unsigned y=0;y<35;++y) for(unsigned x=0;x<320;++x) if(screen.pixel(x,91+y)!=expected[y][x]) { std::fprintf(stderr,"native digit mismatch x=%u y=%u classic=%u segmented=%u text=[%s] expected=%u\n",x,y,classic,model.segmented,model.face_indicator,expected[y][x]);std::abort(); }
}
void clock_header(const Screen& screen,const u32* rows=nullptr) {
    bool expected[32][320]{};
    if(rows) {
        const ui_font::Face font{ui_font::Family::PIXEL,ui_font::Size::PX16};
        unsigned width=0;for(char cp:std::string("12:34")) width+=ui_font::glyph(font,cp).advance;
        int pen=310-width;
        for(char cp:std::string("12:34")) {
            const auto g=ui_font::glyph(font,cp);
            for(unsigned y=0;y<g.height;++y) for(unsigned x=0;x<g.width;++x)
                if(font_glyph::pixel(g,x,y)) expected[9+ui_font::metrics(font).ascent-g.bearing_y+y][pen+g.bearing_x+x]=true;
            pen+=g.advance;
        }
    }
    for(unsigned y=0;y<32;++y) for(unsigned x=240;x<320;++x)
        assert(screen.pixel(x,y)==expected[y][x]);
}
void finish_script(Calculator& calculator) {
    for(unsigned i=0;i<2000 && m61_text::active();++i) { m61_text::service();calculator.tick(); }
    assert(!m61_text::active());
}
}
void picocalc_software_test(const char* preview_path) {
    using namespace picocalc;
    assert(files::mkdir("/Software"));
    Calculator calculator;calculator.init();
    Ui ui;ui.init();static Services services;services.set_ui(ui);
    services.open(Action::DEVELOPMENT,false,calculator);services.input(0x1B);
    script::attach(calculator,services);
    assert(script::file_type("/book.MKS")==program_store::ProgramType::SHEET);
    assert(script::file_type("/book.sheet")==program_store::ProgramType::SHEET);
    assert(script::file_type("/image.wbm")==program_store::ProgramType::IMAGE1);
    assert(script::file_type("/snapshot.state.txt")==program_store::ProgramType::MK61_STATE);
    assert(files::mkdir("/Software/auto"));
    text("/Software/auto/autoexec.m61","poke X 61\n");
    text("/Software/auto/autoexec.tbi","10 .X=17\n20 END\n");
    services.open(Action::EXPLORER,false,calculator);
    services.input('/');
    for(char ch:std::string("/Software/auto")) services.input((u8)ch);
    services.input('\r');
    finish_script(calculator);
    double number=0;assert(mk61_ref::read(mk61_ref::Ref{mk61_ref::Kind::X,0},number) && number==61);
    assert(files::remove("/Software/auto/autoexec.m61"));
    assert(services.enter_directory("/Software/auto"));
    assert(services.last_error()==language_vm::Error::NONE);
    assert(mk61_ref::read(mk61_ref::Ref{mk61_ref::Kind::X,0},number) && number==17);
    assert(files::mkdir("/Software/ordinary") && services.enter_directory("/Software/ordinary"));
    assert(!m61_text::active());

    const u8 image[]={0,0,8,8,0xAA,0x55,0xFF,0,0x81,0x42,0x24,0x18};
    assert(files::write("/Software/check.wbmp",image,sizeof(image)));
    services.set_pump([](void* raw,u8& key) {
        auto& services=*(Services*)raw;
        const u8* frame=services.graphics();assert(frame);
        // WBMP white bits are blank in the calculator's white-on-black raster.
        assert(!pixel(frame,0,0) && pixel(frame,1,0) && pixel(frame,0,1));
        key=0x1B;return true;
    },&services);
    assert(!services.load_document("/Software/check.wbmp"));
    assert(services.active() && !services.dirty());
    services.set_pump(nullptr,nullptr);
    const auto text_font=source_file("programs/games/Turochamp/Turochamp.FMK");
    assert(files::write("/Software/text.fmk",text_font.data(),text_font.size()));
    assert(services.run_external("/Software/text.fmk")==0 && script::font_active());
    assert(script::text_profile({8,5,8,0}));

    // The shared renderer must draw pixels, not the image's alt label.
    text("/Software/image.md","![not a placeholder](check.wbmp)\n");
    MarkdownView document;assert(document.open("/Software/image.md"));
    for(unsigned y=0;y<8;++y) for(unsigned x=0;x<8;++x)
        assert(pixel(document.frame(),92+x,2+y)==!(image[4+y] & (0x80U>>x)));
    text("/Software/plain.md","AB\n");
    text("/Software/styled.md","**AB**\n");
    assert(document.open("/Software/plain.md"));
    std::vector<u8> plain(document.frame(),document.frame()+1536);
    assert(document.open("/Software/styled.md") && std::memcmp(plain.data(),document.frame(),1536));
    text("/Software/links.md","# Header\n\n*italic* ~~strike~~ `code`\n\n> quote\n\n- [x] item\n\n[tail](image.md)\n");
    assert(document.open("/Software/links.md") && document.links()==1);
    const auto first=std::vector<u8>(document.native_frame(),document.native_frame()+12800);
    document.select(1);char resolved[files::PATH_SIZE];
    assert(document.target(resolved) && std::strcmp(resolved,"/Software/image.md")==0);
    assert(std::memcmp(first.data(),document.native_frame(),12800));
    document.scroll(1,true);document.scroll(-1,true);document.restore(0xFFFF,0xFFFF);
    assert(document.top<0xFFFF);document.restore(0,0xFFFF);
    assert(!std::memcmp(first.data(),document.native_frame(),12800));

    if(!files::exists("/Fonts")) assert(files::mkdir("/Fonts"));
    auto ui_font=source_file("programs/Fonts/DejaVu-12.FMK");
    assert(files::write("/Fonts/DejaVu-12.FMK",ui_font.data(),ui_font.size()));
    const u32 key=ui_font_catalog::name_key("DejaVu-12.FMK");
    fonts::Item item{};assert(fonts::describe(key,item) && item.family==3 && item.size==12);
    Settings settings=ui.settings();settings.ui_font_family=3;settings.ui_font_key=key;settings.ui_font_size=12;
    assert(ui.apply_settings(settings));
    mk61_service_ui_glyph glyph{},after{};assert(fonts::glyph(settings,'A',glyph));
    assert(glyph.family==3 && glyph.size==12 && glyph.height==12);
    u8 record[256];encode_settings(settings,63,record);Settings decoded{};u32 sequence=0;
    assert(decode_settings(record,decoded,sequence) && sequence==63 && decoded.ui_font_key==key);
    // An unrelated catalog insertion and a reboot preserve the stable choice.
    assert(files::write("/Fonts/AAA.FMK",ui_font.data(),ui_font.size()));
    ui.init(decoded);assert(ui.settings().ui_font_key==key && fonts::glyph(ui.settings(),'A',after));
    assert(!std::memcmp(&glyph,&after,sizeof(glyph)));
    ui_font.back()^=1;
    assert(files::write("/Fonts/Bad.FMK",ui_font.data(),ui_font.size()));
    auto bad=settings;bad.ui_font_key=ui_font_catalog::name_key("Bad.FMK");
    assert(!ui.apply_settings(bad) && ui.settings().ui_font_key==key);
    assert(fonts::glyph(ui.settings(),'A',after) && !std::memcmp(&glyph,&after,sizeof(glyph)));
    // Valid PFK2 can still be unsuitable for UI. Reject a five-pixel gap
    // atomically, and render missing characters of a subset font legibly.
    u8 subset[34]={'P','F','K','2',1,1,12,2,1,1,1,0,22,0,22,0,34,0,0,0,'A',0};
    for(unsigned i=22;i<sizeof(subset);++i) subset[i]=0x80;
    auto checksum_subset=[&]() {
        const u16 crc=prepared_font::checksum(subset,sizeof(subset));subset[18]=(u8)crc;subset[19]=(u8)(crc>>8);
    };
    checksum_subset();assert(fonts::install(subset,sizeof(subset),key,12));
    assert(fonts::glyph(settings,'A',after) && after.family==3 && after.width==1);
    assert(fonts::glyph(settings,'B',after) && after.family==1 && after.width>1);
    subset[8]=5;checksum_subset();
    assert(!fonts::install(subset,sizeof(subset),key,12));
    assert(fonts::glyph(settings,'A',after) && after.family==3 && after.width==1);
    const u32 revision=ui.settings_revision();assert(ui.apply_settings(settings,false) && ui.settings_revision()==revision);
    assert(fonts::select(Settings{}) && fonts::select(settings));
    // Restore from old settings records: new fields were erased, not zeroed.
    Settings legacy;encode_settings(legacy,7,record);record[4]=4;
    std::memset(record+38,0xFF,26);u32 crc=2166136261U;
    for(unsigned i=0;i<64;++i) crc=(crc^record[i])*16777619U;
    for(unsigned i=0;i<4;++i) record[64+i]=(u8)(crc>>(i*8));
    assert(decode_settings(record,decoded,sequence) && decoded.ui_font_family==1 && !decoded.ui_font_key);
    assert(files::remove("/Fonts/DejaVu-12.FMK"));
    ui.init(settings);assert(ui.settings().ui_font_family==1 && !ui.settings().ui_font_key);
    assert(fonts::step(16,1,item) && item.family==4);
    assert(fonts::step(item.key,1,item) && item.family==5);

    text("/Software/content.txt","content");u32 stamp=0,other=0;
    assert(files::content_stamp("/Software/content.txt",stamp));
    text("/Software/unrelated.txt","changed");
    assert(files::content_stamp("/Software/content.txt",other) && other==stamp);
    text("/Software/content.txt","CONTENT");
    assert(files::content_stamp("/Software/content.txt",other) && other!=stamp);
    stamp=other;assert(files::begin_usb());
    assert(!files::content_stamp("/Software/content.txt",other));
    files::usb_eject();assert(files::end_usb());
    assert(files::content_stamp("/Software/content.txt",other) && other!=stamp);

    m61_text::cancel();clock::init();ui.init();Screen screen;static Services idle;
    auto model=calculator.snapshot();model.idle=true;model.running=model.programming=false;
    model.last_key="DIGIT";model.angle=DEGREE;
    screen.render(model,true,&ui,&idle);
    face_status(screen,ui,idle,M8("АВТ"),M8("Г"),M8("ЦИФРА"));
    native_status(screen,M8("АВТ"),M8("Г"),M8("ЦИФРА"));
    auto locale=ui.settings();locale.russian=0;assert(ui.apply_settings(locale));
    screen.render(model,true,&ui,&idle);face_status(screen,ui,idle,"AUTO","DEG","DIGIT");
    native_status(screen,"AUTO","DEG","DIGIT");
    locale.russian=1;assert(ui.apply_settings(locale));
    model.angle=RADIAN;model.running=true;model.last_key="RETURN";
    screen.render(model,true,&ui,&idle);face_status(screen,ui,idle,M8("СЧЁТ"),M8("Р"),M8("В/О"));
    native_status(screen,M8("СЧЁТ"),M8("Р"),M8("В/О"));
    model.angle=GRADE;model.running=false;model.programming=true;model.last_key="READY";
    screen.render(model,true,&ui,&idle);face_status(screen,ui,idle,M8("ПРГ"),M8("ГРД"),M8("ГОТОВ"));
    native_status(screen,M8("ПРГ"),M8("ГРД"),M8("ГОТОВ"));
    model.angle=DEGREE;model.programming=false;model.last_key="DIGIT";
    screen.render(model,true,&ui,&idle);u8 no_clock[1536],with_clock[1536];
    screen.logical_frame(ui,idle,no_clock);
    clock_header(screen);
    assert(clock::set({2026,10,17,12,34,0}));
    screen.render(model,true,&ui,&idle);screen.logical_frame(ui,idle,with_clock);
    u32 rows[rtc_idle_clock::GRAPHIC_CLOCK_HEIGHT];assert(rtc_idle_clock::build_graphic_clock(12,34,rows));
    for(unsigned y=0;y<7;++y) for(unsigned x=0;x<rtc_idle_clock::GRAPHIC_CLOCK_WIDTH;++x)
        assert(pixel(with_clock,165+x,18+y)==bool(rows[y]&(1U<<x)));
    for(unsigned y=0;y<64;++y) for(unsigned x=0;x<192;++x)
        if(x<165 || x>=190 || y<18 || y>=25)
            assert(pixel(no_clock,x,y)==pixel(with_clock,x,y));
    face_status(screen,ui,idle,M8("АВТ"),M8("Г"),M8("ЦИФРА"));
    native_status(screen,M8("АВТ"),M8("Г"),M8("ЦИФРА"));
    status_preview(screen,preview_path,".ru-status.pbm");
    physical_face(screen,model,false);clock_header(screen,rows);
    locale.russian=0;locale.calculator_font=1;assert(ui.apply_settings(locale));
    screen.render(model,true,&ui,&idle);screen.logical_frame(ui,idle,with_clock);
    face_status(screen,ui,idle,"AUTO","DEG","DIGIT");physical_face(screen,model,true);clock_header(screen,rows);
    native_status(screen,"AUTO","DEG","DIGIT");status_preview(screen,preview_path,".en-status.pbm");
    model.last_key="RETURN";screen.render(model,true,&ui,&idle);native_status(screen,"AUTO","DEG","RETURN");
    status_preview(screen,preview_path,".return-status.pbm");model.last_key="DIGIT";
    for(unsigned y=0;y<7;++y) for(unsigned x=0;x<25;++x)
        assert(pixel(with_clock,165+x,18+y)==bool(rows[y]&(1U<<x)));
    locale.russian=1;locale.calculator_font=0;assert(ui.apply_settings(locale));
    model.idle=false;screen.render(model,true,&ui,&idle);screen.logical_frame(ui,idle,with_clock);
    assert(!std::memcmp(no_clock,with_clock,1536));clock_header(screen);
    model.idle=true;model.running=true;screen.render(model,true,&ui,&idle);screen.logical_frame(ui,idle,with_clock);
    clock_header(screen);
    for(unsigned y=16;y<28;++y) for(unsigned x=0;x<192;++x) assert(!pixel(with_clock,x,y));
    model.running=false;model.programming=true;screen.render(model,true,&ui,&idle);screen.logical_frame(ui,idle,with_clock);
    clock_header(screen);
    for(unsigned y=16;y<28;++y) for(unsigned x=0;x<192;++x) assert(!pixel(with_clock,x,y));

    auto arrow=model;arrow.segmented=false;std::strcpy(arrow.face_indicator," ");
    arrow.face_indicator[1]=(char)display_symbol::uc1609::RT_ARROW;arrow.face_indicator[2]=0;
    for(unsigned face=0;face<2;++face) {
        locale.calculator_font=face;assert(ui.apply_settings(locale));screen.render(arrow,true,&ui,&idle);
        physical_face(screen,arrow,face==1);
    }

    diagnostics::initialize(0x11,false,test_clock);diagnostics::watchdog_started(8000);
    test_time+=20000;diagnostics::feed_watchdog();
    assert(diagnostics::watchdog_status().reloads==1 && diagnostics::watchdog_status().maximum_gap_ms==20);
    diagnostics::profile_start();
    { diagnostics::Scope scope(diagnostics::Point::CORE);test_time+=123; }
    assert(diagnostics::sample(diagnostics::Point::CORE).calls==1 && diagnostics::sample(diagnostics::Point::CORE).total_us==123);
    diagnostics::profile_stop();
    { diagnostics::Scope scope(diagnostics::Point::CORE);test_time+=200; }
    assert(diagnostics::sample(diagnostics::Point::CORE).calls==1);
    const u32 frame[]={1,2,3,4,12,0x10000101,0x20001022,0x01000000};
    const u32 callee[]={4,5,6,7,8,9,10,11};
    diagnostics::context(diagnostics::State::APP,61);
    diagnostics::capture_fault(frame,callee,0xFFFFFFFD,0x20030000,0x20020000,0,1);
    crash_dump_format::Record crash{};assert(diagnostics::crash_copy(crash));
    assert(crash.stacked_pc==0x20001022 && crash.r11==11 && crash.runtime_detail==61);
    assert((crash.capture_flags & 19)==19 && crash_dump_format::valid(crash));
    assert(diagnostics::persist_crash());
    diagnostics::initialize(0x22,true,test_clock);
    assert(diagnostics::crash_copy(crash) && crash.rcc_csr_after_reboot==0x22 &&
        diagnostics::watchdog_status().boot_was_watchdog && diagnostics::watchdog_status().previous_reloads==1);
    std::string output;Terminal terminal(calculator,services,ui);
    terminal.init({&output,[](void* p,const char* data,unsigned n) { ((std::string*)p)->append(data,n); },nullptr,nullptr});
    assert(terminal.execute("wdog status") && output.find("BOOT_WATCHDOG=1")!=std::string::npos);
    assert(terminal.execute("crash show") && output.find("PC=20001022")!=std::string::npos);
    assert(terminal.execute("crash save /Software/crash.txt") && files::exists("/Software/crash.txt"));
    assert(terminal.execute("prof start"));test_time+=1;calculator.tick();
    assert(terminal.execute("prof stop") && terminal.execute("prof save /Software/profile.txt"));
    assert(files::exists("/Software/profile.txt") && output.find("core")!=std::string::npos);
    assert(!terminal.execute("prof invalid") && !terminal.execute("wdog test") && !terminal.execute("crash test"));
    assert(terminal.execute("crash clear") && !diagnostics::crash_available());
    diagnostics::capture_fault(nullptr,nullptr,0,0,0,0,0);
    assert(diagnostics::crash_copy(crash) && !(crash.capture_flags & crash_dump_format::FRAME_VALID) &&
        crash.stacked_pc==crash_dump_format::INVALID_STACK_WORD);
    diagnostics::clear_crash();diagnostics::initialize();
    std::puts("PicoCalc software parity: file dispatch/autoexec, graphical Markdown/WBMP/styles/links, external fonts/settings, content stamps, idle clock, crash/watchdog/profiler PASS");
}
