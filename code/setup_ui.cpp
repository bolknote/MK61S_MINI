#include "config.h"
#include "setup_ui.hpp"
#if !MK61_SETUP_IS_LOADABLE || defined(MK61_BUILD_SETUP_MODULE)
#include "menu.hpp"
#include "cross_hal.h"
#include "lcd_ru.hpp"
#include "hardware_info.hpp"
#include "rtc_clock.hpp"
#include "rtc_settings_core.hpp"
#include "fmk_font.hpp"
#include "setup_service.hpp"
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
#include "setup_compat.hpp"
#endif
#include <stdio.h>
extern void idle_main_process(void);
namespace setup_ui {
#if MK61_UI_FONT_CLIENT
  #define MK61_SETUP_UI_FONT_CHOOSER 1
#else
  #define MK61_SETUP_UI_FONT_CHOOSER 0
#endif
static constexpr i32 DISPLAY_MODE_CHANGED = -2;

static i32 wait_key_or_display_change(u32 display_mode_revision) {
  do {
    idle_main_process();
    if(main_lcd().displayModeRevision() != display_mode_revision) {
      return DISPLAY_MODE_CHANGED;
    }

    const i32 scan_code = kbd::poll_event().code();
    if(scan_code >= 0 && scan_code < (i32) key_state::RELEASED) {
      kbd::handoff(kbd::Event(scan_code));
      return scan_code;
    }
  } while(true);
}

static constexpr usize HARDWARE_LINE_SIZE = 32;

static void printSetupLines(const char* first, const char* second) {
#if MK61_SETUP_UI_FONT_CHOOSER
  if(service(MK61_SETUP_FEATURES) & MK61_SETUP_FEATURE_UI_FONT) {
    service(MK61_SETUP_TEXT, 0, 0, (void*) first);
    service(MK61_SETUP_TEXT, 1, 0, (void*) second);
    return;
  }
#endif
  // Character displays and F401/UC1609 keep the established fixed-cell path.
  lcd_ru::print_lines(first, second);
}

static void build_hardware_lines(
    char lines[hardware_info::LINE_COUNT][HARDWARE_LINE_SIZE],
    const hardware_info::AnalogSnapshot& analog, const mk61_setup_hardware& snapshot) {
  const bool russian = library_mk61::language_is_ru();
  const auto device = hardware_info::decode_device_identity(
      snapshot.idcode, snapshot.flash_kb, (char) snapshot.pin_code);
  const char* rtc_source_name = snapshot.rtc_source;
  hardware_info::format_device_line(
    lines[0], HARDWARE_LINE_SIZE, russian, device);
  hardware_info::format_memory_line(
    lines[1], HARDWARE_LINE_SIZE, russian, device);

  hardware_info::format_vdda_line(
    lines[2], HARDWARE_LINE_SIZE, russian, analog.vdda);
  hardware_info::format_temperature_line(
    lines[3], HARDWARE_LINE_SIZE, russian, analog.mcu_temperature);
  hardware_info::format_battery_line(
    lines[4], HARDWARE_LINE_SIZE, russian, analog.battery);
  hardware_info::format_generator_line(
    lines[5], HARDWARE_LINE_SIZE, russian, rtc_source_name);
  hardware_info::format_display_line(
    lines[6], HARDWARE_LINE_SIZE, russian, snapshot.display);
}

static void draw_hardware_lines(
    const char lines[hardware_info::LINE_COUNT][HARDWARE_LINE_SIZE],
    u8 offset) {
  const u8 rows = main_lcd().rows();
  const u8 visible =
    rows < hardware_info::LINE_COUNT ? rows : hardware_info::LINE_COUNT;
  offset = hardware_info::clamp_scroll_offset(offset, rows);

  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();

  if(library_mk61::language_is_ru() &&
     !(service(MK61_SETUP_FEATURES) & MK61_SETUP_FEATURE_UI_FONT)) {
    const char* window[hardware_info::LINE_COUNT];
    for(u8 row = 0; row < visible; row++) {
      window[row] = lines[offset + row];
    }
    lcd_ru::print_window(window, visible);
    return;
  }

  for(u8 row = 0; row < visible; row++) {
    service(MK61_SETUP_TEXT, row, 0, (void*) lines[offset + row]);
  }
}

bool hardware(void) {
  char lines[hardware_info::LINE_COUNT][HARDWARE_LINE_SIZE];
  mk61_setup_hardware snapshot = {};
  service(MK61_SETUP_HARDWARE, 0, 0, &snapshot);
  hardware_info::AnalogSnapshot analog = {};
  analog.vdda = {bool(snapshot.valid & 1), (u16) snapshot.vdda};
  analog.mcu_temperature = {bool(snapshot.valid & 2), (i16) snapshot.temperature};
  analog.battery = {(hardware_info::BatteryPresence) snapshot.battery_presence,
      (hardware_info::BatteryPresenceReason) snapshot.battery_reason,
      {bool(snapshot.valid & 4), (u16) snapshot.vbat}};
  build_hardware_lines(lines, analog, snapshot);
  u8 offset = 0;

  do {
    offset = hardware_info::clamp_scroll_offset(
      offset, main_lcd().rows());
    draw_hardware_lines(lines, offset);
    const i32 key = wait_key_or_display_change(
      main_lcd().displayModeRevision());

    if(key == DISPLAY_MODE_CHANGED) continue;
    if(key == KEY_LEFT_PRESS || key == KEY_SHG_LEFT_PRESS) {
      offset = hardware_info::step_scroll_offset(
        offset, main_lcd().rows(), -1);
      continue;
    }
    if(key == KEY_RIGHT_PRESS || key == KEY_SHG_RIGHT_PRESS) {
      offset = hardware_info::step_scroll_offset(
        offset, main_lcd().rows(), 1);
      continue;
    }

    lcd_ru::restore_default_font();
    return action::MENU_BACK;
  } while(true);
}

static int dateTimeDigitFromKey(i32 key) {
  for(int i = 0; i < 10; ++i) if(key == keyboard_layout::active().digit[i]) return i;
  return -1;
}

static void drawDateTimeEditor(const rtc_settings::Editor& editor) {
  const bool russian = library_mk61::language_is_ru();
  char date_line[32];
  char time_line[32];
  snprintf(date_line, sizeof(date_line), russian ? "Дата %.10s" : "Date %.10s", editor.text);
  snprintf(time_line, sizeof(time_line), russian ? "Время %.8s" : "Time %.8s", editor.text + 11);

  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();
  printSetupLines(date_line, time_line);

  const usize position = rtc_settings::active_text_position(editor);
  if(position < 10) {
    main_lcd().setCursor((u8) (5 + position), 0);
  } else {
    const u8 time_start = russian ? 6 : 5;
    main_lcd().setCursor((u8) (time_start + position - 11), 1);
  }
  if(main_lcd().supportsCursor()) main_lcd().cursorOn();
}

static void showDateTimeMessage(const char* ru0, const char* en0, const char* ru1, const char* en1,
                                t_time_ms duration_ms) {
  {
    MK61DisplayUpdate update(main_lcd());
    main_lcd().clear();
    printSetupLines(
      library_mk61::language_is_ru() ? ru0 : en0,
      library_mk61::language_is_ru() ? ru1 : en1);
  }
  delay(duration_ms);
}

bool date_time(void) {
  mk61_setup_datetime wire = {};
  service(MK61_SETUP_RTC_READ, 0, 0, &wire);
  rtc_clock::DateTime initial = {(u16) wire.year, (u8) wire.month,
      (u8) wire.day, (u8) wire.hour, (u8) wire.minute, (u8) wire.second};

  rtc_settings::Editor editor = {};
  if(!rtc_settings::begin(editor, initial)) return action::MENU_BACK;

  while(true) {
    drawDateTimeEditor(editor);
    const i32 key = wait_key_or_display_change(
      main_lcd().displayModeRevision());
    if(key == DISPLAY_MODE_CHANGED) continue;
    const int digit = dateTimeDigitFromKey(key);
    if(digit >= 0) {
      rtc_settings::enter_digit(editor, digit);
      continue;
    }

    if(key == KEY_LEFT_PRESS || key == KEY_SHG_LEFT_PRESS) {
      rtc_settings::move_left(editor);
      continue;
    }
    if(key == KEY_RIGHT_PRESS || key == KEY_SHG_RIGHT_PRESS) {
      rtc_settings::move_right(editor);
      continue;
    }
    if(key == KEY_ESC_PRESS) {
      main_lcd().cursorOff();
      lcd_ru::restore_default_font();
      return action::MENU_BACK;
    }
    if(key != KEY_OK_PRESS) continue;

    rtc_clock::DateTime value = {};
    if(!rtc_settings::value(editor, value)) {
      showDateTimeMessage("Неверная дата", "Invalid date", "или время", "or time", 900);
      continue;
    }
    wire = {value.year, value.month, value.day, value.hour, value.minute, value.second};
    if(!service(MK61_SETUP_RTC_WRITE, 0, 0, &wire)) {
      showDateTimeMessage("Ошибка RTC", "RTC error", "Не сохранено", "Not saved", 900);
      continue;
    }

    showDateTimeMessage("Дата и время", "Date and time", "сохранены", "saved", 650);
    lcd_ru::restore_default_font();
    return action::MENU_BACK;
  }
}

static void drawRtcCalibrationEditor(
    const rtc_settings::CalibrationEditor& editor) {
  char value_line[20];
  snprintf(value_line, sizeof(value_line), "%s ppm", editor.text);

  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();
  printSetupLines(
    library_mk61::language_is_ru() ? "Поправка RTC" : "RTC correction",
    value_line);
  main_lcd().setCursor(
    (u8) rtc_settings::active_text_position(editor), 1);
  if(main_lcd().supportsCursor()) main_lcd().cursorOn();
}

bool calibration(void) {
  rtc_settings::CalibrationEditor editor = {};
  if(!rtc_settings::begin(editor, (i16) service(MK61_SETUP_RTC_CALIBRATION, 0))) {
    return action::MENU_BACK;
  }

  while(true) {
    drawRtcCalibrationEditor(editor);
    const i32 key = wait_key_or_display_change(
      main_lcd().displayModeRevision());
    if(key == DISPLAY_MODE_CHANGED) continue;
    const int digit = dateTimeDigitFromKey(key);
    if(digit >= 0) {
      rtc_settings::enter_digit(editor, digit);
      continue;
    }
    if(key == KEY_NEG) {
      rtc_settings::toggle_sign(editor);
      continue;
    }
    if(key == KEY_CX) {
      rtc_settings::begin(editor, 0);
      continue;
    }
    if(key == KEY_LEFT_PRESS || key == KEY_SHG_LEFT_PRESS) {
      rtc_settings::move_left(editor);
      continue;
    }
    if(key == KEY_RIGHT_PRESS || key == KEY_SHG_RIGHT_PRESS) {
      rtc_settings::move_right(editor);
      continue;
    }
    if(key == KEY_ESC_PRESS) {
      main_lcd().cursorOff();
      lcd_ru::restore_default_font();
      return action::MENU_BACK;
    }
    if(key != KEY_OK_PRESS) continue;

    i16 ppm = 0;
    if(!rtc_settings::value(editor, ppm)) {
      showDateTimeMessage(
        "Диапазон RTC", "RTC range", "-487...+488 ppm",
        "-487...+488 ppm", 900);
      continue;
    }
    if(!service(MK61_SETUP_RTC_CALIBRATION, 1, (u32) (i32) ppm)) {
      showDateTimeMessage(
        "Ошибка RTC", "RTC error", "Не сохранено", "Not saved", 900);
      continue;
    }

    showDateTimeMessage(
      "Поправка RTC", "RTC correction", "сохранена", "saved", 650);
    lcd_ru::restore_default_font();
    return action::MENU_BACK;
  }
}

#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
enum class FontSetupPhase : u8 {
  DRAW = 1,
  WAIT_KEY,
  KEY_RECEIVED,
  DROP_EXTERNAL_FONT,
  SET_PROFILE,
  REFRESH_MENU,
  LEAVE
};

static void noteFontSetupPhase(FontSetupPhase phase) {
  service(MK61_SETUP_PHASE, (u32) phase);
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
  return "5x8";
}

static lcd_display::TextProfile nextFontPreset(lcd_display::TextProfile profile, i8 delta) {
  profile = lcd_display::normalizeSettingsTextProfile(profile);
  const u8 current = sameTextProfile(profile, lcd_display::textProfile3x5()) ? 1 :
      (sameTextProfile(profile, lcd_display::textProfile10x16()) ? 2 : 0);
  const u8 next = (u8) ((current + (delta > 0 ? 1 : 2)) % 3);
  switch(next) {
    case 1: return lcd_display::textProfile3x5();
    case 2: return lcd_display::textProfile10x16();
    default: return lcd_display::textProfile5x8();
  }
}

#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
static u8 step_display_rows_value(u8 rows, i8 delta) {
  rows = lcd_display::clamp_u8(rows, lcd_display::MIN_ROWS, lcd_display::GRAPHICS_MAX_ROWS);
  if(delta > 0 && rows < lcd_display::GRAPHICS_MAX_ROWS) {
    return rows + 1;
  }
  if(delta < 0 && rows > lcd_display::MIN_ROWS) {
    return rows - 1;
  }
  return rows;
}
#endif
static lcd_display::TextProfile read_profile() {
  mk61_setup_profile wire = {};
  service(MK61_SETUP_FONT_READ, 0, 0, &wire);
  return {wire.rows, wire.width, wire.height, wire.gap};
}
static u8 calculatorFontFieldCount(void) {
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  return (service(MK61_SETUP_FEATURES) &
          MK61_SETUP_FEATURE_EXTENDED_TEXT_PROFILE) ? 4 : 1;
#else
  return 1;
#endif
}

#if MK61_SETUP_UI_FONT_CHOOSER
static bool uiFontSettingsAvailable(void) {
  // An older resident or USB Screen cannot provide a live UI-font surface.
  const u32 required = MK61_SETUP_FEATURE_UI_FONT |
                       MK61_SETUP_FEATURE_UI_TEXT_MODE;
  return (service(MK61_SETUP_FEATURES) & required) == required;
}

static bool uiFontServiceAvailable(void) {
  return (service(MK61_SETUP_FEATURES) & MK61_SETUP_FEATURE_UI_FONT) != 0;
}

static bool uiFontCatalogAvailable(void) {
  return (service(MK61_SETUP_FEATURES) &
          MK61_SETUP_FEATURE_UI_FONT_CATALOG) != 0;
}

static mk61_setup_ui_font readUiFont(void) {
  mk61_setup_ui_font value = {0, 14};
  if(uiFontSettingsAvailable()) service(MK61_SETUP_UI_FONT_READ, 0, 0, &value);
  return value;
}

struct UiFontChoice {
  mk61_setup_ui_font setting;
  mk61_setup_ui_font_item external;
};

static UiFontChoice readUiFontChoice(void) {
  UiFontChoice choice = {};
  choice.setting = readUiFont();
  if(choice.setting.family == 3 && uiFontCatalogAvailable() &&
     service(MK61_SETUP_UI_FONT_CURRENT, 0, 0, &choice.external)) {
    choice.setting.size = choice.external.size;
  }
  return choice;
}

static void formatUiFontLine(char* out, usize size, u8 field,
                             const UiFontChoice& choice) {
  const bool russian = library_mk61::language_is_ru();
  if(field == 0) {
    const char* name = choice.setting.family == 3 &&
        choice.external.name[0] != 0 ? choice.external.name :
      (choice.setting.family == 3 ? "FMK" :
       (choice.setting.family ? "Pixel" : "5x8"));
    snprintf(out, size, russian ? "Шрифт UI:%s" : "UI font:%s", name);
  } else {
    snprintf(out, size, russian ? "Размер UI:%u" : "UI size:%u",
      (unsigned) choice.setting.size);
  }
}
#endif
static void formatFontSetupLine(char* out, usize size, u8 field, lcd_display::TextProfile profile) {
#if !MK61_ENABLE_EXTENDED_FONT_SETTINGS
  (void) field;
  snprintf(out, size, library_mk61::language_is_ru() ? "Шрифт:%s" : "Font:%s",
    fontPresetName(profile));
  return;
#else
  if(!(service(MK61_SETUP_FEATURES) &
       MK61_SETUP_FEATURE_EXTENDED_TEXT_PROFILE)) {
    snprintf(out, size, library_mk61::language_is_ru() ? "Шрифт:%s" : "Font:%s", fontPresetName(profile));
    return;
  }
  if(library_mk61::language_is_ru()) {
    switch(field) {
      case 0:
        snprintf(out, size, "Строки:%u", (unsigned) profile.rows);
        break;
      case 1:
        snprintf(out, size, "Шрифт:%ux%u", (unsigned) profile.glyph_width, (unsigned) profile.glyph_height);
        break;
      case 2:
        snprintf(out, size, "Интервал:%u", (unsigned) profile.line_gap);
        break;
      case 3:
      default:
        snprintf(out, size, "Ширина:%u", (unsigned) profile.glyph_width);
        break;
    }
    return;
  }

  switch(field) {
    case 0:
      snprintf(out, size, "Rows:%u", (unsigned) profile.rows);
      break;
    case 1:
      snprintf(out, size, "Font:%ux%u", (unsigned) profile.glyph_width, (unsigned) profile.glyph_height);
      break;
    case 2:
      snprintf(out, size, "Gap:%u", (unsigned) profile.line_gap);
      break;
    case 3:
    default:
      snprintf(out, size, "Width:%u", (unsigned) profile.glyph_width);
      break;
  }
#endif
}

static void printFontSetupLine(u8 row, char mark, const char* text) {
  if(library_mk61::language_is_ru()) {
    lcd_ru::print_menu_line(row, mark, text);
    return;
  }

  main_lcd().setCursor(0, row);
  main_lcd().write((u8) mark);
  u8 used = 0;
  while(text[used] != 0 && used < lcd_display::COLS - 1) {
    main_lcd().write((u8) text[used++]);
  }
  while(used++ < lcd_display::COLS - 1) main_lcd().write((u8) ' ');
}

static void drawCalculatorFontSetup(u8 active, lcd_display::TextProfile profile) {
  const u8 FIELD_COUNT = calculatorFontFieldCount();
  noteFontSetupPhase(FontSetupPhase::DRAW);
  MK61DisplayUpdate update(main_lcd());
  const u8 rows = main_lcd().rows();
  const u8 visible_fields = (rows < FIELD_COUNT) ? rows : FIELD_COUNT;
  u8 top = (active + 1 > visible_fields) ? (u8) (active + 1 - visible_fields) : 0;
  if(top + visible_fields > FIELD_COUNT) top = FIELD_COUNT - visible_fields;

  char line[32];
  for(u8 row = 0; row < visible_fields; row++) {
    const u8 field = top + row;
    formatFontSetupLine(line, sizeof(line), field, profile);
    printFontSetupLine(row, (field == active) ? '>' : ' ', line);
  }

  for(u8 row = visible_fields; row < rows; row++) {
    if(row == visible_fields) {
      printFontSetupLine(row, ' ', library_mk61::language_is_ru() ? "Образец 123АБВ" : "Sample 123ABC");
    } else {
      printFontSetupLine(row, ' ', library_mk61::language_is_ru() ? "0123456789+-*/" : "0123456789+-*/");
    }
  }
}

static void applyFontSetupProfile(lcd_display::TextProfile profile) {
  mk61_setup_profile wire = {profile.rows, profile.glyph_width, profile.glyph_height, profile.line_gap};
  service(MK61_SETUP_FONT_APPLY, 0, 0, &wire);
}

static void stepFontSetupProfile(lcd_display::TextProfile& profile, u8 field, i8 delta) {
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
  profile = lcd_display::normalizeSettingsTextProfile(profile);
#if !MK61_ENABLE_EXTENDED_FONT_SETTINGS
  (void) field;
  profile = nextFontPreset(profile, delta);
#else
  if(!(service(MK61_SETUP_FEATURES) &
       MK61_SETUP_FEATURE_EXTENDED_TEXT_PROFILE)) {
    profile = nextFontPreset(profile, delta); return;
  }
  switch(field) {
    case 0: {
      profile.rows = step_display_rows_value(profile.rows, delta);
      break;
    }
    case 1: {
      const u8 max_height = lcd_display::PIXEL_HEIGHT / profile.rows;
      if(delta > 0 && profile.glyph_height < max_height) profile.glyph_height++;
      if(delta < 0 && profile.glyph_height > 5) profile.glyph_height--;
      break;
    }
    case 2: {
      const u8 max_gap = lcd_display::maxLineGap(profile.rows, profile.glyph_height);
      if(delta > 0 && profile.line_gap < max_gap) profile.line_gap++;
      if(delta < 0 && profile.line_gap > 0) profile.line_gap--;
      break;
    }
    case 3:
      if(delta > 0 && profile.glyph_width < 10) profile.glyph_width++;
      if(delta < 0 && profile.glyph_width > 3) profile.glyph_width--;
      break;
  }
  profile = lcd_display::normalizeSettingsTextProfile(profile);
#endif
#else
  (void) profile;
  (void) field;
  (void) delta;
#endif
}

static i32 waitFontSetupKey(u32 revision) {
  noteFontSetupPhase(FontSetupPhase::WAIT_KEY);
  return wait_key_or_display_change(revision);
}
#endif

static bool calculatorFontSetup(void) {
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
  if(!(service(MK61_SETUP_FEATURES) & MK61_SETUP_FEATURE_TEXT_PROFILE) ||
     !main_lcd().graphicsMode()) return action::MENU_BACK;
  const u8 FIELD_COUNT = calculatorFontFieldCount();
  lcd_display::TextProfile profile = read_profile();
  u8 active = 0;
  profile = lcd_display::normalizeSettingsTextProfile(profile);
  main_lcd().endUiText();
  drawCalculatorFontSetup(active, profile);

  while(true) {
    const i32 key = waitFontSetupKey(main_lcd().displayModeRevision());
    noteFontSetupPhase(FontSetupPhase::KEY_RECEIVED);
    if(key == KEY_ESC_PRESS) {
      noteFontSetupPhase(FontSetupPhase::LEAVE);
      MK61DisplayUpdate update(main_lcd());
      lcd_ru::restore_default_font();
      return action::MENU_BACK;
    }

    bool redraw = false;
    bool apply = false;
    i8 delta = 0;
    if(key == DISPLAY_MODE_CHANGED) {
      redraw = true;
    } else if(key == KEY_OK_PRESS) {
      if(FIELD_COUNT > 1) { active = (u8) ((active + 1) % FIELD_COUNT); }
      else { delta = 1; apply = true; }
      redraw = true;
    } else if(key == KEY_RIGHT_PRESS) {
      if(active + 1 < FIELD_COUNT) { ++active; redraw = true; }
    } else if(key == KEY_LEFT_PRESS) {
      if(active > 0) { --active; redraw = true; }
    } else if(key == KEY_SHG_RIGHT_PRESS) {
      delta = 1;
      redraw = true;
      apply = true;
    } else if(key == KEY_SHG_LEFT_PRESS) {
      delta = -1;
      redraw = true;
      apply = true;
    }

    if(apply) stepFontSetupProfile(profile, active, delta);

    if(redraw) {
      profile = lcd_display::normalizeSettingsTextProfile(profile);
      // Смена backing font, геометрии сетки и следующая картинка образуют одну
      // транзакцию: промежуточный кадр со старой ссылкой не существует.
      MK61DisplayUpdate update(main_lcd());
      if(apply) applyFontSetupProfile(profile);
      drawCalculatorFontSetup(active, profile);
    }
  }
#else
  return action::MENU_BACK;
#endif
}

#if MK61_SETUP_UI_FONT_CHOOSER
static u8 uiFontFieldCount(const UiFontChoice& choice) {
  // Calculator digits have a separate fixed face.  This dialog controls only
  // the UI: 5x8 is exact, Pixel has three resident sizes, and each catalog
  // FMK is already a complete raster with its own intrinsic height.
  if(choice.setting.family == 0) return 1U;
  if(choice.setting.family == 3 && uiFontCatalogAvailable()) return 1U;
  return 2U;
}

static u8 stepLegacyUiFontFamily(u8 family, i8 delta) {
  static constexpr u8 families[] = {0, 1, 3};
  u8 index = family == 1 ? 1U : (family == 3 ? 2U : 0U);
  index = (u8) ((index + (delta < 0 ? 2U : 1U)) % 3U);
  return families[index];
}

static u8 stepUiFontSize(u8 size, i8 delta) {
  static constexpr u8 sizes[] = {12, 14, 16};
  u8 index = size == 12 ? 0U : (size == 16 ? 2U : 1U);
  index = (u8) ((index + (delta < 0 ? 2U : 1U)) % 3U);
  return sizes[index];
}

static bool uiFontCatalogStep(u32 key, i8 delta,
                              mk61_setup_ui_font_item& item) {
  item = {};
  return (delta == -1 || delta == 1) &&
      service(MK61_SETUP_UI_FONT_STEP, key, (u32) (i32) delta, &item) != 0 &&
      item.key != 0 && item.name[0] != 0 &&
      (item.size == 12 || item.size == 14 || item.size == 16);
}

static bool applyBuiltinUiFont(UiFontChoice& choice, u8 family) {
  mk61_setup_ui_font next = choice.setting;
  next.family = family;
  if(!service(MK61_SETUP_UI_FONT_APPLY, 0, 0, &next)) return false;
  choice = readUiFontChoice();
  return true;
}

static bool applyCatalogUiFont(UiFontChoice& choice,
                               const mk61_setup_ui_font_item& item) {
  if(item.key == 0 || !service(MK61_SETUP_UI_FONT_APPLY_ITEM, item.key))
    return false;
  choice = readUiFontChoice();
  return true;
}

static bool stepUiFontChoice(UiFontChoice& choice, i8 delta) {
  if(delta != -1 && delta != 1) return false;
  mk61_setup_ui_font_item item = {};
  const u8 family = choice.setting.family;
  if(family == 0) {
    if(delta > 0) return applyBuiltinUiFont(choice, 1);
    return uiFontCatalogStep(0, -1, item)
        ? applyCatalogUiFont(choice, item)
        : applyBuiltinUiFont(choice, 1);
  }
  if(family == 1 || family == 2) {
    if(delta < 0) return applyBuiltinUiFont(choice, 0);
    return uiFontCatalogStep(0, 1, item)
        ? applyCatalogUiFont(choice, item)
        : applyBuiltinUiFont(choice, 0);
  }
  if(family == 3 && uiFontCatalogStep(choice.external.key, delta, item))
    return applyCatalogUiFont(choice, item);
  return applyBuiltinUiFont(choice, delta > 0 ? 0 : 1);
}

static void drawUiFontSetup(u8 active, const UiFontChoice& choice) {
  noteFontSetupPhase(FontSetupPhase::DRAW);
  MK61DisplayUpdate update(main_lcd());
  service(MK61_SETUP_TEXT_MODE, 1);
  main_lcd().clear();
  const u8 rows = main_lcd().rows();
  if(rows == 0) return;
  const u8 fields = uiFontFieldCount(choice);
  // Every accepted external UI FMK leaves at least three visible rows, so a
  // live sample always fits below the one or two option rows.
  const u8 available = rows > 1 ? (u8) (rows - 1) : 1;
  const u8 visible = available < fields ? available : fields;
  const u8 top = active < visible ? 0 : (u8) (active + 1 - visible);
  // A complete 31-byte C5 name plus the localized label fits. Pixel clipping
  // and ellipsis belong to printUiLine(), not to snprintf's byte boundary.
  char line[64];
  for(u8 row = 0; row < visible; ++row) {
    const u8 field = top + row;
    formatUiFontLine(line, sizeof(line), field, choice);
    service(MK61_SETUP_TEXT, row, 0x100U | (field == active ? '>' : ' '), line);
  }
  if(rows > 1) {
    // A space marker reserves the same gutter as every menu row, so the live
    // sample aligns with the labels instead of protruding into their margin.
    service(MK61_SETUP_TEXT, rows - 1, 0x100U | ' ', (void*) (library_mk61::language_is_ru()
        ? "Аа Бб Wi 123" : "Aa Bb Wi 123"));
  }
}
#endif

bool font(void) {
#if MK61_SETUP_UI_FONT_CHOOSER
  if(!uiFontSettingsAvailable()) {
    // UC1609's calculator face is fixed, so USB Screen must not expose
    // the obsolete calculator-profile editor. F401 and old residents retain
    // the established fixed-cell editor.
    return uiFontServiceAvailable() ? action::MENU_BACK
                                    : calculatorFontSetup();
  }
  UiFontChoice ui_font = readUiFontChoice();
  u8 active = 0;
  drawUiFontSetup(active, ui_font);
  while(true) {
    const i32 key = waitFontSetupKey(main_lcd().displayModeRevision());
    noteFontSetupPhase(FontSetupPhase::KEY_RECEIVED);
    if(key == KEY_ESC_PRESS) {
      noteFontSetupPhase(FontSetupPhase::LEAVE);
      lcd_ru::restore_default_font();
      return action::MENU_BACK;
    }
    // USB Screen is monospaced. Never show a misleading proportional preview
    // there; mode changes also require a fresh row budget and complete frame.
    if(!uiFontSettingsAvailable()) {
      return uiFontServiceAvailable() ? action::MENU_BACK
                                      : calculatorFontSetup();
    }
    const u8 fields = uiFontFieldCount(ui_font);
    if(key == KEY_RIGHT_PRESS) {
      if(active + 1 < fields) ++active;
    } else if(key == KEY_LEFT_PRESS) {
      if(active > 0) --active;
    } else if(key == KEY_OK_PRESS || key == KEY_SHG_LEFT_PRESS ||
              key == KEY_SHG_RIGHT_PRESS) {
      const i8 delta = key == KEY_SHG_LEFT_PRESS ? -1 : 1;
      bool applied = false;
      MK61DisplayUpdate update(main_lcd());
      if(active == 0) {
        if(uiFontCatalogAvailable()) {
          applied = stepUiFontChoice(ui_font, delta);
        } else {
          ui_font.setting.family = stepLegacyUiFontFamily(
              ui_font.setting.family, delta);
          applied = service(MK61_SETUP_UI_FONT_APPLY, 0, 0,
                            &ui_font.setting) != 0;
        }
      } else {
        ui_font.setting.size = stepUiFontSize(ui_font.setting.size, delta);
        applied = service(MK61_SETUP_UI_FONT_APPLY, 0, 0,
                          &ui_font.setting) != 0;
      }
      if(!applied) ui_font = readUiFontChoice();
      else if(!uiFontCatalogAvailable() || active != 0)
        ui_font = readUiFontChoice();
      const u8 next_fields = uiFontFieldCount(ui_font);
      if(active >= next_fields) active = (u8) (next_fields - 1U);
      drawUiFontSetup(active, ui_font);
      continue;
    } else if(key != DISPLAY_MODE_CHANGED) {
      continue;
    }
    drawUiFontSetup(active, ui_font);
  }
#else
  return calculatorFontSetup();
#endif
}

void step_font(i8 delta) {
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
  auto profile = read_profile();
  stepFontSetupProfile(profile, 0, delta);
  MK61DisplayUpdate update(main_lcd());
  applyFontSetupProfile(profile);
#else
  (void) delta;
#endif
}

static void print_line(u8 row, const char* text) {
  main_lcd().setCursor(0, row);
  u8 n = 0;
  while(text[n] && n < lcd_display::COLS) main_lcd().write((u8) text[n++]);
  while(n++ < lcd_display::COLS) main_lcd().write(' ');
}
static void show_message(const char* en0, const char* ru0, const char* en1, const char* ru1) {
  lcd_ru::print_lines(library_mk61::language_is_ru() ? ru0 : en0,
                      library_mk61::language_is_ru() ? ru1 : en1);
}
static i32 wait_preview_key() {
  i32 key;
  do { key = wait_key_or_display_change(main_lcd().displayModeRevision()); }
  while(key == DISPLAY_MODE_CHANGED);
  return key;
}
static void draw_font_preview_header(const char* name, const fmk::Face& face) {
  char header[24];
  snprintf(header, sizeof(header), "f1 %ux%u %.12s",
    (unsigned) face.metrics().max_width, (unsigned) face.metrics().height,
    name);
  print_line(0, header);
}

void preview(const char* name, const u8* data, u16 len) {
  fmk::Face face;
  if(!face.open(data, len)) {
    show_message("Bad font", "Ошибка шрифта", name, name);
    wait_preview_key();
    return;
  }
  if(!main_lcd().graphicsMode() && !face.metrics().monospaced) {
    show_message("Proportional", "Пропорциональный", "Not supported", "Не поддержан");
    wait_preview_key();
    return;
  }

  if(main_lcd().graphicsMode()) {
    if(!service(MK61_SETUP_FONT_PREVIEW, len, 0, (void*) data)) {
      show_message("Preview error", "Ошибка просмотра", name, name);
      wait_preview_key();
      return;
    }

    {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().clear();
      draw_font_preview_header(name, face);
      if(main_lcd().rows() > 1) print_line(1, "0123456789+-*/");
      if(main_lcd().rows() > 2) print_line(2, "ABCDEFGHIJKLMNO");
      if(main_lcd().rows() > 3) print_line(3, "abcdefghijklmno");
      if(main_lcd().rows() > 4) lcd_ru::print_at(0, 4, "АБВГДЕЖЗИЙКЛМНО", lcd_display::COLS);
      if(main_lcd().rows() > 5) lcd_ru::print_at(0, 5, "абвгдежзийклмно", lcd_display::COLS);
      for(u8 row = 6; row < main_lcd().rows(); row++) print_line(row, "");
    }
    wait_preview_key();
    service(MK61_SETUP_FONT_PREVIEW_END);
    main_lcd().clear();
    return;
  }

#if defined(MK61_DISPLAY_LCD1602) || defined(MK61_BUILD_PORTABLE_SYSTEM)
  fmk::Glyph glyphs[8];
  if(fmk::selectPreviewGlyphs(face, glyphs) != 8) {
    show_message("No glyphs", "Нет символов", name, name);
    wait_preview_key();
    return;
  }

  u8 rows[8][8];
  for(u8 slot = 0; slot < 8; slot++) {
    if(!fmk::scaleToLcd5x8(face, glyphs[slot], rows[slot])) {
      show_message("Preview error", "Ошибка просмотра", name, name);
      wait_preview_key();
      return;
    }
    service(MK61_SETUP_LCD_CHAR, slot, 0, rows[slot]);
  }

  {
    MK61DisplayUpdate update(main_lcd());
    main_lcd().clear();
    draw_font_preview_header(name, face);
    main_lcd().setCursor(0, 1);
    for(u8 slot = 0; slot < 8; slot++) main_lcd().write(slot);
    for(u8 col = 8; col < lcd_display::COLS; col++) main_lcd().write((u8) ' ');
  }
  wait_preview_key();
  lcd_ru::restore_default_font();
  main_lcd().clear();
#else
  show_message("Preview error", "Ошибка просмотра", name, name);
  wait_preview_key();
#endif
}


} // namespace setup_ui
#endif
