#ifndef MK61_LCD1602_EDITOR_VIEWPORT_HPP
#define MK61_LCD1602_EDITOR_VIEWPORT_HPP

#include "lcd1602_shifted_viewport.hpp"

namespace lcd1602_editor_viewport {

static constexpr u8 ROWS = lcd1602_shifted_viewport::ROWS;
static constexpr u8 VISIBLE_COLS = lcd1602_shifted_viewport::VISIBLE_COLS;
static constexpr u8 TEXT_COLS = VISIBLE_COLS - 1;
static constexpr u8 DDRAM_COLS = lcd1602_shifted_viewport::DDRAM_COLS;

struct RowSpan {
  const char* text;
  u16 length;
};

struct Layout {
  u8 cells[ROWS][DDRAM_COLS];
  u8 shift;
  u8 cursor_col;
};

using ShiftPlan = lcd1602_shifted_viewport::ShiftPlan;

inline ShiftPlan shortest_shift(u8 current, u8 target) {
  return lcd1602_shifted_viewport::shortest_shift(current, target);
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
      // DDRAM каждой строки — кольцо из 40 знакомест. Относительная позиция
      // ноль всегда содержит маркер, следующие 39 заранее содержат текущий
      // текст и продолжение. При сдвиге на один столбец совпадают 38 из 40
      // физических ячеек, включая переход адреса 39 -> 0.
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
