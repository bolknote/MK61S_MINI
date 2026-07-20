#include "text_screen.hpp"

namespace text_screen {

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

Grid::Grid(void) : cells{{0}}, custom_cols{0}, dirty_cols{0}, row_count(1), cursor_x(0), cursor_y(0) {
  clear();
}

void Grid::reset(u8 rows) {
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

void Grid::writeCodepoint(u16 codepoint) {
  cells[cursor_y][cursor_x] = codepoint;
  custom_cols[cursor_y] &= (u16) ~((u16) 1 << cursor_x);
  markCell(cursor_x, cursor_y);
  advance();
}

void Grid::writeByte(u8 value) {
  if(value >= 8) {
    writeCodepoint(value);
    return;
  }
  cells[cursor_y][cursor_x] = value;
  custom_cols[cursor_y] |= (u16) 1 << cursor_x;
  markCell(cursor_x, cursor_y);
  advance();
}

u16 Grid::cell(u8 x, u8 y) const {
  return (x < COLS && y < row_count) ? cells[y][x] : (u16) ' ';
}

bool Grid::cellIsCustom(u8 x, u8 y) const {
  return x < COLS && y < row_count && (custom_cols[y] & ((u16) 1 << x)) != 0;
}

void Grid::markCell(u8 x, u8 y) {
  if(x < COLS && y < row_count) dirty_cols[y] |= (u16) 1 << x;
}

void Grid::markAll(void) {
  for(u8 row = 0; row < row_count; row++) dirty_cols[row] = 0xFFFF;
}

void Grid::markCustomSlot(u8 slot) {
  for(u8 row = 0; row < row_count; row++) {
    for(u8 col = 0; col < COLS; col++) {
      if(cellIsCustom(col, row) && cells[row][col] == (slot & 7)) markCell(col, row);
    }
  }
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

} // пространство имён text_screen
