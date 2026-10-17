#include "screen.hpp"
#include "ui_font.hpp"
#include "mk8_codec.hpp"
#include "mk8_literal.hpp"
#include "menu_model.hpp"
#include "services.hpp"
#include "builtin_font.hpp"
#include "m61_text.hpp"
#include "script.hpp"
#include <cstdio>
#include <cstring>

namespace picocalc {
void Screen::logical_frame(const Ui& ui,const Services& services,u8 out[1536]) const {
    if(services.active() && services.graphics()) { std::memcpy(out,services.graphics(),1536);return; }
    if(!services.active() && ui.page()==Page::CALCULATOR) {
        std::memcpy(out,m61_text::display_owned()?script::frame():face_,1536);return;
    }
    std::memset(out,0,1536);
    auto text=[&](unsigned row,const char* s,bool inverse) {
        for(unsigned x=0;x<32;++x) {
            u8 glyph[8]{};if(*s) builtin_font::copyRows5x8(mk8::codepoint((u8)*s++),glyph);
            for(unsigned y=0;y<8;++y) for(unsigned dx=0;dx<6;++dx)
                if((dx<5 && (glyph[y]&(1U<<(4-dx))))!=inverse) out[row*192+x*6+dx]|=(u8)(1U<<y);
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
        text(row+1,line,!(services.active() && services.fixed_text()) && first+row==selected);
    }
}
void Screen::set_pixel(unsigned x, unsigned y) {
    if(x < WIDTH && y < HEIGHT) pixels_[y * STRIDE + x / 8] |= (u8)(0x80U >> (x % 8));
}
void Screen::text(unsigned x, unsigned y, const char* value, unsigned height) {
    const ui_font::Face font{ui_font::Family::PIXEL,
        height == 16 ? ui_font::Size::PX16 : height == 12 ? ui_font::Size::PX12 : ui_font::Size::PX14};
    const unsigned baseline = y + ui_font::metrics(font).ascent;
    for(; *value && x < WIDTH - 8; ++value) {
        const auto glyph = ui_font::glyph(font, mk8::codepoint((u8)*value));
        for(u8 gy = 0; gy < glyph.height; ++gy) for(u8 gx = 0; gx < glyph.width; ++gx) {
            const int px = (int)x + glyph.bearing_x + gx;
            const int py = (int)baseline - glyph.bearing_y + gy;
            if(px >= 0 && py >= 0 && font_glyph::pixel(glyph, gx, gy)) set_pixel(px, py);
        }
        x += glyph.advance;
    }
}
void Screen::line(unsigned y) {
    for(unsigned x = 8; x < WIDTH - 8; ++x) set_pixel(x, y);
}
void Screen::calculator(const Snapshot& model, const Ui& ui) {
    face_grid_.reset(2);
    char status[40];
    const char* mode = model.running ? "RUN" : model.programming ? "PRG" : "AUTO";
    const char* angle = model.angle == DEGREE ? "DEG" : model.angle == RADIAN ? "RAD" : "GRD";
    std::snprintf(status, sizeof(status), "%-5.5s %-3.3s %-6.6s", mode, angle, model.last_key);
    for(const char* p = status; *p; ++p) face_grid_.writeCodepoint((u8)*p);
    face_grid_.setCursor(0, 1);
    for(const char* p = model.face_indicator; *p; ++p) {
        const u8 token = (u8)*p;
        face_grid_.writeCodepoint(token == ',' ? '.' : token);
    }
    calculator_face::setFont((calculator_face::Font)ui.settings().calculator_font);
    calculator_face::setSegmentFrame(model.segmented ? model.segments : nullptr);
    calculator_face::renderFrame(face_grid_, face_);
    calculator_face::setSegmentFrame(nullptr);
    for(unsigned y = 0; y < 107; ++y) for(unsigned x = 0; x < WIDTH; ++x) {
        const unsigned sx = x * 3 / 5, sy = y * 3 / 5;
        if(face_[(sy / 8) * calculator_face::WIDTH + sx] & (1U << (sy % 8))) set_pixel(x, y + 38);
    }
    const unsigned font_size = ui.settings().ui_font_size;
    line(147);
    if(ui.view() == View::STACK) {
        for(unsigned i = 0; i < 4; ++i) {
            char raw[INDICATOR_STRING_LENGTH];
            const char* number = i < 3 ? model.stack_values[i] : read_stack_register(X1, raw, nullptr);
            std::snprintf(status, sizeof(status), "%s  %s", i == 0 ? "Y" : i == 1 ? "Z" : i == 2 ? "T" : "X1", number);
            text(18, 158 + i * 24, status, 16);
        }
    } else if(ui.view() == View::REGISTERS) {
        for(unsigned row = 0; row < 6; ++row) {
            const unsigned index = ui.offset() + row;
            char raw[INDICATOR_STRING_LENGTH];
            if(index >= 15) break;
            MK61Emu_ReadRegister((int)index, raw, nullptr);
            std::snprintf(status, sizeof(status), "R%X   %s", index, raw);
            text(18, 154 + row * 20, status, font_size);
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
        const char* help[] = {"F1/F: F  F2/K: K  F3/R: S/P", "F4/G: GOTO  F5/C: CALL  B: RET",
            "E: EXP  N: +/-  X: X<>Y", "L: RECALL  S: STORE  Enter: B^",
            "F E: PRG   F N: AUTO", "D: DEG   A: RAD   T: GRAD"};
        for(unsigned row = 0; row < 6; ++row) text(10, 154 + row * 20, help[row], 12);
    }
    std::snprintf(status, sizeof(status), "IP %02X  %u %s", model.ip,
        (unsigned)core_61::program_steps(), ui.settings().russian ? M8("шагов") : "steps");
    text(10, 280, status, 12);
    text(10, 301, ui.footer(), 12);
}
void Screen::render(const Snapshot& model, bool keyboard_online, const Ui* ui, const Services* services) {
    static const Ui default_ui;
    if(!ui) ui = &default_ui;
    std::memset(pixels_, 0, sizeof(pixels_));
    char heading[64];
    if(services && services->active()) services->heading(heading);
    else std::snprintf(heading, sizeof(heading), "%s", ui->title());
    text(10, 9, heading, 16);
    if(!keyboard_online) text(242, 10, "KBD?", 12);
    line(32);
    if(services && services->active()) {
        const u8* graphics = services->graphics();
        unsigned first = 0, rows = Services::ROWS, top = 42;
        if(graphics) {
            for(unsigned y = 0; y < 107; ++y) for(unsigned x = 0; x < WIDTH; ++x) {
                const unsigned sx = x * 3 / 5, sy = y * 3 / 5;
                if(graphics[(sy / 8) * 192 + sx] & (1U << (sy % 8))) set_pixel(x, y + 38);
            }
            rows = 7; first = services->first_console_row(rows); top = 157;
        }
        if(services->custom_console()) {
            text(10,185,services->running()?"BASIC / FOCAL":"M61",14);
            line(282);text(8,297,services->footer(),12);return;
        }
        for(unsigned row = 0; row < rows; ++row) {
            char value[Services::COLS + 1]; services->row(first + row, value);
            if(!services->fixed_text()) { text(10, top + row * 17, value, ui->settings().ui_font_size); continue; }
            for(unsigned column = 0; value[column] && column < Services::COLS; ++column) {
                u8 glyph[8];
                if(builtin_font::copyRows5x8(mk8::codepoint((u8)value[column]), glyph))
                    for(unsigned y = 0; y < 16; ++y) for(unsigned x = 0; x < 7; ++x)
                    if(glyph[y / 2] & (1U << (4 - x * 5 / 7))) set_pixel(8 + column * 8 + x, top + row * 17 + y);
            }
        }
        if(services->editor_cursor()) {
            const unsigned x = 8 + services->cursor_column() * 8, y = top + services->cursor_row() * 17 + 15;
            for(unsigned n = 0; n < 6; ++n) set_pixel(x + n, y);
        }
        line(282); text(8, 297, services->footer(), 12);
        return;
    }
    if(ui->page() == Page::CALCULATOR) {
        if(m61_text::display_owned()) {
            const u8* frame=script::frame();
            for(unsigned y=0;y<107;++y) for(unsigned x=0;x<WIDTH;++x) {
                const unsigned sx=x*3/5,sy=y*3/5;
                if(frame[(sy/8)*192+sx] & (1U<<(sy%8))) set_pixel(x,y+50);
            }
            line(169);text(10,186,"M61 / trap / bind",14);
            text(10,213,m61_text::calculator_suspended()?"M61 WAIT":"M61 ACTIVE",14);
            text(10,247,"Enter: OK binding",12);text(10,278,"Esc: STOP M61   Tab: menu",12);
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
            const char* info[] = {"MK61S / PicoCalc 0.3", "Pico H / RP2040 / 125 MHz", "ST7365P / RGB565 / 320x320",
                "Shared MK61 core + compact math", "Pico SDK / soft float", "Micro-USB: CDC + SD disk + UF2"};
            std::snprintf(label, sizeof(label), "%s", info[row]);
        }
        if(index == ui->selected() && ui->count() && ui->page() != Page::INFO && ui->page() != Page::HARDWARE)
            text(10, 49 + row * 27, ">", ui->settings().ui_font_size);
        text(28, 49 + row * 27, label, ui->settings().ui_font_size);
    }
    line(280);
    text(10, 295, ui->footer(), 12);
}
} // namespace picocalc
