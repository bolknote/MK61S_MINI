#ifndef TEXT_SCREEN_HPP
#define TEXT_SCREEN_HPP

#include "rust_types.h"

namespace text_screen {

static constexpr u8 COLS = 16;
static constexpr u8 MAX_ROWS = 10;

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

    void reset(u8 rows);
    void clear(void);
    void setCursor(u8 x, u8 y);
    void newline(void);
    void writeCodepoint(u16 codepoint);
    void writeByte(u8 value);

    u8 rows(void) const { return row_count; }
    u8 cursorX(void) const { return cursor_x; }
    u8 cursorY(void) const { return cursor_y; }
    u16 cell(u8 x, u8 y) const;
    bool cellIsCustom(u8 x, u8 y) const;

    void markCell(u8 x, u8 y);
    void markAll(void);
    void markCustomSlot(u8 slot);
    u16 dirtyMask(u8 row) const;
    void clearDirty(u8 row);
    void clearColumns(u16 mask);
    bool anyDirty(void) const;

  private:
    u16 cells[MAX_ROWS][COLS];
    u16 custom_cols[MAX_ROWS];
    u16 dirty_cols[MAX_ROWS];
    u8 row_count;
    u8 cursor_x;
    u8 cursor_y;

    void advance(void);
};

} // пространство имён text_screen

#endif
