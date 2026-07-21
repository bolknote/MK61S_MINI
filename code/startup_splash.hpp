#ifndef MK61_STARTUP_SPLASH_HPP
#define MK61_STARTUP_SPLASH_HPP

#include "lcd1602_shifted_viewport.hpp"
#include "rust_types.h"

class MK61Display;

namespace startup_splash {

static constexpr u8 COLS = 16;
static constexpr u8 ROWS = 2;
static constexpr u8 FINAL_FRAME = COLS;
static constexpr t_time_ms LOGO_HOLD_MS = 1000;
static constexpr t_time_ms ANIMATION_MS = 2000;
static constexpr t_time_ms FRAME_MS = ANIMATION_MS / FINAL_FRAME;
static constexpr t_time_ms FINAL_HOLD_MS = 500;

static_assert(COLS == lcd1602_shifted_viewport::VISIBLE_COLS,
              "LCD1602 splash width mismatch");
static_assert(ROWS == lcd1602_shifted_viewport::ROWS,
              "LCD1602 splash height mismatch");
static constexpr u8 LCD1602_TEXT_START =
    lcd1602_shifted_viewport::DDRAM_COLS - COLS;

enum class Result : u8 {
  COMPLETED,
  SKIPPED
};

enum class EscapePolicy : u8 {
  ALLOW_SKIP,
  IGNORE
};

inline bool escapeMaySkip(EscapePolicy policy) {
  return policy == EscapePolicy::ALLOW_SKIP;
}

inline u8 visibleTextColumns(u8 frame) {
  return frame < FINAL_FRAME ? frame : FINAL_FRAME;
}

inline void composeRow(const char* text, const u8* logo, u8 frame, u8 out[COLS]) {
  const u8 text_columns = visibleTextColumns(frame);
  const u8 text_offset = COLS - text_columns;

  for(u8 col = 0; col < text_columns; col++) out[col] = (u8) text[text_offset + col];
  for(u8 col = text_columns; col < COLS; col++) out[col] = logo[col - text_columns];
}

// Физическая DDRAM собирается один раз: логотип виден при shift=0, а текст
// лежит перед ним в кольце 2x40. Шестнадцать сдвигов вправо воспроизводят те
// же кадры, которые composeRow() строит полной перерисовкой.
inline void composeLcd1602DdramRow(
    const char* text, const u8* logo,
    u8 out[lcd1602_shifted_viewport::DDRAM_COLS]) {
  for(u8 address = 0; address < lcd1602_shifted_viewport::DDRAM_COLS;
      address++) out[address] = ' ';
  for(u8 col = 0; col < COLS; col++) {
    out[col] = logo[col];
    out[LCD1602_TEXT_START + col] = (u8) text[col];
  }
}

inline u8 lcd1602ShiftForFrame(u8 frame) {
  const u8 text_columns = visibleTextColumns(frame);
  return text_columns == 0 ? 0 : (u8) (
      lcd1602_shifted_viewport::DDRAM_COLS - text_columns);
}

// Перед Return Home копируем финальный текст в домашнее окно. На последнем
// кадре эти адреса скрыты, поэтому возврат shift=0 получается бесшовным.
inline void stabilizeLcd1602DdramRow(
    const char* text, u8 row[lcd1602_shifted_viewport::DDRAM_COLS]) {
  for(u8 col = 0; col < COLS; col++) row[col] = (u8) text[col];
}

Result show(MK61Display& display, const char* model, const char* version,
            EscapePolicy escape_policy = EscapePolicy::ALLOW_SKIP);

} // пространство имён startup_splash

#endif
