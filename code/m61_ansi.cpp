#include "m61_ansi.hpp"

namespace m61_ansi {

static u8 clamp_coord(u16 value, u8 limit) {
  if(limit == 0) return 0;
  return value >= limit ? (u8) (limit - 1) : (u8) value;
}

Writer::Writer(u8 cols_value, u8 rows_value, u8 initial_x, u8 initial_y,
               SavedCursor& saved, Sink output)
    : cols(cols_value == 0 ? 1 : cols_value),
      rows(rows_value == 0 ? 1 : rows_value),
      cursor_x(clamp_coord(initial_x, cols)),
      cursor_y(clamp_coord(initial_y, rows)),
      saved_cursor(saved),
      sink(output),
      parse_state(ParseState::TEXT),
      params{0},
      param_present{false},
      param_index(0) {}

bool Writer::put(u8 x, u8 y, u8 value) {
  return sink.put_byte != nullptr &&
         sink.put_byte(x, y, value, sink.user_data);
}

bool Writer::putAndAdvance(u8 value) {
  if(!put(cursor_x, cursor_y, value)) return false;
  if(cursor_x + 1 < cols) {
    cursor_x++;
  } else {
    cursor_x = 0;
    if(cursor_y + 1 < rows) cursor_y++;
  }
  return true;
}

void Writer::resetCsi(void) {
  for(u8 i = 0; i < MAX_PARAMS; i++) {
    params[i] = 0;
    param_present[i] = false;
  }
  param_index = 0;
}

u16 Writer::parameter(u8 index, u16 fallback, bool zero_is_default) const {
  if(index >= MAX_PARAMS || !param_present[index]) return fallback;
  const u16 value = params[index];
  return zero_is_default && value == 0 ? fallback : value;
}

void Writer::moveRelative(i16 dx, i16 dy) {
  i16 x = (i16) cursor_x + dx;
  i16 y = (i16) cursor_y + dy;
  if(x < 0) x = 0;
  if(y < 0) y = 0;
  if(x >= cols) x = cols - 1;
  if(y >= rows) y = rows - 1;
  cursor_x = (u8) x;
  cursor_y = (u8) y;
}

void Writer::setPosition(u16 row, u16 col) {
  const u16 row_zero = row == 0 ? 0 : row - 1;
  const u16 col_zero = col == 0 ? 0 : col - 1;
  cursor_y = clamp_coord(row_zero, rows);
  cursor_x = clamp_coord(col_zero, cols);
}

void Writer::saveCursor(void) {
  saved_cursor.x = cursor_x;
  saved_cursor.y = cursor_y;
  saved_cursor.valid = true;
}

void Writer::restoreCursor(void) {
  if(!saved_cursor.valid) return;
  cursor_x = clamp_coord(saved_cursor.x, cols);
  cursor_y = clamp_coord(saved_cursor.y, rows);
}

bool Writer::eraseLine(u16 mode) {
  u8 first = 0;
  u8 last = (u8) (cols - 1);
  if(mode == 0) first = cursor_x;
  else if(mode == 1) last = cursor_x;
  else if(mode != 2) return true;
  for(u8 x = first; x <= last; x++) {
    if(!put(x, cursor_y, ' ')) return false;
  }
  return true;
}

bool Writer::eraseDisplay(u16 mode) {
  if((mode == 2 || mode == 3) && sink.clear_screen != nullptr) {
    return sink.clear_screen(sink.user_data);
  }
  if(mode > 1) return true;

  for(u8 y = 0; y < rows; y++) {
    u8 first = 0;
    u8 last = (u8) (cols - 1);
    if(mode == 0) {
      if(y < cursor_y) continue;
      if(y == cursor_y) first = cursor_x;
    } else {
      if(y > cursor_y) break;
      if(y == cursor_y) last = cursor_x;
    }
    for(u8 x = first; x <= last; x++) {
      if(!put(x, y, ' ')) return false;
    }
  }
  return true;
}

bool Writer::applyCsi(u8 command) {
  const u16 amount = parameter(0, 1, true);
  switch(command) {
    case 'A': moveRelative(0, -(i16) amount); return true;
    case 'B': moveRelative(0, (i16) amount); return true;
    case 'C': moveRelative((i16) amount, 0); return true;
    case 'D': moveRelative(-(i16) amount, 0); return true;
    case 'E':
      moveRelative(0, (i16) amount);
      cursor_x = 0;
      return true;
    case 'F':
      moveRelative(0, -(i16) amount);
      cursor_x = 0;
      return true;
    case 'G':
      setPosition((u16) cursor_y + 1, parameter(0, 1, true));
      return true;
    case 'H':
    case 'f':
      setPosition(parameter(0, 1, true), parameter(1, 1, true));
      return true;
    case 'J': return eraseDisplay(parameter(0, 0, false));
    case 'K': return eraseLine(parameter(0, 0, false));
    case 's': saveCursor(); return true;
    case 'u': restoreCursor(); return true;
    case 'm': return true; // У SGR нет значимых монохромных атрибутов.
    default: return true;
  }
}

bool Writer::write(u8 value) {
  switch(parse_state) {
    case ParseState::ESCAPE:
      parse_state = ParseState::TEXT;
      if(value == '[') {
        resetCsi();
        parse_state = ParseState::CSI;
      } else if(value == '7') {
        saveCursor();
      } else if(value == '8') {
        restoreCursor();
      }
      return true;

    case ParseState::CSI:
      if(value >= '0' && value <= '9') {
        params[param_index] = (u16) (params[param_index] * 10U +
          (u16) (value - '0'));
        if(params[param_index] > 999U) params[param_index] = 999U;
        param_present[param_index] = true;
        return true;
      }
      if(value == ';') {
        if(param_index + 1 < MAX_PARAMS) param_index++;
        return true;
      }
      if(value >= 0x40U && value <= 0x7EU) {
        parse_state = ParseState::TEXT;
        return applyCsi(value);
      }
      // Частные и промежуточные байты CSI принимаются, но игнорируются.
      if(value >= 0x20U && value <= 0x3FU) return true;
      parse_state = ParseState::TEXT;
      return true;

    case ParseState::TEXT:
      break;
  }

  switch(value) {
    case 0x1B:
      parse_state = ParseState::ESCAPE;
      return true;
    case '\r':
      cursor_x = 0;
      return true;
    case '\n':
      cursor_x = 0;
      if(cursor_y + 1 < rows) cursor_y++;
      return true;
    case '\b':
      if(cursor_x > 0) cursor_x--;
      return true;
    case '\t': {
      const u8 next = (u8) ((cursor_x + 4U) & (u8) ~3U);
      cursor_x = next < cols ? next : (u8) (cols - 1);
      return true;
    }
    default:
      return putAndAdvance(value);
  }
}

} // пространство имён m61_ansi
