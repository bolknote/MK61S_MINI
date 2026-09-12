#include "text_screen.hpp"

namespace text_screen {

#if MK61_PROPORTIONAL_UI_FONTS
namespace {

bool flag(const u8* bits, usize index) {
  return (bits[index / 8U] & ((u8) 1U << (index & 7U))) != 0;
}

void setFlag(u8* bits, usize index, bool value) {
  const u8 mask = (u8) ((u8) 1U << (index & 7U));
  if(value) bits[index / 8U] |= mask;
  else bits[index / 8U] &= (u8) ~mask;
}

} // namespace
#endif

FontGeometry sanitizeFontGeometry(FontGeometry geometry) {
  geometry.rows = geometry.rows < 4 ? 4 : (geometry.rows > MAX_ROWS ? MAX_ROWS : geometry.rows);
  geometry.width = geometry.width < 1 ? 1 : (geometry.width > 10 ? 10 : geometry.width);
  const u8 max_height_for_rows = (u8) (64 / geometry.rows);
  const u8 max_height = max_height_for_rows < 16 ? max_height_for_rows : 16;
  geometry.height = geometry.height < 1 ? 1 : (geometry.height > max_height ? max_height : geometry.height);
  const u16 glyph_pixels = (u16) geometry.rows * geometry.height;
  const u8 max_gap = geometry.rows <= 1 || glyph_pixels >= 64
    ? 0
    : (u8) ((64 - glyph_pixels) / (geometry.rows - 1));
  if(geometry.line_gap > max_gap) geometry.line_gap = max_gap;
  return geometry;
}

FontGeometry fitFontToDisplay(u8 width, u8 height, u8 line_gap) {
  FontGeometry result;
  result.width = width < 1 ? 1 : (width > 10 ? 10 : width);
  result.height = height < 1 ? 1 : (height > 16 ? 16 : height);
  result.line_gap = line_gap > 15 ? 15 : line_gap;
  const u8 pitch = result.height + result.line_gap;
  result.rows = pitch == 0 ? 4 : (u8) ((64 + result.line_gap) / pitch);
  result.rows = result.rows < 4 ? 4 : (result.rows > MAX_ROWS ? MAX_ROWS : result.rows);
  return sanitizeFontGeometry(result);
}

#if MK61_PROPORTIONAL_UI_FONTS
Grid::Grid(void) : cells{0}, custom_cells{0}, dirty_cells{0},
    row_count(1), column_count(COLS), cursor_x(0), cursor_y(0) {
  clear();
}

void Grid::reset(u8 rows, u8 cols) {
  column_count = cols < 1 ? 1 : (cols > CELL_CAPACITY ? (u8) CELL_CAPACITY : cols);
  row_count = rows < 1 ? 1 : (rows > MAX_ROWS ? MAX_ROWS : rows);
  const u8 max_rows = (u8) (CELL_CAPACITY / column_count);
  if(row_count > max_rows) row_count = max_rows;
  clear();
}

void Grid::clear(void) {
  for(usize cell = 0; cell < CELL_CAPACITY; cell++) cells[cell] = ' ';
  for(usize byte = 0; byte < FLAG_BYTES; byte++) {
    custom_cells[byte] = 0;
    dirty_cells[byte] = 0;
  }
  cursor_x = 0;
  cursor_y = 0;
}

void Grid::setCursor(u8 x, u8 y) {
  cursor_x = x < column_count ? x : (u8) (column_count - 1);
  cursor_y = y < row_count ? y : (u8) (row_count - 1);
}

void Grid::newline(void) {
  if(cursor_y + 1 < row_count) cursor_y++;
  cursor_x = 0;
}

void Grid::advance(void) {
  if(cursor_x + 1 < column_count) {
    cursor_x++;
    return;
  }
  cursor_x = 0;
  if(cursor_y + 1 < row_count) cursor_y++;
}

bool Grid::writeCodepoint(u16 codepoint) {
  const usize cell = index(cursor_x, cursor_y);
  const bool changed = cells[cell] != codepoint || flag(custom_cells, cell);
  if(changed) {
    cells[cell] = codepoint;
    setFlag(custom_cells, cell, false);
    markCell(cursor_x, cursor_y);
  }
  advance();
  return changed;
}

bool Grid::writeByte(u8 value) {
  if(value >= 8) {
    return writeCodepoint(value);
  }
  const usize cell = index(cursor_x, cursor_y);
  const bool changed = cells[cell] != value || !flag(custom_cells, cell);
  if(changed) {
    cells[cell] = value;
    setFlag(custom_cells, cell, true);
    markCell(cursor_x, cursor_y);
  }
  advance();
  return changed;
}

u16 Grid::cell(u8 x, u8 y) const {
  return (x < column_count && y < row_count) ? cells[index(x, y)] : (u16) ' ';
}

bool Grid::cellIsCustom(u8 x, u8 y) const {
  return x < column_count && y < row_count && flag(custom_cells, index(x, y));
}

void Grid::markCell(u8 x, u8 y) {
  if(x < column_count && y < row_count) setFlag(dirty_cells, index(x, y), true);
}

void Grid::markAll(void) {
  const usize count = (usize) row_count * column_count;
  const usize whole_bytes = count / 8U;
  for(usize byte = 0; byte < whole_bytes; byte++) dirty_cells[byte] = 0xFF;
  if((count & 7U) != 0) {
    dirty_cells[whole_bytes] = (u8) (((u16) 1U << (count & 7U)) - 1U);
  }
}

bool Grid::markCustomSlot(u8 slot) {
  bool found = false;
  for(u8 row = 0; row < row_count; row++) {
    for(u8 col = 0; col < column_count; col++) {
      if(cellIsCustom(col, row) && cells[index(col, row)] == (slot & 7)) {
        markCell(col, row);
        found = true;
      }
    }
  }
  return found;
}

u16 Grid::dirtyMask(u8 row) const {
  if(row >= row_count) return 0;
  if(column_count == COLS) {
    const usize byte = (usize) row * 2U;
    return (u16) dirty_cells[byte] | ((u16) dirty_cells[byte + 1U] << 8);
  }
  u16 mask = 0;
  for(u8 col = 0; col < column_count; col++) {
    if(!flag(dirty_cells, index(col, row))) continue;
    if(column_count > COLS) return 0xFFFF;
    mask |= (u16) ((u16) 1U << col);
  }
  return mask;
}

void Grid::clearDirty(u8 row) {
  if(row >= row_count) return;
  if(column_count == COLS) {
    dirty_cells[(usize) row * 2U] = 0;
    dirty_cells[(usize) row * 2U + 1U] = 0;
    return;
  }
  for(u8 col = 0; col < column_count; col++) {
    setFlag(dirty_cells, index(col, row), false);
  }
}

void Grid::clearColumns(u16 mask) {
  if(mask == 0xFFFF) {
    for(usize byte = 0; byte < FLAG_BYTES; byte++) dirty_cells[byte] = 0;
    return;
  }
  // A partial legacy mask cannot describe the damage of a wider text row.
  if(column_count > COLS) return;
  if(column_count == COLS) {
    for(u8 row = 0; row < row_count; row++) {
      dirty_cells[(usize) row * 2U] &= (u8) ~mask;
      dirty_cells[(usize) row * 2U + 1U] &= (u8) ~(mask >> 8);
    }
    return;
  }
  for(u8 row = 0; row < row_count; row++) {
    for(u8 col = 0; col < column_count; col++) {
      if((mask & ((u16) 1U << col)) != 0) {
        setFlag(dirty_cells, index(col, row), false);
      }
    }
  }
}

bool Grid::anyDirty(void) const {
  for(usize byte = 0; byte < FLAG_BYTES; byte++) {
    if(dirty_cells[byte] != 0) return true;
  }
  return false;
}

#else

Grid::Grid(void) : cells{{0}}, custom_cols{0}, dirty_cols{0},
    row_count(1), cursor_x(0), cursor_y(0) {
  clear();
}

void Grid::reset(u8 rows, u8 cols) {
  (void) cols;
  row_count = rows < 1 ? 1 : (rows > MAX_ROWS ? MAX_ROWS : rows);
  clear();
}

void Grid::clear(void) {
  for(u8 row = 0; row < MAX_ROWS; row++) {
    for(u8 col = 0; col < COLS; col++) cells[row][col] = ' ';
    custom_cols[row] = 0;
    dirty_cols[row] = 0;
  }
  cursor_x = 0;
  cursor_y = 0;
}

void Grid::setCursor(u8 x, u8 y) {
  cursor_x = x < COLS ? x : (u8) (COLS - 1);
  cursor_y = y < row_count ? y : (u8) (row_count - 1);
}

void Grid::newline(void) {
  if(cursor_y + 1 < row_count) cursor_y++;
  cursor_x = 0;
}

void Grid::advance(void) {
  if(cursor_x + 1 < COLS) {
    cursor_x++;
    return;
  }
  cursor_x = 0;
  if(cursor_y + 1 < row_count) cursor_y++;
}

bool Grid::writeCodepoint(u16 codepoint) {
  const u16 bit = (u16) 1U << cursor_x;
  const bool changed = cells[cursor_y][cursor_x] != codepoint ||
                       (custom_cols[cursor_y] & bit) != 0;
  if(changed) {
    cells[cursor_y][cursor_x] = codepoint;
    custom_cols[cursor_y] &= (u16) ~bit;
    markCell(cursor_x, cursor_y);
  }
  advance();
  return changed;
}

bool Grid::writeByte(u8 value) {
  if(value >= 8) return writeCodepoint(value);
  const u16 bit = (u16) 1U << cursor_x;
  const bool changed = cells[cursor_y][cursor_x] != value ||
                       (custom_cols[cursor_y] & bit) == 0;
  if(changed) {
    cells[cursor_y][cursor_x] = value;
    custom_cols[cursor_y] |= bit;
    markCell(cursor_x, cursor_y);
  }
  advance();
  return changed;
}

u16 Grid::cell(u8 x, u8 y) const {
  return (x < COLS && y < row_count) ? cells[y][x] : (u16) ' ';
}

bool Grid::cellIsCustom(u8 x, u8 y) const {
  return x < COLS && y < row_count &&
         (custom_cols[y] & ((u16) 1U << x)) != 0;
}

void Grid::markCell(u8 x, u8 y) {
  if(x < COLS && y < row_count) dirty_cols[y] |= (u16) 1U << x;
}

void Grid::markAll(void) {
  for(u8 row = 0; row < row_count; row++) dirty_cols[row] = 0xFFFF;
}

bool Grid::markCustomSlot(u8 slot) {
  bool found = false;
  for(u8 row = 0; row < row_count; row++) {
    for(u8 col = 0; col < COLS; col++) {
      if(cellIsCustom(col, row) && cells[row][col] == (slot & 7)) {
        markCell(col, row);
        found = true;
      }
    }
  }
  return found;
}

u16 Grid::dirtyMask(u8 row) const {
  return row < row_count ? dirty_cols[row] : 0;
}

void Grid::clearDirty(u8 row) {
  if(row < row_count) dirty_cols[row] = 0;
}

void Grid::clearColumns(u16 mask) {
  for(u8 row = 0; row < row_count; row++) dirty_cols[row] &= (u16) ~mask;
}

bool Grid::anyDirty(void) const {
  for(u8 row = 0; row < row_count; row++) {
    if(dirty_cols[row] != 0) return true;
  }
  return false;
}

#endif

} // пространство имён text_screen
