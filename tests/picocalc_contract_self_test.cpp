#include "services.hpp"
#include "native_display.hpp"
#include "canvas.hpp"
#include "script.hpp"
#include "mk8_literal.hpp"
#include "keyboard_layout.hpp"
#include "fonts.hpp"
#include "input.hpp"
#include "keyboard_core.hpp"
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {
[[noreturn]] void failed(const char* text,unsigned line) {
    std::fprintf(stderr,"Pico contract line %u: %s\n",line,text);std::fflush(stderr);std::abort();
}
#define CHECK(test) ((test)?(void)0:failed(#test,__LINE__))
using namespace picocalc;
void type(Services& s,const char* value) { while(*value) CHECK(s.input((u8)*value++)); }
void replace_prompt(Services& s,const char* value) {
    for(unsigned i=0;i<256;++i) s.input(8);
    type(s,value);s.input('\r');
}
std::string view(const Services& s) {
    std::string text;
    for(unsigned i=0;i<Services::ROWS;++i) { char row[Services::COLS+1];s.row(i,row);text+=row;text+='\n'; }
    return text;
}
u32 edit_hook(u32 op,mk61_service_edit_hook* e) {
    if(op==MK61_EDIT_MOVE) { CHECK(e->delta==-1);e->cursor=0;return 1; }
    if(op==MK61_EDIT_BACKSPACE) { e->source[0]=0;e->length=e->cursor=0;return 1; }
    return 0;
}
void native_contract(void* context,const mk61_app_api& api,const mk61_app_services& s) {
    auto& ui=*(Ui*)context;
    const auto sound_settings=ui.settings();auto quiet=sound_settings;quiet.volume=10;CHECK(ui.apply_settings(quiet));
    CHECK(api.beep(2000,100,100));const auto loud=script::tone_status();CHECK(loud.wrap && loud.level);
    CHECK(api.beep(2000,100,25));CHECK(script::tone_status().level==loud.level/4);
    quiet.volume=1;CHECK(ui.apply_settings(quiet));CHECK(api.beep(2000,100,100));CHECK(script::tone_status().level>=loud.level/10 && script::tone_status().level<=loud.level/10+1);
    quiet.volume=0;CHECK(ui.apply_settings(quiet));CHECK(api.beep(2000,100,100));CHECK(!script::tone_status().level);
    CHECK(!api.beep(65536,1,1) && !api.beep(1,65536,1) && !api.beep(1,0,1) && !api.beep(1,1,101));
    CHECK(ui.apply_settings(sound_settings));CHECK(api.beep(1,65535,100));CHECK(script::tone_status().software);
    api.sound_stop();CHECK(!script::tone_status().wrap && !script::tone_status().software);
    CHECK(!api.led_blink(0,1,1) && !api.led_blink(65536,1,1) && !api.led_blink(1,60001,1));
    CHECK(api.led_blink(65535,60000,60000) && script::led_status() && script::led_blinking());
    script::led_stop();CHECK(!script::led_status() && !script::led_blinking());
    for(unsigned hz=1;hz<=65535;++hz) {
        const auto plan=audio::plan(125000000,hz,10,100);
        CHECK((plan.software && plan.period_us && plan.on_us<=plan.period_us/4+1) ||
              (!plan.software && plan.wrap>0 && plan.wrap<=65536 && plan.divider16>=16 && plan.divider16<=4095 && plan.level<=plan.wrap/4+1));
    }
    CHECK(api.file_size(0xFFFFFFFF)==UINT32_MAX);
    CHECK(api.file_size(MK61_SERVICE_ROOT_ID)==UINT32_MAX);
    u8 bytes[128]{};
    CHECK(api.file_read(0xFFFFFFFF,0,bytes,1)==UINT32_MAX);
    program_store::Entry parent{};CHECK(script::register_file("/Contract",parent));
    const char* value=M8("Привет, ёж!\n");
    mk61_service_write write{M8("текст"),(const u8*)value,(u32)std::strlen(value),MK61_SERVICE_INVALID_ID};
    CHECK(s.call(MK61_SERVICE_FILE_WRITE,parent.id,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_TEXT,&write));
    const u32 id=write.id;
    CHECK(api.file_size(id)==std::strlen(value));
    CHECK(api.file_read(id,0,bytes,sizeof(bytes))==std::strlen(value));
    CHECK(!std::memcmp(bytes,value,std::strlen(value)));
    CHECK(api.file_read(id,3,bytes,4)==4 && !std::memcmp(bytes,value+3,4));
    CHECK(api.file_read(id,0,nullptr,0)==0);
    CHECK(api.file_read(id,0,nullptr,1)==UINT32_MAX);
    CHECK(api.file_read(id,0x10000,bytes,1)==UINT32_MAX);
    unsigned used=0;
    CHECK(files::read("/Contract/текст.txt",bytes,sizeof(bytes),used));
    CHECK(used==std::strlen("Привет, ёж!\n") && !std::memcmp(bytes,"Привет, ёж!\n",used));
    // Eviction preserves logical M8 lengths and partial reads for every text type.
    for(const char* suffix:{".md",".foc",".tbi",".state.txt",".m61"}) {
        const auto path=std::string("/Contract/Russian")+suffix;
        CHECK(files::write_text(path.c_str(),value,std::strlen(value)));
        program_store::Entry entry{};CHECK(script::register_file(path.c_str(),entry));
        CHECK(entry.data_len==std::strlen(value));
        CHECK(api.file_read(entry.id,2,bytes,3)==3 && !std::memcmp(bytes,value+2,3));
        CHECK(api.file_size(id)==std::strlen(value));
    }
    char source[32]="abc";
    mk61_service_edit_key edit{};edit.source=source;edit.capacity=sizeof(source);
    edit.length=edit.cursor=3;edit.options=16;edit.key=keyboard_layout::MINI.left;
    edit.hook_mask=4;edit.hook=edit_hook;
    CHECK(s.call(MK61_SERVICE_EDITOR_KEY,0,0,0,&edit)==1 && edit.cursor==0 && edit.length==3);
    edit.key=keyboard_layout::MINI.esc;
    CHECK(s.call(MK61_SERVICE_EDITOR_KEY,0,0,0,&edit)==2);
    edit.key=keyboard_layout::MINI.cx;edit.hook_mask=8;
    CHECK(s.call(MK61_SERVICE_EDITOR_KEY,0,0,0,&edit)==1 && !edit.length && !source[0]);
    edit.shift=3;
    CHECK(!s.call(MK61_SERVICE_EDITOR_KEY,0,0,0,&edit));
    edit.shift=0;edit.hook=nullptr;
    CHECK(!s.call(MK61_SERVICE_EDITOR_KEY,0,0,0,&edit));
    const auto display=[&](u32 op,u32 b=0,u32 c=0,void* data=nullptr) {
        return s.call(MK61_SERVICE_DISPLAY,op,b,c,data);
    };
    const auto frame=[]() { return std::vector<u8>(script::frame(),script::frame()+1536); };
    CHECK(display(MK61_SERVICE_DISPLAY_GRAPHICS_MODE)==1);
    CHECK(display(MK61_SERVICE_DISPLAY_SUPPORTS_CURSOR)==1);
    api.display_clear();const auto empty=frame();
    display(MK61_SERVICE_DISPLAY_CURSOR_ON);CHECK(frame()!=empty);
    display(MK61_SERVICE_DISPLAY_CURSOR_OFF);CHECK(frame()==empty);
    display(MK61_SERVICE_DISPLAY_BLINK_ON);CHECK(frame()!=empty);
    display(MK61_SERVICE_DISPLAY_CURSOR_OFF);CHECK(frame()==empty);
    display(MK61_SERVICE_DISPLAY_BEGIN_UPDATE);
    CHECK(api.display_write_m8(0,0,"A",1));CHECK(frame()==empty);
    display(MK61_SERVICE_DISPLAY_END_UPDATE);CHECK(frame()!=empty);
    CHECK(!display(MK61_SERVICE_DISPLAY_WRITE,256) && !display(MK61_SERVICE_DISPLAY_WRITE,127));
    CHECK(!api.display_write_m8(0,0,"\x7f",1));
    const auto saved=ui.settings();
    for(const auto choice: {std::pair<unsigned,unsigned>{1,12},{1,14},{1,16},{4,16},{5,5},{0,14}}) {
        auto settings=saved;settings.ui_font_family=choice.first;settings.ui_font_size=choice.second;
        settings.ui_font_key=0;CHECK(ui.apply_settings(settings));
        CHECK(s.call(MK61_SERVICE_SETUP,MK61_SETUP_TEXT_MODE,1,0,nullptr));
        CHECK(display(MK61_SERVICE_DISPLAY_UI_TEXT_ACTIVE)==1);
        api.display_clear();
        const auto info=fonts::info(settings);
        const unsigned rows=(64+info.line_gap)/(info.height+info.line_gap);
        CHECK(api.display_rows()==rows);
        CHECK(display(MK61_SERVICE_DISPLAY_UI_TEXT_WIDTH)==(choice.first==4?192:188));
        mk61_service_ui_glyph glyph{};CHECK(fonts::glyph(settings,'A',glyph));
        CHECK(display(MK61_SERVICE_DISPLAY_MEASURE_UI_TEXT,0,0,(void*)"A")==glyph.advance);
        CHECK(display(MK61_SERVICE_DISPLAY_UI_LINE,0,0,(void*)"A"));
        std::vector<u8> expected(1536);
        const unsigned top=(64-(rows*info.height+(rows-1)*info.line_gap))/2;
        for(unsigned y=0;y<glyph.height;++y) for(unsigned x=0;x<glyph.width;++x) {
            if(glyph.pixels[y*((glyph.width+7)/8)+x/8] & (0x80>>(x%8))) {
                const unsigned px=(choice.first==4?0:2)+glyph.bearing_x+x;
                const unsigned py=top+info.ascent-glyph.bearing_y+y;
                expected[(py/8)*192+px]|=1<<(py%8);
            }
        }
        CHECK(frame()==expected);
    }
    CHECK(ui.apply_settings(saved));display(MK61_SERVICE_DISPLAY_END_UI_TEXT);
    CHECK(!display(MK61_SERVICE_DISPLAY_UI_TEXT_ACTIVE));
    CHECK(api.display_columns()==32 && api.display_rows()==8);
    std::vector<u8> bitmap(1536,0xA5);
    CHECK(api.graphics_begin() && api.graphics_present(bitmap.data(),bitmap.size()));
    CHECK(frame()==bitmap);
    CHECK(display(MK61_SERVICE_DISPLAY_WRITE,'Z'));CHECK(frame()==bitmap);
    api.graphics_end();CHECK(frame()!=bitmap && frame()!=empty);
    std::string lines;for(unsigned i=0;i<25;++i) lines+="a\n";
    mk61_service_editor editor{lines.c_str(),(u32)lines.size(),(u32)lines.size(),0,0};
    CHECK(s.call(MK61_SERVICE_EDITOR_SCROLL,0,0,0,&editor) && editor.top==36);
    CHECK(s.call(MK61_SERVICE_EDITOR_DRAW,0,0,0,&editor) && editor.top==36);
    editor.top=0x10000;CHECK(!s.call(MK61_SERVICE_EDITOR_SCROLL,0,0,0,&editor));
    const auto key=[&](u32 op,u32 value=0) { return s.call(MK61_SERVICE_KEYBOARD,op,value,0,nullptr); };
    controls::clear();
    controls::event({1,'1'});
    CHECK(key(MK61_SERVICE_KEY_ANY) && key(MK61_SERVICE_KEY_PRESSED,keyboard_layout::MINI.digit[1]));
    CHECK(key(MK61_SERVICE_KEY_IMMEDIATE,keyboard_layout::MINI.digit[1])==1);
    CHECK(key(MK61_SERVICE_KEY_IMMEDIATE,keyboard_layout::MINI.digit[1])==0);
    CHECK(key(MK61_SERVICE_KEY_POLL)==keyboard_layout::MINI.digit[1]);
    CHECK(key(MK61_SERVICE_KEY_LAST)==keyboard_layout::MINI.digit[1]);
    CHECK(key(MK61_SERVICE_KEY_POLL)==UINT32_MAX);
    controls::event({3,'1'});
    CHECK(key(MK61_SERVICE_KEY_GET,keyboard_core::RELEASE_MASK)==(keyboard_layout::MINI.digit[1]|keyboard_core::RELEASE_MASK));
    CHECK(!key(MK61_SERVICE_KEY_ANY));
    controls::event({1,'\r'});CHECK(key(MK61_SERVICE_KEY_POLL)==keyboard_layout::MINI.ok);
    CHECK(key(MK61_SERVICE_KEY_HANDOFF,keyboard_layout::MINI.ok));
    CHECK(key(MK61_SERVICE_KEY_HANDOFF_PENDING));
    controls::event({1,'\r'});controls::event({1,'2'});controls::event({3,'\r'});
    CHECK(!key(MK61_SERVICE_KEY_HANDOFF_PENDING));
    CHECK(key(MK61_SERVICE_KEY_GET,0)==keyboard_layout::MINI.digit[2]);
    controls::event({3,'2'});CHECK(api.key_poll()==MK61_APP_KEY_NONE);
    controls::event({1,'\r'});CHECK(api.key_poll()==MK61_APP_KEY_OK);controls::event({3,'\r'});
    CHECK(api.key_poll()==MK61_APP_KEY_NONE);
    controls::event({1,'3'});controls::event({3,'3'});
    CHECK(key(MK61_SERVICE_KEY_WAIT)==keyboard_layout::MINI.digit[3]);
    controls::event({1,'4'});CHECK(api.key_wait()==MK61_APP_KEY_DIGIT_4);
    CHECK(key(MK61_SERVICE_KEY_CLEAR_IMMEDIATE));
    CHECK(!key(MK61_SERVICE_KEY_IMMEDIATE,keyboard_layout::MINI.digit[4]));
    controls::event({3,'4'});CHECK(api.key_poll()==MK61_APP_KEY_NONE);
    CHECK(key(MK61_SERVICE_KEY_CLEAR_HOLD));CHECK(key(MK61_SERVICE_KEY_GET,17)==UINT32_MAX);
    // Physical QWERTY letters are literal input even where the calculator
    // has E/F/L aliases. An explicitly scanned USB key retains its identity.
    char qwerty[32]{};mk61_service_edit_key typed{};
    typed.source=qwerty;typed.capacity=sizeof(qwerty);typed.options=1;
    for(const char* c="hello fkl";*c;++c) {
        controls::event({1,(u8)*c});
        typed.key=(i32)key(MK61_SERVICE_KEY_GET,0);
        CHECK(typed.key==MK61_APP_KEY_RAW_BASE+*c);
        CHECK(s.call(MK61_SERVICE_EDITOR_KEY,0,0,0,&typed)==1);
        controls::event({3,(u8)*c});CHECK(key(MK61_SERVICE_KEY_GET,keyboard_core::RELEASE_MASK)==UINT32_MAX);
    }
    CHECK(!std::strcmp(qwerty,"hello fkl") && typed.length==9);
    controls::event({1,'L'});
    const u8 recall=(u8)keyboard_layout::MINI.p_to_x;
    const u8 recall_code=controls::from_scan(recall);
    controls::event({1,recall_code,recall},controls::Source::REMOTE);
    CHECK(key(MK61_SERVICE_KEY_GET,0)==MK61_APP_KEY_RAW_BASE+'L');
    CHECK(key(MK61_SERVICE_KEY_GET,0)==recall);
    CHECK(key(MK61_SERVICE_KEY_PRESSED,recall) && key(MK61_SERVICE_KEY_PRESSED,MK61_APP_KEY_RAW_BASE+'L'));
    CHECK(key(MK61_SERVICE_KEY_HANDOFF,recall));
    controls::event({3,recall_code,recall},controls::Source::REMOTE);
    CHECK(!key(MK61_SERVICE_KEY_HANDOFF_PENDING) && !key(MK61_SERVICE_KEY_PRESSED,recall));
    CHECK(key(MK61_SERVICE_KEY_PRESSED,MK61_APP_KEY_RAW_BASE+'L'));
    controls::event({3,'L'});CHECK(key(MK61_SERVICE_KEY_GET,keyboard_core::RELEASE_MASK)==UINT32_MAX);
    for(unsigned scan=0;scan<keyboard_core::KEY_COUNT;++scan) {
        const u8 code=controls::from_scan(scan);if(!code) continue;
        controls::event({1,code,(u8)scan},controls::Source::REMOTE);
        CHECK(key(MK61_SERVICE_KEY_GET,0)==scan && key(MK61_SERVICE_KEY_PRESSED,scan));
        controls::event({3,code,(u8)scan},controls::Source::REMOTE);
        CHECK(key(MK61_SERVICE_KEY_GET,keyboard_core::RELEASE_MASK)==(scan|keyboard_core::RELEASE_MASK));
        CHECK(!key(MK61_SERVICE_KEY_PRESSED,scan));
    }
}
void filename_contract(void*,const mk61_app_api& base,const mk61_app_services& api) {
    char name[32];std::strcpy(name,M8("ёж"));mk61_service_save_target target{name,MK61_SERVICE_ROOT_ID};
    CHECK(api.call(MK61_SERVICE_FILE_SAVE_TARGET,MK61_SERVICE_FILE_TEXT,0,sizeof(name),&target));
    CHECK(!std::strcmp(name,M8("Привет.txt")) && target.parent==MK61_SERVICE_ROOT_ID);
    CHECK(base.key_poll()==MK61_APP_KEY_NONE);
}
void cancelled_filename_contract(void*,const mk61_app_api& base,const mk61_app_services& api) {
    char name[6];std::strcpy(name,"KEEP");mk61_service_save_target target{name,MK61_SERVICE_ROOT_ID};
    CHECK(!api.call(MK61_SERVICE_FILE_SAVE_TARGET,MK61_SERVICE_FILE_TEXT,0,sizeof(name),&target));
    CHECK(!std::strcmp(name,"KEEP") && base.key_poll()==MK61_APP_KEY_NONE);
}
}
void picocalc_contract_test() {
    {
        Settings settings{};settings.ui_font_family=1;settings.ui_font_size=16;
        NativeDisplay display(settings,true);
        CHECK(display.width()==320 && display.height()==320 && display.rows()>10);
        CHECK(display.call(MK61_SERVICE_DISPLAY_BEGIN_UI_TEXT,0,0,nullptr));
        char label[16];std::strcpy(label,M8("ЯЁg"));CHECK(display.call(MK61_SERVICE_DISPLAY_UI_LINE,12,0,label));
        mk61_service_ui_glyph glyph{};CHECK(fonts::glyph(settings,0x042F,glyph));
        const unsigned pitch=fonts::info(settings).height+fonts::info(settings).line_gap;
        for(unsigned y=0;y<glyph.height;++y) for(unsigned x=0;x<glyph.width;++x) {
            const int px=2+glyph.bearing_x+x,py=12*pitch+fonts::info(settings).ascent-glyph.bearing_y+y;
            CHECK(bool(canvas::frame()[py/8*320+px]&(1U<<(py&7)))==bool(glyph.pixels[y*((glyph.width+7)/8)+x/8]&(0x80U>>(x&7))));
        }
        const auto text=std::vector<u8>(canvas::frame(),canvas::frame()+12800);
        CHECK(display.bitmap_begin());mk61_service_framebuffer frame{};
        CHECK(display.call(MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(frame),0,&frame));
        CHECK(frame.width==320 && frame.height==320 && frame.bytes==12800 && frame.pixels==canvas::frame());
        std::memset(frame.pixels,0,frame.bytes);canvas::pixel(frame.pixels,319,319);canvas::pixel(frame.pixels,319,0);
        CHECK(display.bitmap_present(frame.pixels,frame.bytes));
        CHECK(!display.bitmap_present(frame.pixels,1536));
        CHECK(script::native_frame()[39*320+319]==128);
        display.bitmap_end();CHECK(!std::memcmp(text.data(),canvas::frame(),12800));
    }

    using namespace picocalc;
    CHECK(files::mkdir("/Contract") && files::mkdir("/Contract/target"));
    for(unsigned i=0;i<18;++i) {
        char name[64];std::snprintf(name,sizeof(name),"/Contract/Find%02u.txt",i);
        CHECK(files::write_text(name,"Move me",7));
    }
    CHECK(files::write_text("/Contract/ЁЖ.txt","Russian name",12));
    Calculator calculator;calculator.init();Ui ui;ui.init();static Services s;s.set_ui(ui);
    s.open(Action::EXPLORER,false,calculator);s.new_document(Document::TEXT);
    type(s,"\x88Ghbdtn");CHECK(view(s).find(M8("Привет"))!=std::string::npos);
    CHECK(s.save_document("/Contract/target/русский.txt"));s.input(0x88);
    s.open(Action::EXPLORER,false,calculator);CHECK(s.enter_directory("/Contract"));
    s.input(0x84);for(unsigned i=0;i<256;++i) s.input(8);
    type(s,"\x88`;\x08;");CHECK(view(s).find(M8("ёж"))!=std::string::npos && s.cursor_column()==2);
    s.input('\r');CHECK(files::exists("/Contract/ёж"));s.input(0x86);type(s,"~:");s.input('\r');
    CHECK(view(s).find(M8("ёж"))!=std::string::npos);
    s.input(0x86);s.input(0x88);s.input(0x1B);s.filter_directory("");
    s.filter_directory("ёж");CHECK(view(s).find(M8("ЁЖ.txt"))!=std::string::npos);
    s.filter_directory("FiNd");CHECK(view(s).find("Find00.txt")!=std::string::npos);
    for(unsigned i=0;i<8;++i) s.input(0xB6);
    CHECK(view(s).find("Find07.txt")!=std::string::npos && view(s).find("Find00.txt")==std::string::npos);
    s.input(0x1B);CHECK(std::strcmp(s.page_name(),"BROWSER")==0 && view(s).find("? FiNd")==std::string::npos);
    s.input(0x86);CHECK(std::strcmp(s.page_name(),"PROMPT")==0);type(s,"find17");s.input('\r');
    CHECK(view(s).find("Find17.txt")!=std::string::npos && view(s).find("Find16.txt")==std::string::npos);
    s.input(0xB6);s.input(0x81);for(unsigned i=0;i<4;++i) s.input(0xB6);s.input('\r');
    CHECK(std::strcmp(s.page_name(),"PROMPT")==0);replace_prompt(s,"/Contract/target");
    CHECK(!files::exists("/Contract/Find17.txt") && files::exists("/Contract/target/Find17.txt"));
    CHECK(files::write_text("/Contract/Find17.txt","original",8));s.filter_directory("find17");s.input(0xB6);s.input(0x87);
    replace_prompt(s,"target");CHECK(std::strcmp(s.page_name(),"MESSAGE")==0);
    char bytes[32];unsigned used=0;
    CHECK(files::read_text("/Contract/Find17.txt",bytes,sizeof(bytes),used) && !std::strcmp(bytes,"original"));
    CHECK(files::read_text("/Contract/target/Find17.txt",bytes,sizeof(bytes),used) && !std::strcmp(bytes,"Move me"));
    s.input(0x1B);s.input(0x1B);s.input(0x1B);
    script::attach(calculator,s);CHECK(script::text_profile({8,5,8,0}));s.test_native_contract(native_contract,&ui);
    const char* keys="\x08\x08\x88Ghbdtn\x88.txt\r";
    s.set_pump([](void* context,u8& code) { auto& next=*(const char**)context;if(!*next) return false;code=(u8)*next++;return true; },&keys);
    s.test_native_contract(filename_contract,nullptr);CHECK(!*keys);
    keys="\x08\x08\x08\x08TOO-LONG\r\x1b";s.test_native_contract(cancelled_filename_contract,nullptr);CHECK(!*keys);
    s.set_pump(nullptr,nullptr);
    CHECK(files::mkdir("/Contract/gone"));s.open(Action::EXPLORER,false,calculator);
    CHECK(s.enter_directory("/Contract/gone") && files::remove("/Contract/gone"));
    s.open(Action::EXPLORER,false,calculator);
    CHECK(!std::strcmp(s.page_name(),"BROWSER") && view(s).rfind("/\n",0)==0);
    std::puts("PicoCalc public contract: browser search/move, M8 APP I/O, shared editor hooks/scrolling, atomic display/cursor/UI raster, bitmap restoration, raw key press/release/immediate/handoff PASS");
}
