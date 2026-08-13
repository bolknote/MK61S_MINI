#ifndef MK61_CHARACTER_DISPLAY_GEOMETRY_HPP
#define MK61_CHARACTER_DISPLAY_GEOMETRY_HPP

#include "rust_types.h"

// The visible module geometry is shared by all character displays, while the
// hidden DDRAM ring belongs to the controller.  HD44780-compatible A00/A02
// modules expose 40 cells per row; WS0010 exposes all 64 cells per row.
namespace character_display_geometry {

static constexpr u8 ROWS = 2;
static constexpr u8 VISIBLE_COLS = 16;
#if defined(MK61_OLED1602_WS0010) || defined(DISPLAY_OLED1602_WS0010)
static constexpr u8 DDRAM_COLS = 64;
#else
static constexpr u8 DDRAM_COLS = 40;
#endif

struct ShiftPlan {
  u8 steps;
  bool left;
};

inline ShiftPlan shortestShift(u8 current, u8 target) {
  current = (u8) (current % DDRAM_COLS);
  target = (u8) (target % DDRAM_COLS);
  const u8 left_steps = (u8) ((target + DDRAM_COLS - current) % DDRAM_COLS);
  const u8 right_steps = (u8) ((current + DDRAM_COLS - target) % DDRAM_COLS);
  return left_steps <= right_steps ? ShiftPlan{left_steps, true}
                                   : ShiftPlan{right_steps, false};
}

constexpr u8 physicalAddress(u8 shift, u8 visible_column) {
  return (u8) ((shift + visible_column) % DDRAM_COLS);
}

} // namespace character_display_geometry

#endif
