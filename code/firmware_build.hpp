#ifndef MK61_FIRMWARE_BUILD_HPP
#define MK61_FIRMWARE_BUILD_HPP

#include "config.h"

namespace firmware_build {

constexpr u32 fnv1a_character(u32 state, char value) {
  return (state ^ (u8) value) * 16777619UL;
}

constexpr u32 fnv1a_text(const char* text, u32 state = 2166136261UL) {
  return *text == 0 ? state : fnv1a_text(
      text + 1, fnv1a_character(state, *text));
}

#if defined(MK61_BOARD_CLASSIC_V2)
static constexpr char PROFILE[] = "classic-v2-uc1609";
#elif defined(MK61_BOARD_CLASSIC_V3)
static constexpr char PROFILE[] = "classic-v3-uc1609";
#elif defined(MK61_BOARD_40TH)
static constexpr char PROFILE[] = "40th-uc1609";
#elif defined(MK61_DISPLAY_UC1609)
// Compatibility selector retained for sketches that predate the explicit
// Classic V2/V3 board profiles.
static constexpr char PROFILE[] = "uc1609-compat";
#elif defined(MK61_OLED1602_WS0010)
  #if defined(REVISION_V2)
static constexpr char PROFILE[] = "mini-v2-ws0010";
  #else
static constexpr char PROFILE[] = "mini-v3-ws0010";
  #endif
#elif defined(MK61_LCD1602_A02)
  #if defined(REVISION_V2)
static constexpr char PROFILE[] = "mini-v2-a02";
  #else
static constexpr char PROFILE[] = "mini-v3-a02";
  #endif
#else
  #if defined(REVISION_V2)
static constexpr char PROFILE[] = "mini-v2-a00";
  #else
static constexpr char PROFILE[] = "mini-v3-a00";
  #endif
#endif

static constexpr u32 PROFILE_ID = fnv1a_text(PROFILE);

} // namespace firmware_build

#endif
