#ifndef MK61_UI_FONT_SETTINGS_HPP
#define MK61_UI_FONT_SETTINGS_HPP

#include "rust_types.h"

// One byte, independent of the calculator's fixed-cell font profile. The
// family is stored explicitly; the high size bit selects 14 instead of 12 px.
struct UiFontSettings {
  static constexpr u8 FAMILY_MASK = 0x03;
  static constexpr u8 LARGE_MASK = 0x04;
  static constexpr u8 KNOWN_MASK = FAMILY_MASK | LARGE_MASK;
  static constexpr u8 DEFAULT_PRESET = LARGE_MASK; // legacy UI, 14 px if enabled

  u8 raw;

  constexpr UiFontSettings(void) : raw(DEFAULT_PRESET) {}
  constexpr explicit UiFontSettings(u8 value) : raw(value) {}
  constexpr u8 family(void) const { return raw & FAMILY_MASK; }
  constexpr u8 size(void) const { return (raw & LARGE_MASK) ? 14 : 12; }
};

static_assert(sizeof(UiFontSettings) == 1, "UI font settings must fit one byte");

inline UiFontSettings normalize_ui_font_settings(u8 raw) {
  if((raw & (u8) ~UiFontSettings::KNOWN_MASK) != 0 ||
     (raw & UiFontSettings::FAMILY_MASK) > 2) return UiFontSettings();
  return UiFontSettings(raw);
}

inline UiFontSettings make_ui_font_settings(u8 family, u8 size) {
  if(family > 2 || (size != 12 && size != 14)) return UiFontSettings();
  return UiFontSettings((u8) (family | (size == 14 ? UiFontSettings::LARGE_MASK : 0)));
}

#endif
