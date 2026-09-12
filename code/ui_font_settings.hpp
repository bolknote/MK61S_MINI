#ifndef MK61_UI_FONT_SETTINGS_HPP
#define MK61_UI_FONT_SETTINGS_HPP

#include "rust_types.h"

// One byte, independent of the calculator's fixed-cell font profile. The
// Family and size share one byte. Legacy family 2 (Roboto) migrates to Pixel;
// family 3 selects the replaceable UI12/UI14/UI16 FMK family.
struct UiFontSettings {
  static constexpr u8 FAMILY_MASK = 0x03;
  static constexpr u8 SIZE_MASK = 0x0C;
  static constexpr u8 SIZE_SHIFT = 2;
  static constexpr u8 KNOWN_MASK = FAMILY_MASK | SIZE_MASK;
  static constexpr u8 DEFAULT_PRESET = 0x04; // fixed 5x8; remember size 14

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
     (raw & UiFontSettings::FAMILY_MASK) > 3 ||
     ((raw & UiFontSettings::SIZE_MASK) >> UiFontSettings::SIZE_SHIFT) > 2) {
    return UiFontSettings();
  }
  if((raw & UiFontSettings::FAMILY_MASK) == 2) {
    raw = (u8) ((raw & (u8) ~UiFontSettings::FAMILY_MASK) | 1U);
  }
  return UiFontSettings(raw);
}

inline UiFontSettings make_ui_font_settings(u8 family, u8 size) {
  if(family > 3 || (size != 12 && size != 14 && size != 16)) return UiFontSettings();
  if(family == 2) family = 1; // compatibility with the retired Roboto family
  const u8 size_code = size == 16 ? 2U : (size == 14 ? 1U : 0U);
  return UiFontSettings((u8) (family | (size_code << UiFontSettings::SIZE_SHIFT)));
}

#endif
