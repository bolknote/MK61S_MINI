#include "ui.hpp"
#include "menu_model.hpp"
#include "fonts.hpp"
#include <cstdio>
#include <cstring>

namespace picocalc {
namespace {
bool back(u8 code) { return code == 0x1B || code == 0xB1 || code == 0x08; }
bool enter(u8 code) { return code == '\n' || code == '\r'; }
} // namespace
void Ui::init(const Settings &value) {
  (void)fonts::select(Settings{});
  settings_ = valid_settings(value) ? value : Settings{};
  if(!fonts::select(settings_)) {
    settings_.ui_font_family=1;settings_.ui_font_key=0;settings_.ui_font_size=14;
    (void)fonts::select(settings_);
  }
  page_ = Page::CALCULATOR;
  view_ = View::STACK;
  action_ = confirm_ = Action::NONE;
  std::memset(selected_, 0, sizeof(selected_));
  offset_ = 0;
  settings_revision_ = 0;
}
bool Ui::apply_settings(const Settings& value,bool persist) {
  if(!valid_settings(value) || !fonts::select(value)) return false;
  settings_=value;if(persist) ++settings_revision_;return true;
}
unsigned Ui::count() const {
  switch (page_) {
  case Page::MAIN:
    return menu_model::MAIN_COUNT;
  case Page::SETTINGS:
    return 11;
  case Page::FONTS:
    return 3;
  case Page::SYSTEM:
    return 8;
  case Page::CLOCK:
    return 9;
  case Page::ALARMS:
    return 9;
  case Page::INFO:
  case Page::HARDWARE:
    return 6;
  default:
    return 0;
  }
}
const char *Ui::title() const {
  switch (page_) {
  case Page::CALCULATOR:
    return "MK61S";
  case Page::MAIN:
    return text("Main menu", M8("Главное меню"));
  case Page::SETTINGS:
    return text("Settings", M8("Настройки"));
  case Page::FONTS:
    return text("Fonts", M8("Шрифты"));
  case Page::SYSTEM:
    return text("System", M8("Система"));
  case Page::INFO:
    return text("Information", M8("Информация"));
  case Page::HARDWARE:
    return text("Hardware", M8("Плата"));
  case Page::ALARMS:
    return alarm_index_ ? "Alarm B" : "Alarm A";
  case Page::CLOCK:
    return text("Clock (local time)", M8("Часы (местное время)"));
  case Page::CONFIRM:
    return text("Confirm", M8("Подтверждение"));
  default:
    return text("PicoCalc port", M8("Перенос PicoCalc"));
  }
}
const char *Ui::page_name() const {
  static const char *names[] = {"CALCULATOR", "MAIN",  "SETTINGS", "FONTS",
                                "SYSTEM",     "INFO",  "HARDWARE", "NOTICE",
                                "CONFIRM",    "CLOCK", "ALARMS"};
  return names[(unsigned)page_];
}
void Ui::notice(Page parent, const char *en, const char *ru) {
  parent_ = parent;
  notice_en_ = en;
  notice_ru_ = ru;
  page_ = Page::NOTICE;
}
Action Ui::take_action() {
  const Action result = action_;
  action_ = Action::NONE;
  return result;
}
bool Ui::input(u8 code, Calculator &calculator) {
  if (code == '\t') {
    page_ = page_ == Page::CALCULATOR ? Page::MAIN : Page::CALCULATOR;
    confirm_ = Action::NONE;
    return true;
  }
  if (page_ == Page::CALCULATOR) {
    if (code == 0xB5 || code == 0xB6) {
      view_ = (View)(((unsigned)view_ + (code == 0xB5 ? 3U : 1U)) % 4U);
      offset_ = 0;
      return true;
    }
    if (code == 0xD6 || code == 0xD7) {
      const unsigned limit =
          view_ == View::REGISTERS ? 9 : core_61::program_steps() - 6;
      offset_ = (u8)menu_model::step(offset_, limit + 1, code == 0xD6 ? -1 : 1);
      return true;
    }
    return false;
  }
  if (back(code)) {
    switch (page_) {
    case Page::MAIN:
      page_ = Page::CALCULATOR;
      break;
    case Page::FONTS:
      page_ = Page::SETTINGS;
      break;
    case Page::ALARMS:
      page_ = Page::CLOCK;
      break;
    case Page::INFO:
    case Page::HARDWARE:
    case Page::CLOCK:
      page_ = Page::SYSTEM;
      break;
    case Page::NOTICE:
    case Page::CONFIRM:
      page_ = parent_;
      confirm_ = Action::NONE;
      break;
    default:
      page_ = Page::MAIN;
      break;
    }
    return true;
  }
  if (page_ == Page::NOTICE) {
    if (enter(code))
      page_ = parent_;
    return true;
  }
  if (page_ == Page::CONFIRM) {
    if (enter(code)) {
      action_ = confirm_;
      confirm_ = Action::NONE;
      page_ = Page::CALCULATOR;
    }
    return true;
  }
  if (page_ == Page::INFO || page_ == Page::HARDWARE)
    return true;
  if (code == 0xB5 || code == 0xB6) {
    selected_[(unsigned)page_] =
        (u8)menu_model::step(selected(), count(), code == 0xB5 ? -1 : 1);
    return true;
  }
  if (page_ == Page::CLOCK) {
    int *fields[] = {&clock_edit_.year,   &clock_edit_.month,
                     &clock_edit_.day,    &clock_edit_.hour,
                     &clock_edit_.minute, &clock_edit_.second};
    const int lo[] = {2000, 1, 1, 0, 0, 0},
              hi[] = {
                  2099,
                  12,
                  (int)clock::month_days(clock_edit_.year, clock_edit_.month),
                  23,
                  59,
                  59};
    const unsigned index = selected();
    if (index >= 7 && enter(code)) {
      alarm_index_ = (u8)(index - 7);
      alarm_edit_ = clock::alarm(alarm_index_);
      if (!alarm_edit_.enabled)
        alarm_edit_.when = clock::get();
      page_ = Page::ALARMS;
    } else if (index == 6 && enter(code)) {
      (void)clock::set(clock_edit_);
      page_ = Page::SYSTEM;
    } else if (index < 6 && (code == 0xB4 || code == 0xB7 || enter(code))) {
      const int v = *fields[index] + (code == 0xB4 ? -1 : 1);
      *fields[index] = v < lo[index]   ? hi[index]
                       : v > hi[index] ? lo[index]
                                       : v;
      const unsigned max =
          clock::month_days(clock_edit_.year, clock_edit_.month);
      if (clock_edit_.day > (int)max)
        clock_edit_.day = (int)max;
    }
    return true;
  }
  if (page_ == Page::ALARMS) {
    const unsigned index = selected();
    if (code == 0xB4 || code == 0xB7 || enter(code)) {
      if (index == 0)
        alarm_edit_.enabled = !alarm_edit_.enabled;
      else if (index == 1)
        alarm_edit_.daily = !alarm_edit_.daily;
      else if (index == 8) {
        if (clock::schedule(alarm_index_, alarm_edit_)) {
          sync_alarms();
          page_ = Page::CLOCK;
        }
      } else {
        auto &d = alarm_edit_.when;
        int *field[] = {&d.year, &d.month,  &d.day,
                        &d.hour, &d.minute, &d.second};
        const int low[] = {2000, 1, 1, 0, 0, 0},
                  high[] = {2099, 12, (int)clock::month_days(d.year, d.month),
                            23,   59, 59};
        const unsigned f = index - 2;
        int value = *field[f] + (code == 0xB4 ? -1 : 1);
        *field[f] = value < low[f] ? high[f] : value > high[f] ? low[f] : value;
        if (d.day > (int)clock::month_days(d.year, d.month))
          d.day = (int)clock::month_days(d.year, d.month);
      }
    }
    return true;
  }
  if (page_ == Page::SETTINGS || page_ == Page::FONTS) {
    if (code == 0xB4 || code == 0xB7 || enter(code))
      adjust(code == 0xB4 ? -1 : 1, calculator, enter(code));
    return true;
  }
  if (code == 0xB4 || code == 0xB7) {
    selected_[(unsigned)page_] =
        (u8)menu_model::step(selected(), count(), code == 0xB4 ? -1 : 1);
    return true;
  }
  if (!enter(code))
    return true; // Menu typing must never reach the calculator.
  if (page_ == Page::MAIN) {
    switch ((menu_model::MainItem)selected()) {
    case menu_model::MainItem::SETTINGS:
      page_ = Page::SETTINGS;
      break;
    case menu_model::MainItem::SYSTEM:
      page_ = Page::SYSTEM;
      break;
    case menu_model::MainItem::BOOTLOADER:
      parent_ = page_;
      page_ = Page::CONFIRM;
      confirm_ = Action::BOOTLOADER;
      break;
    case menu_model::MainItem::USB_DISK:
      action_ = Action::USB_DISK;
      break;
    case menu_model::MainItem::EXPLORER:
      action_ = Action::EXPLORER;
      break;
    case menu_model::MainItem::DEVELOPMENT:
      action_ = Action::DEVELOPMENT;
      break;
    default:
      break;
    }
  } else if (page_ == Page::SYSTEM) {
    switch (selected()) {
    case 0:
      parent_ = page_;
      page_ = Page::CONFIRM;
      confirm_ = Action::RESTART;
      break;
    case 1:
      page_ = Page::INFO;
      break;
    case 2:
      page_ = Page::HARDWARE;
      break;
    case 3:
      action_ = Action::FORMAT;
      break;
    case 4:
      parent_ = page_;
      page_ = Page::CONFIRM;
      confirm_ = Action::RESET;
      break;
    case 5:
      action_ = Action::USB_SCREEN;
      break;
    case 6:
      clock_edit_ = clock::get();
      page_ = Page::CLOCK;
      break;
    case 7:
      action_ = Action::SLEEP;
      page_ = Page::CALCULATOR;
      break;
    }
  }
  return true;
}
void Ui::adjust(int direction, Calculator &calculator, bool cycle) {
  const Settings before = settings_;
  if (page_ == Page::FONTS) {
    if (selected() == 0)
      settings_.calculator_font ^= 1;
    else if(selected()==1) {
      fonts::Item item{};
      if(fonts::step(fonts::key(settings_),direction,item)) {
        auto candidate=settings_;candidate.ui_font_size=item.size;
        candidate.ui_font_family=item.family;candidate.ui_font_key=item.family==3?item.key:0;
        if(!fonts::select(candidate)) {
          notice(page_,"Cannot load UI font",M8("Не удалось загрузить шрифт"));return;
        }
        settings_=candidate;
      }
    }
    else {
      const unsigned current=settings_.text_width==3?1:settings_.text_width==10?2:0;
      const unsigned next=(current+(direction<0?2:1))%3;
      settings_.text_rows=next==1?10:next==2?4:8;
      settings_.text_width=next==1?3:next==2?10:5;
      settings_.text_height=next==1?5:next==2?16:8;settings_.text_gap=0;
    }
  } else
    switch (selected()) {
    case 0:
      settings_.volume =
          cycle ? (u8)((settings_.volume + 1) % 11)
                : (u8)menu_model::step(settings_.volume, 11, direction);
      break;
    case 1:
      settings_.idle_signal ^= 1;
      break;
    case 2:
      settings_.classic_speed ^= 1;
      break;
    case 3:
      if (!calculator.idle() || core_61::is_RUN()) {
        notice(page_, "Wait for the calculator to stop.",
               M8("Дождитесь остановки калькулятора."));
        return;
      }
      settings_.memory = (u8)((settings_.memory + (direction > 0 ? 1 : 2)) % 3);
      break;
    case 4:
      settings_.random ^= 1;
      break;
    case 5:
      settings_.russian ^= 1;
      break;
    case 6:
      page_ = Page::FONTS;
      return;
    case 7:
      settings_.lcd_backlight = (u8)(16 * (1 + ((settings_.lcd_backlight / 16 -
                                                 1 + (direction > 0 ? 1 : 14)) %
                                                15)));
      break;
    case 8:
      settings_.key_backlight =
          (u8)(40 *
               ((settings_.key_backlight / 40 + (direction > 0 ? 1 : 6)) % 7));
      break;
    case 9: {
      const u8 values[] = {0, 1, 5, 15, 30};
      unsigned at = 0;
      while (at < 4 && values[at] != settings_.sleep_minutes)
        ++at;
      settings_.sleep_minutes = values[(at + (direction > 0 ? 1 : 4)) % 5];
      break;
    }
    case 10:
      settings_.rtc_ppm = (i16)(settings_.rtc_ppm + (direction > 0 ? 1 : -1));
      if (settings_.rtc_ppm > 500)
        settings_.rtc_ppm = -500;
      if (settings_.rtc_ppm < -500)
        settings_.rtc_ppm = 500;
      break;
    }
  if (std::memcmp(&before, &settings_, sizeof(Settings)) != 0)
    ++settings_revision_;
}
void Ui::row(unsigned index, char out[64]) const {
  out[0] = 0;
  if (count() && index >= count())
    return;
  if (page_ == Page::MAIN) {
    std::snprintf(out, 64, "%s",
                  index == (unsigned)menu_model::MainItem::BOOTLOADER
                      ? text("UF2 bootloader", M8("UF2 прошивка"))
                      : menu_model::mainLabel((menu_model::MainItem)index,
                                              settings_.russian));
  } else if (page_ == Page::SETTINGS) {
    switch (index) {
    case 0:
      std::snprintf(out, 64, "%s %u", text("Volume", M8("Громкость")),
                    settings_.volume);
      break;
    case 1:
      std::snprintf(out, 64, "%s %s", text("5 min beep", M8("5 мин звук")),
                    settings_.idle_signal ? "ON" : "OFF");
      break;
    case 2:
      std::snprintf(out, 64, "%s %s", text("Speed", M8("Скорость")),
                    settings_.classic_speed ? "CLASSIC" : "MAXIMUM");
      break;
    case 3:
      std::snprintf(out, 64, "%s %s", text("Memory", M8("Память")),
                    settings_.memory == 0   ? "105"
                    : settings_.memory == 1 ? "112+F"
                                            : text("AUTO",M8("АВТО")));
      break;
    case 4:
      std::snprintf(out, 64, "%s %s", text("Random", M8("К СЧ")),
                    settings_.random ? "MK61S" : "MK61");
      break;
    case 5:
      std::snprintf(out, 64, "%s", text("Language EN", M8("Язык рус")));
      break;
    case 6:
      std::snprintf(out, 64, "%s", text("Fonts...", M8("Шрифты...")));
      break;
    case 7:
      std::snprintf(out, 64, "%s %u",
                    text("LCD backlight", M8("Подсветка экрана")),
                    settings_.lcd_backlight);
      break;
    case 8:
      std::snprintf(out, 64, "%s %u",
                    text("Keyboard light", M8("Подсветка клавиш")),
                    settings_.key_backlight);
      break;
    case 9:
      std::snprintf(out, 64, "%s %u min", text("Sleep after", M8("Сон через")),
                    settings_.sleep_minutes);
      break;
    case 10:
      std::snprintf(out, 64, "RTC ppm: %+d", settings_.rtc_ppm);
      break;
    }
  } else if (page_ == Page::FONTS) {
    if (index == 0)
      std::snprintf(out, 64, "%s: %s", text("Calculator", M8("Калькулятор")),
                    settings_.calculator_font ? "Classic 10x16" : "MK61");
    else if(index==1) {
      fonts::Item item{};
      const bool found=fonts::describe(fonts::key(settings_),item);
      std::snprintf(out,64,"%s: %.43s",text("Interface",M8("Интерфейс")),found?item.name:"Ark Pixel");
    }
    else if(index==2) std::snprintf(out,64,"%s: %ux%u / %u",text("Text",M8("Текст")),settings_.text_width,settings_.text_height,settings_.text_rows);
  } else if (page_ == Page::SYSTEM) {
    static const char *en[] = {"Restart",     "Information", "Hardware",
                               "Format disk", "Full reset",  "USB Screen",
                               "Clock",       "Sleep"};
    const char *ru[] = {M8("Перезагрузка"), M8("Информация"),   M8("Плата"),
                        M8("Формат диска"), M8("Полный сброс"), "USB Screen",
                        M8("Часы"),         M8("Сон")};
    if (index < 8)
      std::snprintf(out, 64, "%s", text(en[index], ru[index]));
  } else if (page_ == Page::CLOCK) {
    const char *en[] = {"Year", "Month", "Day", "Hour", "Minute", "Second"};
    const char *ru[] = {M8("Год"), M8("Месяц"),  M8("День"),
                        M8("Час"), M8("Минута"), M8("Секунда")};
    const int v[] = {clock_edit_.year, clock_edit_.month,  clock_edit_.day,
                     clock_edit_.hour, clock_edit_.minute, clock_edit_.second};
    if (index < 6)
      std::snprintf(out, 64, "%s: %02d", text(en[index], ru[index]), v[index]);
    else if (index == 6)
      std::snprintf(out, 64, "%s", text("Save time", M8("Сохранить время")));
    else
      std::snprintf(out, 64, "%s %c: %s", text("Alarm", M8("Будильник")),
                    index == 7 ? 'A' : 'B',
                    clock::alarm(index - 7).enabled ? "ON" : "OFF");
  } else if (page_ == Page::ALARMS) {
    if (index == 0)
      std::snprintf(out, 64, "%s: %s", text("Enabled", M8("Включён")),
                    alarm_edit_.enabled ? "ON" : "OFF");
    else if (index == 1)
      std::snprintf(out, 64, "%s",
                    alarm_edit_.daily
                        ? text("Repeat: daily", M8("Повтор: ежедневно"))
                        : text("Repeat: once", M8("Повтор: один раз")));
    else if (index < 8) {
      const auto &d = alarm_edit_.when;
      const int v[] = {d.year, d.month, d.day, d.hour, d.minute, d.second};
      const char *label[] = {"Year", "Month",  "Day",
                             "Hour", "Minute", "Second"};
      std::snprintf(out, 64, "%s: %02d", label[index - 2], v[index - 2]);
    } else
      std::snprintf(out, 64, "%s",
                    text("Save alarm", M8("Сохранить будильник")));
  } else if (page_ == Page::NOTICE) {
    if (index == 0)
      std::snprintf(out, 64, "%s", text(notice_en_, notice_ru_));
    if (index == 2)
      std::snprintf(out, 64, "%s",
                    text("Enter / Esc: back", M8("Enter / Esc: назад")));
  } else if (page_ == Page::CONFIRM) {
    if (index == 0)
      std::snprintf(
          out, 64, "%s",
          confirm_ == Action::BOOTLOADER ? "USB BOOTSEL / UF2"
          : confirm_ == Action::RESET
              ? text("Reset settings and calculator?",
                     M8("Сбросить настройки и калькулятор?"))
              : text("Restart PicoCalc?", M8("Перезагрузить PicoCalc?")));
    if (index == 2)
      std::snprintf(
          out, 64, "%s",
          text("Enter: confirm   Esc: cancel", M8("Enter: да   Esc: отмена")));
  }
}
void Ui::sync_alarms() {
  u32 values[2];
  u8 flags;
  clock::save_alarms(values, flags);
  if (flags != settings_.alarm_flags || values[0] != settings_.alarm_epoch[0] ||
      values[1] != settings_.alarm_epoch[1]) {
    settings_.alarm_flags = flags;
    settings_.alarm_epoch[0] = values[0];
    settings_.alarm_epoch[1] = values[1];
    ++settings_revision_;
  }
}
const char *Ui::footer() const {
  if (page_ == Page::CALCULATOR)
    return text("Tab: menu   Up/Down: view", M8("Tab: меню   Up/Down: вид"));
  if (page_ == Page::SETTINGS && selected() == 3)
    return text("Memory change resets calculator",
                M8("Смена памяти сбрасывает калькулятор"));
  if (page_ == Page::SETTINGS || page_ == Page::FONTS)
    return text("Left/Right: change   Esc: back",
                M8("Left/Right: изменить   Esc: назад"));
  return text("Up/Down  Enter: select  Esc: back",
              M8("Up/Down  Enter: выбор  Esc: назад"));
}
} // namespace picocalc
