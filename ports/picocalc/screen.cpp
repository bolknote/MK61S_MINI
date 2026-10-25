#include "screen.hpp"
#include "canvas.hpp"
#include "display_symbols.hpp"
#include "ui_font.hpp"
#include "mk8_codec.hpp"
#include "mk8_literal.hpp"
#include "menu_model.hpp"
#include "services.hpp"
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
} // namespace
void Screen::logical_frame(const Ui& ui,const Services& services,u8 out[1536]) const {
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
void Screen::text(unsigned x, unsigned y, const char* value, unsigned height, unsigned right) {
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
            if(px >= 0 && (unsigned)px<right && py >= 0 && (glyph.pixels[offset] & (0x80U>>(gx%8U)))) set_pixel(px, py);
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
void Screen::calculator(const Snapshot& model, const Ui& ui) {
    face_grid_.reset(2);
    char status[40];
    const bool russian=ui.settings().russian;
    const char* mode = model.running ? (russian?M8("СЧЁТ"):"RUN") :
        model.programming ? (russian?M8("ПРГ"):"PRG") : (russian?M8("АВТ"):"AUTO");
    // Use the original MK-61 switch names: Г = degrees, Р = radians, ГРД = gradians.
    const char* angle = model.angle == DEGREE ? (russian?M8("Г"):"DEG") :
        model.angle == RADIAN ? (russian?M8("Р"):"RAD") : (russian?M8("ГРД"):"GRD");
    const char* last_key=key_label(model.last_key,russian);
    std::snprintf(status, sizeof(status), "%-5.5s %-3.3s %-6.6s", mode, angle, last_key);
    for(const char* p = status; *p; ++p) face_grid_.writeCodepoint(mk8::codepoint((u8)*p));
    face_grid_.setCursor(0, 1);
    for(const char* p = model.face_indicator; *p; ++p) {
        const u8 token = (u8)*p;
        face_grid_.writeCodepoint(token == ',' ? '.' : token);
    }
    calculator_face::setFont((calculator_face::Font)ui.settings().calculator_font);
    calculator_face::setSegmentFrame(model.segmented ? model.segments : nullptr);
    calculator_face::renderFrame(face_grid_, face_);
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
        for(unsigned col=0;col<face_grid_.cols();++col) {
            const u16 token=face_grid_.cell(col,1);
            if(token=='.') { if(slot) digit(slot-1,128,0); }
            else if(slot<12) { digit(slot++,calculator_face::sourceSegments(token),token); }
        }
    }
    status_field(8,96,mode);
    status_field(112,96,angle);
    status_field(216,96,last_key);
    if(model.idle && !model.running && !model.programming && clock::configured()) {
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
    // The large face is the IK1302 display latch (X2), not the stack X.
    text(10,72,"X2",16);
    const unsigned font_size = ui.settings().ui_font_size;
    line(147);
    if(ui.view() == View::STACK) {
        auto font=ui.settings();if(font.ui_font_family==1) font.ui_font_size=16;
        const unsigned value_left=18+fonts::text_width(font,"X1",2)+8;
        static constexpr const char* labels[]={"X","Y","Z","T","X1"};
        for(unsigned i = 0; i < 5; ++i) {
            char raw[INDICATOR_STRING_LENGTH];
            const char* number = i==0 ? read_stack_register(X,raw,nullptr) :
                i<4 ? model.stack_values[i-1] : read_stack_register(X1,raw,nullptr);
            const unsigned y=154+i*24;
            text(18,y,labels[i],16,value_left-4);
            text(value_left,y,number,16);
        }
    } else if(ui.view() == View::REGISTERS) {
        unsigned label_width=0;
        for(unsigned index=0;index<15;++index) {
            char label[4];std::snprintf(label,sizeof(label),"R%X",index);
            const unsigned width=fonts::text_width(ui.settings(),label,2);
            if(width>label_width) label_width=width;
        }
        const unsigned value_left=18+label_width+8;
        for(unsigned row = 0; row < 6; ++row) {
            const unsigned index = ui.offset() + row;
            char raw[INDICATOR_STRING_LENGTH],label[4];
            if(index >= 15) break;
            MK61Emu_ReadRegister((int)index, raw, nullptr);
            std::snprintf(label,sizeof(label),"R%X",index);
            const unsigned y=154+row*20;
            text(18,y,label,font_size,value_left-4);
            text(value_left,y,raw,font_size);
        }
    } else if(ui.view() == View::PROGRAM) {
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
void Screen::render(const Snapshot& model, bool keyboard_online, const Ui* ui, const Services* services, BatteryStatus battery) {
    // CLS begins a BASIC/FOCAL frame. Keep the previous complete picture while
    // the VM builds its replacement; input, WAIT and module completion publish it.
    if(services && services->display_deferred()) return;
    diagnostics::Scope measure(diagnostics::Point::DISPLAY);
    static const Ui default_ui;
    if(!ui) ui = &default_ui;
    font_settings_=&ui->settings();battery_=battery;scroll_region_={};
    const bool service_active=services && services->active();
    const u8* graphics=service_active?services->graphics():nullptr;
    const u8* native=graphics?services->native_graphics():nullptr;
    if(native && !services->graphical_document()) { scroll_region_={0,HEIGHT};native_bitmap(native);return; }
    if(!service_active && ui->page()==Page::CALCULATOR && m61_text::display_owned()) {
        if(const auto frame=script::native_frame()) { scroll_region_={0,HEIGHT};native_bitmap(frame);return; }
    }
    native_valid_=false;
    std::memset(pixels_, 0, sizeof(pixels_));
    char heading[64];
    if(services && services->active()) services->heading(heading);
    else std::snprintf(heading, sizeof(heading), "%s", ui->title());
    const bool clock_visible=!service_active && ui->page()==Page::CALCULATOR && model.idle && !model.running && !model.programming && clock::configured();
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
                    scroll_region_={40,240};bitmap(native,320,240,0,40);
                    line(282);text(8,297,services->footer(),12);
                } else {
                    std::memset(pixels_,0,sizeof(pixels_));
                    bitmap(native,320,320);
                }
                return;
            }
            // Legacy APP bitmaps have explicit 192x64 geometry: 1:1 centred.
            bitmap(graphics,192,64,64,96);
            line(282);text(8,297,services->footer(),12);return;
        }
        if(services->fixed_text()) scroll_region_={42,238};
        for(unsigned row = 0; row < rows; ++row) {
            char value[Services::COLS + 1]; services->row(first + row, value);
            if(!services->fixed_text()) { text(10, top + row * (menu_rows?menu_pitch:17), value, ui->settings().ui_font_size); continue; }
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
        if(index == ui->selected() && ui->count() && ui->page() != Page::INFO && ui->page() != Page::HARDWARE)
            text(10, 49 + row * 27, ">", ui->settings().ui_font_size);
        text(28, 49 + row * 27, label, ui->settings().ui_font_size);
    }
    line(280);
    text(10, 295, ui->footer(), 12);
}
} // namespace picocalc
