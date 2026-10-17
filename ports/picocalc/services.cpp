#include "services.hpp"
#include "script.hpp"
#include "m61_text.hpp"
#include "markdown.hpp"
#include "text_editor.hpp"
#include "mk8_codec.hpp"
#include "mk8_literal.hpp"
#include "menu_model.hpp"
#include <cstdio>
#include <cstring>
#include <new>

namespace picocalc {
namespace {
bool back(u8 c) { return c == 0x1B || c == 0xB1; }
bool enter(u8 c) { return c == '\r' || c == '\n'; }
bool join(const char* directory, const char* name, char out[files::PATH_SIZE]) {
    const int n = std::snprintf(out, files::PATH_SIZE, "%s%s%s", directory,
        std::strcmp(directory, "/") == 0 ? "" : "/", name);
    return n > 0 && n < (int)files::PATH_SIZE;
}
bool extension(const char* path, const char* ext) {
    const char* dot = std::strrchr(path, '.');
    if(!dot) return false;
    do {
        char a = *dot++, b = *ext++;
        if(a >= 'A' && a <= 'Z') a += 32;
        if(a != b) return false;
    } while(*ext);
    return *dot == 0;
}
void label(const char* utf8, char* out, unsigned capacity) {
    unsigned used = 0;
    while(*utf8 && used + 1 < capacity) {
        u32 cp = (u8)*utf8++;
        if(cp >= 0xC2 && cp <= 0xDF && ((u8)*utf8 & 0xC0) == 0x80)
            cp = ((cp & 31) << 6) | ((u8)*utf8++ & 63);
        else if(cp >= 0xE0 && cp <= 0xEF && utf8[0] && utf8[1] &&
                ((u8)utf8[0] & 0xC0) == 0x80 && ((u8)utf8[1] & 0xC0) == 0x80) {
            cp = ((cp & 15) << 12) | (((u8)utf8[0] & 63) << 6) | ((u8)utf8[1] & 63); utf8 += 2;
        }
        u8 m8;
        out[used++] = mk8::from_codepoint(cp, m8) ? (char)m8 : '?';
    }
    out[used] = 0;
}
}
void Services::message(const char* value, ServicePage parent) {
    std::snprintf(status_, sizeof(status_), "%s", value);
    message_parent_ = parent; page_ = ServicePage::MESSAGE;
}
bool Services::leave_for_script() {
    if(dirty_ || running_ || files::usb_active() || m61_text::active()) return false;
    page_ = ServicePage::CLOSED;
    viewing_ = image_viewing_ = waiting_ = pending_run_ = false;
    runtime_graphics_ = graph_visible_ = false;
    graph_.reset();
    return true;
}
void Services::open(Action action, bool russian, Calculator& calculator) {
    calculator_ = &calculator; russian_ = russian; selection_ = 0;
    script::attach(calculator, *this);
    if(action == Action::USB_DISK) {
        if(files::begin_usb()) page_ = ServicePage::USB_DISK;
        else message(files::error(), ServicePage::CLOSED);
    } else if(action == Action::EXPLORER) browse(ServicePage::CLOSED);
    else if(action == Action::FORMAT) {
        page_ = ServicePage::CONFIRM; confirm_ = Confirm::FORMAT; confirm_parent_ = ServicePage::CLOSED;
    } else page_ = ServicePage::DEVELOPMENT;
}
void Services::browse(ServicePage parent) {
    browser_parent_ = parent; page_ = ServicePage::BROWSER;
    browser_load_program_ = false;
    skip_ = selection_ = 0; refresh();
}
void Services::refresh() {
    if(!files::list(directory_, skip_, entries_, 7, used_, more_)) message(files::error(), browser_parent_);
    if(selection_ > used_) selection_ = used_;
}
bool Services::selected_path(char out[files::PATH_SIZE]) const {
    return selection_ && selection_ <= used_ && join(directory_, entries_[selection_ - 1].name, out);
}
void Services::parent_directory() {
    if(std::strcmp(directory_, "/") == 0) { page_ = browser_parent_; selection_ = 0; return; }
    char* slash = std::strrchr(directory_, '/');
    if(slash == directory_) directory_[1] = 0;
    else if(slash) *slash = 0;
    skip_ = selection_ = 0; refresh();
}
void Services::new_document(Document kind) {
    document_ = kind; source_[0] = path_[0] = 0;
    length_ = cursor_ = top_ = horizontal_ = 0; dirty_ = false;
    page_ = ServicePage::EDITOR; status_[0] = 0;
}
bool Services::load_document(const char* path,bool edit) {
    if(!edit && extension(path,".md")) { (void)view_markdown(path);return false; }
    if(extension(path,".sheet")) { (void)run_handled(path,program_store::TYPE_MAGIC_SHEET);return false; }
    if(extension(path, ".app")) {
        (void)run_native(path);
        return false;
    }
    if(extension(path, ".ch8") || extension(path, ".c8")) {
        (void)run_chip8(path);
        return false;
    }
    if(extension(path, ".bin")) {
        program_store::Entry entry;
        const bool ok = script::register_file(path, entry) && script::open_entry(entry) == 0;
        message(ok ? "MK61 binary program loaded" : "Invalid MK61 binary program", ServicePage::BROWSER);
        return false;
    }
    // Read into temporary storage so a failed decode never destroys an open document.
    files::Entry info;
    if(!files::stat(path,info)) { message(files::error(),ServicePage::BROWSER); return false; }
    const unsigned capacity=info.size>=SOURCE_CAPACITY-1?SOURCE_CAPACITY:info.size+1;
    auto* temporary = new(std::nothrow) char[capacity];
    if(!temporary) { message("Not enough memory to open source", ServicePage::BROWSER); return false; }
    unsigned used = 0;
    const bool ok = files::read_text(path, temporary, capacity, used);
    if(ok) {
        std::memcpy(source_, temporary, used + 1); length_ = (u16)used;
        std::snprintf(path_, sizeof(path_), "%s", path);
        document_ = extension(path, ".bas") || extension(path, ".tbi") ? Document::BASIC : extension(path, ".foc") || extension(path, ".fcl")
            ? Document::FOCAL : extension(path, ".m61") ? Document::MK61 : Document::TEXT;
        cursor_ = top_ = horizontal_ = 0; dirty_ = false; page_ = ServicePage::EDITOR; status_[0] = 0;
    }
    delete[] temporary;
    if(!ok) message(files::error(), ServicePage::BROWSER);
    return ok;
}
bool Services::save_document(const char* path) {
    if(!files::write_text(path, source_, length_)) { message(files::error(), ServicePage::EDITOR); return false; }
    if(path != path_) std::snprintf(path_, sizeof(path_), "%s", path);
    dirty_ = false;
    std::snprintf(status_, sizeof(status_), "Saved %u bytes", length_);
    return true;
}
void Services::prompt(Prompt op, ServicePage parent, const char* initial) {
    prompt_ = op; prompt_parent_ = parent; page_ = ServicePage::PROMPT;
    std::snprintf(prompt_text_, sizeof(prompt_text_), "%s", initial);
    prompt_length_ = (u16)std::strlen(prompt_text_);
}
void Services::accept_prompt() {
    if(!prompt_length_) return;
    if(prompt_==Prompt::OPEN) {
        char target[files::PATH_SIZE];
        if(prompt_text_[0]=='/' || prompt_text_[0]=='\\') std::snprintf(target,sizeof(target),"%s",prompt_text_);
        else if(!join(directory_,prompt_text_,target)) { message("Path too long",ServicePage::PROMPT);return; }
        return_=ServicePage::BROWSER;(void)load_document(target);return;
    }
    if(std::strchr(prompt_text_, '/') || std::strchr(prompt_text_, '\\') ||
        std::strcmp(prompt_text_, ".") == 0 || std::strcmp(prompt_text_, "..") == 0) {
        message("Enter a filename without slashes", ServicePage::PROMPT); return;
    }
    char target[files::PATH_SIZE];
    if(!join(directory_, prompt_text_, target)) { message("Path too long", ServicePage::PROMPT); return; }
    if((prompt_ == Prompt::SAVE || prompt_ == Prompt::EXPORT) && files::exists(target) &&
       (prompt_ == Prompt::EXPORT || std::strcmp(target, path_) != 0)) {
        std::snprintf(selected_file_, sizeof(selected_file_), "%s", target);
        confirm_ = Confirm::OVERWRITE; confirm_parent_ = page_; page_ = ServicePage::CONFIRM; return;
    }
    bool ok = false;
    switch(prompt_) {
        case Prompt::SAVE: ok = save_document(target); if(ok) page_ = ServicePage::EDITOR; return;
        case Prompt::RENAME: ok = files::rename(selected_file_, target); break;
        case Prompt::MKDIR: ok = files::mkdir(target); break;
        case Prompt::EXPORT: ok = export_program(target); break;
        case Prompt::OPEN: return_ = ServicePage::BROWSER; (void)load_document(target); return;
        case Prompt::NEW_FILE:
            if(files::exists(target)) { message("Name already exists", ServicePage::PROMPT); return; }
            new_document(extension(target, ".bas") ? Document::BASIC : extension(target, ".foc") ? Document::FOCAL :
                extension(target, ".m61") ? Document::MK61 : Document::TEXT);
            std::snprintf(path_, sizeof(path_), "%s", target); dirty_ = true; return;
    }
    if(!ok) { message(files::error(), ServicePage::PROMPT); return; }
    page_ = prompt_parent_; if(page_ == ServicePage::BROWSER) { selection_ = 0; refresh(); }
}
void Services::leave_editor() {
    if(dirty_) { confirm_ = Confirm::DISCARD; confirm_parent_ = ServicePage::EDITOR; page_ = ServicePage::CONFIRM; }
    else { page_ = return_; selection_ = 0; if(page_ == ServicePage::BROWSER) refresh(); }
}
void Services::normalize_view() {
    const u16 active = text_editor::line_start_for_cursor(source_, cursor_);
    if(top_ > active) top_ = active;
    unsigned at = top_, row = 0;
    while(at < active && row < ROWS) { at = text_editor::next_line_start(source_, (u16)at, length_); ++row; }
    if(row >= ROWS) {
        top_ = active;
        for(unsigned i = 1; i < ROWS && top_; ++i) top_ = text_editor::previous_line_start(source_, top_);
    }
    const unsigned column = cursor_ - active;
    if(column < horizontal_) horizontal_ = (u16)column;
    if(column >= horizontal_ + COLS) horizontal_ = (u16)(column - COLS + 1);
}
bool Services::input(u8 code) {
    if(!active()) return false;
    const bool cancel = back(code), accept = enter(code);
    if(page_ == ServicePage::USB_DISK) {
        if(cancel || accept) {
            if(!files::end_usb()) std::snprintf(status_, sizeof(status_), "%s", files::error());
            else { page_ = ServicePage::CLOSED; status_[0] = 0; }
        }
        return true;
    }
    if(page_ == ServicePage::MESSAGE) { if(cancel || accept) page_ = message_parent_; return true; }
    if(page_ == ServicePage::PROMPT) {
        if(cancel) page_ = prompt_parent_;
        else if(accept) accept_prompt();
        else if((code == 8 || code == 0x7F || code == 0xD4) && prompt_length_) prompt_text_[--prompt_length_] = 0;
        else if(code >= 32 && code < 127 && (unsigned)prompt_length_ + 1 < sizeof(prompt_text_)) {
            prompt_text_[prompt_length_++] = (char)code; prompt_text_[prompt_length_] = 0;
        }
        return true;
    }
    if(page_ == ServicePage::CONFIRM) {
        if(cancel) page_ = confirm_parent_;
        else if(accept) {
            if(confirm_ == Confirm::FORMAT) {
                if(files::format()) message("microSD formatted", ServicePage::CLOSED);
                else message(files::error(), confirm_parent_);
            } else if(confirm_ == Confirm::DELETE_FILE) {
                if(!files::remove(selected_file_)) message(files::error(), ServicePage::BROWSER);
                else { page_ = ServicePage::BROWSER; selection_ = 0; refresh(); }
            } else if(confirm_ == Confirm::OVERWRITE) {
                const bool ok = prompt_ == Prompt::EXPORT ? export_program(selected_file_) : save_document(selected_file_);
                if(ok) { page_ = prompt_parent_; if(page_ == ServicePage::BROWSER) refresh(); }
                else if(page_ == ServicePage::CONFIRM) message(files::error(), confirm_parent_);
            } else { dirty_ = false; page_ = return_; selection_ = 0; if(page_ == ServicePage::BROWSER) refresh(); }
        }
        return true;
    }
    if(page_ == ServicePage::CONSOLE) {
        if(runtime_graphics_ && !running_) {
            if(cancel || accept) { runtime_graphics_=viewing_=false;page_=ServicePage::BROWSER;refresh(); }
            return true;
        }
        if(cancel || accept || code == 0x83) { page_ = ServicePage::EDITOR; graph_visible_ = false; }
        return true;
    }
    if(page_ == ServicePage::EDITOR) {
        if(cancel) { leave_editor(); return true; }
        if(code == 0x82 || code == 0x13) {
            if(path_[0]) (void)save_document(path_);
            else prompt(Prompt::SAVE, page_, document_ == Document::BASIC ? "new.bas" :
                document_ == Document::FOCAL ? "new.foc" : document_ == Document::MK61 ? "new.m61" : "new.txt");
            return true;
        }
        if(code == 0x81) { prompt(Prompt::SAVE, page_, path_[0] ? std::strrchr(path_, '/') + 1 : "new.bas"); return true; }
        if(code == 0x83 || code == 0x12) { pending_run_ = true; return true; }
        bool changed = false;
        if(code == 0xB4) { if(cursor_) --cursor_; }
        else if(code == 0xB7) { if(cursor_ < length_) ++cursor_; }
        else if(code == 0xB5 || code == 0xB6) text_editor::move_cursor_line(source_, length_, cursor_, code == 0xB5 ? -1 : 1);
        else if(code == 0xD2) cursor_ = text_editor::line_start_for_cursor(source_, cursor_);
        else if(code == 0xD5) cursor_ = text_editor::line_end_for_start(source_, text_editor::line_start_for_cursor(source_, cursor_), length_);
        else if(code == 0xD6 || code == 0xD7) {
            for(unsigned i = 0; i < ROWS; ++i) text_editor::move_cursor_line(source_, length_, cursor_, code == 0xD6 ? -1 : 1);
        } else if(code == 8) changed = text_editor::backspace(source_, length_, cursor_);
        else if(code == 0x7F || code == 0xD4) {
            if(cursor_ < length_) changed = text_editor::replace_range(source_, length_, cursor_, SOURCE_CAPACITY, cursor_, cursor_ + 1, "");
        } else if(accept || code == '\t' || (code >= 32 && code < 127)) {
            char text[] = {(char)(accept ? '\n' : code), 0};
            changed = text_editor::insert_text(source_, length_, cursor_, SOURCE_CAPACITY, code == '\t' ? "  " : text);
            if(!changed) std::snprintf(status_, sizeof(status_), "Source limit: 65534 bytes");
        }
        if(changed) { dirty_ = true; status_[0] = 0; }
        normalize_view(); return true;
    }
    if(page_ == ServicePage::BROWSER) {
        if(cancel || code == 0xB4) { parent_directory(); return true; }
        if(code == 0xB5) {
            if(selection_) --selection_;
            else if(skip_ >= 7) { skip_ -= 7; refresh(); selection_ = used_; }
        } else if(code == 0xB6) {
            if(selection_ < used_) ++selection_;
            else if(more_) { skip_ += 7; selection_ = 1; refresh(); }
        } else if(code == 0x82) prompt(Prompt::NEW_FILE, page_, "new.bas");
        else if(code == '/') prompt(Prompt::OPEN, page_);
        else if(code == 0x84) prompt(Prompt::MKDIR, page_, "NewFolder");
        else if(code == 0x85) prompt(Prompt::EXPORT, page_, "program.m61");
        else if(accept || code == 0x81 || code == 0x83) {
            if(!selection_) { parent_directory(); return true; }
            if(!selected_path(selected_file_)) { message("Path too long", page_); return true; }
            if(code == 0x81) { page_ = ServicePage::FILE_ACTIONS; selection_ = 0; }
            else if(entries_[selection_ - 1].directory) {
                std::snprintf(directory_, sizeof(directory_), "%s", selected_file_); skip_ = selection_ = 0; refresh();
            } else {
                return_ = ServicePage::BROWSER;
                if(load_document(selected_file_) && (code == 0x83 || (browser_load_program_ && document_ == Document::MK61))) pending_run_ = true;
            }
        }
        return true;
    }
    if(page_ == ServicePage::FILE_ACTIONS) {
        if(cancel) { page_ = ServicePage::BROWSER; selection_ = 0; refresh(); }
        else if(code == 0xB5 || code == 0xB6) selection_ = menu_model::step(selection_, 4, code == 0xB5 ? -1 : 1);
        else if(accept) {
            if(selection_ < 2) { return_ = ServicePage::BROWSER; if(load_document(selected_file_,selection_==0) && selection_ == 1) pending_run_ = true; }
            else if(selection_ == 2) prompt(Prompt::RENAME, ServicePage::BROWSER, std::strrchr(selected_file_, '/') + 1);
            else { confirm_ = Confirm::DELETE_FILE; confirm_parent_ = page_; page_ = ServicePage::CONFIRM; }
        }
        return true;
    }
    const unsigned count = page_ == ServicePage::LANGUAGE && tool_ == Document::MK61 ? 2 : 4;
    if(cancel) {
        if(page_ == ServicePage::LANGUAGE) page_ = ServicePage::DEVELOPMENT;
        else page_ = ServicePage::CLOSED;
        selection_ = 0; return true;
    }
    if(code == 0xB5 || code == 0xB6) selection_ = menu_model::step(selection_, count, code == 0xB5 ? -1 : 1);
    if(accept && page_ == ServicePage::DEVELOPMENT) {
        if(selection_ == 0) browse(page_);
        else { tool_ = selection_ == 1 ? Document::MK61 : selection_ == 2 ? Document::FOCAL : Document::BASIC;
            page_ = ServicePage::LANGUAGE; selection_ = 0; }
    } else if(accept && page_ == ServicePage::LANGUAGE) {
        return_ = ServicePage::LANGUAGE;
        if(tool_ == Document::MK61) {
            if(selection_ == 0) { browse(page_); browser_load_program_ = true; }
            else prompt(Prompt::EXPORT, page_, "program.m61");
        } else if(selection_ == 0) new_document(tool_);
        else if(selection_ == 1) browse(page_);
        else if(tool_ != document_) message("Open or create a source for this language first", page_);
        else { page_ = ServicePage::EDITOR; if(selection_ == 3) pending_run_ = true; }
    }
    return true;
}
void Services::tick() {
    restore_script_editor();
    if(pending_run_) { pending_run_=false;run_document(); }
    restore_script_editor();
    if(!m61_text::active() && !script_editor_.valid) script::reset_files();
}
const char* Services::page_name() const {
    if(viewing_) return "VIEWER";
    static const char* names[] = {"CLOSED", "DEVELOPMENT", "LANGUAGE", "BROWSER", "FILE_ACTIONS", "EDITOR",
        "CONSOLE", "PROMPT", "CONFIRM", "MESSAGE", "USB_DISK"};
    return names[(unsigned)page_];
}
const char* Services::title() const {
    switch(page_) {
        case ServicePage::DEVELOPMENT: return tr("Development", M8("Разработка"));
        case ServicePage::LANGUAGE:
            return tool_ == Document::BASIC ? "TinyBASIC" : tool_ == Document::FOCAL ? "FOCAL" : "MK61 files";
        case ServicePage::EDITOR: case ServicePage::CONSOLE:
            return document_ == Document::BASIC ? "TinyBASIC" : document_ == Document::FOCAL ? "FOCAL" : document_ == Document::MK61 ? "MK61 files" : "Text";
        case ServicePage::BROWSER: return tr("Explorer / microSD", M8("Проводник / microSD"));
        case ServicePage::FILE_ACTIONS: return tr("File actions", M8("Действия с файлом"));
        case ServicePage::PROMPT: return tr("Filename", M8("Имя файла"));
        case ServicePage::CONFIRM: return tr("Confirm", M8("Подтверждение"));
        case ServicePage::USB_DISK: return tr("USB disk / microSD", M8("USB-диск / microSD"));
        default: return "MK61S";
    }
}
void Services::heading(char out[64]) const {
    if(page_ == ServicePage::EDITOR) {
        char name[40];
        const char* slash = std::strrchr(path_, '/');
        label(path_[0] ? (slash ? slash + 1 : path_) : title(), name, sizeof(name));
        std::snprintf(out, 64, "%s%s  %u B", name, dirty_ ? " *" : "", length_);
    } else std::snprintf(out, 64, "%s", title());
}
const char* Services::footer() const {
    if(markdown_) return tr("Up/Down: scroll  Left/Right: links  Enter", M8("Up/Down: текст  Left/Right: ссылки"));
    if(viewing_) return tr("Up/Down: scroll  Enter/Esc: close", M8("Up/Down: текст  Enter/Esc: назад"));
    if(page_ == ServicePage::EDITOR) return tr("F1: Save as  F2: Save  F3: Run  Esc", M8("F1: имя  F2: запись  F3: пуск  Esc"));
    if(page_ == ServicePage::BROWSER) return tr("F1: actions F2: new F4: dir F5: MK61", M8("F1: файл F2: новый F4: папка F5: MK61"));
    if(page_ == ServicePage::USB_DISK) return tr("Eject on computer, then Enter / Esc", M8("Извлечь на ПК, затем Enter / Esc"));
    if(page_ == ServicePage::CONSOLE) return running_ ? "Esc: STOP" : tr("Enter / Esc: editor", M8("Enter / Esc: редактор"));
    return tr("Up/Down  Enter: select  Esc: back", M8("Up/Down  Enter: выбор  Esc: назад"));
}
void Services::row(unsigned index, char out[COLS + 1]) const {
    out[0] = 0;
    if(markdown_) { markdown_->row(index,out);return; }
    if(page_ == ServicePage::EDITOR) {
        u16 at = top_;
        for(unsigned i = 0; i < index && at < length_; ++i) at = text_editor::next_line_start(source_, at, length_);
        if(index && at == length_ && (index > cursor_row() || !length_ || source_[length_ - 1] != '\n')) return;
        const u16 end = text_editor::line_end_for_start(source_, at, length_);
        at = (u16)(at + (horizontal_ < end - at ? horizontal_ : end - at));
        unsigned n = 0; while(at < end && n < COLS) out[n++] = source_[at++]; out[n] = 0;
    } else if(page_ == ServicePage::CONSOLE) std::snprintf(out, COLS + 1, "%s", console_[index % ROWS]);
    else if(page_ == ServicePage::BROWSER) {
        if(index == 0) label(directory_, out, COLS + 1);
        else if(index == 2) std::snprintf(out, COLS + 1, "%c ..", selection_ == 0 ? '>' : ' ');
        else if(index >= 3 && index < 3 + used_) {
            const auto& item = entries_[index - 3]; char name[COLS - 3]; label(item.name, name, sizeof(name));
            std::snprintf(out, COLS + 1, "%c%c %s", selection_ == index - 2 ? '>' : ' ', item.directory ? '/' : ' ', name);
        } else if(index == 11 && more_) std::snprintf(out, COLS + 1, "%s", tr("Down: next page", M8("Down: следующая страница")));
        else if(index == 13) std::snprintf(out, COLS + 1, "%s", tr("/: open file by name", M8("/: открыть файл по имени")));
    } else if(page_ == ServicePage::DEVELOPMENT || page_ == ServicePage::LANGUAGE || page_ == ServicePage::FILE_ACTIONS) {
        if(index < 4) {
            const char* dev[] = {tr("Explorer", M8("Проводник")), tr("MK61 files", M8("Файлы МК-61")), "FOCAL", "TinyBASIC"};
            const char* lang[] = {tr("New source", M8("Новый исходник")), tr("Open file...", M8("Открыть файл...")),
                tr("Edit source", M8("Редактор")), tr("Run source", M8("Запуск"))};
            const char* actions[] = {tr("Open / edit", M8("Открыть / править")), tr("Run", M8("Запуск")),
                tr("Rename", M8("Переименовать")), tr("Delete", M8("Удалить"))};
            if(page_ == ServicePage::LANGUAGE && tool_ == Document::MK61) {
                if(index < 2) std::snprintf(out, COLS + 1, "%c %s", selection_ == index ? '>' : ' ',
                    index == 0 ? tr("Load MK61", M8("Загрузить МК-61")) : tr("Save MK61", M8("Сохранить МК-61")));
                return;
            }
            std::snprintf(out, COLS + 1, "%c %s", selection_ == index ? '>' : ' ',
                page_ == ServicePage::DEVELOPMENT ? dev[index] : page_ == ServicePage::LANGUAGE ? lang[index] : actions[index]);
        }
    } else if(page_ == ServicePage::PROMPT) {
        if(index == 0) label(directory_, out, COLS + 1);
        if(index == 2) std::snprintf(out, COLS + 1, "%.38s", prompt_text_ + (prompt_length_ >= COLS ? prompt_length_ - COLS + 1 : 0));
        if(index == 5) std::snprintf(out, COLS + 1, "Enter: OK   Esc: cancel");
    } else if(page_ == ServicePage::CONFIRM) {
        if(index == 0) std::snprintf(out, COLS + 1, "%s", confirm_ == Confirm::FORMAT ? tr("Erase ALL files on microSD?", M8("Стереть ВСЕ файлы microSD?")) :
            confirm_ == Confirm::OVERWRITE ? tr("Replace the existing file?", M8("Заменить существующий файл?")) :
            confirm_ == Confirm::DELETE_FILE ? tr("Delete selected file/directory?", M8("Удалить выбранный файл/папку?")) : tr("Discard unsaved changes?", M8("Отменить несохранённые изменения?")));
        if(index == 1 && (confirm_ == Confirm::DELETE_FILE || confirm_ == Confirm::OVERWRITE)) label(selected_file_, out, COLS + 1);
        if(index == 3) std::snprintf(out, COLS + 1, "Enter: YES   Esc: cancel");
    } else if(page_ == ServicePage::USB_DISK) {
        const char* text[] = {tr("Card is connected to the computer.", M8("Карта подключена к компьютеру.")), "",
            tr("Editors are paused.", M8("Редакторы приостановлены.")), "", tr("Safely eject the disk on the PC", M8("Безопасно извлеките диск на ПК")),
            tr("before returning to MK61S.", M8("перед возвратом в MK61S.")), "", files::usb_ejected() ? "EJECTED: Enter / Esc" : "USB ACTIVE"};
        if(index < 8) std::snprintf(out, COLS + 1, "%s", text[index]);
        if(index == 10) std::snprintf(out, COLS + 1, "%.38s", status_);
    } else if(page_ == ServicePage::MESSAGE) {
        const unsigned at = index * COLS, length = (unsigned)std::strlen(status_);
        if(at < length) std::snprintf(out, COLS + 1, "%.*s", COLS, status_ + at);
    }
}
unsigned Services::cursor_row() const {
    if(page_ == ServicePage::PROMPT) return 2;
    unsigned row = 0; for(u16 at = top_; at < cursor_ && at < length_; ++at) if(source_[at] == '\n') ++row;
    return row < ROWS ? row : ROWS - 1;
}
unsigned Services::cursor_column() const {
    if(page_ == ServicePage::PROMPT) return prompt_length_ < COLS ? prompt_length_ : COLS - 1;
    return cursor_ - text_editor::line_start_for_cursor(source_, cursor_) - horizontal_;
}
} // namespace picocalc
