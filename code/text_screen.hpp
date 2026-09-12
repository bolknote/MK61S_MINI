#ifndef TEXT_SCREEN_HPP
#define TEXT_SCREEN_HPP

#include "rust_types.h"

namespace text_screen {

static constexpr u8 COLS = 16;
static constexpr u8 MAX_ROWS = 10;
static constexpr usize CELL_CAPACITY = (usize) COLS * MAX_ROWS;
static constexpr usize FLAG_BYTES = (CELL_CAPACITY + 7U) / 8U;

struct FontGeometry {
  u8 rows;
  u8 width;
  u8 height;
  u8 line_gap;
};

FontGeometry fitFontToDisplay(u8 width, u8 height, u8 line_gap);
FontGeometry sanitizeFontGeometry(FontGeometry geometry);

class Grid {
  public:
    Grid(void);

    // Rows and columns share the same 160-token backing store. Excess rows
    // are clipped to capacity after columns have been normalised.
    void reset(u8 rows, u8 cols = COLS);
    void clear(void);
    void setCursor(u8 x, u8 y);
    void newline(void);
    // Возвращает true, только если видимое содержимое ячейки изменилось.
    // Курсор продвигается в любом случае, как у обычного текстового дисплея.
    bool writeCodepoint(u16 codepoint);
    bool writeByte(u8 value);

    u8 rows(void) const { return row_count; }
    u8 cols(void) const { return column_count; }
    u8 cursorX(void) const { return cursor_x; }
    u8 cursorY(void) const { return cursor_y; }
    u16 cell(u8 x, u8 y) const;
    bool cellIsCustom(u8 x, u8 y) const;

    void markCell(u8 x, u8 y);
    void markAll(void);
    bool markCustomSlot(u8 slot);
    // The legacy mask names individual columns only up to 16 columns. Wider
    // text rows return 0xFFFF for any damage and must be repainted as a unit.
    u16 dirtyMask(u8 row) const;
    void clearDirty(u8 row);
    void clearColumns(u16 mask);
    bool anyDirty(void) const;

  private:
    u16 cells[CELL_CAPACITY];
    u8 custom_cells[FLAG_BYTES];
    u8 dirty_cells[FLAG_BYTES];
    u8 row_count;
    u8 column_count;
    u8 cursor_x;
    u8 cursor_y;

    void advance(void);
    usize index(u8 x, u8 y) const { return (usize) y * column_count + x; }
};

} // пространство имён text_screen

#endif
