#ifndef MK61_UI_FONT_SETTINGS_HPP
#define MK61_UI_FONT_SETTINGS_HPP

#include "rust_types.h"

// One byte, independent of the calculator's fixed-cell font profile. The
// Family and size share one byte. Existing 12/14 values keep their exact bit
// representation; size code 2 adds 16 px without a settings migration.
struct UiFontSettings {
  static constexpr u8 FAMILY_MASK = 0x03;
  static constexpr u8 SIZE_MASK = 0x0C;
  static constexpr u8 SIZE_SHIFT = 2;
  static constexpr u8 KNOWN_MASK = FAMILY_MASK | SIZE_MASK;
  static constexpr u8 DEFAULT_PRESET = 0x04; // legacy UI, 14 px if enabled

  u8 raw;

  constexpr UiFontSettings(void) : raw(DEFAULT_PRESET) {}
  constexpr explicit UiFontSettings(u8 value) : raw(value) {}
  constexpr u8 family(void) const { return raw & FAMILY_MASK; }
  constexpr u8 sizeCode(void) const { return (raw & SIZE_MASK) >> SIZE_SHIFT; }
  constexpr u8 size(void) const {
    return sizeCode() == 2 ? 16 : (sizeCode() == 1 ? 14 : 12);
  }
};

static_assert(sizeof(UiFontSettings) == 1, "UI font settings must fit one byte");

inline UiFontSettings normalize_ui_font_settings(u8 raw) {
  if((raw & (u8) ~UiFontSettings::KNOWN_MASK) != 0 ||
     (raw & UiFontSettings::FAMILY_MASK) > 2 ||
     ((raw & UiFontSettings::SIZE_MASK) >> UiFontSettings::SIZE_SHIFT) > 2) {
    return UiFontSettings();
  }
  return UiFontSettings(raw);
}

inline UiFontSettings make_ui_font_settings(u8 family, u8 size) {
  if(family > 2 || (size != 12 && size != 14 && size != 16)) return UiFontSettings();
  const u8 size_code = size == 16 ? 2U : (size == 14 ? 1U : 0U);
  return UiFontSettings((u8) (family | (size_code << UiFontSettings::SIZE_SHIFT)));
}

#endif
