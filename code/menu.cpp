#include <stdio.h>
#include <string.h>
#include "config.h"
#include "menu.hpp"
#include "cross_hal.h"
#include "lcd_ru.hpp"
#include "basic.hpp"
#include "development.hpp"
#include "focal.hpp"
#include "tinybasic.hpp"

extern MK61Display lcd;
extern t_time_ms runtime_ms;
extern void idle_main_process(void);
extern void reset_ext_program_state(void);
extern bool usb_start_mass_storage_mode(void);
extern void usb_start_terminal_mode(void);
extern isize mk61_quants_reload;

namespace library_mk61 {

static constexpr int MENU_DFU      = 0;
static constexpr int MENU_USB_DISK = 1;
static constexpr int MENU_SETTINGS = 2;
static constexpr int MENU_GAMES    = 3;
static constexpr int MENU_LIBRARY  = 4;
static constexpr int MENU_AFTER_LIBRARY = MENU_LIBRARY + 1;
static constexpr int MENU_DEVELOP  = MENU_AFTER_LIBRARY;
static constexpr int MENU_RESET    = MENU_DEVELOP + 1;
static constexpr int MENU_ERASE    = MENU_RESET + 1;
static constexpr int MENU_INFO     = MENU_ERASE + 1;
static constexpr int MENU_HW       = MENU_INFO + 1;

static constexpr int SETTINGS_VOLUME  = 0;
static constexpr int SETTINGS_IDLE_SIGNAL = 1;
static constexpr int SETTINGS_SPEED   = 2;
static constexpr int SETTINGS_MEMORY  = 3;
static constexpr int SETTINGS_LANGUAGE = 4;
static constexpr int SETTINGS_DISPLAY_ROWS = 5;

static u8 sound_volume_state = 10;
static SpeedMode speed_mode_state = SpeedMode::MAXIMUM;
static bool russian_language = false;
static bool expanded_program = false;
static bool idle_signal_state = true;
static u8 display_rows_state = lcd_display::DEFAULT_ROWS;
static ProgramMemoryMode memory_mode = ProgramMemoryMode::AUTO;
static DeferredSave settings_save;
static constexpr t_time_ms SETTINGS_SAVE_IDLE_MS = 1000;

struct MutablePunct {
  u8            size;
  menu_action   action;
  char          text[32];
};

static MutablePunct VOLUME_punct = {.size = 15, .action = (menu_action) &TurnSoundVolume, .text = "Volume 10      "};
static MutablePunct RU_VOLUME_punct = {.size = 15, .action = (menu_action) &TurnSoundVolume, .text = "Громкость 10"};
#if defined(MK61_DISPLAY_UC1609)
static MutablePunct ROWS_punct = {.size = 15, .action = (menu_action) &TurnDisplayRows, .text = "Rows: 4        "};
static MutablePunct RU_ROWS_punct = {.size = 15, .action = (menu_action) &TurnDisplayRows, .text = "Строк: 4"};
#endif

#if defined(MK61_DISPLAY_UC1609)
static constexpr u8 DISPLAY_ROW_OPTIONS[] = {
  lcd_display::DEFAULT_ROWS,
  lcd_display::SPACED_ROWS_5,
  lcd_display::SPACED_ROWS_7,
  lcd_display::COMPACT_ROWS
};

static u8 normalize_display_rows(u8 rows) {
  for(u8 i = 0; i < sizeof(DISPLAY_ROW_OPTIONS) / sizeof(DISPLAY_ROW_OPTIONS[0]); i++) {
    if(DISPLAY_ROW_OPTIONS[i] == rows) return rows;
  }
  return lcd_display::DEFAULT_ROWS;
}

static u8 display_rows_mode(u8 rows) {
  rows = normalize_display_rows(rows);
  for(u8 i = 0; i < sizeof(DISPLAY_ROW_OPTIONS) / sizeof(DISPLAY_ROW_OPTIONS[0]); i++) {
    if(DISPLAY_ROW_OPTIONS[i] == rows) return i;
  }
  return 0;
}

static u8 display_rows_from_mode(u8 mode) {
  return (mode < sizeof(DISPLAY_ROW_OPTIONS) / sizeof(DISPLAY_ROW_OPTIONS[0]))
    ? DISPLAY_ROW_OPTIONS[mode]
    : lcd_display::DEFAULT_ROWS;
}

static u8 step_display_rows_value(u8 rows, i8 delta) {
  const u8 count = sizeof(DISPLAY_ROW_OPTIONS) / sizeof(DISPLAY_ROW_OPTIONS[0]);
  u8 index = display_rows_mode(rows);
  if(delta >= 0) {
    index = (u8) ((index + 1) % count);
  } else {
    index = (index == 0) ? (count - 1) : (u8) (index - 1);
  }
  return DISPLAY_ROW_OPTIONS[index];
}
#endif

static void set_speed_mode_state(SpeedMode mode) {
  speed_mode_state = mode;
  ::mk61_quants_reload = (mode == SpeedMode::CLASSIC) ? cfg::CLASSIC_MK61_QUANTS : 1;
}

static void append_text(char*& out, char* end, const char* text) {
  while(*text != 0 && out < end) *out++ = *text++;
}

static void append_until_space(char*& out, char* end, const char* text) {
  while(*text != 0 && *text != ' ' && out < end) *out++ = *text++;
}

static void build_ru_memory_text(char* out, usize size) {
  char* cursor = out;
  char* end = out + size - 1;
  const char* ram = strstr(mem_text, "RAM:");
  const char* rom = strstr(mem_text, "ROM:");

  if(ram == NULL || rom == NULL) {
    append_text(cursor, end, mem_text);
    *cursor = 0;
    return;
  }

  append_text(cursor, end, "ОЗУ:");
  append_until_space(cursor, end, ram + 4);
  append_text(cursor, end, " ПЗУ:");
  append_until_space(cursor, end, rom + 4);
  *cursor = 0;
}

bool  HardwareInfo(void) {
  {
    MK61DisplayUpdate update(lcd);
    lcd.clear();
    if(language_is_ru()) {
      char chip_line[24] = "ЧИП:";
      char memory_line[32];
      char* cursor = &chip_line[sizeof("ЧИП:") - 1];
      append_text(cursor, chip_line + sizeof(chip_line) - 1, chip_name);
      *cursor = 0;
      build_ru_memory_text(memory_line, sizeof(memory_line));
      lcd_ru::print_lines(chip_line, memory_line);
    } else {
      lcd.setCursor(0, 0);
      lcd.print("Chip:");
      lcd.print(chip_name);
      lcd.setCursor(0,1);
      lcd.print(mem_text);
    }
  }
  kbd::get_key_wait();
  return action::MENU_BACK;
}

bool  InfoData(void) {
  if(language_is_ru()) {
    char line0[24];
    char line1[24];
    snprintf(line0, sizeof(line0), "СЧ:%u УГ:%u%s",
      (u32) read_counter_switch(),
      (u32) ((u8) read_grade_switch()),
      flash_is_ok ? " ФЛ" : "");
    snprintf(line1, sizeof(line1), "ВР:%lu МС", (unsigned long) runtime_ms);
    lcd_ru::print_lines(line0, line1);
  } else {
    MK61DisplayUpdate update(lcd);
    lcd.clear();
    lcd.setCursor(0,0);
    lcd.print("cnt:"); lcd.print(read_counter_switch());
    lcd.print(" sw:"); lcd.print((u8) read_grade_switch());
    if(flash_is_ok) lcd.print(" W25");
    lcd.setCursor(0,1);
    lcd.print("run "); lcd.print(runtime_ms); lcd.print(" ms");
  }
  kbd::get_key_wait();
  return false;
}

const t_punct DFU_mode_punct      = {.size = 15, .action = (menu_action) &DFU_enable,           .text = "DFU mode enable"};
const t_punct USB_DISK_punct      = {.size = 8,  .action = (menu_action) &UsbDiskMode,          .text = "USB Disk"};
const t_punct SETTINGS_punct      = {.size = 8,  .action = &settings_select,                    .text = "Settings"};
const t_punct LIB_61_punct        = {.size = 12, .action = &mk61_library_select,                .text = "MK61 library"};
const t_punct GAME_61_punct       = {.size = 10, .action = &mk61_games_select,                  .text = "MK61 Games"};
const t_punct DEVELOPMENT_punct   = {.size = 11, .action = &development_select,                 .text = "Development"};
const t_punct RESET_punct         = {.size = 12, .action = &ResetDevice,                        .text = "Reset device"};
const t_punct ERASE_punct         = {.size = 12, .action = (menu_action) &EraseFlash,           .text = "Erase FLASH!"};
const t_punct SPEED_LOW_punct     = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Speed CLASSIC  "};
const t_punct SPEED_HIGH_punct    = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Speed MAXIMUM  "};
const t_punct SPEED_TURBO_punct   = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Speed TURBO    "};
const t_punct MEMORY_105_punct    = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Memory 105     "};
const t_punct MEMORY_112_punct    = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Memory 112+F   "};
const t_punct MEMORY_AUTO_punct   = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Memory Auto    "};
const t_punct LANGUAGE_EN_punct   = {.size = 15, .action = (menu_action) &TurnLanguage,         .text = "Language EN    "};
const t_punct LANGUAGE_RU_punct   = {.size = 15, .action = (menu_action) &TurnLanguage,         .text = "Язык рус"};
const t_punct IDLE_SIGNAL_OFF_punct = {.size = 15, .action = (menu_action) &TurnIdleSignal,     .text = "5 min beep OFF "};
const t_punct IDLE_SIGNAL_ON_punct  = {.size = 15, .action = (menu_action) &TurnIdleSignal,     .text = "5 min beep ON  "};
const t_punct FLASH_punct         = {.size = 11, .action = (menu_action) &InfoData,             .text = "Information"};
const t_punct HARDWARE_punct      = {.size = 8,  .action = (menu_action) &HardwareInfo,         .text = "Hardware"};

const t_punct RU_DFU_mode_punct   = {.size = 15, .action = (menu_action) &DFU_enable,           .text = "DFU прошивка"};
const t_punct RU_USB_DISK_punct   = {.size = 15, .action = (menu_action) &UsbDiskMode,          .text = "USB-диск"};
const t_punct RU_SETTINGS_punct   = {.size = 15, .action = &settings_select,                    .text = "Настройки"};
const t_punct RU_LIB_61_punct     = {.size = 15, .action = &mk61_library_select,                .text = "Библиотека"};
const t_punct RU_GAME_61_punct    = {.size = 15, .action = &mk61_games_select,                  .text = "Игры MK61"};
const t_punct RU_DEVELOPMENT_punct= {.size = 15, .action = &development_select,                 .text = "Разработка"};
const t_punct RU_RESET_punct      = {.size = 15, .action = &ResetDevice,                        .text = "Сброс"};
const t_punct RU_ERASE_punct      = {.size = 15, .action = (menu_action) &EraseFlash,           .text = "Стереть FLASH"};
const t_punct RU_SPEED_LOW_punct  = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Скорость норма"};
const t_punct RU_SPEED_HIGH_punct = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Скорость макс"};
const t_punct RU_SPEED_TURBO_punct= {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Скорость турбо"};
const t_punct RU_MEMORY_105_punct = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Память 105ШГ"};
const t_punct RU_MEMORY_112_punct = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Память 112ШГ+ПF"};
const t_punct RU_MEMORY_AUTO_punct= {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Память АВТО"};
const t_punct RU_IDLE_SIGNAL_OFF_punct = {.size = 15, .action = (menu_action) &TurnIdleSignal,  .text = "5 мин звук выкл"};
const t_punct RU_IDLE_SIGNAL_ON_punct  = {.size = 15, .action = (menu_action) &TurnIdleSignal,  .text = "5 мин звук вкл"};
const t_punct RU_FLASH_punct      = {.size = 15, .action = (menu_action) &InfoData,             .text = "Информация"};
const t_punct RU_HARDWARE_punct   = {.size = 15, .action = (menu_action) &HardwareInfo,         .text = "Плата"};

t_punct* MENU[] = {
      (t_punct*) &DFU_mode_punct,
      (t_punct*) &USB_DISK_punct,
      (t_punct*) &SETTINGS_punct,
      (t_punct*) &GAME_61_punct,
      (t_punct*) &LIB_61_punct,
      (t_punct*) &DEVELOPMENT_punct,
      (t_punct*) &RESET_punct,
      (t_punct*) &ERASE_punct,
      (t_punct*) &FLASH_punct,
      (t_punct*) &HARDWARE_punct
};

extern const int COUNT_PUNCTS = sizeof(MENU) / sizeof(MENU[0]);

t_punct* SETTINGS_MENU[] = {
      (t_punct*) &VOLUME_punct,
      (t_punct*) &IDLE_SIGNAL_ON_punct,
      (t_punct*) &SPEED_HIGH_punct,
      (t_punct*) &MEMORY_AUTO_punct,
      (t_punct*) &LANGUAGE_EN_punct,
#if defined(MK61_DISPLAY_UC1609)
      (t_punct*) &ROWS_punct,
#endif
};

extern const int COUNT_SETTINGS_PUNCTS = sizeof(SETTINGS_MENU) / sizeof(SETTINGS_MENU[0]);

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

u8 display_rows(void) {
  return display_rows_state;
}

void set_display_rows(u8 rows) {
#if defined(MK61_DISPLAY_UC1609)
  display_rows_state = normalize_display_rows(rows);
#else
  (void) rows;
  display_rows_state = lcd_display::DEFAULT_ROWS;
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

static t_punct* idle_signal_punct(void) {
  if(idle_signal_is_on()) return (t_punct*) (russian_language ? &RU_IDLE_SIGNAL_ON_punct : &IDLE_SIGNAL_ON_punct);
  return (t_punct*) (russian_language ? &RU_IDLE_SIGNAL_OFF_punct : &IDLE_SIGNAL_OFF_punct);
}

#if defined(MK61_DISPLAY_UC1609)
static t_punct* display_rows_punct(void) {
  return (t_punct*) (russian_language ? &RU_ROWS_punct : &ROWS_punct);
}
#endif

static void format_volume_text(void) {
  int used = snprintf(VOLUME_punct.text, sizeof(VOLUME_punct.text), "Volume %u", (u32) sound_volume_state);
  if(used < 0) used = 0;
  if(used > 15) used = 15;
  while(used < 15) VOLUME_punct.text[used++] = ' ';
  VOLUME_punct.text[used] = 0;
  VOLUME_punct.size = 15;

  snprintf(RU_VOLUME_punct.text, sizeof(RU_VOLUME_punct.text), "Громкость %u", (u32) sound_volume_state);
  RU_VOLUME_punct.size = 15;
}

#if defined(MK61_DISPLAY_UC1609)
static void format_display_rows_text(void) {
  int used = snprintf(ROWS_punct.text, sizeof(ROWS_punct.text), "Rows: %u", (u32) display_rows_state);
  if(used < 0) used = 0;
  if(used > 15) used = 15;
  while(used < 15) ROWS_punct.text[used++] = ' ';
  ROWS_punct.text[used] = 0;
  ROWS_punct.size = 15;

  snprintf(RU_ROWS_punct.text, sizeof(RU_ROWS_punct.text), "Строк: %u", (u32) display_rows_state);
  RU_ROWS_punct.size = 15;
}
#endif

void refresh_menu_text(void) {
  format_volume_text();
#if defined(MK61_DISPLAY_UC1609)
  format_display_rows_text();
#endif

  MENU[MENU_DFU]      = (t_punct*) (russian_language ? &RU_DFU_mode_punct : &DFU_mode_punct);
  MENU[MENU_SETTINGS] = (t_punct*) (russian_language ? &RU_SETTINGS_punct : &SETTINGS_punct);
  MENU[MENU_USB_DISK] = (t_punct*) (russian_language ? &RU_USB_DISK_punct : &USB_DISK_punct);
  MENU[MENU_LIBRARY]  = (t_punct*) (russian_language ? &RU_LIB_61_punct : &LIB_61_punct);
  MENU[MENU_GAMES]    = (t_punct*) (russian_language ? &RU_GAME_61_punct : &GAME_61_punct);
  MENU[MENU_DEVELOP]  = (t_punct*) (russian_language ? &RU_DEVELOPMENT_punct : &DEVELOPMENT_punct);
  MENU[MENU_RESET]    = (t_punct*) (russian_language ? &RU_RESET_punct : &RESET_punct);
  MENU[MENU_ERASE]    = (t_punct*) (russian_language ? &RU_ERASE_punct : &ERASE_punct);
  MENU[MENU_INFO]     = (t_punct*) (russian_language ? &RU_FLASH_punct : &FLASH_punct);
  MENU[MENU_HW]       = (t_punct*) (russian_language ? &RU_HARDWARE_punct : &HARDWARE_punct);

  SETTINGS_MENU[SETTINGS_VOLUME]   = (t_punct*) (russian_language ? &RU_VOLUME_punct : &VOLUME_punct);
  SETTINGS_MENU[SETTINGS_IDLE_SIGNAL] = idle_signal_punct();
  SETTINGS_MENU[SETTINGS_SPEED]    = speed_punct();
  SETTINGS_MENU[SETTINGS_MEMORY]   = memory_punct();
  SETTINGS_MENU[SETTINGS_LANGUAGE] = (t_punct*) (russian_language ? &LANGUAGE_RU_punct : &LANGUAGE_EN_punct);
#if defined(MK61_DISPLAY_UC1609)
  SETTINGS_MENU[SETTINGS_DISPLAY_ROWS] = display_rows_punct();
#endif
}

void  store_settings_state(void) {
  SettingsFlags flags;
  flags.bits.language_ru = russian_language;
  flags.bits.program_memory_mode = (u8) memory_mode;
  flags.bits.speed_mode = (u8) speed_mode_state;
  flags.bits.reserved = 0;
  flags.bits.idle_signal_off = idle_signal_state ? 0 : 1;
#if defined(MK61_DISPLAY_UC1609)
  flags.bits.display_rows_8 = (display_rows_state == lcd_display::COMPACT_ROWS) ? 1 : 0;
#else
  flags.bits.display_rows_8 = 0;
#endif
  store_settings_flags(flags);

  SoundSettings sound_settings;
  sound_settings.bits.volume = sound_volume_state;
#if defined(MK61_DISPLAY_UC1609)
  sound_settings.bits.display_rows_mode = display_rows_mode(display_rows_state);
#endif
  store_sound_settings(sound_settings);
}

static void mark_settings_dirty(void) {
  settings_save.schedule(millis(), SETTINGS_SAVE_IDLE_MS);
}

void defer_settings_state_save(void) {
  if(settings_save.pending()) settings_save.schedule(millis(), SETTINGS_SAVE_IDLE_MS);
}

void flush_settings_state(void) {
  if(!settings_save.pending()) return;
  store_settings_state();
  settings_save.clear();
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
  set_idle_signal_state(flags.bits.idle_signal_off == 0);
#if defined(MK61_DISPLAY_UC1609)
  const u8 stored_rows_mode = sound_settings.bits.display_rows_mode;
  set_display_rows((stored_rows_mode == 0 && flags.bits.display_rows_8)
    ? lcd_display::COMPACT_ROWS
    : display_rows_from_mode(stored_rows_mode));
#else
  set_display_rows(lcd_display::DEFAULT_ROWS);
#endif
  set_sound_volume(sound_settings.bits.volume);
  refresh_menu_text();
}

SpeedMode speed_mode(void) {
  return speed_mode_state;
}

bool  speed_is_max(void) {
  return speed_mode_state != SpeedMode::CLASSIC;
}

bool  speed_is_turbo(void) {
  return speed_mode_state == SpeedMode::TURBO;
}

} // namespace library_mk61

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

bool settings_select(void) {
  library_mk61::refresh_menu_text();
  class_menu settings_menu = class_menu((t_punct**) library_mk61::SETTINGS_MENU, library_mk61::COUNT_SETTINGS_PUNCTS);
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
  MK61DisplayUpdate update(lcd);
  lcd.clear();
  library_mk61::print_localized_at(0, 0, ru0, en0);
  library_mk61::print_localized_at(0, 1, ru1, en1);
}

bool UsbDiskMode(void) {
  library_mk61::flush_settings_state();
  draw_usb_disk_status("USB-диск", "USB Disk", "Запуск...", "Starting...");

  if(!usb_start_mass_storage_mode()) {
    usb_start_terminal_mode();
    draw_usb_disk_status("Ошибка USB", "USB error", "ESC", "ESC");
    kbd::get_key_wait();
    return action::MENU_BACK;
  }

  draw_usb_disk_status("USB-диск", "USB Disk", "ESC выход", "ESC exit");
  while(true) {
    idle_main_process();
    const i32 key = kbd::scan_and_debounced();
    if(key == KEY_ESC_PRESS) {
      kbd::exclude_before(key);
      break;
    }
  }

  usb_start_terminal_mode();
  lcd_ru::restore_default_font();
  return action::MENU_EXIT;
}

bool TurnIdleSignal(void) {
  library_mk61::set_idle_signal_state(!library_mk61::idle_signal_is_on());
  library_mk61::refresh_menu_text();
  library_mk61::mark_settings_dirty();

  return action::MENU_BACK;
}

static void ApplyDisplayRows(u8 rows) {
#if defined(MK61_DISPLAY_UC1609)
  const u8 previous_rows = library_mk61::display_rows();
  library_mk61::set_display_rows(rows);
  if(library_mk61::display_rows() == previous_rows) return;

  lcd.setRows(library_mk61::display_rows());
  library_mk61::refresh_menu_text();
  library_mk61::mark_settings_dirty();
#else
  (void) rows;
#endif
}

bool TurnDisplayRows(void) {
#if defined(MK61_DISPLAY_UC1609)
  ApplyDisplayRows(library_mk61::step_display_rows_value(library_mk61::display_rows(), 1));
#endif

  return action::MENU_BACK;
}

static void StepDisplayRows(i8 delta) {
#if defined(MK61_DISPLAY_UC1609)
  ApplyDisplayRows(library_mk61::step_display_rows_value(library_mk61::display_rows(), delta));
#else
  (void) delta;
#endif
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

#if defined(MK61_DISPLAY_UC1609)
    case library_mk61::SETTINGS_DISPLAY_ROWS:
      if(key == KEY_OK_PRESS) {
        TurnDisplayRows();
        return true;
      }

      if(key == KEY_SHG_RIGHT_PRESS || key == KEY_SHG_LEFT_PRESS) {
        StepDisplayRows((key == KEY_SHG_LEFT_PRESS) ? -1 : 1);
        return true;
      }
      break;
#endif
  }

  return false;
}

void class_menu::draw(void) {
  MK61DisplayUpdate update(lcd);
  const int size_menu_window = lcd.rows();
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
      lcd.setCursor(0, i);
      for(int x=0; x < lcd_display::COLS; x++) lcd.write((u8) ' ');
    }
    previous_up = up;
    return;
  }

  for(int i=0; i < visible_count; i++) {
    lcd.setCursor(0,  i);
    const int real_index = i + up;
    const int previous_real_index = i + previous_up;

    // формируем постоянную часть пункта меню
    lcd.print( (active_punct == real_index)?  '>'  :  ' ' );
    lcd.print(puncts[real_index]->text);

    int previous_punct_size = puncts[previous_real_index]->size;
    const int size = puncts[real_index]->size;
    // формируем переменную часть пункта меню
    while(previous_punct_size-- > size) {
      lcd.print(' ');
    }
  }
  for(int i=visible_count; i < size_menu_window; i++) {
    lcd.setCursor(0, i);
    for(int x=0; x < lcd_display::COLS; x++) lcd.write((u8) ' ');
  }
  previous_up = up;
}

i32 class_menu::wait_key(void) {
  do {
    idle_main_process();

    const i32 scan_code = kbd::scan_and_debounced();
    if(scan_code >= 0 && scan_code < (i32) key_state::RELEASED) {
      kbd::exclude_before(scan_code);
      return scan_code;
    }
  } while(true);
}

bool class_menu::select(void) {
  lcd.clear();
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
            dbgln(MENU, "Select menu: '", puncts[active_punct]->text, "\'");
            lcd.clear();
            lcd_ru::restore_default_font();
            if(puncts[active_punct]->action() == action::MENU_EXIT) {
              return action::MENU_EXIT;
            } else {
              lcd.clear();
              break;
            }
      case KEY_ESC_PRESS:
            lcd_ru::restore_default_font();
            return action::MENU_BACK; // отмена
    }
  } while(true);
}

i32 class_menu::select(i32 key) {
  lcd.clear();
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
            dbgln(MENU, "Select menu: '", puncts[active_punct]->text, "\'");
            lcd.clear();
            lcd_ru::restore_default_font();
            if(puncts[active_punct]->action() == action::MENU_EXIT) {
              return -1;
            } else {
              lcd.clear();
              break;
            }
      case KEY_ESC_PRESS:
            lcd_ru::restore_default_font();
            return -1; // отмена
    }
  
  draw();
  dbgln(MENU, "select exit");
  return 0;
}
