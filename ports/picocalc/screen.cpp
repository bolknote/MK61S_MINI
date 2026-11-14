#include "screen.hpp"
#include "canvas.hpp"
#include "display_symbols.hpp"
#include "ui_font.hpp"
#include "mk8_codec.hpp"
#include "mk8_literal.hpp"
#include "menu_model.hpp"
#include "services.hpp"
#include "native_display.hpp"
#include "builtin_font.hpp"
#include "m61_text.hpp"
#include "script.hpp"
#include "fonts.hpp"
#include "clock.hpp"
#include "rtc_idle_clock_core.hpp"
#include "diagnostics.hpp"
#include "version.hpp"
#include <cstdio>
#include <cstring>

namespace picocalc {
namespace {
bool browser_glyph(void*,u8 size,u16 codepoint,explorer_view::Glyph& out) {
    if(size==8) {
        builtin_font::Raster glyph{};
        if(!builtin_font::decode(builtin_font::FaceId::FONT_5X8,codepoint,glyph) &&
           !builtin_font::decode(builtin_font::FaceId::FONT_5X8,'?',glyph)) return false;
        out={};out.width=glyph.width;out.height=glyph.height;out.advance=6;out.bearing_y=8;
        std::memcpy(out.pixels,glyph.data,8);return true;
    }
    Settings font{};font.ui_font_family=1;font.ui_font_size=size;
    mk61_service_ui_glyph glyph{};
    if(!fonts::glyph(font,codepoint,glyph)) return false;
    out={};out.width=glyph.width;out.height=glyph.height;out.advance=glyph.advance;
    out.bearing_x=glyph.bearing_x;out.bearing_y=glyph.bearing_y+size-fonts::info(font).ascent;
    std::memcpy(out.pixels,glyph.pixels,sizeof(out.pixels));return true;
}
void draw_browser(u8* pixels,unsigned bytes,explorer_view::Packing packing,
                  unsigned width,unsigned height,const Services& services) {
    const explorer_view::Geometry geometry{(u16)width,(u16)height,
        services.browser_actions()?explorer_view::Mode::LIST:services.browser_mode()};
    explorer_view::Canvas canvas(pixels,bytes,geometry,packing,browser_glyph);
    canvas.clear();
    char title[64],progress[32]{};services.browser_title(title);
    if(!services.browser_actions() && (services.browser_offset() || services.browser_more()))
        std::snprintf(progress,sizeof(progress),"%u%s",services.browser_offset()/Services::BROWSER_PAGE_SIZE+1,
            services.browser_more()?" >":"");
    const bool ru=services.russian();
    canvas.header(title,progress,ru?M8("Файл"):"File",services.browser_has_parent());
    if(services.browser_actions()) {
        for(unsigned row=0;row<services.selection_menu_rows();++row) {
            char value[Services::COLS+1];services.row(row,value);
            canvas.item((u8)row,value+2,explorer_view::Kind::FILE,nullptr,services.browser_action_selection()==row);
        }
        return;
    }
    const unsigned selected=services.browser_selection();
    const unsigned first=geometry.classic()?(selected/geometry.page_size())*geometry.page_size():0;
    for(unsigned slot=0;slot<geometry.page_size() && first+slot<services.browser_count();++slot) {
        const unsigned index=first+slot;char name[64];if(!services.browser_label(index,name)) continue;
        explorer_view::Icon icon{};const bool custom=services.browser_icon(index,icon);
        canvas.item((u8)slot,name,services.browser_directory(index)?explorer_view::Kind::DIRECTORY:explorer_view::Kind::FILE,
                    custom?&icon:nullptr,index==selected);
    }
    if(!services.browser_count()) canvas.empty(services.browser_filtered()?
        (ru?M8("Нет совпадений"):"No matches"):(ru?M8("Папка пуста"):"Folder empty"));
    if(height==320) {
        canvas.rectangle(0,299,width,1);
        canvas.text(10,303,services.footer(),12,width-20);
    }
}
bool manual_clock_visible(const Snapshot& model) {
    // A queued/held key is ordinary manual input, not a display mode change.
    return !model.running && !model.programming && clock::configured();
}
const char* key_label(const char* label,bool russian) {
    if(!russian) return label;
    static const struct { const char* en; const char* ru; } labels[] = {
        {"READY",M8("ГОТОВ")},{"DIGIT",M8("ЦИФРА")},{"ENTER",M8("В↑")},
        {"EXP",M8("ВП")},{"S/P",M8("С/П")},{"GOTO",M8("БП")},
        {"CALL",M8("ПП")},{"RETURN",M8("В/О")},{"RECALL",M8("ИП")},
        {"STORE",M8("П")},{"STEP <",M8("ШАГ ←")},{"STEP >",M8("ШАГ →")},
        {"DEG",M8("Г")},{"RAD",M8("Р")},{"GRAD",M8("ГРД")}
    };
    for(const auto& item:labels) if(!std::strcmp(label,item.en)) return item.ru;
    return label;
}
struct RegisterStyle { Settings font;unsigned label_width=0; };
RegisterStyle register_style(const Settings& selected) {
    RegisterStyle style{selected};
    const auto fits=[&]() {
        style.label_width=0;
        for(unsigned index=0;index<Ui::REGISTER_COUNT;++index) {
            char label[4];std::snprintf(label,sizeof(label),"R%X",index);
            const unsigned width=fonts::text_width(style.font,label,2);
            if(width>style.label_width) style.label_width=width;
        }
        unsigned cell=0;
        for(const char* p="0123456789 .-LCrE";*p;++p) {
            mk61_service_ui_glyph glyph{};
            if(!fonts::glyph(style.font,(u8)*p,glyph) || glyph.bearing_x<0) return false;
            const unsigned extent=glyph.bearing_x+glyph.width;
            if(glyph.advance>cell) cell=glyph.advance;
            if(extent>cell) cell=extent;
        }
        return fonts::info(style.font).height<=18 &&
            style.label_width+6+(INDICATOR_STRING_LENGTH-1)*cell<=144;
    };
    // Keep complete signed mantissas and exponents in each 144-pixel column.
    // A wide selected face uses a native strike here, never resampled glyphs.
    if(!fits()) {
        style.font.ui_font_family=1;style.font.ui_font_size=14;style.font.ui_font_key=0;
        (void)fits();
    }
    return style;
}
} // namespace
// Keep zero-filled rasters in BSS.
Screen::Screen() {}
void Screen::logical_frame(const Ui& ui,const Services& services,u8 out[1536]) const {
    if(services.browser_display()) {
        draw_browser(out,1536,explorer_view::Packing::PAGE_LSB,192,64,services);return;
    }
    if(services.active() && services.graphics()) { std::memcpy(out,services.graphics(),1536);return; }
    if(!services.active() && ui.page()==Page::CALCULATOR) {
        std::memcpy(out,m61_text::display_owned()?script::frame():face_,1536);return;
    }
    std::memset(out,0,1536);
    auto text=[&](unsigned row,const char* s,bool inverse,unsigned source_row=Services::ROWS) {
        for(unsigned x=0;x<32;++x) {
            u8 glyph[8]{};if(*s) builtin_font::copyRows5x8(mk8::codepoint((u8)*s++),glyph);
            const bool selected=inverse || (source_row<Services::ROWS && services.selected_text(source_row,x));
            for(unsigned y=0;y<8;++y) for(unsigned dx=0;dx<6;++dx)
                if((dx<5 && (glyph[y]&(1U<<(4-dx))))!=selected) out[row*192+x*6+dx]|=(u8)(1U<<y);
        }
    };
    char line[65]{};
    if(services.active()) services.heading(line);else std::snprintf(line,sizeof(line),"%s",ui.title());
    text(0,line,false);
    const unsigned selected=services.active()?services.cursor_row():ui.selected();
    unsigned first=selected>=7?selected-6:0;
    if(services.active() && services.fixed_text()) first=services.first_console_row(7);
    for(unsigned row=0;row<7;++row) {
        if(services.active()) services.row(first+row,line);else ui.row(first+row,line);
        text(row+1,line,!(services.active() && services.fixed_text()) && first+row==selected,first+row);
    }
}
void Screen::set_pixel(unsigned x, unsigned y) {
    if(x < WIDTH && y < HEIGHT) pixels_[y * STRIDE + x / 8] |= (u8)(0x80U >> (x % 8));
}
void Screen::clear_pixel(unsigned x, unsigned y) {
    if(x < WIDTH && y < HEIGHT) pixels_[y * STRIDE + x / 8] &= (u8)~(0x80U >> (x % 8));
}
void Screen::fill_rect(unsigned x,unsigned y,unsigned width,unsigned height) {
    for(unsigned dy=0;dy<height && y+dy<HEIGHT;++dy)
        for(unsigned dx=0;dx<width && x+dx<WIDTH;++dx) set_pixel(x+dx,y+dy);
}
void Screen::text(unsigned x, unsigned y, const char* value, unsigned height, unsigned right, bool erase) {
    auto choice=font_settings_?*font_settings_:Settings{};
    if(choice.ui_font_family==1) choice.ui_font_size=(u8)height;
    const auto info=fonts::info(choice);
    const unsigned baseline = y + info.ascent;
    for(; *value && x < right; ++value) {
        mk61_service_ui_glyph glyph{};
        if(!fonts::glyph(choice,mk8::codepoint((u8)*value),glyph)) continue;
        for(u8 gy = 0; gy < glyph.height; ++gy) for(u8 gx = 0; gx < glyph.width; ++gx) {
            const int px = (int)x + glyph.bearing_x + gx;
            const int py = (int)baseline - glyph.bearing_y + gy;
            const unsigned offset=gy*((glyph.width+7U)/8U)+gx/8U;
            if(px >= 0 && (unsigned)px<right && py >= 0 && (glyph.pixels[offset] & (0x80U>>(gx%8U)))) {
                if(erase) clear_pixel(px,py); else set_pixel(px,py);
            }
        }
        x += glyph.advance;
    }
}
void Screen::status_field(unsigned left,unsigned width,const char* value) {
    auto choice=font_settings_?*font_settings_:Settings{};
    if(choice.ui_font_family==1) choice.ui_font_size=16;
    char label[7]{};unsigned length=0,advance=0;
    for(;*value && length<sizeof(label)-1;++value) {
        mk61_service_ui_glyph glyph{};
        if(!fonts::glyph(choice,mk8::codepoint((u8)*value),glyph)) continue;
        if(advance+glyph.advance>width) break;
        label[length++]=*value;advance+=glyph.advance;
    }
    text(left+(width-advance)/2,40,label,16);
    for(unsigned x=left;x<left+width;++x) set_pixel(x,63);
}
void Screen::bitmap(const u8* frame,unsigned width,unsigned height,unsigned left,unsigned top) {
    if(width==WIDTH && height==HEIGHT && !left && !top) {
        static constexpr auto reverse=[] {
            struct Bytes { u8 value[256]; } table{};
            for(unsigned n=0;n<256;++n) for(unsigned bit=0;bit<8;++bit)
                table.value[n]|=(u8)(((n>>bit)&1U)<<(7-bit));
            return table;
        }();
        // Native canvases are vertical LSB pages, the LCD buffer horizontal
        // MSB rows. Transpose whole 8x8 tiles; overwrite zero pixels too.
        for(unsigned page=0;page<HEIGHT/8;++page) for(unsigned block=0;block<WIDTH/8;++block) {
            u64 bits;std::memcpy(&bits,frame+page*WIDTH+block*8,sizeof(bits));
            u64 t=(bits^(bits>>7))&0x00AA00AA00AA00AAULL;bits^=t^(t<<7);
            t=(bits^(bits>>14))&0x0000CCCC0000CCCCULL;bits^=t^(t<<14);
            t=(bits^(bits>>28))&0x00000000F0F0F0F0ULL;bits^=t^(t<<28);
            u8 transposed[8];std::memcpy(transposed,&bits,sizeof(bits));
            for(unsigned row=0;row<8;++row) {
                pixels_[(page*8+row)*STRIDE+block]=reverse.value[transposed[row]];
            }
        }
        return;
    }
    for(unsigned y=0;y<height && top+y<HEIGHT;++y) for(unsigned x=0;x<width && left+x<WIDTH;++x)
        if(frame[y/8*width+x]&(1U<<(y&7))) set_pixel(left+x,top+y);
}
void Screen::line(unsigned y) {
    for(unsigned x = 8; x < WIDTH - 8; ++x) set_pixel(x, y);
}
void Screen::segment_row(unsigned left,unsigned top,const u8 masks[12]) {
    // Native 7x13 segments, plus a decimal point, in twelve 12-pixel cells.
    // Draw every published bit, including masks that have no text equivalent.
    for(unsigned slot=0;slot<12;++slot) {
        const unsigned x=left+slot*12;const u8 mask=masks[slot];
        for(unsigned p=1;p<=5;++p) {
            if(mask&0x01) set_pixel(x+p,top);
            if(mask&0x02) set_pixel(x+6,top+p);
            if(mask&0x04) set_pixel(x+6,top+6+p);
            if(mask&0x08) set_pixel(x+p,top+12);
            if(mask&0x10) set_pixel(x,top+6+p);
            if(mask&0x20) set_pixel(x,top+p);
            if(mask&0x40) set_pixel(x+p,top+6);
        }
        if(mask&0x80) { set_pixel(x+9,top+11);set_pixel(x+9,top+12); }
    }
}
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((optimize("Os", "no-jump-tables")))
#endif
void Screen::calculator(const Snapshot& model, const Ui& ui) {
    theme_.add(0,63,WIDTH,1,lcd::Ink::LINE);
    theme_.add(0,91,WIDTH,35,lcd::Ink::GREEN);
    theme_.add(0,147,WIDTH,1,lcd::Ink::LINE);
    text_screen::Grid face_grid;
    face_grid.reset(2);
    char status[40];
    const bool russian=ui.settings().russian;
    const char* mode = model.running ? (russian?M8("СЧЁТ"):"RUN") :
        model.programming ? (russian?M8("ПРГ"):"PRG") : (russian?M8("АВТ"):"AUTO");
    // Use the original MK-61 switch names: Г = degrees, Р = radians, ГРД = gradians.
    const char* angle = model.angle == DEGREE ? (russian?M8("Г"):"DEG") :
        model.angle == RADIAN ? (russian?M8("Р"):"RAD") : (russian?M8("ГРД"):"GRD");
    const char* last_key=key_label(model.last_key,russian);
    std::snprintf(status, sizeof(status), "%-5.5s %-3.3s %-6.6s", mode, angle, last_key);
    for(const char* p = status; *p; ++p) face_grid.writeCodepoint(mk8::codepoint((u8)*p));
    face_grid.setCursor(0, 1);
    for(const char* p = model.face_indicator; *p; ++p) {
        const u8 token = (u8)*p;
        face_grid.writeCodepoint(token == ',' ? '.' : token);
    }
    calculator_face::setFont((calculator_face::Font)ui.settings().calculator_font);
    calculator_face::setSegmentFrame(model.segmented ? model.segments : nullptr);
    calculator_face::renderFrame(face_grid, face_);
    calculator_face::setSegmentFrame(nullptr);
    // Twelve 26-pixel slots fit the original 16x35 strike with no resampling.
    const auto digit=[&](unsigned slot,u8 mask,u16 token) {
        const unsigned left=4+slot*26+5,top=91;
        if(token==display_symbol::uc1609::RT_ARROW) {
            for(unsigned x=0;x<10;++x) for(unsigned y=0;y<9;++y)
                if(calculator_face::sourceArrowColumn(x)&(1U<<y)) set_pixel(left+3+x,top+12+y);
            return;
        }
        if(ui.settings().calculator_font==1 && (token || mask==128)) {
            Settings font{};font.ui_font_family=1;font.ui_font_size=16;
            mk61_service_ui_glyph glyph{};
            if(token && fonts::glyph(font,token,glyph)) {
                const int x0=left+(16-glyph.advance)/2+glyph.bearing_x;
                const int y0=top+9+fonts::info(font).ascent-glyph.bearing_y;
                for(unsigned y=0;y<glyph.height;++y) for(unsigned x=0;x<glyph.width;++x)
                    if(glyph.pixels[y*((glyph.width+7)/8)+x/8]&(0x80U>>(x&7))) set_pixel(x0+x,y0+y);
            }
            if(mask&128) for(unsigned y=0;y<2;++y) for(unsigned x=0;x<2;++x) set_pixel(left+18+x,top+23+y);
        } else for(unsigned y=0;y<35;++y) {
            const u16 bits=calculator_face::sourceRow(mask,y);
            for(unsigned x=0;x<16;++x) if(bits&(0x8000U>>x)) set_pixel(left+x,top+y);
        }
    };
    if(model.segmented) for(unsigned slot=0;slot<12;++slot)
        digit(slot,model.segments[slot],calculator_face::sourceToken(model.segments[slot]&127));
    else {
        unsigned slot=0;
        for(unsigned col=0;col<face_grid.cols();++col) {
            const u16 token=face_grid.cell(col,1);
            if(token=='.') { if(slot) digit(slot-1,128,0); }
            else if(slot<12) { digit(slot++,calculator_face::sourceSegments(token),token); }
        }
    }
    status_field(8,96,mode);
    status_field(112,96,angle);
    status_field(216,96,last_key);
    if(manual_clock_visible(model)) {
        const auto now=clock::get();
        u32 rows[rtc_idle_clock::GRAPHIC_CLOCK_HEIGHT];
        if(rtc_idle_clock::build_graphic_clock(now.hour,now.minute,rows)) {
            constexpr unsigned left=192-rtc_idle_clock::GRAPHIC_CLOCK_WIDTH-2;
            // USB Screen's 192x64 frame has no title row. Keep its clock in
            // the empty row below the status rails; the LCD uses its header.
            constexpr unsigned top=18;
            for(unsigned y=0;y<rtc_idle_clock::GRAPHIC_CLOCK_HEIGHT;++y)
                for(unsigned x=0;x<rtc_idle_clock::GRAPHIC_CLOCK_WIDTH;++x)
                    if(rows[y] & (1U<<x)) {
                        face_[((top+y)/8)*192+left+x]|=(u8)(1U<<((top+y)%8));
                    }
        }
        char time[6];std::snprintf(time,sizeof(time),"%02u:%02u",now.hour,now.minute);
        Settings clock_font{};clock_font.ui_font_family=1;clock_font.ui_font_size=16;
        const auto* saved=font_settings_;font_settings_=&clock_font;
        text(WIDTH-(battery_.available?44:10)-fonts::text_width(clock_font,time,5),9,time,16);
        font_settings_=saved;
    }
    const unsigned font_size = ui.settings().ui_font_size;
    line(147);
    if(ui.view() == View::STACK) {
        auto font=ui.settings();if(font.ui_font_family==1) font.ui_font_size=16;
        const unsigned value_left=18+fonts::text_width(font,"X1",2)+8;
        theme_.add(18,154,value_left-18-4,120,lcd::Ink::OCHRE);
        static constexpr const char* labels[]={"X","Y","Z","T","X1","X2"};
        for(unsigned i = 0; i < 6; ++i) {
            char raw[INDICATOR_STRING_LENGTH];
            const char* number = i==0 ? read_stack_register(X,raw,nullptr) :
                i<4 ? model.stack_values[i-1] : i==4 ? read_stack_register(X1,raw,nullptr) : raw;
            const unsigned y=154+i*20;
            text(18,y,labels[i],16,value_left-4);
            if(i==5 && model.segmented) segment_row(value_left,y+1,model.segments);
            else {
                if(i==5) {
                    // X2 follows the same published clear/hold state as the
                    // large face. Its legacy tokens are not M8 text bytes.
                    unsigned n=0;
                    for(;model.face_indicator[n] && n<sizeof(raw)-1;++n) {
                        const u8 token=(u8)model.face_indicator[n];
                        const u16 cp=token=='O'?'0':token==','?'.':display_symbol::uc1609::unicodeCodepoint(token);
                        u8 byte='?';(void)mk8::from_codepoint(cp,byte);raw[n]=(char)byte;
                    }
                    raw[n]=0;
                }
                text(value_left,y,number,16);
            }
        }
    } else if(ui.view() == View::REGISTERS) {
        const auto style=register_style(ui.settings());
        const auto* saved=font_settings_;font_settings_=&style.font;
        theme_.add(8,154,style.label_width+2,120,lcd::Ink::OCHRE);
        theme_.add(168,154,style.label_width+2,120,lcd::Ink::OCHRE);
        for(unsigned n = 0; n < Ui::VISIBLE_REGISTERS; ++n) {
            const unsigned index = ui.offset() + n;
            char raw[INDICATOR_STRING_LENGTH],label[4];
            if(index >= Ui::REGISTER_COUNT) break;
            MK61Emu_ReadRegister((int)index, raw, nullptr);
            std::snprintf(label,sizeof(label),"R%X",index);
            const unsigned left=8+(n/Ui::REGISTER_ROWS)*160;
            const unsigned value_left=left+style.label_width+6;
            const unsigned y=154+(n%Ui::REGISTER_ROWS)*20;
            text(left,y,label,style.font.ui_font_size,value_left-4);
            text(value_left,y,raw,style.font.ui_font_size,left+144);
        }
        font_settings_=saved;
    } else if(ui.view() == View::PROGRAM) {
        theme_.add(18,154,44,120,lcd::Ink::OCHRE);
        for(unsigned row = 0; row < 6; ++row) {
            const unsigned address = ui.offset() + row;
            if(address >= core_61::program_steps()) break;
            const unsigned code = core_61::get_code(core_61::get_ring_address(address));
            std::snprintf(status, sizeof(status), "%c %02X   %02X", address == model.ip ? '>' : ' ', address, code);
            text(18, 154 + row * 20, status, font_size);
        }
    } else {
        const char* help_en[] = {"F1/F: F  F2/K: K  F3/R: S/P", "F4/G: GOTO  F5/C: CALL  B: RET",
            "E: EXP  N: +/-  X: X<>Y", "L: RECALL  S: STORE  Enter: B^",
            "F E: PRG   F N: AUTO", "D: DEG   A: RAD   T: GRAD"};
        const char* help_ru[] = {M8("F1/F: F  F2/K: K  F3/R: С/П"),M8("F4/G: БП  F5/C: ПП  B: В/О"),
            M8("E: ВП  N: +/-  X: X<>Y"),M8("L: ИП  S: П  Enter: В↑"),
            M8("F E: ПРГ   F N: АВТ"),M8("D: Г   A: Р   T: ГРД")};
        for(unsigned row = 0; row < 6; ++row) text(10, 154 + row * 20, russian?help_ru[row]:help_en[row], 12);
    }
    if(ui.view()==View::REGISTERS) std::snprintf(status,sizeof(status),"%s",M8("Shift+↑/↓: R0-RE"));
    else std::snprintf(status, sizeof(status), russian?M8("ШАГ %02X  %u шагов"):"IP %02X  %u steps", model.ip,
        (unsigned)core_61::program_steps());
    text(10, 280, status, 12);
    text(10, 301, ui.footer(), 12);
}
void Screen::native_bitmap(const u8* frame) {
    const bool published=frame==script::native_frame();
    const u32 revision=script::frame_revision();
    // The published canvas changes only through the script/display API.
    // Preserve the already transposed LCD buffer between BASIC parts.
    if(published && native_valid_ && revision==native_revision_) return;
    bitmap(frame,WIDTH,HEIGHT);
    native_revision_=revision;native_valid_=published;
}
void Screen::RenderKey::data(const void* value,unsigned size) {
    if(size>sizeof(bytes)-used) { overflow=true;return; }
    std::memcpy(bytes+used,value,size);used+=size;
}
void Screen::RenderKey::number(u32 value) { data(&value,sizeof(value)); }
void Screen::RenderKey::text(const char* value) { if(!value) value="";data(value,(unsigned)std::strlen(value)+1); }
bool Screen::RenderKey::same(const RenderKey& other) const {
    return !overflow && !other.overflow && used==other.used && !std::memcmp(bytes,other.bytes,used);
}
bool Screen::RenderKey::same_scene(const RenderKey& other) const {
    return animation_at && animation_at==other.animation_at && !overflow && !other.overflow &&
        used==other.used && animation_at+4<=used &&
        !std::memcmp(bytes,other.bytes,animation_at) &&
        !std::memcmp(bytes+animation_at+4,other.bytes+animation_at+4,used-animation_at-4);
}
utility::Mode Screen::utility_mode(const Ui& ui,const Services* services) const {
    if(animation_.bootloader_pending()) return animation_.boot_mode();
    if(services && services->usb_disk()) return files::usb_ejected()?utility::Mode::EJECTED:utility::Mode::USB;
    if((!services || !services->active()) && ui.bootloader_confirmation()) return utility::Mode::UF2_CONFIRM;
    return utility::Mode::NONE;
}
void Screen::utility_theme(utility::Mode mode,unsigned phase) {
    using U=utility::Mode;using A=lcd::UtilityArt;
    switch(mode) {
    case U::USB: theme_.utility=A::USB;break;
    case U::EJECTED: theme_.utility=A::EJECTED;break;
    case U::UF2_CONFIRM: theme_.utility=A::UF2_CONFIRM;break;
    case U::UF2_ENTERING: theme_.utility=A::UF2_ENTERING;break;
    case U::UF2_READY: theme_.utility=A::UF2_READY;break;
    default: theme_.utility=A::NONE;break;
    }
    theme_.phase=(u8)phase;
    theme_.cartridge=(mode==U::UF2_CONFIRM || mode==U::UF2_ENTERING || mode==U::UF2_READY)
        ?utility_art::cartridge_mask:nullptr;
}
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((optimize("Os")))
#endif
void Screen::utility_caption(unsigned top,const char* value,unsigned height) {
    Settings font=*font_settings_;font.ui_font_size=(u8)height;
    unsigned width=0;
    for(const char* p=value;*p;++p) {
        mk61_service_ui_glyph glyph{};
        if(fonts::glyph(font,mk8::codepoint((u8)*p),glyph)) width+=glyph.advance+1;
    }
    unsigned left=width<=296?(WIDTH-width)/2:12;
    const unsigned baseline=top+fonts::info(font).ascent;
    for(;*value;++value) {
        mk61_service_ui_glyph glyph{};
        if(!fonts::glyph(font,mk8::codepoint((u8)*value),glyph))continue;
        if(left+glyph.advance+1>308)break;
        for(unsigned y=0;y<glyph.height;++y)for(unsigned x=0;x<glyph.width;++x) {
            if(!(glyph.pixels[y*((glyph.width+7)/8)+x/8]&(128U>>(x&7))))continue;
            const int px=(int)left+glyph.bearing_x+x,py=(int)baseline-glyph.bearing_y+y;
            if(px<12 || px>=307 || py<0 || py>=319)continue;
            // Native strike, heavier weight; extra tracking preserves the
            // blank column between letters instead of closing their gaps.
            u8* row=pixels_+py*STRIDE+px/8;const u8 mask=(u8)(0xc0U>>(px&7));
            row[0]|=mask;row[STRIDE]|=mask;
            if((px&7)==7) {row[1]|=0x80;row[STRIDE+1]|=0x80;}
        }
        left+=glyph.advance+1;
    }
}
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((optimize("Os")))
#endif
void Screen::utility_page(utility::Mode mode,unsigned phase,const Ui& ui,const Services* services) {
    theme_.add(0,0,WIDTH,27,lcd::Ink::WHITE);
    theme_.add(0,34,WIDTH,24,lcd::Ink::OCHRE);
    theme_.add(0,64,WIDTH,160,lcd::Ink::WHITE);
    theme_.add(12,27,296,2,lcd::Ink::LINE);
    theme_.add(12,288,296,2,lcd::Ink::LINE);
    utility_theme(mode,phase);
    const auto* saved=font_settings_;Settings font{};
    font.ui_font_family=1;font.ui_font_key=0;font_settings_=&font;
    const bool ru=ui.settings().russian;
    if(!utility::draw_headers(pixels_,mode,ru)) text(12,5,"MK61S / USB / UF2",16);
    battery_icon(battery_,[this](unsigned x,unsigned y){set_pixel(x,y);});utility::rectangle(pixels_,12,27,296,2);
    const bool usb=mode==utility::Mode::USB || mode==utility::Mode::EJECTED;
    const bool ejected=mode==utility::Mode::EJECTED;
    const bool ready=mode==utility::Mode::UF2_READY;
    if(!utility::draw(pixels_,mode,phase)) text(12,144,"USB / UF2",16);
    if(usb) {
        const bool failed=services && ejected && !files::usb_active() && !files::ready() && *services->status();
        utility_caption(227,failed?(ru?M8("Не удалось открыть карту"):"Cannot open the card"):ejected?(ru?M8("Можно вернуться в MK61S"):"Ready to return to MK61S"):
            (ru?M8("Карта подключена к ПК"):"Card connected to computer"));
        utility_caption(247,failed?(ru?M8("Проверьте microSD"):"Check the microSD card"):ejected?(ru?M8("Карта снова будет у PicoCalc"):"PicoCalc will take the card back"):
            (ru?M8("Файлы доступны на компьютере"):"Files are available on your PC"));
        const char* status=services?services->status():"";
        if(ru && !std::strcmp(status,"Eject the USB disk on the computer")) status=M8("Сначала извлеките диск на ПК");
        utility_caption(271,failed?status:ejected?"":*status?status:
            (ru?M8("Сначала извлеките диск на ПК"):"Safely eject on the computer first"),14);
    } else {
        utility_caption(237,ready?(ru?M8("Откройте диск RPI-RP2 на ПК"):"Open RPI-RP2 on the computer"):
            (ru?M8("На ПК появится RPI-RP2"):"RPI-RP2 appears on the computer"));
        utility_caption(257,ru?M8("Скопируйте на него файл .uf2"):"Copy your .uf2 file onto it");
        if(ready) utility_caption(273,ru?M8("После записи: перезапуск"):"PicoCalc restarts after writing",14);
    }
    utility::rectangle(pixels_,12,288,296,2);
    const char* footer=usb?(ru?M8("Enter / Esc: вернуться"):"Enter / Esc: return"):
        mode==utility::Mode::UF2_CONFIRM?(ru?M8("Enter: начать  Esc: назад"):"Enter: start  Esc: back"):
        mode==utility::Mode::UF2_ENTERING?(ru?M8("Включаем загрузчик..."):"Starting loader..."):
        (ru?M8("Ожидание файла .uf2"):"Waiting for a .uf2 file");
    utility_caption(295,footer);font_settings_=saved;
}
Screen::RenderKey Screen::key(const Snapshot& m,bool keyboard,const Ui& ui,const Services* services,BatteryStatus battery) const {
    RenderKey out;
    u8 settings[SETTINGS_PAGE_BYTES];encode_settings(ui.settings(),0,settings);out.data(settings,sizeof(settings));
    out.number((u32)battery.percent);out.number(battery.available);out.number(battery.power_status);
    out.number(fonts::revision());out.number(keyboard);
    const auto mode=utility_mode(ui,services);out.number((u32)mode);
    if(mode!=utility::Mode::NONE) {
        out.animation_at=out.used;
        out.number(animation_.frame(mode));
        if(services && services->usb_disk()) out.text(services->status());
        return out;
    }
    out.number(files::revision());
    out.number((u32)ui.page());out.number((u32)ui.view());out.number(ui.offset());out.number(ui.selected());
    const bool active=services && services->active();out.number(active);
    if(active) {
        if(services->browser_display()) {
            out.number(services->display_revision());out.number(services->browser_actions());
            out.number((u32)services->browser_mode());out.number(services->browser_selection());
            out.number(services->browser_action_selection());out.number(services->browser_has_parent());
            out.number(services->browser_offset());out.number(services->browser_more());out.number(services->browser_filtered());
            char title[64];services->browser_title(title);out.text(title);
            if(services->browser_actions()) for(unsigned row=0;row<services->selection_menu_rows();++row) {
                char value[Services::COLS+1];services->row(row,value);out.text(value);
            } else for(unsigned row=0;row<services->browser_count();++row) {
                char value[64];services->browser_label(row,value);out.text(value);out.number(services->browser_directory(row));
            }
            return out;
        }
        char title[64];services->heading(title);out.text(title);out.text(services->footer());out.text(services->path());
        out.number(services->display_revision());out.number(services->console_revision());out.number(script::frame_revision());
        out.number(services->fixed_text());out.number(services->editor_cursor());
        out.number(services->cursor_row());out.number(services->cursor_column());
        for(unsigned row=0;!services->native_graphics() && row<Services::ROWS;++row) {
            char text[Services::COLS+1]{};services->row(row,text);out.text(text);
            u8 selected[5]{};
            for(unsigned x=0;x<Services::COLS;++x) if(services->selected_text(row,x)) selected[x/8]|=(u8)(1U<<(x%8));
            out.data(selected,sizeof(selected));
        }
    } else if(ui.page()==Page::CALCULATOR) {
        out.number(m61_text::display_owned());
        if(m61_text::display_owned()) { out.number(script::frame_revision());return out; }
        out.text(m.indicator);out.text(m.face_indicator);out.text(m.last_key);
        for(const auto& value:m.stack_values) out.text(value);
        out.data(m.segments,sizeof(m.segments));out.number(m.segmented);out.number(m.angle);out.number(m.ip);
        out.number(m.running);out.number(m.programming);out.number(core_61::program_steps());
        if(ui.view()==View::STACK) { char text[INDICATOR_STRING_LENGTH];read_stack_register(X,text,nullptr);out.text(text);read_stack_register(X1,text,nullptr);out.text(text); }
        if(ui.view()==View::REGISTERS) for(unsigned n=0;n<Ui::VISIBLE_REGISTERS && ui.offset()+n<Ui::REGISTER_COUNT;++n) {
            char text[INDICATOR_STRING_LENGTH];MK61Emu_ReadRegister(ui.offset()+n,text,nullptr);out.text(text);
        }
        if(ui.view()==View::PROGRAM) for(unsigned n=0;n<6 && ui.offset()+n<core_61::program_steps();++n)
            out.number(core_61::get_code(core_61::get_ring_address(ui.offset()+n)));
        out.number(clock::configured());
        if(manual_clock_visible(m)) {
            const auto date=clock::get();out.number(date.hour*60+date.minute);
        }
        out.text(ui.footer());
    } else {
        out.text(ui.title());out.text(ui.footer());out.number(ui.count());
        const unsigned first=menu_model::firstVisible(ui.selected(),ui.count(),8);
        for(unsigned row=0;row<8;++row) { char text[64]{};ui.row(first+row,text);out.text(text); }
    }
    return out;
}
bool Screen::render(const Snapshot& model,bool keyboard,const Ui* ui,const Services* services,BatteryStatus battery) {
    if(services && services->display_deferred()) { ++skipped_;return false; }
    static const Ui defaults;if(!ui) ui=&defaults;
    const auto next=key(model,keyboard,*ui,services,battery);
    if(key_valid_ && key_.same(next)) { ++skipped_;return false; }
    const auto mode=utility_mode(*ui,services);
    const unsigned phase=animation_.frame(mode);
    const bool partial=key_valid_ && key_.same_scene(next) && utility::redraw(pixels_,mode,phase);
    if(partial) { utility_theme(mode,phase);++partial_renders_; }
    else paint(model,keyboard,ui,services,battery);
    // Rendering a custom console/graph can publish its completed canvas.
    // Remember that resulting generation, avoiding a second idle redraw.
    key_=partial?next:key(model,keyboard,*ui,services,battery);key_valid_=!key_.overflow;
    present_pending_=true;++renders_;return true;
}
void Screen::paint(const Snapshot& model, bool keyboard_online, const Ui* ui, const Services* services, BatteryStatus battery) {
    // CLS begins a BASIC/FOCAL frame. Keep the previous complete picture while
    // the VM builds its replacement; input, WAIT and module completion publish it.
    if(services && services->display_deferred()) return;
    diagnostics::Scope measure(diagnostics::Point::DISPLAY);
    static const Ui default_ui;
    if(!ui) ui = &default_ui;
    font_settings_=&ui->settings();battery_=battery;scroll_region_={};theme_.reset();
    const bool service_active=services && services->active();
    if(service_active && services->browser_display()) {browser(*services);return;}
    const u8* graphics=service_active?services->graphics():nullptr;
    const u8* native=graphics?services->native_graphics():nullptr;
    if(native && !services->graphical_document()) {
        if(const auto* app_theme=NativeDisplay::published_theme()) theme_=*app_theme;
        else theme_.reset(lcd::Ink::MONO);
        scroll_region_={0,HEIGHT};native_bitmap(native);return;
    }
    if(!service_active && ui->page()==Page::CALCULATOR && m61_text::display_owned()) {
        if(const auto frame=script::native_frame()) {
            if(const auto* app_theme=NativeDisplay::published_theme()) theme_=*app_theme;
            else theme_.reset(lcd::Ink::MONO);
            scroll_region_={0,HEIGHT};native_bitmap(frame);return;
        }
    }
    native_valid_=false;
    std::memset(pixels_, 0, sizeof(pixels_));
    const auto mode=utility_mode(*ui,services);
    if(mode!=utility::Mode::NONE) {utility_page(mode,animation_.frame(mode),*ui,services);return;}
    theme_.add(0,0,WIDTH,32,lcd::Ink::WHITE);
    theme_.add(0,32,WIDTH,1,lcd::Ink::LINE);
    char heading[64];
    if(services && services->active()) services->heading(heading);
    else std::snprintf(heading, sizeof(heading), "%s", ui->title());
    const bool clock_visible=!service_active && ui->page()==Page::CALCULATOR && manual_clock_visible(model);
    const unsigned title_right=clock_visible?(battery_.available?220:254):(battery_.available?278:WIDTH-8);
    text(10,9,heading,16,title_right);
    battery_icon(battery_,[this](unsigned x,unsigned y){set_pixel(x,y);});
    if(!keyboard_online) text(190, 10, "KBD?", 12);
    line(32);
    if(services && services->active()) {
        const unsigned menu_rows=services->selection_menu_rows();
        const auto metrics=fonts::info(ui->settings());
        const unsigned measured_pitch=metrics.height+metrics.line_gap+8;
        const unsigned menu_pitch=measured_pitch>27?measured_pitch:27;
        unsigned first=0,rows=menu_rows?menu_rows:Services::ROWS,top=menu_rows?49:42;
        if(graphics) {
            if(native) {
                if(services->graphical_document()) {
                    theme_.add(0,40,WIDTH,240,lcd::Ink::MONO);
                    scroll_region_={40,240};bitmap(native,320,240,0,40);
                    line(282);text(8,297,services->footer(),12);
                } else {
                    std::memset(pixels_,0,sizeof(pixels_));
                    bitmap(native,320,320);
                }
                return;
            }
            // Legacy APP bitmaps have explicit 192x64 geometry: 1:1 centred.
            theme_.add(64,96,192,64,lcd::Ink::MONO);
            bitmap(graphics,192,64,64,96);
            line(282);text(8,297,services->footer(),12);return;
        }
        if(services->fixed_text()) scroll_region_={42,238};
        for(unsigned row = 0; row < rows; ++row) {
            char value[Services::COLS + 1]; services->row(first + row, value);
            if(!services->fixed_text()) {
                const unsigned y=top+row*(menu_rows?menu_pitch:17);
                const bool selected=menu_rows && value[0]=='>';
                if(selected) {fill_rect(8,y-2,304,25);theme_.add(8,y-2,304,25,lcd::Ink::OCHRE);}
                text(10,y,value,ui->settings().ui_font_size,WIDTH-8,selected);continue;
            }
            auto font=ui->settings();font.ui_font_family=1;font.ui_font_size=16;
            unsigned x=8;
            for(unsigned column=0;value[column];++column) {
                mk61_service_ui_glyph glyph{};if(!fonts::glyph(font,mk8::codepoint((u8)value[column]),glyph)) continue;
                if(x+glyph.advance>312) break;
                const unsigned y=top+row*17;
                const bool inverse=services->selected_text(first+row,column);
                if(inverse) for(unsigned dy=0;dy<17;++dy) for(unsigned dx=0;dx<glyph.advance;++dx) set_pixel(x+dx,y+dy);
                for(unsigned dy=0;dy<glyph.height;++dy) for(unsigned dx=0;dx<glyph.width;++dx) {
                    const int py=(int)y+fonts::info(font).ascent-glyph.bearing_y+dy;
                    if(py<0 || py>=320) continue;
                    if(glyph.pixels[dy*((glyph.width+7)/8)+dx/8]&(0x80U>>(dx&7))) {
                        const unsigned px=x+glyph.bearing_x+dx;
                        if(inverse) pixels_[py*STRIDE+px/8]&=(u8)~(0x80U>>(px&7));else set_pixel(px,py);
                    }
                }
                x+=glyph.advance;
            }
        }
        if(services->editor_cursor()) {
            char value[Services::COLS+1];services->row(services->cursor_row(),value);
            Settings font{};font.ui_font_family=1;font.ui_font_size=16;
            const unsigned x=8+fonts::text_width(font,value,services->cursor_column()),y=top+services->cursor_row()*17+15;
            for(unsigned n=0;n<7;++n) set_pixel(x+n,y);
        }
        line(282); text(8, 297, services->footer(), 12);
        return;
    }
    if(ui->page() == Page::CALCULATOR) {
        if(m61_text::display_owned()) {
            // M61 owns every pixel between BASIC parts, including blank ones.
            theme_.reset(lcd::Ink::MONO);
            std::memset(pixels_,0,sizeof(pixels_));
            if(const auto native=script::native_frame()) bitmap(native,320,320);
            else bitmap(script::frame(),192,64,64,96);
        } else calculator(model,*ui);
        return;
    }
    const unsigned rows = 8;
    const unsigned first = menu_model::firstVisible(ui->selected(), ui->count(), rows);
    for(unsigned row = 0; row < rows; ++row) {
        const unsigned index = first + row;
        char label[64];
        ui->row(index, label);
        if((ui->page() == Page::INFO || ui->page() == Page::HARDWARE) && row < 6) {
            const char* info[] = {"MK61S / PicoCalc", "Pico H / RP2040 / 125 MHz", "ST7365P / RGB565 / 320x320",
                "Shared MK61 core + compact math", "Pico SDK / soft float", "Micro-USB: CDC + SD disk + UF2"};
            if(row==0) std::snprintf(label,sizeof(label),"%s %s",info[row],VERSION);
            else std::snprintf(label, sizeof(label), "%s", info[row]);
        }
        const unsigned y=49+row*27;
        const bool selected=index==ui->selected() && ui->count() && ui->page()!=Page::INFO && ui->page()!=Page::HARDWARE;
        if(selected) {
            fill_rect(8,y-2,304,25);theme_.add(8,y-2,304,25,lcd::Ink::OCHRE);
            text(10,y,">",ui->settings().ui_font_size,WIDTH-8,true);
        }
        text(28,y,label,ui->settings().ui_font_size,WIDTH-8,selected);
    }
    theme_.add(0,280,WIDTH,1,lcd::Ink::LINE);
    line(280);
    text(10, 295, ui->footer(), 12);
}
void Screen::browser(const Services& services) {
    native_valid_=false;scroll_region_={};
    draw_browser(pixels_,sizeof(pixels_),explorer_view::Packing::ROW_MSB,WIDTH,HEIGHT,services);
    theme_.add(0,0,WIDTH,31,lcd::Ink::WHITE);
    theme_.add(0,31,WIDTH,1,lcd::Ink::LINE);
    theme_.add(0,299,WIDTH,1,lcd::Ink::LINE);
    if(!services.browser_actions() && services.browser_mode()==explorer_view::Mode::ICONS) {
        // One band per row colors the icons without spending a separate
        // region on every file. Labels sit outside these bands.
        for(unsigned row=0;row<3 && row*3<services.browser_count();++row)
            theme_.add(0,43+row*86+9,WIDTH,32,lcd::Ink::OCHRE);
        const unsigned slot=services.browser_selection();
        if(slot<services.browser_count() && slot<Services::BROWSER_PAGE_SIZE)
            theme_.add(10+(slot%3)*100,43+(slot/3)*86+48,100,18,lcd::Ink::OCHRE);
    } else {
        const unsigned slot=services.browser_actions()?services.browser_action_selection():services.browser_selection();
        if(slot<Services::BROWSER_PAGE_SIZE) theme_.add(10,48+slot*29,300,18,lcd::Ink::OCHRE);
    }
}
} // namespace picocalc
