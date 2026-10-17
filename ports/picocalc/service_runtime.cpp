#include "services.hpp"
#include "mk61_ref.hpp"
#include "mk_math.hpp"
#include "mk8_codec.hpp"
#include "builtin_font.hpp"
#include "number_format.hpp"
#include "basic_graphics_client.hpp"
#include "loadable_app_api.h"
#include "script.hpp"
#include "m61_text.hpp"
#include "cross_hal.h"
#include "markdown_document.hpp"
#include "markdown.hpp"
#include <memory>
#include "wbmp.hpp"
#include "language_resources.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#if defined(PICO_ON_DEVICE)
#include "pico/rand.h"
#endif

namespace { picocalc::Services* graphics_owner = nullptr; }
namespace basic_graphics {
Result dispatch(Request& request) {
    return graphics_owner ? graphics_owner->graph_request(request) : Result::UNAVAILABLE;
}
u8 native_text_rows() { return (u8)picocalc::script::rows(); }
int native_text_flow(const char* text,u16 length,u8 first,u8 maximum) {
    return picocalc::script::flow_text(text,length,first,maximum,true,true);
}
}
namespace picocalc {
namespace {
bool cancelled(u8 code) { return code == 0x1B || code == 0xB1; }
u32 random_word() {
#if defined(PICO_ON_DEVICE)
    return get_rand_32();
#else
    static u32 word = 0x13579BDF; word ^= word << 13; word ^= word >> 17; return word ^= word << 5;
#endif
}
int logical_key(u8 code) {
    if(code >= '0' && code <= '9') return MK61_APP_KEY_DIGIT_0 + code - '0';
    switch(code) {
        case '.': case ',': return MK61_APP_KEY_DECIMAL;
        case '+': return MK61_APP_KEY_ADD; case '-': return MK61_APP_KEY_SUBTRACT;
        case '*': return MK61_APP_KEY_MULTIPLY; case '/': return MK61_APP_KEY_DIVIDE;
        case 0xB4: return MK61_APP_KEY_LEFT; case 0xB7: return MK61_APP_KEY_RIGHT;
        case 0xB5: return MK61_APP_KEY_BACKWARD; case 0xB6: return MK61_APP_KEY_FORWARD;
        case '\r': case '\n': return MK61_APP_KEY_OK;
        case 8: return MK61_APP_KEY_CLEAR;
        default: break;
    }
    const auto key=picocalc::map_key(code);
    if(key.angle!=NONE) return keyboard_layout::logical_key(keyboard_layout::ACTIVE,
        key.angle==DEGREE?KEY_DEGREE:key.angle==RADIAN?KEY_RADIAN:KEY_GRADE);
    if(key.valid()) for(unsigned i=0;i<40;++i)
        if(KeyPairs[i].x==key.x && KeyPairs[i].y==key.y) return keyboard_layout::logical_key(keyboard_layout::ACTIVE,(i32)i);
    return MK61_APP_KEY_RAW_BASE+code;
}
}
Services::Services() : graph_({this,
    [](void*, u16& width, u16& height) { width = 192; height = 64; },
    [](void* context) { ((Services*)context)->graph_visible_ = true; return true; },
    [](void* context) { ((Services*)context)->graph_visible_ = false; },
    [](void* context, const u8*, size_t) { ((Services*)context)->graph_visible_ = true; return true; },
    &Services::graph_capture, [](u16 cp) -> const u8* {
        static u8 rows[8]; return script::font_rows(cp,rows) || builtin_font::copyRows5x8(cp, rows) ? rows : nullptr;
    }, nullptr,
    [](void*, size_t count) { return std::malloc(count); },
    [](void*, void* memory) { std::free(memory); }}) {
    graphics_owner = this;
}
basic_graphics::Result Services::graph_request(basic_graphics::Request& request) {
    const auto result=graph_.apply(request);
    if(runtime_[0]=='A' && graph_.active()) { script::show_frame(graph_.frame());runtime_graphics_=false; }
    return result;
}
bool Services::graph_capture(void* raw, u8* frame, size_t bytes, u8 first, u8 count) {
    if(bytes != 1536) return false;
    auto& self = *(Services*)raw;
    const unsigned text_first=self.first_console_row(script::rows());
    script::show_lines(self.console_[text_first],sizeof(self.console_[0]),self.rows()-text_first,
        self.console_col_,self.console_row_-text_first);
    const unsigned end = first + count < 8 ? first + count : 8;
    for(unsigned row=first;row<end;++row) std::memcpy(frame+row*192,script::frame()+row*192,192);
    return true;
}
void Services::clear_console() {
    std::memset(console_, 0, sizeof(console_)); console_row_ = console_col_ = 0; console_scroll_=false;
}
void Services::put(char ch) {
    if(ch == '\r') return;
    const auto scroll=[&] {
        std::memmove(console_,console_+1,(rows()-1)*sizeof(console_[0]));
        console_row_=rows()-1;console_col_=0;std::memset(console_[console_row_],0,sizeof(console_[0]));
    };
    // Retain a completely printed last row. Scroll only when the next byte
    // needs a new line, so a nine-line FMK screen keeps its heading visible.
    if(console_scroll_) {
        scroll();
        if(ch=='\n') return;
        console_scroll_=false;
    }
    if(ch == '\n' || console_col_ == columns()) {
        console_col_ = 0;
        if(console_row_+1>=rows()) {if(ch=='\n') console_scroll_=true;else scroll();}
        else ++console_row_;
        if(ch == '\n') return;
    }
    console_[console_row_][console_col_++] = ch; console_[console_row_][console_col_] = 0;
}
void Services::append(const char* text, unsigned length) {
    for(unsigned i = 0; i < length; ++i) put(text[i]);
    if(serial_output_ && length) std::printf("%.*s", (int)length, text);
}
bool Services::service() {
    if(stopped_) return false;
    u8 key = 0;
    if(pump_ && pump_(pump_context_, key)) {
        if(cancelled(key)) { stopped_ = true; return false; }
        if(deferred_count_ < sizeof(deferred_keys_)) {
            deferred_keys_[(deferred_read_ + deferred_count_) % sizeof(deferred_keys_)] = key; ++deferred_count_;
        }
    }
    return true;
}
bool Services::wait_key(u8& key) {
    if(deferred_count_) {
        key = deferred_keys_[deferred_read_]; deferred_read_ = (deferred_read_ + 1) % sizeof(deferred_keys_); --deferred_count_; return true;
    }
    if(!pump_) return false;
    waiting_ = true;
    while(!stopped_) {
        if(pump_(pump_context_, key)) {
            waiting_ = false;
            if(cancelled(key)) { stopped_ = true; return false; }
            return true;
        }
    }
    waiting_ = false; return false;
}
double Services::math(language_vm::Function function, double a, double b) {
    using language_vm::Function;
    constexpr double pi = 3.14159265358979323846264338327950288;
    const double unit = language_ == language_vm::Language::FOCAL || MK61Emu_GetAngleUnit() == RADIAN ? 1 :
        MK61Emu_GetAngleUnit() == GRADE ? pi / 200 : pi / 180;
    switch(function) {
        case Function::SIN: return mk_math::sin(a * unit);
        case Function::COS: return mk_math::cos(a * unit);
        case Function::TAN: return mk_math::tan(a * unit);
        case Function::ASIN: return mk_math::asin(a) / unit;
        case Function::ACOS: return mk_math::acos(a) / unit;
        case Function::ATAN: return mk_math::atan(a) / unit;
        case Function::LN: return mk_math::ln(a);
        case Function::LOG10: return mk_math::log10(a);
        case Function::EXP: return mk_math::exp(a);
        case Function::SQRT: return mk_math::sqrt(a);
        case Function::ABS: return mk_math::fabs(a);
        case Function::INT: return mk_math::trunc(a);
        case Function::FRAC: return a - mk_math::trunc(a);
        case Function::ROUND: return a < 0 ? -mk_math::floor(-a + .5) : mk_math::floor(a + .5);
        case Function::SGN: return (a > 0) - (a < 0);
        default: return mk_math::pow(a, b); // Wire function 255: exponentiation.
    }
}
language_vm::Services Services::vm_services() {
    return {this,
        [](void* p) { return ((Services*)p)->service(); },
        [](void* p, language_vm::Function f, double a, double b) { return ((Services*)p)->math(f, a, b); },
        [](void*) { return (double)random_word() / 4294967296.0; },
        [](void* p, language_vm::Function f) {
            const auto& self=*(Services*)p;
            return f == language_vm::Function::SIZE ? 385.0 : f == language_vm::Function::COLS ? (double)self.columns() :
                f == language_vm::Function::ROWS ? (double)self.rows() : f == language_vm::Function::GW ? 192.0 : 64.0;
        },
        [](void*, bool write, u8 index, double& value) {
            const mk61_ref::Ref ref{index < 4 ? (mk61_ref::Kind)index : mk61_ref::Kind::R, (u8)(index < 4 ? 0 : index - 4)};
            return write ? mk61_ref::write(ref, value) : mk61_ref::read(ref, value);
        },
        [](void* p, language_vm::Event e, const char* text, u16 length, double& value) {
            return ((Services*)p)->event(e, text, length, value);
        }, false, true};
}
bool Services::flush_print(bool newline) {
    if(position_.positioned) return basic_graphics::flush_at(position_, print_, print_cursor_, false) == basic_graphics::Result::OK;
    append(print_, (unsigned)std::strlen(print_)); print_[0] = 0; print_cursor_ = 0;
    if(newline) append("\n", 1);
    return true;
}
bool Services::read_number(const char* text, u16 length, double& value) {
    flush_print(false); append(text, length);
    char input[128] = {}; unsigned used = 0;
    for(;;) {
        u8 key;
        if(!wait_key(key)) return false;
        if(key == '\r' || key == '\n') {
            append("\n", 1);
            u8 image[1024];
            const auto compiled = language_vm::compile_expression(language_, input, (u16)used, image, sizeof(image));
            language_vm::View view;
            if(compiled.error == language_vm::Error::NONE && language_vm::inspect(image, compiled.size, view) == language_vm::Error::NONE) {
                language_vm::State state{}; language_vm::Value stack[language_vm::MAX_STACK];
                state.variables = active_variables(); state.array = active_array(); state.array_count = 385; state.stack = stack; state.stack_capacity = language_vm::MAX_STACK;
                const auto result = language_vm::run(view, state, vm_services(), 100000);
                if(result.error == language_vm::Error::NONE && state.sp == 1) { value = stack[0].number(); return true; }
            }
            append("Invalid number, retry: ", 23); used = 0; input[0] = 0;
        } else if(key == 8 || key == 0x7F || key == 0xD4) {
            if(used) { input[--used] = 0; if(console_col_) console_[console_row_][--console_col_] = 0; }
        } else if(key >= 32 && key < 127 && used + 1 < sizeof(input)) {
            input[used++] = (char)key; input[used] = 0; put((char)key);
        }
    }
}
bool Services::event(language_vm::Event event, const char* text, u16 length, double& value) {
    using language_vm::Event;
    const auto read_resource=[](void* raw,u16 offset,u8* output,u16 count) {
        const auto& self=*(Services*)raw;
        if(offset>self.length_ || count>self.length_-offset || (count && !output)) return false;
        if(count) std::memcpy(output,self.source_+offset,count);
        return true;
    };
    auto add = [&](const char* bytes, unsigned count) {
        for(unsigned i = 0; i < count; ++i) {
            if(print_cursor_ + 1 == sizeof(print_) && !flush_print(false)) return false;
            print_[print_cursor_++] = bytes[i]; print_[print_cursor_] = 0;
        }
        return true;
    };
    switch(event) {
        case Event::PRINT_BEGIN: print_width_ = 0; precision_ = 10; position_ = {}; return true;
        case Event::TEXT: return add(text, length);
        case Event::RESOURCE_TEXT:
            return language_vm::resource_text((const u8*)text,read_resource,this,
                [](void* raw,const char* bytes,u16 count,bool) {
                    double unused=0;return ((Services*)raw)->event(Event::TEXT,bytes,count,unused);
                },this);
        case Event::RESOURCE_INPUT: {
            char prompt[96];
            return language_vm::resource_prompt((const u8*)text,prompt,read_resource,this) &&
                read_number(prompt,(u16)std::strlen(prompt),value);
        }
        case Event::NUMBER: {
            char number[32]; if(!number_format::general(value, precision_, number, sizeof(number))) return false;
            for(int i = print_width_ - (int)std::strlen(number); i > 0; --i) if(!add(" ", 1)) return false;
            return add(number, (unsigned)std::strlen(number));
        }
        case Event::FORMAT:
            if(value < 0 || value > 63 || mk_math::fabs(value - mk_math::floor(value + .5)) > 1e-7) return false;
            print_width_ = (int)(value + .5); return true;
        case Event::PRECISION: print_width_ = (int)value; precision_ = (u8)length; return true;
        case Event::PRINT_STATE: value = print_width_ * 16 + precision_; return true;
        case Event::SEPARATOR:
            if(length == 1) return add(" ", 1);
            if(length == 2) { do { if(!add(" ", 1)) return false; } while(print_cursor_ % 8); }
            return true;
        case Event::FLUSH: return flush_print(true);
        case Event::PRINT_END:
            if(position_.positioned) return basic_graphics::flush_at(position_, print_, print_cursor_) == basic_graphics::Result::OK;
            return length ? true : flush_print(true);
        case Event::READ_INPUT: return read_number(text, length, value);
        case Event::WAIT: { flush_print(false); u8 key; return wait_key(key); }
        case Event::READ_KEY: { u8 key; if(!wait_key(key)) return false; value = logical_key(key); return true; }
        case Event::CLEAR: clear_console(); return true;
        case Event::FINISH: {
            if(print_[0] && !flush_print(false)) return false;
            basic_graphics::Request request{}; request.operation = basic_graphics::Operation::SHOW;
            return graph_.apply(request) == basic_graphics::Result::OK;
        }
        case Event::GRAPHICS: {
            if(!text || length != sizeof(basic_graphics::Request)) return false;
            auto request = *(const basic_graphics::Request*)text;
            const auto result = graph_.apply(request); value = request.value;
            if(result != basic_graphics::Result::OK) last_error_ = basic_graphics::error(result);
            return result == basic_graphics::Result::OK;
        }
        case Event::PRINT_AT: return basic_graphics::print_at(position_, print_, print_cursor_, *(const basic_graphics::Request*)text) == basic_graphics::Result::OK;
        case Event::PRINT_PUSH: return basic_graphics::push_print(position_, print_, print_cursor_) == basic_graphics::Result::OK;
        case Event::PRINT_POP: return basic_graphics::pop_print(position_, print_, print_cursor_) == basic_graphics::Result::OK;
        case Event::TARGET_REF: return value != 19 || mk61_ref::register_available(15);
        case Event::TRACE: return true;
        default: return false;
    }
}
void Services::run_document() {
    if(calculator_ && (!calculator_->idle() || core_61::is_RUN())) { message("Stop MK61 before running source", ServicePage::EDITOR); return; }
    if(document_ == Document::TEXT) { message("Text file: use .bas, .foc or .m61 to run", ServicePage::EDITOR); return; }
    graph_.reset();
    if(!external_run_) clear_console();
    print_[0] = 0; print_cursor_ = 0; position_ = {};
    stopped_ = false; deferred_count_ = deferred_read_ = 0; last_error_ = language_vm::Error::NONE;
    page_ = ServicePage::CONSOLE; running_ = true; serial_output_ = true;
    if(document_ == Document::MK61) {
        const bool keep_editor=dirty_;
        script_editor_.valid=false;
        if(keep_editor) {
            std::snprintf(script_editor_.path,sizeof(script_editor_.path),"%s",path_);
            script_editor_.cursor=cursor_;script_editor_.top=top_;script_editor_.horizontal=horizontal_;
            script_editor_.parent=return_;
        }
        char name[files::PATH_SIZE];
        std::snprintf(name, sizeof(name), "%s", path_[0] ? path_ : "/untitled.m61");
        page_ = ServicePage::CLOSED; running_ = serial_output_ = false;
        calculator_requested_ = true;
        const bool ok = script::start_source(name, source_, length_,&script_editor_.id);
        script_editor_.valid=keep_editor && script_editor_.id!=program_store::INVALID_ID;
        last_error_ = ok ? language_vm::Error::NONE : language_vm::Error::SYNTAX;
        if(!ok && !active()) message("Cannot start M61 scenario", ServicePage::EDITOR);
        std::printf("M61_RESULT=%s ACTIVE=%u\n", ok ? "OK" : "ERROR", m61_text::active());
        return;
    }
    language_ = document_ == Document::FOCAL ? language_vm::Language::FOCAL : language_vm::Language::BASIC;
    // Page reads also keep the foreground device loop alive while a long
    // source is compiled. They never return a mutable pointer to the editor.
    language_vm::source::Reader source(language_vm::source::Input{this,
        [](void* raw, u16 offset, u8* out, u16 count) {
            auto& self = *(Services*)raw;
            if(!self.service() || offset > self.length_ || count > self.length_ - offset) return false;
            if(count && !out) return false;
            if(count) std::memcpy(out, self.source_ + offset, count);
            return true;
        }, length_});
    language_vm::ResourceSource resources{0, 0, language_vm::ResourceMode::EMBEDDED};
    auto compiled = language_vm::compile_source(language_, source, image_, sizeof(image_), core_61::expanded_program_is_on(), &resources);
    if(!stopped_ && compiled.error==language_vm::Error::FULL) {
        resources.mode=language_vm::ResourceMode::SOURCE;
        compiled=language_vm::compile_source(language_,source,image_,sizeof(image_),core_61::expanded_program_is_on(),&resources);
    }
    u32 line = compiled.line, steps = 0;
    last_error_ = compiled.error;
    if(stopped_) last_error_ = language_vm::Error::STOPPED;
    if(last_error_ == language_vm::Error::NONE) {
        language_vm::View view{};
        last_error_ = language_vm::inspect(image_, compiled.size, view);
        if(last_error_ == language_vm::Error::NONE) {
            state_ = {};
            state_.variables = active_variables(); state_.array = active_array(); state_.array_count = 385;
            state_.stack = stack_; state_.stack_capacity = language_vm::MAX_STACK;
            const auto result = language_vm::run(view, state_, vm_services());
            if(last_error_ == language_vm::Error::NONE) last_error_ = stopped_ ? language_vm::Error::STOPPED : result.error;
            line = result.line; steps = result.steps;
        }
    }
    running_ = false;
    std::snprintf(status_, sizeof(status_), "%s  line %lu  %lu steps", language_vm::error_name(last_error_), (unsigned long)line, (unsigned long)steps);
    if(!external_run_) { append("\n", 1); append(status_, (unsigned)std::strlen(status_)); append("\n", 1); }
    std::printf("VM_RESULT=%s LINE=%lu STEPS=%lu\n", language_vm::error_name(last_error_), (unsigned long)line, (unsigned long)steps);
    serial_output_ = false;
}
void Services::restore_script_editor() {
    if(!script_editor_.valid || m61_text::active()) return;
    program_store::Entry entry;u16 used=0;
    if(!program_store::entry_by_id(script_editor_.id,entry) || entry.data_len>=SOURCE_CAPACITY ||
        !program_store::read_range_id(script_editor_.id,0,(u8*)source_,entry.data_len,&used) || used!=entry.data_len) return;
    source_[used]=0;length_=used;document_=Document::MK61;dirty_=true;
    graph_.reset();graph_visible_=false;
    std::snprintf(path_,sizeof(path_),"%s",script_editor_.path);
    cursor_=script_editor_.cursor;top_=script_editor_.top;horizontal_=script_editor_.horizontal;return_=script_editor_.parent;
    script_editor_.valid=false;
    if(page_==ServicePage::CLOSED) page_=ServicePage::EDITOR;
    else if(page_==ServicePage::MESSAGE) message_parent_=ServicePage::EDITOR;
}
bool Services::export_program(const char* path) {
    if(!calculator_ || !calculator_->idle() || core_61::is_RUN()) { std::snprintf(status_, sizeof(status_), "Stop MK61 before saving its program"); return false; }
    char text[512]; unsigned at = 0;
    for(unsigned offset = 0; offset < core_61::program_steps(); offset += 24) {
        at += (unsigned)std::snprintf(text + at, sizeof(text) - at, "hin %04u ", offset);
        for(unsigned i = offset; i < offset + 24 && i < core_61::program_steps(); ++i)
            at += (unsigned)std::snprintf(text + at, sizeof(text) - at, "%02X", core_61::get_code(core_61::get_ring_address(i)));
        text[at++] = '\n';
    }
    return files::write_text(path, text, at);
}
u8 Services::run_external(const char* path) {
    const char* suffix=std::strrchr(path,'.');
    if(suffix) {
        char ext[8]{};unsigned i=0;
        for(;suffix[i] && i<7;++i) ext[i]=(char)(suffix[i]>='A' && suffix[i]<='Z'?suffix[i]+32:suffix[i]);
        if(!std::strcmp(ext,".app")) return run_native(path);
        if(!std::strcmp(ext,".md")) return view_markdown(path);
        if(!std::strcmp(ext,".sheet")) return run_handled(path,program_store::TYPE_MAGIC_SHEET);
        if(!std::strcmp(ext,".ch8") || !std::strcmp(ext,".c8")) return run_chip8(path);
    }
    if(!load_document(path)) return 2;
    if(document_ == Document::TEXT) {
        viewing_ = waiting_ = true;
        if(!pump_) { viewing_ = waiting_ = false; page_ = ServicePage::CLOSED; return 2; }
        for(;;) {
            u8 key=0;
            if(!pump_(pump_context_,key)) continue;
            if(key==0x1B || key==0xB1 || key=='\n' || key=='\r') break;
            if(key==0xB6 || key==0xD6) {
                while(top_<length_ && source_[top_++]!='\n') {}
            } else if(key==0xB5 || key==0xD5) {
                if(top_) --top_;
                while(top_ && source_[top_-1]!='\n') --top_;
            }
        }
        viewing_ = waiting_ = false; page_ = ServicePage::CLOSED; return 0;
    }
    if(document_ != Document::BASIC && document_ != Document::FOCAL) { page_ = ServicePage::CLOSED; return 2; }
    external_run_=true;
    run_document();
    external_run_=false;
    const u8 result=last_error_==language_vm::Error::NONE?0:last_error_==language_vm::Error::STOPPED?1:2;
    if(result==0) {
        if(graph_visible_) script::show_frame(graph_.frame());
        else {
            const unsigned first=first_console_row(script::rows());
            script::show_lines(console_[first],sizeof(console_[0]),rows()-first,console_col_,console_row_-first);
        }
    }
    page_ = ServicePage::CLOSED; return result;
}
unsigned Services::columns() const { return external_run_ || m61_text::active() || script::font_active()?script::columns():COLS; }
bool Services::selected_text(unsigned row,unsigned column) const {
    return markdown_ && markdown_->selected(row,column);
}
u8 Services::view_markdown(const char* path) {
    if(markdown_ || !pump_) return 2;
    std::unique_ptr<MarkdownView> document(new(std::nothrow) MarkdownView);
    if(!document || !document->open(path)) { message("Cannot open Markdown",ServicePage::BROWSER);return 2; }
    struct History { char path[files::PATH_SIZE];u16 top,selection; } history[8]{};
    unsigned depth=0;
    const ServicePage parent=m61_text::active()?ServicePage::CLOSED:ServicePage::BROWSER;
    markdown_=document.get();viewing_=waiting_=true;page_=ServicePage::EDITOR;
    for(;;) {
        std::snprintf(path_,sizeof(path_),"%s",document->path());
        u8 key=0;if(!pump_(pump_context_,key)) continue;
        if(key==0x1B || key==0xB1) {
            if(!depth) break;
            const auto& previous=history[--depth];
            if(!document->open(previous.path)) { depth=0;break; }
            document->top=previous.top;document->selection=previous.selection;
        } else if(key==0xB5 || key==0xB6) document->scroll(key==0xB5?-1:1);
        else if(key==0xB4 || key==0xB7 || key=='\t') document->select(key==0xB4?-1:1);
        else if(key=='\r' || key=='\n') {
            if(!document->links()) break;
            if(document->selection==0xFFFF) { document->select(1);continue; }
            char target[files::PATH_SIZE];
            if(depth==8 || !document->target(target)) { std::snprintf(status_,sizeof(status_),"Link unavailable");continue; }
            std::unique_ptr<MarkdownView> next(new(std::nothrow) MarkdownView);
            if(!next || !next->open(target)) continue;
            auto& saved=history[depth++];std::snprintf(saved.path,sizeof(saved.path),"%s",document->path());
            saved.top=document->top;saved.selection=document->selection;
            document=std::move(next);markdown_=document.get();status_[0]=0;
        }
    }
    markdown_=nullptr;viewing_=waiting_=false;page_=parent;
    if(parent==ServicePage::BROWSER) refresh();
    return 0;
}
unsigned Services::rows() const { return external_run_ || m61_text::active() || script::font_active()?script::rows():ROWS; }
bool Services::custom_console() const { return page_==ServicePage::CONSOLE && script::font_active() && !graph_visible_; }
const u8* Services::graphics() const {
    if(runtime_graphics_) return script::frame();
    if(image_viewing_) return script::frame();
    if(graph_visible_) return graph_.frame();
    if(!custom_console()) return nullptr;
    script::show_lines(console_[0],sizeof(console_[0]),rows(),console_col_,console_row_);return script::frame();
}
u8 Services::view_image(const char* path) {
    auto* bytes=(u8*)std::malloc(program_store::MAX_IMAGE1_SIZE);unsigned used=0;wbmp::Info info{};
    if(!bytes) return 2;
    if(!files::read(path,bytes,program_store::MAX_IMAGE1_SIZE,used) || wbmp::inspect(bytes,used,info)!=wbmp::Status::OK || !pump_) {std::free(bytes);return 2;}
    std::snprintf(path_,sizeof(path_),"%s",path);clear_console();page_=ServicePage::CONSOLE;running_=false;viewing_=image_viewing_=true;
    unsigned x=0,y=0;u8 frame[1536];
    for(;;) {
        if(wbmp::decode_viewport(bytes,used,info,x,y,192,64,wbmp::Layout::PAGE_MAJOR_LSB,frame,sizeof(frame))!=wbmp::Status::OK) break;
        script::show_frame(frame);
        u8 key=0;while(!pump_(pump_context_,key)) {}
        if(key==0x1B || key==0xB1 || key=='\n' || key=='\r') {std::free(bytes);viewing_=image_viewing_=false;page_=ServicePage::CLOSED;return 0;}
        if(key==0xB4) x=x>8?x-8:0;
        if(key==0xB7 && x+192<info.width) x+=8;
        if(key==0xB5) y=y>8?y-8:0;
        if(key==0xB6 && y+64<info.height) y+=8;
    }
    std::free(bytes);viewing_=image_viewing_=false;page_=ServicePage::CLOSED;return 2;
}
} // namespace picocalc
