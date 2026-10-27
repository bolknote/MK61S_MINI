#ifndef MK61_OLED_SETTINGS_HPP
#define MK61_OLED_SETTINGS_HPP

#include "rust_types.h"

// One journal byte dedicated to character-OLED policy. Explicit masks avoid
// implementation-defined C++ bitfield layout in persistent storage. The low
// nibble remains reserved until a current-control command is documented and
// qualified for the exact WEH001602A revision.
struct OledSettings {
  static constexpr u8 TIMEOUT_SHIFT = 4;
  static constexpr u8 TIMEOUT_MASK = 0x30;
  static constexpr u8 KNOWN_MASK = TIMEOUT_MASK;

  u8 raw;

  constexpr OledSettings(void) : raw(0) {}
  constexpr explicit OledSettings(u8 value) : raw(value) {}

  constexpr u8 timeout(void) const {
    return (u8) ((raw & TIMEOUT_MASK) >> TIMEOUT_SHIFT);
  }

  void setTimeout(u8 value) {
    raw = (u8) ((raw & (u8) ~TIMEOUT_MASK) |
                ((value << TIMEOUT_SHIFT) & TIMEOUT_MASK));
  }
};

static_assert(sizeof(OledSettings) == 1,
              "OledSettings must fit one journal byte");
static constexpr u8 DEFAULT_OLED_TIMEOUT = 2; // 15 minutes

inline OledSettings normalize_oled_settings(u8 raw_settings) {
  const u8 timeout = raw_settings == 0xFF
    ? DEFAULT_OLED_TIMEOUT
    : (u8) ((raw_settings & OledSettings::TIMEOUT_MASK) >>
            OledSettings::TIMEOUT_SHIFT);
  return OledSettings((u8) (timeout << OledSettings::TIMEOUT_SHIFT));
}

static_assert(OledSettings::TIMEOUT_MASK == 0x30 &&
              OledSettings::KNOWN_MASK == 0x30,
              "OLED journal bit allocation regression");

#endif
