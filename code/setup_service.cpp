#include "config.h"
#include "setup_service.hpp"
#include "cross_hal.h"
#include "hardware_info.hpp"
#include "rtc_clock.hpp"
#include "menu.hpp"
#include "lcd_ru.hpp"
#include "crash_dump.hpp"
#include <string.h>

namespace setup_ui {
static u32 apply_font_profile(void* payload) {
#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
      if(!payload) return 0;
      const auto& in = *(const mk61_setup_profile*) payload;
      const auto profile = lcd_display::normalizeSettingsTextProfile({in.rows, in.width, in.height, in.gap});
      const auto old = library_mk61::display_text_profile();
      if(memcmp(&old, &profile, sizeof(profile)) == 0 && !main_lcd().externalFontActive()) return 1;
      // Caller holds a display update across profile, font and redraw.
      service(MK61_SETUP_PHASE, 4); main_lcd().useBuiltinFont();
      service(MK61_SETUP_PHASE, 5); library_mk61::set_display_text_profile(profile);
      main_lcd().setTextProfile(library_mk61::display_text_profile());
      service(MK61_SETUP_PHASE, 6); library_mk61::refresh_menu_text();
      library_mk61::mark_settings_dirty();
      return 1;
#else
      (void) payload;
      return 0;
#endif
}

u32 service(u32 operation, u32 a, u32 b, void* payload) {
  switch(operation) {
    case MK61_SETUP_VERSION: return 1;
    case MK61_SETUP_FEATURES:
      return (MK61_HAS_GRAPHICAL_TEXT_SETTINGS ? 1U : 0U) |
             (MK61_ENABLE_EXTENDED_FONT_SETTINGS ? 2U : 0U)
#if defined(MK61_DISPLAY_UC1609)
             | 4U
#endif
             ;
    case MK61_SETUP_HARDWARE: {
      if(!payload) return 0;
      auto& out = *(mk61_setup_hardware*) payload;
      out = {};
      const auto device = hardware_info::read_device_identity();
      const auto analog = hardware_info::read_analog_snapshot();
      out.idcode = device.device_id | ((u32) device.revision_id << 16);
      out.flash_kb = device.flash_kb; out.pin_code = device.pin_count_code;
      out.valid = analog.vdda.valid | (analog.mcu_temperature.valid << 1) |
                  (analog.battery.voltage.valid << 2);
      out.vdda = analog.vdda.millivolts; out.vbat = analog.battery.voltage.millivolts;
      out.temperature = analog.mcu_temperature.decicelsius;
      out.battery_presence = (u32) analog.battery.presence;
      out.battery_reason = (u32) analog.battery.reason;
      rtc_clock::ClockSource source = rtc_clock::ClockSource::LSI;
      strncpy(out.rtc_source, rtc_clock::read_clock_source(source)
          ? rtc_clock::clock_source_name(source) : "--", sizeof(out.rtc_source) - 1);
      strncpy(out.display, hardware_info::display_type(), sizeof(out.display) - 1);
      return 1;
    }
    case MK61_SETUP_RTC_READ: {
      if(!payload) return 0;
      rtc_clock::DateTime value = {};
      if(!rtc_clock::read(value) && !rtc_clock::parse_build_datetime(__DATE__, __TIME__, value))
        value = {2001, 1, 1, 0, 0, 0};
      *(mk61_setup_datetime*) payload = {value.year, value.month, value.day,
                                        value.hour, value.minute, value.second};
      return 1;
    }
    case MK61_SETUP_RTC_WRITE: {
      if(!payload) return 0;
      const auto& value = *(const mk61_setup_datetime*) payload;
      if(value.year > 65535 || value.month > 255 || value.day > 255 ||
         value.hour > 255 || value.minute > 255 || value.second > 255) return 0;
      return rtc_clock::set({(u16) value.year, (u8) value.month, (u8) value.day,
                             (u8) value.hour, (u8) value.minute, (u8) value.second});
    }
    case MK61_SETUP_RTC_CALIBRATION:
      return a == 0 ? (u32) (i32) rtc_clock::calibration_ppm()
          : (i32) b >= -487 && (i32) b <= 488 && rtc_clock::set_calibration_ppm((i16) b);
    case MK61_SETUP_FONT_READ: {
      if(!payload) return 0;
      const auto profile = library_mk61::display_text_profile();
      *(mk61_setup_profile*) payload = {profile.rows, profile.glyph_width,
                                       profile.glyph_height, profile.line_gap};
      return 1;
    }
    case MK61_SETUP_FONT_APPLY: return apply_font_profile(payload);
    case MK61_SETUP_UI_FONT_READ:
#if defined(MK61_DISPLAY_UC1609)
      if(!payload) return 0;
      *(mk61_setup_ui_font*) payload = {library_mk61::ui_font_family(),
                                       library_mk61::ui_font_size()};
      return 1;
#else
      return 0;
#endif
    case MK61_SETUP_UI_FONT_APPLY:
#if defined(MK61_DISPLAY_UC1609)
      if(!payload) return 0;
      {
        const auto& in = *(const mk61_setup_ui_font*) payload;
        if(in.family > 2 || (in.size != 12 && in.size != 14)) return 0;
        if(library_mk61::ui_font_family() == in.family &&
           library_mk61::ui_font_size() == in.size) return 1;
        library_mk61::set_ui_font(in.family, in.size);
        library_mk61::mark_settings_dirty();
      }
      return 1;
#else
      return 0;
#endif
    case MK61_SETUP_FONT_PREVIEW: return payload && a <= 1536 && main_lcd().setFontPreview((const u8*) payload, (u16) a);
    case MK61_SETUP_FONT_PREVIEW_END: main_lcd().clearFontPreview(); return 1;
    case MK61_SETUP_LCD_CHAR:
#if defined(MK61_DISPLAY_LCD1602)
      if(!payload || a >= 8) return 0;
      main_lcd().createChar((u8) a, (u8*) payload); return 1;
#else
      return 0;
#endif
    case MK61_SETUP_FONT_RESTORE: lcd_ru::restore_default_font(); return 1;
    case MK61_SETUP_TEXT:
      if(!payload || a >= main_lcd().rows()) return 0;
#if defined(MK61_DISPLAY_UC1609)
      if(main_lcd().uiTextActive() && ((b & 0x100U) || b == 0)) {
        main_lcd().printUiLine((u8) a, (const char*) payload,
                              (b & 0x100U) ? (char) b : 0);
        return 1;
      }
#endif
      if(b & 0x100U) lcd_ru::print_menu_line((u8) a, (char) b, (const char*) payload);
      else lcd_ru::print_at((u8) b, (u8) a, (const char*) payload, lcd_display::COLS);
      return 1;
    case MK61_SETUP_PHASE:
      crash_dump::update_runtime(crash_dump::RUNTIME_MENU, 0x464E0000UL | a, millis()); return 1;
    default: return 0;
  }
}
}
