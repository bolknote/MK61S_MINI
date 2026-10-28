#ifndef MK61_LCD1602_EDITOR_VIEWPORT_HPP
#define MK61_LCD1602_EDITOR_VIEWPORT_HPP

#include "character_display_geometry.hpp"

#include <stddef.h>

namespace lcd1602_editor_viewport {

static constexpr u8 ROWS = character_display_geometry::ROWS;
static constexpr u8 VISIBLE_COLS =
    character_display_geometry::VISIBLE_COLS;
static constexpr u8 TEXT_COLS = VISIBLE_COLS - 1;
static constexpr u8 DDRAM_COLS = character_display_geometry::DDRAM_COLS;

struct RowSpan {
  const char* text;
  u16 length;
};

struct Layout {
  u8 cells[ROWS][DDRAM_COLS];
  u8 shift;
  u8 cursor_col;
};

using ShiftPlan = character_display_geometry::ShiftPlan;

inline ShiftPlan shortest_shift(u8 current, u8 target) {
  return character_display_geometry::shortestShift(current, target);
}

inline u16 first_visible_column(u16 active_column) {
  return active_column >= TEXT_COLS
       ? (u16) (active_column - (TEXT_COLS - 1)) : 0;
}

inline void build(const RowSpan rows[ROWS], u8 active_row,
                  u16 active_column, Layout& layout) {
  if(active_row >= ROWS) active_row = 0;

  const u16 view_left = first_visible_column(active_column);
  layout.shift = (u8) (view_left % DDRAM_COLS);
  layout.cursor_col = (u8) (1 + active_column - view_left);
  if(layout.cursor_col >= VISIBLE_COLS) {
    layout.cursor_col = VISIBLE_COLS - 1;
  }

  for(u8 row = 0; row < ROWS; row++) {
    const char* const text = rows[row].text;
    const u16 length = text != NULL ? rows[row].length : 0;
    for(u8 address = 0; address < DDRAM_COLS; address++) {
      // DDRAM is the native controller ring: 40 cells on A00/A02 and 64 on
      // WS0010. Relative position zero is the row marker; the remaining cells
      // hold the current text window and its hidden continuation.
      const u8 relative = (u8) ((address + DDRAM_COLS - layout.shift) %
                                DDRAM_COLS);
      if(relative == 0) {
        layout.cells[row][address] = row == active_row ? (u8) '>'
                                                       : (u8) ' ';
        continue;
      }
      const u32 column = (u32) view_left + relative - 1;
      layout.cells[row][address] = column < length ? (u8) text[column]
                                                   : (u8) ' ';
    }
  }
}

} // пространство имён lcd1602_editor_viewport

#endif
