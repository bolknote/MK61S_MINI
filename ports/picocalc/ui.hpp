#ifndef MK61_PICOCALC_UI_HPP
#define MK61_PICOCALC_UI_HPP
#include "calculator.hpp"
#include "settings.hpp"
#include "clock.hpp"

namespace picocalc {
enum class Page : u8 { CALCULATOR, MAIN, SETTINGS, FONTS, SYSTEM, INFO, HARDWARE, NOTICE, CONFIRM, CLOCK, ALARMS };
enum class Action : u8 { NONE, RESTART, BOOTLOADER, RESET, USB_DISK, EXPLORER, DEVELOPMENT, FORMAT, USB_SCREEN, SLEEP };
enum class View : u8 { STACK, REGISTERS, PROGRAM, HELP };

class Ui {
public:
    void init(const Settings& value = Settings{});
    bool input(u8 code, Calculator& calculator);
    Page page() const { return page_; }
    View view() const { return view_; }
    u8 offset() const { return offset_; }
    u8 selected() const { return selected_[(unsigned)page_]; }
    unsigned count() const;
    const Settings& settings() const { return settings_; }
    u32 settings_revision() const { return settings_revision_; }
    const char* title() const;
    void row(unsigned index, char out[64]) const;
    const char* footer() const;
    const char* page_name() const;
    Action take_action();
    void calculator_page() { page_ = Page::CALCULATOR; }
    void sync_alarms();
private:
    const char* text(const char* en, const char* ru) const { return settings_.russian ? ru : en; }
    void notice(Page parent, const char* en, const char* ru);
    void adjust(int direction, Calculator& calculator, bool cycle);
    Settings settings_;
    Page page_ = Page::CALCULATOR, parent_ = Page::MAIN;
    View view_ = View::STACK;
    Action action_ = Action::NONE, confirm_ = Action::NONE;
    u8 selected_[11] = {};
    clock::DateTime clock_edit_;
    clock::Alarm alarm_edit_;
    u8 alarm_index_=0;
    u8 offset_ = 0;
    u32 settings_revision_ = 0;
    const char* notice_en_ = "", *notice_ru_ = "";
};
} // namespace picocalc
#endif
