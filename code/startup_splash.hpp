#ifndef MK61_STARTUP_SPLASH_HPP
#define MK61_STARTUP_SPLASH_HPP

#include "rust_types.h"

class MK61Display;

namespace startup_splash {

static constexpr u8 COLS = 16;
static constexpr u8 ROWS = 2;
static constexpr u8 FINAL_FRAME = COLS;
static constexpr t_time_ms LOGO_HOLD_MS = 1000;
static constexpr t_time_ms ANIMATION_MS = 2000;
static constexpr t_time_ms FRAME_MS = ANIMATION_MS / FINAL_FRAME;

enum class Result : u8 {
  COMPLETED,
  SKIPPED
};

inline u8 visibleTextColumns(u8 frame) {
  return frame < FINAL_FRAME ? frame : FINAL_FRAME;
}

inline void composeRow(const char* text, const u8* logo, u8 frame, u8 out[COLS]) {
  const u8 text_columns = visibleTextColumns(frame);
  const u8 text_offset = COLS - text_columns;

  for(u8 col = 0; col < text_columns; col++) out[col] = (u8) text[text_offset + col];
  for(u8 col = text_columns; col < COLS; col++) out[col] = logo[col - text_columns];
}

Result show(MK61Display& display, const char* model, const char* version);

} // пространство имён startup_splash

#endif
