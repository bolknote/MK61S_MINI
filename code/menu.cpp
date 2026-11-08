#include <stdio.h>
#include "config.h"
#include "menu.hpp"
#include "menu_model.hpp"
#include "cross_hal.h"
#include "lcd_ru.hpp"
#include "mk8_literal.hpp"
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
#include "compute_clock.hpp"

extern t_time_ms runtime_ms;
extern void idle_main_process(void);
extern void reset_ext_program_state(void);
extern void lcd_std_display_redraw(void);
extern bool usb_start_mass_storage_mode(void);
extern bool usb_start_terminal_mode(void);

namespace library_mk61 {

static constexpr int MENU_DFU      = 0;
static constexpr int MENU_USB_DISK = 1;
static constexpr int MENU_SETTINGS = 2;
static constexpr int MENU_EXPLORER = 3;
static constexpr int MENU_DEVELOP  = 4;
static constexpr int MENU_SYSTEM   = 5;

static constexpr int SYSTEM_RESTART = 0;
static constexpr int SYSTEM_INFO = 1;
#if MK61_ENABLE_SETUP
static constexpr int SYSTEM_HARDWARE = 2;
static constexpr int SYSTEM_FORMAT = 3;
static constexpr int SYSTEM_FULL_RESET = 4;
#else
static constexpr int SYSTEM_FORMAT = 2;
static constexpr int SYSTEM_FULL_RESET = 3;
#endif

static u8 sound_volume_state = 10;
static SpeedMode speed_mode_state = SpeedMode::MAXIMUM;
#if MK61_COMPUTE_CLOCK_SUPPORTED
static u8 compute_profile_state;
#endif
static bool russian_language = false;
static bool expanded_program = false;
static bool idle_signal_state = true;
#if defined(MK61_OLED1602_WS0010)
static u8 oled_timeout_state = DEFAULT_OLED_TIMEOUT;
#endif
static lcd_display::TextProfile display_text_profile_state = lcd_display::defaultSettingsTextProfile();
static u8 display_rows_state = lcd_display::defaultSettingsTextProfile().rows;
#if MK61_PROPORTIONAL_UI_FONTS
static UiFontSettings ui_font_state;
static u32 ui_font_key_state = 0;
#endif
static ProgramMemoryMode memory_mode = ProgramMemoryMode::AUTO;
static RandomMode random_mode_state = RandomMode::MK61;
static DeferredSave settings_save;
static constexpr t_time_ms SETTINGS_SAVE_IDLE_MS = 1000;

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

static u8 display_rows_mode(lcd_display::TextProfile profile) {
  profile = lcd_display::normalizeSettingsTextProfile(profile);
  if(sameTextProfile(profile, lcd_display::textProfile10x16())) return 2;
  if(sameTextProfile(profile, lcd_display::textProfile3x5())) return 3;
  return 0;
}

static u8 display_rows_from_mode(u8 mode) {
  switch(mode) {
    case 1:
      // Reserved legacy value: migrate the removed 5x9 preset to 5x8.
      return lcd_display::FONT_5X8_ROWS;
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
  char line0[24];
  char line1[24];
  if(language_is_ru()) {
    snprintf(line0, sizeof(line0), M8("СЧ:%u УГ:%u%s"),
      (unsigned) read_counter_switch(),
      (unsigned) ((u8) read_grade_switch()),
      flash_is_ok ? M8(" ФЛ") : "");
    snprintf(line1, sizeof(line1), M8("ВР:%lu МС"), (unsigned long) runtime_ms);
  } else {
    snprintf(line0, sizeof(line0), "cnt:%u sw:%u%s",
      (unsigned) read_counter_switch(),
      (unsigned) ((u8) read_grade_switch()),
      flash_is_ok ? " W25" : "");
    snprintf(line1, sizeof(line1), "run %lu ms", (unsigned long) runtime_ms);
  }
  {
    MK61DisplayUpdate update(main_lcd());
    main_lcd().clear();
    lcd_ru::print_lines(line0, line1);
  }
  kbd::get_key_wait();
  return false;
}

bool HardwareInfo(void) { return setup_ui::hardware(); }

#define MK61_MAIN_ITEM(id, en_object, ru_object, callback, width, en, ru) \
const t_punct en_object = {.size = width, .action = (menu_action)&callback, .text = en}; \
static constexpr auto ru_object = M8_PUNCT(15, &callback, ru);
#include "main_menu_items.inc"
#undef MK61_MAIN_ITEM
const t_punct RESET_punct         = {.size = 7,  .action = &ResetDevice,                        .text = "Restart"};
const t_punct FORMAT_punct        = {.size = 11, .action = &FormatDisk,                         .text = "Format disk"};
const t_punct ERASE_punct         = {.size = 10, .action = &EraseFlash,                         .text = "Full reset"};
const t_punct FLASH_punct         = {.size = 11, .action = (menu_action) &InfoData,             .text = "Information"};
const t_punct HARDWARE_punct      = {.size = 8,  .action = (menu_action) &HardwareInfo,         .text = "Hardware"};

static constexpr auto RU_RESET_punct = M8_PUNCT(15, &ResetDevice, "Перезагрузка");
static constexpr auto RU_FORMAT_punct = M8_PUNCT(15, &FormatDisk, "Формат диска");
static constexpr auto RU_ERASE_punct = M8_PUNCT(15, &EraseFlash, "Полный сброс");
// LCD1602 reserves one of its 16 cells for the selection marker.
static_assert(mk8::literal_size("Система") <= 16 &&
              mk8::literal_size("Перезагрузка") <= 16 &&
              mk8::literal_size("Формат диска") <= 16 &&
              mk8::literal_size("Полный сброс") <= 16,
              "System menu labels must fit A00/A02 with a cursor");
static constexpr auto RU_FLASH_punct = M8_PUNCT(15, &InfoData, "Информация");
static constexpr auto RU_HARDWARE_punct = M8_PUNCT(15, &HardwareInfo, "Плата");

t_punct* MENU[] = {
      (t_punct*) &DFU_mode_punct,
      (t_punct*) &USB_DISK_punct,
      (t_punct*) &SETTINGS_punct,
      (t_punct*) &EXPLORER_punct,
      (t_punct*) &DEVELOPMENT_punct,
      (t_punct*) &SYSTEM_punct
};

static_assert(sizeof(MENU) / sizeof(MENU[0]) == MAIN_MENU_COUNT,
              "Main menu count mismatch");
extern const int COUNT_PUNCTS = sizeof(MENU) / sizeof(MENU[0]);

t_punct* SYSTEM_MENU[] = {
      (t_punct*) &RESET_punct,
      (t_punct*) &FLASH_punct,
#if MK61_ENABLE_SETUP
      (t_punct*) &HARDWARE_punct,
#endif
      (t_punct*) &FORMAT_punct,
      (t_punct*) &ERASE_punct
};

static constexpr int SYSTEM_MENU_COUNT = sizeof(SYSTEM_MENU) / sizeof(SYSTEM_MENU[0]);
static_assert(SYSTEM_MENU_COUNT == SYSTEM_FULL_RESET + 1,
              "System menu item count mismatch");

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
  display_text_profile_state = main_lcd().externalTextFontActive()
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

void refresh_menu_text(void) {
  MENU[MENU_DFU]      = (t_punct*) (russian_language ? mk8::punct_view<t_punct>(RU_DFU_mode_punct) : &DFU_mode_punct);
  MENU[MENU_SETTINGS] = (t_punct*) (russian_language ? mk8::punct_view<t_punct>(RU_SETTINGS_punct) : &SETTINGS_punct);
  MENU[MENU_USB_DISK] = (t_punct*) (russian_language ? mk8::punct_view<t_punct>(RU_USB_DISK_punct) : &USB_DISK_punct);
  MENU[MENU_EXPLORER] = (t_punct*) (russian_language ? mk8::punct_view<t_punct>(RU_EXPLORER_punct) : &EXPLORER_punct);
  MENU[MENU_DEVELOP]  = (t_punct*) (russian_language ? mk8::punct_view<t_punct>(RU_DEVELOPMENT_punct) : &DEVELOPMENT_punct);
  MENU[MENU_SYSTEM]   = (t_punct*) (russian_language ? mk8::punct_view<t_punct>(RU_SYSTEM_punct) : &SYSTEM_punct);

  SYSTEM_MENU[SYSTEM_RESTART] = (t_punct*) (russian_language ? mk8::punct_view<t_punct>(RU_RESET_punct) : &RESET_punct);
  SYSTEM_MENU[SYSTEM_INFO] = (t_punct*) (russian_language ? mk8::punct_view<t_punct>(RU_FLASH_punct) : &FLASH_punct);
#if MK61_ENABLE_SETUP
  SYSTEM_MENU[SYSTEM_HARDWARE] = (t_punct*) (russian_language ? mk8::punct_view<t_punct>(RU_HARDWARE_punct) : &HARDWARE_punct);
#endif
  SYSTEM_MENU[SYSTEM_FORMAT] = (t_punct*) (russian_language ? mk8::punct_view<t_punct>(RU_FORMAT_punct) : &FORMAT_punct);
  SYSTEM_MENU[SYSTEM_FULL_RESET] = (t_punct*) (russian_language ? mk8::punct_view<t_punct>(RU_ERASE_punct) : &ERASE_punct);

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
#if MK61_COMPUTE_CLOCK_SUPPORTED
  set_stored_compute_clock_profile(flags,sound_settings,compute_profile_state);
#endif
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
#elif MK61_PROPORTIONAL_UI_FONTS
  return store_settings_snapshot(flags, sound_settings, stored_profile,
                                 NULL, &ui_font_state, &ui_font_key_state);
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
#if MK61_COMPUTE_CLOCK_SUPPORTED
  compute_profile_state = compute_clock::normalize(compute_clock::platform(), read_compute_clock_profile());
#endif
  set_language_state(flags.bits.language_ru != 0);
  const u8 stored_memory = flags.bits.program_memory_mode;
  memory_mode = (stored_memory <= (u8) ProgramMemoryMode::AUTO) ? (ProgramMemoryMode) stored_memory : ProgramMemoryMode::AUTO;
  set_program_memory_state(memory_mode == ProgramMemoryMode::EXPANDED_112);
  const u8 stored_speed = flags.bits.speed_mode;
  set_speed_mode_state(stored_speed == speed_mode_storage::CLASSIC
      ? SpeedMode::CLASSIC
      : SpeedMode::MAXIMUM);
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
#if MK61_PROPORTIONAL_UI_FONTS
  const UiFontSettings ui_font = read_ui_font_settings();
  (void) set_calculator_font(ui_font.calculatorFont());
  const u32 ui_key = read_ui_font_key();
  if(!set_ui_font(ui_font.family(), ui_font.size(), ui_key)) {
    // A missing/corrupt external family must never strand the settings UI.
    // Keep the same requested size and fall back to the resident Pixel face.
    (void) set_ui_font(1, ui_font.size());
    mark_settings_dirty();
  }
#endif
#if defined(MK61_OLED1602_WS0010)
  set_oled_timeout(read_oled_settings().timeout());
#endif
  refresh_menu_text();
}

u8 ui_font_family(void) {
#if MK61_PROPORTIONAL_UI_FONTS
  return ui_font_state.family();
#else
  return 0;
#endif
}

u8 ui_font_size(void) {
#if MK61_PROPORTIONAL_UI_FONTS
  return ui_font_state.size();
#else
  return 14;
#endif
}

u32 ui_font_key(void) {
#if MK61_PROPORTIONAL_UI_FONTS
  return ui_font_key_state;
#else
  return 0;
#endif
}

bool set_ui_font(u8 family, u8 size, u32 key) {
#if MK61_PROPORTIONAL_UI_FONTS
  UiFontSettings next = make_ui_font_settings(family, size);
  if(next.family() == 3) {
    u8 actual_height = next.size();
    const bool applied = key != 0
        ? program_store_apply_ui_font(key, actual_height)
        : program_store_apply_legacy_ui_font(next.size());
    if(!applied) return false;
    next = make_ui_font_settings(3, actual_height);
  } else {
    program_store_clear_ui_font();
    key = 0;
  }
  next.setCalculatorFont(ui_font_state.calculatorFont());
  ui_font_state = next;
  ui_font_key_state = key;
  main_lcd().setUiFont(next.family(), next.size());
  return true;
#else
  (void) family;
  (void) size;
  (void) key;
  return false;
#endif
}

bool adopt_external_ui_font(u8 size, u32 key) {
#if MK61_PROPORTIONAL_UI_FONTS
  UiFontSettings next = make_ui_font_settings(3, size);
  const auto* face = main_lcd().externalUiFont();
  if(key == 0 || face == nullptr || !face->valid() ||
     face->metrics().height != next.size()) return false;
  next.setCalculatorFont(ui_font_state.calculatorFont());
  ui_font_state = next;
  ui_font_key_state = key;
  main_lcd().setUiFont(3, next.size());
  return true;
#else
  (void) size;
  (void) key;
  return false;
#endif
}

u8 calculator_font(void) {
#if MK61_FIXED_CALCULATOR_FACE && MK61_PROPORTIONAL_UI_FONTS
  return ui_font_state.calculatorFont();
#else
  return 0;
#endif
}

bool set_calculator_font(u8 font) {
#if MK61_FIXED_CALCULATOR_FACE && MK61_PROPORTIONAL_UI_FONTS
  if(font > 1) return false;
  ui_font_state.setCalculatorFont(font);
  main_lcd().setCalculatorFont(font);
  return true;
#else
  (void) font;
  return false;
#endif
}

SpeedMode speed_mode(void) {
  return speed_mode_state;
}

void read_settings_snapshot(mk61_setup_settings& out) {
  out={{sound_volume_state, u8(idle_signal_state), u8(speed_mode_state),
        u8(memory_mode), u8(random_mode_state), u8(russian_language), 0}, 0};
#if MK61_ENABLE_SETUP
  out.features|=MK61_SETTINGS_RTC;
#endif
#if MK61_ENABLE_SETUP && MK61_HAS_GRAPHICAL_TEXT_SETTINGS
  if(main_lcd().graphicsMode())out.features|=MK61_SETTINGS_FONTS;
#endif
#if defined(MK61_OLED1602_WS0010)
  out.value[MK61_SETTING_OLED]=oled_timeout_state;
  out.features|=MK61_SETTINGS_OLED;
#endif
#if MK61_COMPUTE_CLOCK_SUPPORTED && MK61_ENABLE_SETUP
  out.features|=MK61_SETTINGS_COMPUTE;
#endif
}

bool apply_setting(u32 setting,u32 value) {
  static const u8 maximum[]={10,1,1,2,1,1,3};
  if(setting>=MK61_SETTING_COUNT || value>maximum[setting])return false;
  mk61_setup_settings current;
  read_settings_snapshot(current);
  if(setting==MK61_SETTING_OLED && !(current.features&MK61_SETTINGS_OLED))return false;
  if(current.value[setting]==value)return true;
  switch(setting) {
    case MK61_SETTING_VOLUME:
      sound_stop();set_sound_volume(value);
      sound(PIN_BUZZER,2500,20,sound_volume_state);break;
    case MK61_SETTING_IDLE_SIGNAL:set_idle_signal_state(value);break;
    case MK61_SETTING_SPEED:set_speed_mode_state((SpeedMode)value);break;
    case MK61_SETTING_MEMORY: {
      const bool expanded=expanded_program;
      set_program_memory_mode((ProgramMemoryMode)value);
      if(expanded!=expanded_program){reset_ext_program_state();core_61::enable();}
      break;
    }
    case MK61_SETTING_RANDOM:
      set_random_mode_state((RandomMode)value);entropy_pool::configure_calculator(value!=0);break;
    case MK61_SETTING_LANGUAGE:set_language_state(value);break;
#if defined(MK61_OLED1602_WS0010)
    case MK61_SETTING_OLED:set_oled_timeout(value);break;
#endif
  }
  mark_settings_dirty();refresh_menu_text();return true;
}

u8 compute_clock_profile(void) {
#if MK61_COMPUTE_CLOCK_SUPPORTED
  return compute_profile_state;
#else
  return 0;
#endif
}

bool set_compute_clock_profile(u8 profile) {
#if MK61_COMPUTE_CLOCK_SUPPORTED
  if(profile >= compute_clock::profile_count(compute_clock::platform()))return false;
  compute_profile_state = profile;
  mark_settings_dirty();
  return true;
#else
  (void)profile;return false;
#endif
}

bool  speed_is_classic(void) {
  return speed_mode_state == SpeedMode::CLASSIC;
}

bool  speed_is_max(void) {
  return speed_mode_state == SpeedMode::MAXIMUM;
}

} // пространство имён library_mk61

bool ResetDevice(void) {
  library_mk61::store_settings_state();
  NVIC_SystemReset();

  return action::MENU_EXIT;
}

bool system_select(void) {
  library_mk61::refresh_menu_text();
  class_menu system_menu(library_mk61::SYSTEM_MENU,
                         library_mk61::SYSTEM_MENU_COUNT);
  return system_menu.select();
}

bool settings_select(void) {
  setup_ui::settings();
  library_mk61::defer_settings_state_save();
  library_mk61::refresh_menu_text();
  return action::MENU_BACK;
}

static void draw_usb_disk_status(const char* ru0, const char* en0, const char* ru1, const char* en1) {
  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();
  lcd_ru::print_lines(library_mk61::language_is_ru() ? ru0 : en0,
                      library_mk61::language_is_ru() ? ru1 : en1);
}

static constexpr u32 USB_HOST_CONFIGURATION_TIMEOUT_MS = 15000U;
static constexpr u32 USB_HOST_LOST_TIMEOUT_MS = 3000U;

static bool usb_disk_mode(bool wait_for_key_on_error) {
  if(!compute_clock::usb_available(compute_clock::platform(),compute_clock::active_profile())) {
    draw_usb_disk_status(M8("USB отключён"), "USB disabled",
        M8("Выберите 96-120 МГц"), "Select 96-120 MHz");
    kbd::get_key_wait();
    return action::MENU_BACK;
  }
  draw_usb_disk_status(M8("USB-диск"), "USB Disk", M8("запуск..."), "starting...");
  library_mk61::flush_settings_state();
  // C9 is mounted once during normal boot and its in-memory catalog remains
  // authoritative until the MSC session starts.  Remounting here used to run
  // catalog repair and clear persistent FAT staging immediately before the
  // USB-disk APP performed its own recovery.  Apart from duplicating a slow
  // flash scan, that could strand the device before CDC was handed over to
  // MSC.  Refresh is only the recovery path for an unexpectedly unmounted
  // store; virtual_fat::reset_session() performs the USB-specific recovery.
  if(!program_store::ready() && !program_store::refresh()) {
    if(program_store::mount_status() ==
       program_store::MountStatus::FORMAT_REQUIRED) {
      draw_usb_disk_status(M8("Неизвестная ФС"), "Unsupported FS",
                           M8("нужен формат"), "format needed");
    } else if(program_store::mount_status() ==
              program_store::MountStatus::REPAIR_REQUIRED) {
      draw_usb_disk_status(M8("ФС повреждена"), "FS damaged",
                           M8("нужен формат"), "format needed");
    } else {
      draw_usb_disk_status(M8("Ошибка ФС"), "FS error", "ESC", "ESC");
    }
    if(wait_for_key_on_error) kbd::get_key_wait();
    lcd_ru::restore_default_font();
    return action::MENU_BACK;
  }
  // Empty files are valid C9/FAT objects. Cleaning them implicitly here
  // both destroyed user data and performed another full catalog walk before
  // the APP could report a startup stage. Empty-file deletion is explicit.
  if(!usb_start_mass_storage_mode()) {
    usb_mass_storage::note_startup_stage(720U);
    // deinit()/APP eviction performs its own finalization and can otherwise
    // replace the first startup failure with an empty APP diagnostic.  Keep
    // the exact cause promised by `vlog` across the return to CDC.
    const virtual_fat::Diagnostic startup_failure =
        virtual_fat::diagnostic();
    usb_start_terminal_mode();
    usb_mass_storage::note_startup_stage(721U);
    if(startup_failure.code != virtual_fat::ErrorCode::NONE) {
      virtual_fat::restore_diagnostic(startup_failure);
    }
    draw_usb_disk_status(M8("Ошибка USB"), "USB error", "ESC", "ESC");
    usb_mass_storage::note_startup_stage(722U);
    if(wait_for_key_on_error) kbd::get_key_wait();
    lcd_ru::restore_default_font();
    return action::MENU_BACK;
  }

  draw_usb_disk_status(M8("USB-диск"), "USB Disk", M8("ESC выход"), "ESC exit");
  const u32 host_wait_started = millis();
  u32 host_last_configured = host_wait_started;
  bool host_was_configured = false;
  bool host_configuration_timed_out = false;
  bool host_connection_lost = false;
  while(true) {
    idle_main_process();
    // Safe host eject already includes SYNCHRONIZE CACHE.  Return CDC
    // automatically after the SCSI command completes instead of leaving an
    // ejected, inaccessible disk on screen until a physical ESC is pressed.
    if(usb_mass_storage::host_ejected()) break;
    const u32 now = millis();
    if(usb_mass_storage::host_configured()) {
      host_was_configured = true;
      host_last_configured = now;
    } else if(!host_was_configured &&
              (u32) (now - host_wait_started) >=
                  USB_HOST_CONFIGURATION_TIMEOUT_MS) {
      // A successful USBD_Start() is not sufficient: a broken re-enumeration
      // used to leave both CDC and MSC absent forever while the foreground
      // kept feeding the watchdog.  Return to CDC deterministically so vlog
      // can explain the failed transition and another attempt remains safe.
      host_configuration_timed_out = true;
      break;
    } else if(host_was_configured &&
              (u32) (now - host_last_configured) >=
                  USB_HOST_LOST_TIMEOUT_MS) {
      // A host can configure the class and then reject it before a disk is
      // published.  That is not a usable session and must not strand the
      // calculator in an invisible, watchdog-fed foreground loop.
      host_connection_lost = true;
      break;
    }
    const i32 key = kbd::poll_event().code();

    if(key == KEY_ESC_PRESS) {
      kbd::handoff(kbd::Event(key));
      break;
    }
  }

  // Stopping MSC may validate and commit a complete C9 batch. On a large
  // directory this takes seconds; show that ESC/eject was accepted instead
  // of leaving the interactive prompt frozen on screen.
#if defined(MK61_DISPLAY_UC1609)
  main_lcd().beginDiskSaving(library_mk61::language_is_ru());
#else
  draw_usb_disk_status(M8("USB-диск"), "USB Disk",
                       M8("сохранение..."), "saving...");
#endif
  const bool clean_exit = usb_start_terminal_mode();
#if defined(MK61_DISPLAY_UC1609)
  main_lcd().endDiskSaving();
#endif
  if(host_configuration_timed_out || host_connection_lost) {
    virtual_fat::report_startup_failure(
        host_configuration_timed_out ? 19U : 20U,
        host_configuration_timed_out ? "host-config" : "host-lost");
    draw_usb_disk_status(M8("Ошибка USB"), "USB error",
                         M8("подробно: vlog"), "details: vlog");
    if(wait_for_key_on_error) kbd::get_key_wait();
    lcd_ru::restore_default_font();
    return action::MENU_BACK;
  }
  if(!clean_exit) {
    char error_code[10];
    virtual_fat::format_error_code(virtual_fat::diagnostic().code, error_code);
    draw_usb_disk_status(error_code, error_code,
                         M8("подробно: vlog"), "details: vlog");
    delay(900);
  }
  lcd_ru::restore_default_font();
  // The ordinary menu owner redraws the calculator after MENU_EXIT.  The
  // terminal/HIL entry has no menu frame to unwind, so without an explicit
  // redraw the completed session leaves the last transient "saving..."
  // message on the physical display even though CDC is already restored.
  if(!wait_for_key_on_error && clean_exit) lcd_std_display_redraw();
  return action::MENU_EXIT;
}

bool UsbDiskMode(void) { return usb_disk_mode(true); }

bool UsbDiskModeUnattended(void) { return usb_disk_mode(false); }

bool UsbScreenMode(void) {
  draw_usb_disk_status(M8("USB-экран"), "USB Screen",
                       M8("ждём приложение"), "start desktop app");
  if(!usb_screen::start()) {
    draw_usb_disk_status(M8("Ошибка USB"), "USB error", "ESC", "ESC");
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

void class_menu::draw(void) {
  MK61DisplayUpdate update(main_lcd());
  main_lcd().beginUiText();
  const int size_menu_window = main_lcd().rows();
  const int visible_count = (MENU_PUNCT_COUNT < size_menu_window) ? MENU_PUNCT_COUNT : size_menu_window;
  const int up = menu_model::firstVisible(active_punct, MENU_PUNCT_COUNT, size_menu_window);

#if defined(MK61_DISPLAY_UC1609)
  if(main_lcd().uiTextActive()) {
    for(int row = 0; row < size_menu_window; ++row) {
      const int index = up + row;
      main_lcd().printUiLine((u8) row, row < visible_count ? puncts[index]->text : "",
                            row < visible_count && index == active_punct ? '>' : ' ');
    }
    previous_up = up;
    return;
  }
#endif

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
  MK61DisplayTextScope text_scope(main_lcd());
  main_lcd().clear();
  do{
    draw();
    const i32 last_key_code = wait_key();
    switch(last_key_code) {
      case KEY_RIGHT_PRESS:
              active_punct = menu_model::step(active_punct, MENU_PUNCT_COUNT, 1);
        break;
      case KEY_LEFT_PRESS:
              active_punct = menu_model::step(active_punct, MENU_PUNCT_COUNT, -1);
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
  main_lcd().beginUiText();
  main_lcd().clear();
  dbgln(MENU, "select entry");

  switch(key) {
      case KEY_RIGHT_PRESS:
              active_punct = menu_model::step(active_punct, MENU_PUNCT_COUNT, 1);
        break;
      case KEY_LEFT_PRESS:
              active_punct = menu_model::step(active_punct, MENU_PUNCT_COUNT, -1);
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
