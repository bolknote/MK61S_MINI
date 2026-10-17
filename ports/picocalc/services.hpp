#ifndef MK61_PICOCALC_SERVICES_HPP
#define MK61_PICOCALC_SERVICES_HPP
#include "ui.hpp"
#include "storage.hpp"
#include "language_bytecode.hpp"
#include "basic_graphics.hpp"
#include "text_screen.hpp"

namespace picocalc {
enum class ServicePage : u8 { CLOSED, DEVELOPMENT, LANGUAGE, BROWSER, FILE_ACTIONS,
    EDITOR, CONSOLE, PROMPT, CONFIRM, MESSAGE, USB_DISK };
enum class Document : u8 { BASIC, FOCAL, MK61, TEXT };

// The same source compiler, VM, editor primitives and graphics rasterizer as
// STM32. Only the device loop, QWERTY input and FAT paths are board adapters.
class Services {
public:
    static constexpr unsigned COLS = 38, ROWS = 14, SOURCE_CAPACITY = 65535;
    using Pump = bool (*)(void*, u8&);
    Services();
    void set_pump(Pump callback, void* context) { pump_ = callback; pump_context_ = context; }
    bool active() const { return page_ != ServicePage::CLOSED; }
    void open(Action action, bool russian, Calculator& calculator);
    bool input(u8 code);
    void tick();
    const char* title() const;
    void heading(char out[64]) const;
    bool fixed_text() const { return page_ == ServicePage::EDITOR || page_ == ServicePage::CONSOLE || page_ == ServicePage::PROMPT; }
    unsigned first_console_row(unsigned visible) const { return console_row_ >= visible ? console_row_ + 1 - visible : 0; }
    const char* footer() const;
    const char* page_name() const;
    void row(unsigned index, char out[COLS + 1]) const;
    unsigned cursor_row() const;
    unsigned cursor_column() const;
    bool editor_cursor() const { return !viewing_ && (page_ == ServicePage::EDITOR || page_ == ServicePage::PROMPT); }
    const u8* graphics() const;
    bool custom_console() const;
    unsigned columns() const;
    unsigned rows() const;
    basic_graphics::Result graph_request(basic_graphics::Request& request);
    bool running() const { return running_; }
    unsigned source_size() const { return length_; }
    bool dirty() const { return dirty_; }
    const char* path() const { return path_; }
    const char* status() const { return status_; }
    language_vm::Error last_error() const { return last_error_; }
    // Device/host integration tests use the same public document operations.
    bool load_document(const char* path);
    bool save_document(const char* path);
    void new_document(Document kind);
    u8 run_external(const char* path);
    u8 view_image(const char* path);
    u8 run_chip8(const char* path);
    u8 run_native(const char* path, u16 file = 0xFFFF);
    u8 run_handled(const char* path, u16 magic);
    const char* runtime_name() const { return runtime_; }
    void show_script_error(const char* text) { message(text, ServicePage::CLOSED); }
    bool take_calculator_request() { const bool value=calculator_requested_;calculator_requested_=false;return value; }
private:
    friend class NativeHost;
    enum class Prompt : u8 { SAVE, RENAME, MKDIR, NEW_FILE, EXPORT, OPEN };
    enum class Confirm : u8 { DELETE_FILE, DISCARD, FORMAT, OVERWRITE };
    const char* tr(const char* en, const char* ru) const { return russian_ ? ru : en; }
    void message(const char* value, ServicePage parent);
    void browse(ServicePage parent);
    void refresh();
    bool selected_path(char out[files::PATH_SIZE]) const;
    void parent_directory();
    void prompt(Prompt op, ServicePage parent, const char* initial = "");
    void accept_prompt();
    void leave_editor();
    void normalize_view();
    void run_document();
    void restore_script_editor();
    bool service();
    bool wait_key(u8& code);
    bool event(language_vm::Event, const char*, u16, double&);
    bool read_number(const char*, u16, double&);
    language_vm::Services vm_services();
    language_vm::Value* active_variables() { return language_==language_vm::Language::FOCAL ? focal_variables_ : variables_; }
    language_vm::Value* active_array() { return language_==language_vm::Language::FOCAL ? focal_array_ : array_; }
    void append(const char*, unsigned);
    void put(char ch);
    void clear_console();
    bool flush_print(bool newline);
    double math(language_vm::Function, double, double);
    bool export_program(const char* path);
    static bool graph_capture(void*, u8*, size_t, u8, u8);

    ServicePage page_ = ServicePage::CLOSED, return_ = ServicePage::DEVELOPMENT;
    ServicePage browser_parent_ = ServicePage::DEVELOPMENT, prompt_parent_ = ServicePage::EDITOR;
    ServicePage message_parent_ = ServicePage::DEVELOPMENT, confirm_parent_ = ServicePage::EDITOR;
    Document document_ = Document::BASIC;
    Document tool_ = Document::BASIC;
    Prompt prompt_ = Prompt::SAVE;
    Confirm confirm_ = Confirm::DISCARD;
    Calculator* calculator_ = nullptr;
    bool russian_ = true, dirty_ = false, more_ = false, pending_run_ = false;
    bool browser_load_program_ = false;
    bool running_ = false, stopped_ = false, waiting_ = false, graph_visible_ = false;
    bool serial_output_ = false;
    bool viewing_ = false;
    bool image_viewing_ = false;
    bool calculator_requested_ = false;
    bool external_run_ = false;
    bool console_scroll_ = false;
    bool runtime_graphics_ = false;
    const char* runtime_ = "NONE";
    struct ScriptEditor {
        bool valid=false;
        u16 id=0,cursor=0,top=0,horizontal=0;
        ServicePage parent=ServicePage::BROWSER;
        char path[files::PATH_SIZE]{};
    } script_editor_;
    unsigned selection_ = 0, skip_ = 0, used_ = 0, console_row_ = 0, console_col_ = 0;
    u16 length_ = 0, cursor_ = 0, top_ = 0, horizontal_ = 0;
    u16 prompt_length_ = 0;
    char source_[SOURCE_CAPACITY] = {};
    char path_[files::PATH_SIZE] = {}, directory_[files::PATH_SIZE] = "/";
    char selected_file_[files::PATH_SIZE] = {}, prompt_text_[256] = {};
    char status_[96] = {}, console_[ROWS][text_screen::MAX_COLS + 1] = {};
    files::Entry entries_[7] = {};
    u8 image_[language_vm::MAX_MODULE] = {};
    language_vm::State state_{};
    language_vm::Value variables_[26]{}, array_[385]{}, stack_[language_vm::MAX_STACK]{};
    language_vm::Value focal_variables_[26]{}, focal_array_[385]{};
    language_vm::Error last_error_ = language_vm::Error::NONE;
    language_vm::Language language_ = language_vm::Language::BASIC;
    int print_width_ = 0;
    u8 precision_ = 10, print_cursor_ = 0;
    char print_[96] = {};
    u8 deferred_keys_[32] = {}, deferred_read_ = 0, deferred_count_ = 0;
    basic_graphics::PrintPosition position_{};
    Pump pump_ = nullptr;
    void* pump_context_ = nullptr;
    basic_graphics::Session graph_;
};
} // namespace picocalc
#endif
