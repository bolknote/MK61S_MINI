#include <stdio.h>
#include "config.h"
#include "menu.hpp"
#include "cross_hal.h"
#include "lcd_ru.hpp"
#include "development.hpp"
#include "focal.hpp"
#include "hardware_info.hpp"
#include "tinybasic.hpp"
#include "entropy_pool.hpp"
#include "program_store.hpp"
#include "rtc_clock.hpp"
#include "setup_ui.hpp"
#include "crash_dump.hpp"
#include "virtual_fat.hpp"
#include "usb_screen.hpp"
#include "usb_mass_storage.hpp"

extern t_time_ms runtime_ms;
extern void idle_main_process(void);
extern void reset_ext_program_state(void);
extern bool usb_start_mass_storage_mode(void);
extern bool usb_start_terminal_mode(void);

namespace library_mk61 {

static constexpr int MENU_DFU      = 0;
static constexpr int MENU_USB_DISK = 1;
static constexpr int MENU_SETTINGS = 2;
static constexpr int MENU_EXPLORER = 3;
static constexpr int MENU_LIBRARY  = 4;
static constexpr int MENU_DEVELOP  = 5;
static constexpr int MENU_RESET    = MENU_DEVELOP + 1;
static constexpr int MENU_ERASE    = MENU_RESET + 1;
static constexpr int MENU_INFO     = MENU_ERASE + 1;
static constexpr int MENU_HW       = MENU_INFO + 1;

static constexpr int SETTINGS_VOLUME  = 0;
static constexpr int SETTINGS_IDLE_SIGNAL = 1;
static constexpr int SETTINGS_SPEED   = 2;
static constexpr int SETTINGS_MEMORY  = 3;
static constexpr int SETTINGS_RANDOM  = 4;
static constexpr int SETTINGS_DATE_TIME = 5;
static constexpr int SETTINGS_RTC_CALIBRATION = 6;
static constexpr int SETTINGS_LANGUAGE = 7;
#if defined(MK61_OLED1602_WS0010)
static constexpr int SETTINGS_OLED_TIMEOUT = 8;
static constexpr int SETTINGS_DISPLAY_ROWS = 9;
#else
static constexpr int SETTINGS_DISPLAY_ROWS = 8;
#endif

static u8 sound_volume_state = 10;
static SpeedMode speed_mode_state = SpeedMode::MAXIMUM;
static bool russian_language = false;
static bool expanded_program = false;
static bool idle_signal_state = true;
#if defined(MK61_OLED1602_WS0010)
static u8 oled_timeout_state = DEFAULT_OLED_TIMEOUT;
#endif
static lcd_display::TextProfile display_text_profile_state = lcd_display::defaultSettingsTextProfile();
static u8 display_rows_state = lcd_display::defaultSettingsTextProfile().rows;
static ProgramMemoryMode memory_mode = ProgramMemoryMode::AUTO;
static RandomMode random_mode_state = RandomMode::MK61;
static DeferredSave settings_save;
static constexpr t_time_ms SETTINGS_SAVE_IDLE_MS = 1000;

struct MutablePunct {
  u8            size;
  menu_action   action;
  char          text[32];
};

static MutablePunct VOLUME_punct = {.size = 15, .action = (menu_action) &TurnSoundVolume, .text = "Volume 10      "};
static MutablePunct RU_VOLUME_punct = {.size = 15, .action = (menu_action) &TurnSoundVolume, .text = "Громкость 10"};
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
static MutablePunct ROWS_punct = {.size = 15, .action = (menu_action) &FontSetup, .text = "Font 5x8       "};
static MutablePunct RU_ROWS_punct = {.size = 15, .action = (menu_action) &FontSetup, .text = "Шрифт 5x8"};
#endif

#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
static constexpr u8 DISPLAY_ROWS_MIN = lcd_display::MIN_ROWS;

static u8 normalize_display_rows(u8 rows) {
  return lcd_display::clamp_u8(rows, DISPLAY_ROWS_MIN, lcd_display::GRAPHICS_MAX_ROWS);
}

static bool sameTextProfile(lcd_display::TextProfile left, lcd_display::TextProfile right) {
  left = lcd_display::normalizeSettingsTextProfile(left);
  right = lcd_display::normalizeSettingsTextProfile(right);
  return left.rows == right.rows &&
    left.glyph_width == right.glyph_width &&
    left.glyph_height == right.glyph_height &&
    left.line_gap == right.line_gap;
}

static const char* fontPresetName(lcd_display::TextProfile profile) {
  profile = lcd_display::normalizeSettingsTextProfile(profile);
  if(sameTextProfile(profile, lcd_display::textProfile10x16())) return "10x16";
  if(sameTextProfile(profile, lcd_display::textProfile3x5())) return "3x5";
  if(sameTextProfile(profile, lcd_display::textProfile5x9())) return "5x9";
  return "5x8";
}

static u8 display_rows_mode(lcd_display::TextProfile profile) {
  profile = lcd_display::normalizeSettingsTextProfile(profile);
  if(sameTextProfile(profile, lcd_display::textProfile5x9())) return 1;
  if(sameTextProfile(profile, lcd_display::textProfile10x16())) return 2;
  if(sameTextProfile(profile, lcd_display::textProfile3x5())) return 3;
  return 0;
}

static u8 display_rows_from_mode(u8 mode) {
  switch(mode) {
    case 1:
      return lcd_display::FONT_5X9_ROWS;
    case 2:
      return lcd_display::FONT_10X16_ROWS;
    case 3:
      return lcd_display::FONT_3X5_ROWS;
    default:
      return lcd_display::DEFAULT_ROWS;
  }
}


#endif

static void set_speed_mode_state(SpeedMode mode) {
  speed_mode_state = mode;
}

bool  InfoData(void) {
  if(language_is_ru()) {
    char line0[24];
    char line1[24];
    snprintf(line0, sizeof(line0), "СЧ:%u УГ:%u%s",
      (unsigned) read_counter_switch(),
      (unsigned) ((u8) read_grade_switch()),
      flash_is_ok ? " ФЛ" : "");
    snprintf(line1, sizeof(line1), "ВР:%lu МС", (unsigned long) runtime_ms);
    lcd_ru::print_lines(line0, line1);
  } else {
    MK61DisplayUpdate update(main_lcd());
    main_lcd().clear();
    main_lcd().setCursor(0,0);
    main_lcd().print("cnt:"); main_lcd().print(read_counter_switch());
    main_lcd().print(" sw:"); main_lcd().print((u8) read_grade_switch());
    if(flash_is_ok) main_lcd().print(" W25");
    main_lcd().setCursor(0,1);
    main_lcd().print("run "); main_lcd().print(runtime_ms); main_lcd().print(" ms");
  }
  kbd::get_key_wait();
  return false;
}

bool HardwareInfo(void) { return setup_ui::hardware(); }

const t_punct DFU_mode_punct      = {.size = 15, .action = (menu_action) &DFU_enable,           .text = "DFU mode enable"};
const t_punct USB_DISK_punct      = {.size = 8,  .action = (menu_action) &UsbDiskMode,          .text = "USB Disk"};
const t_punct SETTINGS_punct      = {.size = 8,  .action = &settings_select,                    .text = "Settings"};
const t_punct LIB_61_punct        = {.size = 12, .action = &mk61_library_select,                .text = "MK61 library"};
const t_punct EXPLORER_punct      = {.size = 8,  .action = &program_store_explorer_select,      .text = "Explorer"};
const t_punct DEVELOPMENT_punct   = {.size = 11, .action = &development_select,                 .text = "Development"};
const t_punct RESET_punct         = {.size = 12, .action = &ResetDevice,                        .text = "Reset device"};
const t_punct ERASE_punct         = {.size = 12, .action = (menu_action) &EraseFlash,           .text = "Erase FLASH!"};
const t_punct SPEED_LOW_punct     = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Speed CLASSIC  "};
const t_punct SPEED_HIGH_punct    = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Speed MAXIMUM  "};
const t_punct SPEED_TURBO_punct   = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Speed TURBO    "};
const t_punct MEMORY_105_punct    = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Memory 105     "};
const t_punct MEMORY_112_punct    = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Memory 112+F   "};
const t_punct MEMORY_AUTO_punct   = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Memory Auto    "};
const t_punct RANDOM_MK61_punct   = {.size = 15, .action = (menu_action) &TurnRandomMode,       .text = "Random MK61    "};
const t_punct RANDOM_MK61S_punct  = {.size = 15, .action = (menu_action) &TurnRandomMode,       .text = "Random MK61s   "};
const t_punct DATE_TIME_punct      = {.size = 11, .action = (menu_action) &SetDateTime,          .text = "Date & time"};
const t_punct RTC_CALIBRATION_punct = {.size = 14, .action = (menu_action) &SetRtcCalibration,   .text = "RTC correction"};
const t_punct LANGUAGE_EN_punct   = {.size = 15, .action = (menu_action) &TurnLanguage,         .text = "Language EN    "};
const t_punct LANGUAGE_RU_punct   = {.size = 15, .action = (menu_action) &TurnLanguage,         .text = "Язык рус"};
const t_punct IDLE_SIGNAL_OFF_punct = {.size = 15, .action = (menu_action) &TurnIdleSignal,     .text = "5 min beep OFF "};
const t_punct IDLE_SIGNAL_ON_punct  = {.size = 15, .action = (menu_action) &TurnIdleSignal,     .text = "5 min beep ON  "};
const t_punct FLASH_punct         = {.size = 11, .action = (menu_action) &InfoData,             .text = "Information"};
const t_punct HARDWARE_punct      = {.size = 8,  .action = (menu_action) &HardwareInfo,         .text = "Hardware"};

#if defined(MK61_OLED1602_WS0010)
// These variants deliberately live in Flash.  A pair of mutable 32-byte menu
// buffers would be a surprisingly expensive way to format four fixed values
// on the 64-KiB F401 target.
const t_punct OLED_TIMEOUT_OFF_punct = {.size = 15, .action = (menu_action) &TurnOledProtection, .text = "OLED sleep OFF "};
const t_punct OLED_TIMEOUT_5M_punct  = {.size = 15, .action = (menu_action) &TurnOledProtection, .text = "OLED sleep 5m  "};
const t_punct OLED_TIMEOUT_15M_punct = {.size = 15, .action = (menu_action) &TurnOledProtection, .text = "OLED sleep 15m "};
const t_punct OLED_TIMEOUT_30M_punct = {.size = 15, .action = (menu_action) &TurnOledProtection, .text = "OLED sleep 30m "};
const t_punct RU_OLED_TIMEOUT_OFF_punct = {.size = 15, .action = (menu_action) &TurnOledProtection, .text = "OLED сон выкл"};
const t_punct RU_OLED_TIMEOUT_5M_punct  = {.size = 15, .action = (menu_action) &TurnOledProtection, .text = "OLED сон 5 мин"};
const t_punct RU_OLED_TIMEOUT_15M_punct = {.size = 15, .action = (menu_action) &TurnOledProtection, .text = "OLED сон 15мин"};
const t_punct RU_OLED_TIMEOUT_30M_punct = {.size = 15, .action = (menu_action) &TurnOledProtection, .text = "OLED сон 30мин"};
#endif

const t_punct RU_DFU_mode_punct   = {.size = 15, .action = (menu_action) &DFU_enable,           .text = "DFU прошивка"};
const t_punct RU_USB_DISK_punct   = {.size = 15, .action = (menu_action) &UsbDiskMode,          .text = "USB-диск"};
const t_punct RU_SETTINGS_punct   = {.size = 15, .action = &settings_select,                    .text = "Настройки"};
const t_punct RU_LIB_61_punct     = {.size = 15, .action = &mk61_library_select,                .text = "Библиотека"};
const t_punct RU_EXPLORER_punct   = {.size = 15, .action = &program_store_explorer_select,      .text = "Проводник"};
const t_punct RU_DEVELOPMENT_punct= {.size = 15, .action = &development_select,                 .text = "Разработка"};
const t_punct RU_RESET_punct      = {.size = 15, .action = &ResetDevice,                        .text = "Сброс"};
const t_punct RU_ERASE_punct      = {.size = 15, .action = (menu_action) &EraseFlash,           .text = "Стереть FLASH"};
const t_punct RU_SPEED_LOW_punct  = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Скорость норма"};
const t_punct RU_SPEED_HIGH_punct = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Скорость макс"};
const t_punct RU_SPEED_TURBO_punct= {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Скорость турбо"};
const t_punct RU_MEMORY_105_punct = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Память 105ШГ"};
const t_punct RU_MEMORY_112_punct = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Память 112ШГ+ПF"};
const t_punct RU_MEMORY_AUTO_punct= {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Память АВТО"};
const t_punct RU_RANDOM_MK61_punct= {.size = 15, .action = (menu_action) &TurnRandomMode,       .text = "К СЧ MK61"};
const t_punct RU_RANDOM_MK61S_punct={.size = 15, .action = (menu_action) &TurnRandomMode,       .text = "К СЧ MK61s"};
const t_punct RU_DATE_TIME_punct   = {.size = 15, .action = (menu_action) &SetDateTime,          .text = "Дата и время"};
const t_punct RU_RTC_CALIBRATION_punct = {.size = 15, .action = (menu_action) &SetRtcCalibration, .text = "Поправка RTC"};
const t_punct RU_IDLE_SIGNAL_OFF_punct = {.size = 15, .action = (menu_action) &TurnIdleSignal,  .text = "5 мин звук выкл"};
const t_punct RU_IDLE_SIGNAL_ON_punct  = {.size = 15, .action = (menu_action) &TurnIdleSignal,  .text = "5 мин звук вкл"};
const t_punct RU_FLASH_punct      = {.size = 15, .action = (menu_action) &InfoData,             .text = "Информация"};
const t_punct RU_HARDWARE_punct   = {.size = 15, .action = (menu_action) &HardwareInfo,         .text = "Плата"};

t_punct* MENU[] = {
      (t_punct*) &DFU_mode_punct,
      (t_punct*) &USB_DISK_punct,
      (t_punct*) &SETTINGS_punct,
      (t_punct*) &EXPLORER_punct,
      (t_punct*) &LIB_61_punct,
      (t_punct*) &DEVELOPMENT_punct,
      (t_punct*) &RESET_punct,
      (t_punct*) &ERASE_punct,
      (t_punct*) &FLASH_punct,
      (t_punct*) &HARDWARE_punct
};

static_assert(sizeof(MENU) / sizeof(MENU[0]) == MAIN_MENU_COUNT,
              "Main menu count mismatch");
extern const int COUNT_PUNCTS = sizeof(MENU) / sizeof(MENU[0]);

t_punct* SETTINGS_MENU[] = {
      (t_punct*) &VOLUME_punct,
      (t_punct*) &IDLE_SIGNAL_ON_punct,
      (t_punct*) &SPEED_HIGH_punct,
      (t_punct*) &MEMORY_AUTO_punct,
      (t_punct*) &RANDOM_MK61_punct,
      (t_punct*) &DATE_TIME_punct,
      (t_punct*) &RTC_CALIBRATION_punct,
      (t_punct*) &LANGUAGE_EN_punct,
#if defined(MK61_OLED1602_WS0010)
      (t_punct*) &OLED_TIMEOUT_15M_punct,
#endif
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
      (t_punct*) &ROWS_punct,
#endif
};

extern const int COUNT_SETTINGS_PUNCTS = sizeof(SETTINGS_MENU) / sizeof(SETTINGS_MENU[0]);

int current_settings_punct_count(void) {
#if defined(MK61_DISPLAY_LCD1602) && MK61_ENABLE_USB_SCREEN
  if(main_lcd().graphicsMode()) return COUNT_SETTINGS_PUNCTS;
  #if defined(MK61_OLED1602_WS0010)
    return SETTINGS_OLED_TIMEOUT + 1;
  #else
    return SETTINGS_DISPLAY_ROWS;
  #endif
#else
  return COUNT_SETTINGS_PUNCTS;
#endif
}

bool  sound_is_on(void) {
  return sound_volume_state != 0;
}

u8  sound_volume(void) {
  return sound_volume_state;
}

void  set_sound_volume(u8 volume) {
  sound_volume_state = (volume > 10) ? 10 : volume;
}

bool  language_is_ru(void) {
  return russian_language;
}

void  set_language_state(bool enable) {
  russian_language = enable;
}

bool idle_signal_is_on(void) {
  return idle_signal_state;
}

void set_idle_signal_state(bool enable) {
  idle_signal_state = enable;
}

#if defined(MK61_OLED1602_WS0010)
u8 oled_timeout(void) { return oled_timeout_state; }

void set_oled_timeout(u8 timeout) {
  oled_timeout_state = (u8) oled_protection::normalizeTimeout(timeout);
  main_lcd().configureOledProtection(
    (oled_protection::Timeout) oled_timeout_state, millis());
}
#endif

u8 display_rows(void) {
  return display_rows_state;
}

lcd_display::TextProfile display_text_profile(void) {
  return display_text_profile_state;
}

void set_display_text_profile(lcd_display::TextProfile profile) {
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
#if defined(MK61_DISPLAY_UC1609)
  display_text_profile_state = main_lcd().externalFontActive()
    ? profile
    : lcd_display::normalizeSettingsTextProfile(profile);
#else
  display_text_profile_state = lcd_display::normalizeSettingsTextProfile(profile);
#endif
#else
  (void) profile;
  display_text_profile_state = lcd_display::defaultSettingsTextProfile();
#endif
  display_rows_state = display_text_profile_state.rows;
}

void set_display_rows(u8 rows) {
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
  set_display_text_profile(lcd_display::defaultSettingsTextProfileForRows(normalize_display_rows(rows)));
#else
  (void) rows;
  set_display_text_profile(lcd_display::defaultSettingsTextProfile());
#endif
}

bool  expanded_program_is_on(void) {
  return expanded_program;
}

void  set_program_memory_state(bool enable) {
  expanded_program = enable;
  core_61::set_expanded_program_mode(enable);
}

ProgramMemoryMode program_memory_mode(void) {
  return memory_mode;
}

bool program_memory_mode_accepts(bool needs_expanded) {
  if(memory_mode == ProgramMemoryMode::AUTO) return true;
  if(memory_mode == ProgramMemoryMode::EXPANDED_112) return true;
  return !needs_expanded;
}

void set_program_memory_mode(ProgramMemoryMode mode) {
  memory_mode = mode;
  if(memory_mode != ProgramMemoryMode::AUTO) {
    set_program_memory_state(memory_mode == ProgramMemoryMode::EXPANDED_112);
  }
}

RandomMode random_mode(void) {
  return random_mode_state;
}

bool random_mode_is_mk61s(void) {
  return random_mode_state == RandomMode::MK61S;
}

void set_random_mode_state(RandomMode mode) {
  random_mode_state = mode;
}

static t_punct* memory_punct(void) {
  if(memory_mode == ProgramMemoryMode::AUTO) {
    return (t_punct*) (russian_language ? &RU_MEMORY_AUTO_punct : &MEMORY_AUTO_punct);
  }
  if(memory_mode == ProgramMemoryMode::EXPANDED_112) {
    return (t_punct*) (russian_language ? &RU_MEMORY_112_punct : &MEMORY_112_punct);
  }
  return (t_punct*) (russian_language ? &RU_MEMORY_105_punct : &MEMORY_105_punct);
}

static t_punct* speed_punct(void) {
  switch(speed_mode_state) {
    case SpeedMode::CLASSIC:
      return (t_punct*) (russian_language ? &RU_SPEED_LOW_punct : &SPEED_LOW_punct);
    case SpeedMode::TURBO:
      return (t_punct*) (russian_language ? &RU_SPEED_TURBO_punct : &SPEED_TURBO_punct);
    case SpeedMode::MAXIMUM:
    default:
      return (t_punct*) (russian_language ? &RU_SPEED_HIGH_punct : &SPEED_HIGH_punct);
  }
}

static t_punct* random_punct(void) {
  if(random_mode_is_mk61s()) {
    return (t_punct*) (russian_language ? &RU_RANDOM_MK61S_punct : &RANDOM_MK61S_punct);
  }
  return (t_punct*) (russian_language ? &RU_RANDOM_MK61_punct : &RANDOM_MK61_punct);
}

static t_punct* idle_signal_punct(void) {
  if(idle_signal_is_on()) return (t_punct*) (russian_language ? &RU_IDLE_SIGNAL_ON_punct : &IDLE_SIGNAL_ON_punct);
  return (t_punct*) (russian_language ? &RU_IDLE_SIGNAL_OFF_punct : &IDLE_SIGNAL_OFF_punct);
}

#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
static t_punct* display_rows_punct(void) {
  return (t_punct*) (russian_language ? &RU_ROWS_punct : &ROWS_punct);
}
#endif

static void format_volume_text(void) {
  int used = snprintf(VOLUME_punct.text, sizeof(VOLUME_punct.text), "Volume %u", (unsigned) sound_volume_state);
  if(used < 0) used = 0;
  if(used > 15) used = 15;
  while(used < 15) VOLUME_punct.text[used++] = ' ';
  VOLUME_punct.text[used] = 0;
  VOLUME_punct.size = 15;

  snprintf(RU_VOLUME_punct.text, sizeof(RU_VOLUME_punct.text), "Громкость %u", (unsigned) sound_volume_state);
  RU_VOLUME_punct.size = 15;
}

#if defined(MK61_OLED1602_WS0010)
static t_punct* oled_timeout_punct(void) {
  static const t_punct* const EN[] = {
    &OLED_TIMEOUT_OFF_punct, &OLED_TIMEOUT_5M_punct,
    &OLED_TIMEOUT_15M_punct, &OLED_TIMEOUT_30M_punct
  };
  static const t_punct* const RU[] = {
    &RU_OLED_TIMEOUT_OFF_punct, &RU_OLED_TIMEOUT_5M_punct,
    &RU_OLED_TIMEOUT_15M_punct, &RU_OLED_TIMEOUT_30M_punct
  };
  const u8 index = oled_timeout_state & 3u;
  return (t_punct*) (russian_language ? RU[index] : EN[index]);
}
#endif

#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
static void format_display_rows_text(void) {
  int used = snprintf(ROWS_punct.text, sizeof(ROWS_punct.text), "Font %s",
    fontPresetName(display_text_profile_state));
  if(used < 0) used = 0;
  if(used > 15) used = 15;
  while(used < 15) ROWS_punct.text[used++] = ' ';
  ROWS_punct.text[used] = 0;
  ROWS_punct.size = 15;

  snprintf(RU_ROWS_punct.text, sizeof(RU_ROWS_punct.text), "Шрифт %s",
    fontPresetName(display_text_profile_state));
  RU_ROWS_punct.size = 15;
}
#endif

void refresh_menu_text(void) {
  format_volume_text();
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
  format_display_rows_text();
#endif

  MENU[MENU_DFU]      = (t_punct*) (russian_language ? &RU_DFU_mode_punct : &DFU_mode_punct);
  MENU[MENU_SETTINGS] = (t_punct*) (russian_language ? &RU_SETTINGS_punct : &SETTINGS_punct);
  MENU[MENU_USB_DISK] = (t_punct*) (russian_language ? &RU_USB_DISK_punct : &USB_DISK_punct);
  MENU[MENU_LIBRARY]  = (t_punct*) (russian_language ? &RU_LIB_61_punct : &LIB_61_punct);
  MENU[MENU_EXPLORER] = (t_punct*) (russian_language ? &RU_EXPLORER_punct : &EXPLORER_punct);
  MENU[MENU_DEVELOP]  = (t_punct*) (russian_language ? &RU_DEVELOPMENT_punct : &DEVELOPMENT_punct);
  MENU[MENU_RESET]    = (t_punct*) (russian_language ? &RU_RESET_punct : &RESET_punct);
  MENU[MENU_ERASE]    = (t_punct*) (russian_language ? &RU_ERASE_punct : &ERASE_punct);
  MENU[MENU_INFO]     = (t_punct*) (russian_language ? &RU_FLASH_punct : &FLASH_punct);
  MENU[MENU_HW]       = (t_punct*) (russian_language ? &RU_HARDWARE_punct : &HARDWARE_punct);

  SETTINGS_MENU[SETTINGS_VOLUME]   = (t_punct*) (russian_language ? &RU_VOLUME_punct : &VOLUME_punct);
  SETTINGS_MENU[SETTINGS_IDLE_SIGNAL] = idle_signal_punct();
  SETTINGS_MENU[SETTINGS_SPEED]    = speed_punct();
  SETTINGS_MENU[SETTINGS_MEMORY]   = memory_punct();
  SETTINGS_MENU[SETTINGS_RANDOM]   = random_punct();
  SETTINGS_MENU[SETTINGS_DATE_TIME] = (t_punct*) (russian_language ? &RU_DATE_TIME_punct : &DATE_TIME_punct);
  SETTINGS_MENU[SETTINGS_RTC_CALIBRATION] = (t_punct*) (
    russian_language ? &RU_RTC_CALIBRATION_punct : &RTC_CALIBRATION_punct);
  SETTINGS_MENU[SETTINGS_LANGUAGE] = (t_punct*) (russian_language ? &LANGUAGE_RU_punct : &LANGUAGE_EN_punct);
#if defined(MK61_OLED1602_WS0010)
  SETTINGS_MENU[SETTINGS_OLED_TIMEOUT] = oled_timeout_punct();
#endif
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
  SETTINGS_MENU[SETTINGS_DISPLAY_ROWS] = display_rows_punct();
#endif
}

bool  store_settings_state(void) {
  SettingsFlags flags;
  flags.bits.language_ru = russian_language;
  flags.bits.program_memory_mode = (u8) memory_mode;
  flags.bits.speed_mode = (u8) speed_mode_state;
  flags.bits.random_mode_mk61s = random_mode_is_mk61s() ? 1 : 0;
  flags.bits.idle_signal_off = idle_signal_state ? 0 : 1;
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
  flags.bits.display_rows_8 = (display_text_profile_state.rows == lcd_display::COMPACT_ROWS) ? 1 : 0;
#else
  flags.bits.display_rows_8 = 0;
#endif
  SoundSettings sound_settings;
  sound_settings.bits.volume = sound_volume_state;
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
  sound_settings.bits.display_rows_mode = display_rows_mode(display_text_profile_state);
#endif

#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS && MK61_ENABLE_EXTENDED_FONT_SETTINGS
  const lcd_display::TextProfile* stored_profile = &display_text_profile_state;
#else
  const lcd_display::TextProfile* stored_profile = NULL;
#endif
#if defined(MK61_OLED1602_WS0010)
  OledSettings oled_settings = read_oled_settings();
  oled_settings.setTimeout(oled_timeout_state);
  return store_settings_snapshot(flags, sound_settings, stored_profile,
                                 &oled_settings);
#else
  return store_settings_snapshot(flags, sound_settings, stored_profile);
#endif
}

void mark_settings_dirty(void) {
  settings_save.schedule(millis(), SETTINGS_SAVE_IDLE_MS);
}

void defer_settings_state_save(void) {
  if(settings_save.pending()) settings_save.schedule(millis(), SETTINGS_SAVE_IDLE_MS);
}

void flush_settings_state(void) {
  if(!settings_save.pending()) return;
  if(store_settings_state()) {
    settings_save.clear();
  } else {
    settings_save.schedule(millis(), SETTINGS_SAVE_IDLE_MS);
  }
}

void poll_settings_state_save(void) {
  if(settings_save.due(millis())) flush_settings_state();
}

void  load_settings_state(void) {
  const SettingsFlags flags = read_settings_flags();
  const SoundSettings sound_settings = read_sound_settings();
  set_language_state(flags.bits.language_ru != 0);
  const u8 stored_memory = flags.bits.program_memory_mode;
  memory_mode = (stored_memory <= (u8) ProgramMemoryMode::AUTO) ? (ProgramMemoryMode) stored_memory : ProgramMemoryMode::AUTO;
  set_program_memory_state(memory_mode == ProgramMemoryMode::EXPANDED_112);
  const u8 stored_speed = flags.bits.speed_mode;
  set_speed_mode_state((stored_speed <= (u8) SpeedMode::TURBO) ? (SpeedMode) stored_speed : SpeedMode::MAXIMUM);
  set_random_mode_state(flags.bits.random_mode_mk61s ? RandomMode::MK61S : RandomMode::MK61);
  set_idle_signal_state(flags.bits.idle_signal_off == 0);
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
  const u8 stored_rows_mode = sound_settings.bits.display_rows_mode;
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  lcd_display::TextProfile stored_profile;
  if(read_display_text_profile(stored_profile)) {
    set_display_text_profile(stored_profile);
  } else {
#endif
    set_display_rows((stored_rows_mode == 0 && flags.bits.display_rows_8)
      ? lcd_display::FONT_3X5_ROWS
      : display_rows_from_mode(stored_rows_mode));
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  }
#endif
#else
  set_display_rows(lcd_display::DEFAULT_ROWS);
#endif
  set_sound_volume(sound_settings.bits.volume);
#if defined(MK61_OLED1602_WS0010)
  set_oled_timeout(read_oled_settings().timeout());
#endif
  refresh_menu_text();
}

SpeedMode speed_mode(void) {
  return speed_mode_state;
}

bool  speed_is_classic(void) {
  return speed_mode_state == SpeedMode::CLASSIC;
}

bool  speed_is_max(void) {
  return speed_mode_state != SpeedMode::CLASSIC;
}

bool  speed_is_turbo(void) {
  return speed_mode_state == SpeedMode::TURBO;
}

} // пространство имён library_mk61

bool ResetDevice(void) {
  library_mk61::store_settings_state();
  NVIC_SystemReset();

  return action::MENU_EXIT;
}

bool   TurnSpeed(void) {
  switch(library_mk61::speed_mode()) {
    case SpeedMode::MAXIMUM:
      library_mk61::set_speed_mode_state(SpeedMode::CLASSIC);
      break;
    case SpeedMode::CLASSIC:
      library_mk61::set_speed_mode_state(SpeedMode::TURBO);
      break;
    case SpeedMode::TURBO:
      library_mk61::set_speed_mode_state(SpeedMode::MAXIMUM);
      break;
  }
  library_mk61::refresh_menu_text();
  library_mk61::mark_settings_dirty();

  return action::MENU_BACK;
}

static void StepSpeedMode(i8 delta) {
  SpeedMode next_mode = library_mk61::speed_mode();
  switch(library_mk61::speed_mode()) {
    case SpeedMode::CLASSIC:
      next_mode = (delta > 0) ? SpeedMode::MAXIMUM : SpeedMode::TURBO;
      break;
    case SpeedMode::MAXIMUM:
      next_mode = (delta > 0) ? SpeedMode::TURBO : SpeedMode::CLASSIC;
      break;
    case SpeedMode::TURBO:
      next_mode = (delta > 0) ? SpeedMode::CLASSIC : SpeedMode::MAXIMUM;
      break;
  }

  library_mk61::set_speed_mode_state(next_mode);
  library_mk61::refresh_menu_text();
  library_mk61::mark_settings_dirty();
}

bool   TurnSoundVolume(void) {
  sound_stop();
  const u8 next_volume = (library_mk61::sound_volume() >= 10) ? 0 : (library_mk61::sound_volume() + 1);
  library_mk61::set_sound_volume(next_volume);
  library_mk61::refresh_menu_text();
  library_mk61::mark_settings_dirty();

  return action::MENU_BACK;
}

static void ApplySoundVolume(u8 next_volume) {
  sound_stop();
  const u8 volume = library_mk61::sound_volume();
  if(next_volume == volume) return;

  library_mk61::set_sound_volume(next_volume);
  library_mk61::refresh_menu_text();
  library_mk61::mark_settings_dirty();
  sound(PIN_BUZZER, 2500, 20, library_mk61::sound_volume());
}

static void StepSoundVolume(i8 delta) {
  const u8 volume = library_mk61::sound_volume();

  u8 next_volume = volume;
  if(delta > 0 && volume < 10) {
    next_volume = volume + 1;
  } else if(delta < 0 && volume > 0) {
    next_volume = volume - 1;
  }

  ApplySoundVolume(next_volume);
}

static void CycleSoundVolumeUp(void) {
  const u8 volume = library_mk61::sound_volume();
  ApplySoundVolume((volume >= 10) ? 0 : (volume + 1));
}

bool SetDateTime(void) { return setup_ui::date_time(); }
bool SetRtcCalibration(void) { return setup_ui::calibration(); }
bool FontSetup(void) { return setup_ui::font(); }

bool settings_select(void) {
  library_mk61::refresh_menu_text();
  class_menu settings_menu = class_menu(
    (t_punct**) library_mk61::SETTINGS_MENU,
    library_mk61::current_settings_punct_count());
  settings_menu.select();
  library_mk61::defer_settings_state_save();
  library_mk61::refresh_menu_text();
  return action::MENU_BACK;
}

bool   TurnLanguage(void) {
  library_mk61::set_language_state(!library_mk61::language_is_ru());
  library_mk61::refresh_menu_text();
  library_mk61::mark_settings_dirty();

  return action::MENU_BACK;
}

static void draw_usb_disk_status(const char* ru0, const char* en0, const char* ru1, const char* en1) {
  if(library_mk61::language_is_ru()) {
    {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().clear();
    }
    lcd_ru::print_lines(ru0, ru1);
    return;
  }

  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();
  main_lcd().setCursor(0, 0);
  main_lcd().print(en0);
  main_lcd().setCursor(0, 1);
  main_lcd().print(en1);
}

bool UsbDiskMode(void) {
  draw_usb_disk_status("USB-диск", "USB Disk", "запуск...", "starting...");
  library_mk61::flush_settings_state();
  if(!program_store::refresh()) {
    if(program_store::mount_status() ==
       program_store::MountStatus::REPAIR_REQUIRED) {
      draw_usb_disk_status("ФС повреждена", "FS damaged",
                           "нужен формат", "format needed");
    } else {
      draw_usb_disk_status("Ошибка ФС", "FS error", "ESC", "ESC");
    }
    kbd::get_key_wait();
    return action::MENU_BACK;
  }
  (void) program_store::purge_empty();
  if(!usb_start_mass_storage_mode()) {
    usb_start_terminal_mode();
    draw_usb_disk_status("Ошибка USB", "USB error", "ESC", "ESC");
    kbd::get_key_wait();
    return action::MENU_BACK;
  }

  draw_usb_disk_status("USB-диск", "USB Disk", "ESC выход", "ESC exit");
  const u32 host_configuration_deadline = millis() + 15000U;
  bool host_was_configured = false;
  bool host_configuration_timeout = false;
  while(true) {
    idle_main_process();
    if(usb_mass_storage::host_configured()) host_was_configured = true;
    // Safe host eject already includes SYNCHRONIZE CACHE.  Return CDC
    // automatically after the SCSI command completes instead of leaving an
    // ejected, inaccessible disk on screen until a physical ESC is pressed.
    if(usb_mass_storage::host_ejected()) break;
    // A locked macOS host may enumerate VID/PID but intentionally withhold
    // SET_CONFIGURATION. Do not strand the calculator forever in an MSC mode
    // that no host can use; once configured, ordinary long sessions remain
    // unlimited and can still be ended by eject or ESC.
    if(!host_was_configured &&
       (i32) (millis() - host_configuration_deadline) >= 0) {
      host_configuration_timeout = true;
      break;
    }
    const i32 key = kbd::poll_event().code();

    if(key == KEY_ESC_PRESS) {
      kbd::handoff(kbd::Event(key));
      break;
    }
  }

  const bool clean_exit = usb_start_terminal_mode();
  if(host_configuration_timeout) {
    draw_usb_disk_status("Хост не готов", "Host timeout",
                         "USB заблок.", "USB blocked");
    delay(900);
  } else if(!clean_exit) {
    char error_code[10];
    virtual_fat::format_error_code(virtual_fat::diagnostic().code, error_code);
    draw_usb_disk_status(error_code, error_code,
                         "подробно: vlog", "details: vlog");
    delay(900);
  }
  lcd_ru::restore_default_font();
  return action::MENU_EXIT;
}

bool UsbScreenMode(void) {
  draw_usb_disk_status("USB-экран", "USB Screen",
                       "ждём приложение", "start desktop app");
  if(!usb_screen::start()) {
    draw_usb_disk_status("Ошибка USB", "USB error", "ESC", "ESC");
    kbd::get_key_wait();
    return action::MENU_BACK;
  }

  // До handshake физический дисплей остаётся включён и показывает эту
  // подсказку. После ATTACH display backend сам гасит его до выхода из режима.
  while(usb_screen::state() == usb_screen::State::WAITING_FOR_HOST) {
    idle_main_process();
    const i32 key = kbd::poll_event().code();

    if(key == KEY_ESC_PRESS) {
      kbd::handoff(kbd::Event(key));
      usb_screen::cancel();
      lcd_ru::restore_default_font();
      return action::MENU_BACK;
    }
  }

  if(!usb_screen::attached()) {
    lcd_ru::restore_default_font();
    return action::MENU_BACK;
  }
  return action::MENU_EXIT;
}

bool TurnIdleSignal(void) {
  library_mk61::set_idle_signal_state(!library_mk61::idle_signal_is_on());
  library_mk61::refresh_menu_text();
  library_mk61::mark_settings_dirty();

  return action::MENU_BACK;
}

#if defined(MK61_OLED1602_WS0010)
bool TurnOledProtection(void) {
  library_mk61::set_oled_timeout(
    (u8) ((library_mk61::oled_timeout() + 1u) & 3u));
  library_mk61::refresh_menu_text();
  library_mk61::mark_settings_dirty();
  return action::MENU_BACK;
}

static void StepOledProtection(i8 delta) {
  const u8 current = library_mk61::oled_timeout();
  const u8 next = (u8) ((current + (delta > 0 ? 1u : 3u)) & 3u);
  library_mk61::set_oled_timeout(next);
  library_mk61::refresh_menu_text();
  library_mk61::mark_settings_dirty();
}
#endif

bool TurnDisplayRows(void) {
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
  return FontSetup();
#endif

  return action::MENU_BACK;
}

bool   TurnProgramMemory(void) {
  const bool was_expanded = library_mk61::expanded_program_is_on();

  switch(library_mk61::program_memory_mode()) {
    case ProgramMemoryMode::CLASSIC_105:
      library_mk61::set_program_memory_mode(ProgramMemoryMode::EXPANDED_112);
      break;
    case ProgramMemoryMode::EXPANDED_112:
      library_mk61::set_program_memory_mode(ProgramMemoryMode::AUTO);
      break;
    case ProgramMemoryMode::AUTO:
      library_mk61::set_program_memory_mode(ProgramMemoryMode::CLASSIC_105);
      break;
  }

  library_mk61::refresh_menu_text();
  library_mk61::mark_settings_dirty();

  if(was_expanded != library_mk61::expanded_program_is_on()) {
    reset_ext_program_state();
    core_61::enable();
  }

  return action::MENU_BACK;
}

static void StepProgramMemoryMode(i8 delta) {
  const bool was_expanded = library_mk61::expanded_program_is_on();

  ProgramMemoryMode next_mode = library_mk61::program_memory_mode();
  switch(library_mk61::program_memory_mode()) {
    case ProgramMemoryMode::CLASSIC_105:
      next_mode = (delta > 0) ? ProgramMemoryMode::EXPANDED_112 : ProgramMemoryMode::AUTO;
      break;
    case ProgramMemoryMode::EXPANDED_112:
      next_mode = (delta > 0) ? ProgramMemoryMode::AUTO : ProgramMemoryMode::CLASSIC_105;
      break;
    case ProgramMemoryMode::AUTO:
      next_mode = (delta > 0) ? ProgramMemoryMode::CLASSIC_105 : ProgramMemoryMode::EXPANDED_112;
      break;
  }

  library_mk61::set_program_memory_mode(next_mode);
  library_mk61::refresh_menu_text();
  library_mk61::mark_settings_dirty();

  if(was_expanded != library_mk61::expanded_program_is_on()) {
    reset_ext_program_state();
    core_61::enable();
  }
}

static void ApplyRandomMode(RandomMode mode) {
  library_mk61::set_random_mode_state(mode);
  entropy_pool::configure_calculator(mode == RandomMode::MK61S);
  library_mk61::refresh_menu_text();
  library_mk61::mark_settings_dirty();
}

bool TurnRandomMode(void) {
  ApplyRandomMode(library_mk61::random_mode_is_mk61s() ? RandomMode::MK61 : RandomMode::MK61S);
  return action::MENU_BACK;
}

static void StepRandomMode(i8 delta) {
  (void) delta;
  ApplyRandomMode(library_mk61::random_mode_is_mk61s() ? RandomMode::MK61 : RandomMode::MK61S);
}

bool  mk61_library_select(void) {
  const int n = select_program();
  if(n < 0) return action::MENU_BACK;

  if(!load_program(n)) return action::MENU_BACK;
  return action::MENU_EXIT;
}

bool  mk61_games_select(void) {
  const int n = select_game();
  if(n < 0) return action::MENU_BACK;

  if(!load_game(n)) return action::MENU_BACK;
  return action::MENU_EXIT;
}

bool class_menu::handle_settings_adjustment(i32 key) {
  if(puncts != library_mk61::SETTINGS_MENU) return false;

  switch(active_punct) {
    case library_mk61::SETTINGS_VOLUME:
      if(key == KEY_OK_PRESS) {
        CycleSoundVolumeUp();
        return true;
      }

      if(key == KEY_SHG_RIGHT_PRESS) {
        StepSoundVolume(1);
        return true;
      }

      if(key == KEY_SHG_LEFT_PRESS) {
        StepSoundVolume(-1);
        return true;
      }
      break;

    case library_mk61::SETTINGS_SPEED:
      if(key == KEY_OK_PRESS) {
        TurnSpeed();
        return true;
      }

      if(key == KEY_SHG_RIGHT_PRESS) {
        StepSpeedMode(1);
        return true;
      }

      if(key == KEY_SHG_LEFT_PRESS) {
        StepSpeedMode(-1);
        return true;
      }
      break;

    case library_mk61::SETTINGS_MEMORY:
      if(key == KEY_OK_PRESS) {
        TurnProgramMemory();
        return true;
      }

      if(key == KEY_SHG_RIGHT_PRESS) {
        StepProgramMemoryMode(1);
        return true;
      }

      if(key == KEY_SHG_LEFT_PRESS) {
        StepProgramMemoryMode(-1);
        return true;
      }
      break;

    case library_mk61::SETTINGS_RANDOM:
      if(key == KEY_OK_PRESS) {
        TurnRandomMode();
        return true;
      }

      if(key == KEY_SHG_RIGHT_PRESS) {
        StepRandomMode(1);
        return true;
      }

      if(key == KEY_SHG_LEFT_PRESS) {
        StepRandomMode(-1);
        return true;
      }
      break;

    case library_mk61::SETTINGS_LANGUAGE:
      if(key == KEY_OK_PRESS) {
        TurnLanguage();
        return true;
      }

      if(key == KEY_SHG_RIGHT_PRESS || key == KEY_SHG_LEFT_PRESS) {
        TurnLanguage();
        return true;
      }
      break;

    case library_mk61::SETTINGS_IDLE_SIGNAL:
      if(key == KEY_OK_PRESS) {
        TurnIdleSignal();
        return true;
      }

      if(key == KEY_SHG_RIGHT_PRESS || key == KEY_SHG_LEFT_PRESS) {
        TurnIdleSignal();
        return true;
      }
      break;

#if defined(MK61_OLED1602_WS0010)
    case library_mk61::SETTINGS_OLED_TIMEOUT:
      if(key == KEY_OK_PRESS) {
        TurnOledProtection();
        return true;
      }
      if(key == KEY_SHG_RIGHT_PRESS || key == KEY_RIGHT_PRESS) {
        StepOledProtection(1);
        return true;
      }
      if(key == KEY_SHG_LEFT_PRESS || key == KEY_LEFT_PRESS) {
        StepOledProtection(-1);
        return true;
      }
      break;
#endif

#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
    case library_mk61::SETTINGS_DISPLAY_ROWS:
      if(key == KEY_OK_PRESS) {
        FontSetup();
        return true;
      }

      if(key == KEY_SHG_RIGHT_PRESS || key == KEY_SHG_LEFT_PRESS || key == KEY_RIGHT_PRESS || key == KEY_LEFT_PRESS) {
        setup_ui::step_font((key == KEY_SHG_LEFT_PRESS || key == KEY_LEFT_PRESS) ? -1 : 1);
        draw();
        return true;
      }
      break;
#endif
  }

  return false;
}

void class_menu::draw(void) {
  MK61DisplayUpdate update(main_lcd());
  const int size_menu_window = main_lcd().rows();
  const int visible_count = (MENU_PUNCT_COUNT < size_menu_window) ? MENU_PUNCT_COUNT : size_menu_window;
  const int max_up = MENU_PUNCT_COUNT - visible_count;
  const int delta = (active_punct + 1) - visible_count;
  int up = (delta <= 0)? 0 : delta;
  if(up > max_up) up = max_up;

  if(library_mk61::language_is_ru()) {
    if(visible_count == 2) {
      const int top_index = up;
      const int bottom_index = up + 1;
      lcd_ru::print_menu_window(
        (active_punct == top_index)? '>' : ' ', puncts[top_index]->text,
        (active_punct == bottom_index)? '>' : ' ', puncts[bottom_index]->text
      );
    } else {
      for(int i=0; i < visible_count; i++) {
        const int real_index = i + up;
        lcd_ru::print_menu_line(i, (active_punct == real_index)? '>' : ' ', puncts[real_index]->text);
      }
    }
    for(int i=visible_count; i < size_menu_window; i++) {
      main_lcd().setCursor(0, i);
      for(int x=0; x < lcd_display::COLS; x++) main_lcd().write((u8) ' ');
    }
    previous_up = up;
    return;
  }

  for(int i=0; i < visible_count; i++) {
    main_lcd().setCursor(0,  i);
    const int real_index = i + up;
    const int previous_real_index = i + previous_up;

    // формируем постоянную часть пункта меню
    main_lcd().print( (active_punct == real_index)?  '>'  :  ' ' );
    main_lcd().print(puncts[real_index]->text);

    int previous_punct_size = puncts[previous_real_index]->size;
    const int size = puncts[real_index]->size;
    // формируем переменную часть пункта меню
    while(previous_punct_size-- > size) {
      main_lcd().print(' ');
    }
  }
  for(int i=visible_count; i < size_menu_window; i++) {
    main_lcd().setCursor(0, i);
    for(int x=0; x < lcd_display::COLS; x++) main_lcd().write((u8) ' ');
  }
  previous_up = up;
}

i32 class_menu::wait_key(void) {
#if MK61_ENABLE_USB_SCREEN
  u32 display_mode_revision = main_lcd().displayModeRevision();
#endif
  do {
    idle_main_process();
#if MK61_ENABLE_USB_SCREEN
    const u32 next_display_mode_revision =
      main_lcd().displayModeRevision();
    if(next_display_mode_revision != display_mode_revision) {
      display_mode_revision = next_display_mode_revision;
      draw();
    }
#endif

    const i32 scan_code = kbd::poll_event().code();

    if(scan_code >= 0 && scan_code < (i32) key_state::RELEASED) {
      return scan_code;
    }
  } while(true);
}

bool class_menu::select(void) {
  main_lcd().clear();
  do{
    draw();
    const i32 last_key_code = wait_key();
    if(handle_settings_adjustment(last_key_code)) continue;
    switch(last_key_code) {
      case KEY_RIGHT_PRESS:
              if(active_punct < (MENU_PUNCT_COUNT-1)) active_punct++;
        break;
      case KEY_LEFT_PRESS:
              if(active_punct > 0) active_punct--;
        break;
      case KEY_OK_PRESS:
            kbd::handoff(kbd::Event(last_key_code));
            dbgln(MENU, "Select menu: '", puncts[active_punct]->text, "\'");
            main_lcd().clear();
            lcd_ru::restore_default_font();
            if(puncts[active_punct]->action() == action::MENU_EXIT) {
              return action::MENU_EXIT;
            } else {
              main_lcd().clear();
              break;
            }
      case KEY_ESC_PRESS:
            kbd::handoff(kbd::Event(last_key_code));
            lcd_ru::restore_default_font();
            return action::MENU_BACK; // отмена
    }
  } while(true);
}

i32 class_menu::select(i32 key) {
  main_lcd().clear();
  dbgln(MENU, "select entry");

  if(handle_settings_adjustment(key)) {
    draw();
    dbgln(MENU, "select exit");
    return 0;
  }

  switch(key) {
      case KEY_RIGHT_PRESS:
              if(active_punct < (MENU_PUNCT_COUNT-1)) active_punct++;
        break;
      case KEY_LEFT_PRESS:
              if(active_punct > 0) active_punct--;
        break;
      case KEY_OK_PRESS:
            kbd::handoff(kbd::Event(key));
            dbgln(MENU, "Select menu: '", puncts[active_punct]->text, "\'");
            main_lcd().clear();
            lcd_ru::restore_default_font();
            if(puncts[active_punct]->action() == action::MENU_EXIT) {
              return -1;
            } else {
              main_lcd().clear();
              break;
            }
      case KEY_ESC_PRESS:
            kbd::handoff(kbd::Event(key));
            lcd_ru::restore_default_font();
            return -1; // отмена
    }

  draw();
  dbgln(MENU, "select exit");
  return 0;
}
