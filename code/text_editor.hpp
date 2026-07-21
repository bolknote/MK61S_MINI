#ifndef TEXT_EDITOR_HPP
#define TEXT_EDITOR_HPP

#include "keyboard_layout.hpp"
#include "rust_types.h"

#ifndef TEXT_EDITOR_HOST_TEST
#include "lcd_gui.hpp"
#endif

#if defined(MK61_DISPLAY_LCD1602) && !defined(TEXT_EDITOR_HOST_TEST)
#include "lcd1602_editor_viewport.hpp"
static_assert(lcd1602_editor_viewport::ROWS == lcd_display::ROWS,
              "Editor viewport must match the LCD row count");
static_assert(lcd1602_editor_viewport::VISIBLE_COLS == lcd_display::COLS,
              "Editor viewport must match the visible LCD width");
static_assert(lcd1602_editor_viewport::DDRAM_COLS == lcd_display::DDRAM_COLS,
              "Editor viewport must match the HD44780 DDRAM width");
#endif

#include <string.h>

namespace text_editor {

static constexpr u32 SMS_INPUT_TIMEOUT_MS = 1200;
static constexpr u8  CURSOR_ASCII        = 0xFF;
static constexpr u8  SMS_CURSOR_ASCII    = '_';

enum class Shift : u8 {
  NONE,
  ALPHA,
  K
};

struct SmsState {
  bool active;
  i32 key_code;
  u8 index;
  u32 deadline_ms;
};

struct Buffer {
  char* source;
  u16 capacity;
  u16 len;
  u16 cursor;
  u16 view_top;
  Shift shift;
  SmsState sms;
};

struct KeyMap {
  i32 left;
  i32 left_press;
  i32 right;
  i32 right_press;
  i32 ok;
  i32 ok_press;
  i32 esc;
  i32 esc_press;
  i32 shg_left_press;
  i32 shg_right_press;
  i32 k;
  i32 alpha;
  i32 pp;
};

struct Hooks {
  const char* (*insert_text_for_key)(Shift shift, i32 key_code, const char* source, u16 cursor, void* context);
  bool (*apply_alpha_macro)(char* source, u16& len, u16& cursor, u16 capacity, i32 key_code, void* context);
  bool (*move_cursor_horizontal)(const char* source, u16 len, u16& cursor, int delta, void* context);
  bool (*backspace)(char* source, u16& len, u16& cursor, u16 capacity, void* context);
  void* context;
};

struct Options {
  const char* ok_insert_text;
  bool sms_enabled;
  bool alpha_digit_symbols;
  bool alpha_cx_clear_line;
  i32 backspace_key;
};

enum class KeyResult : u8 {
  NONE,
  DIRTY,
  SAVE
};

#if defined(MK61_DISPLAY_LCD1602) && !defined(TEXT_EDITOR_HOST_TEST)
// Аппаратный shift HD44780 относится сразу к обеим строкам и переживает
// обычные записи в DDRAM. Сессия гарантирует возврат дисплея к стандартному
// положению при любом выходе из редактора, в том числе через ранний return.
class DisplaySession {
  public:
    explicit DisplaySession(MK61Display& display) : display(display) {}
    ~DisplaySession(void) {
      display.endShiftedViewport();
    }

  private:
    MK61Display& display;

    DisplaySession(const DisplaySession&) = delete;
    DisplaySession& operator=(const DisplaySession&) = delete;
};
#endif

inline const Options& default_options(void) {
  static const Options options = {
    "\n",
    true,
    true,
    true,
    keyboard_layout::ACTIVE.cx
  };
  return options;
}

inline void sms_reset(SmsState& sms) {
  sms.active = false;
  sms.key_code = -1;
  sms.index = 0;
  sms.deadline_ms = 0;
}

inline bool time_reached(u32 now, u32 target) {
  return (i32) (now - target) >= 0;
}

inline bool sms_expired(const SmsState& sms, u32 now) {
  return sms.active && time_reached(now, sms.deadline_ms);
}

inline usize bounded_length(const char* text, usize capacity) {
  if(text == NULL) return 0;
  usize len = 0;
  while(len < capacity && text[len] != 0) len++;
  return len;
}

inline bool valid_buffer(const char* source, u16 len, u16 cursor, u16 capacity) {
  return source != NULL && capacity != 0 && len < capacity && cursor <= len && source[len] == 0;
}

inline void sanitize(Buffer& editor) {
  if(editor.source == NULL || editor.capacity == 0) {
    editor.len = 0;
    editor.cursor = 0;
    editor.view_top = 0;
    sms_reset(editor.sms);
    return;
  }

  usize len = bounded_length(editor.source, editor.capacity);
  if(len == editor.capacity) {
    editor.source[editor.capacity - 1] = 0;
    len = editor.capacity - 1;
  }
  editor.len = (u16) len;
  if(editor.cursor > editor.len) editor.cursor = editor.len;
  if(editor.view_top > editor.len) editor.view_top = editor.len;
}

inline void init(Buffer& editor, char* source, u16 capacity) {
  editor.source = source;
  editor.capacity = capacity;
  editor.len = 0;
  editor.cursor = 0;
  editor.view_top = 0;
  editor.shift = Shift::NONE;
  sms_reset(editor.sms);
  sanitize(editor);
}

inline int digit_from_key(i32 key_code, const keyboard_layout::Mapping& mapping) {
  return keyboard_layout::digit_from_key(mapping, key_code);
}

inline int digit_from_key(i32 key_code) {
  return digit_from_key(key_code, keyboard_layout::ACTIVE);
}

inline const char* sms_letters_for_key(i32 key_code, const keyboard_layout::Mapping& mapping) {
  switch(digit_from_key(key_code, mapping)) {
    case 1: return "PQRS";
    case 2: return "TUV";
    case 3: return "WXYZ";
    case 4: return "GHI";
    case 5: return "JKL";
    case 6: return "MNO";
    case 8: return "ABC";
    case 9: return "DEF";
    default: break;
  }
  return NULL;
}

inline const char* sms_letters_for_key(i32 key_code) {
  return sms_letters_for_key(key_code, keyboard_layout::ACTIVE);
}

inline bool sms_key_is_letters(i32 key_code) {
  return sms_letters_for_key(key_code) != NULL;
}

inline bool sms_key_is_letters(i32 key_code, const keyboard_layout::Mapping& mapping) {
  return sms_letters_for_key(key_code, mapping) != NULL;
}

inline bool sms_key_is_space(i32 key_code) {
  return digit_from_key(key_code) == 7;
}

inline bool sms_key_is_space(i32 key_code, const keyboard_layout::Mapping& mapping) {
  return digit_from_key(key_code, mapping) == 7;
}

inline const char* symbol_for_digit_key(i32 key_code, const keyboard_layout::Mapping& mapping) {
  switch(digit_from_key(key_code, mapping)) {
    case 0: return "!";
    case 1: return "@";
    case 2: return "#";
    case 3: return "$";
    case 4: return "%";
    case 5: return "^";
    case 6: return "&";
    case 7: return "*";
    case 8: return "(";
    case 9: return ")";
    default: break;
  }
  return NULL;
}

inline const char* symbol_for_digit_key(i32 key_code) {
  return symbol_for_digit_key(key_code, keyboard_layout::ACTIVE);
}

inline const char* kshift_text_for_key(i32 key_code, const keyboard_layout::Mapping& mapping) {
  if(key_code == mapping.ok) return ":";
  if(key_code == mapping.ret) return ";";
  if(key_code == mapping.pp) return ",";
  if(key_code == mapping.left) return "(";
  if(key_code == mapping.right) return ")";
  if(key_code == mapping.xy) return "\"";
  if(key_code == mapping.add) return "=";
  if(key_code == mapping.dot) return "'";
  if(key_code == mapping.run) return "!";
  if(key_code == mapping.shg_left) return "<";
  if(key_code == mapping.sub) return ">";
  return NULL;
}

inline const char* kshift_text_for_key(i32 key_code) {
  return kshift_text_for_key(key_code, keyboard_layout::ACTIVE);
}

inline const char* plain_text_for_key(i32 key_code, const keyboard_layout::Mapping& mapping) {
  if(key_code == mapping.mul) return "*";
  if(key_code == mapping.div) return "/";
  if(key_code == mapping.power) return "^";
  if(key_code == mapping.add) return "+";
  if(key_code == mapping.sub) return "-";
  if(key_code == mapping.dot) return ".";
  if(key_code == mapping.pp) return " ";

  switch(digit_from_key(key_code, mapping)) {
    case 0: return "0";
    case 1: return "1";
    case 2: return "2";
    case 3: return "3";
    case 4: return "4";
    case 5: return "5";
    case 6: return "6";
    case 7: return "7";
    case 8: return "8";
    case 9: return "9";
    default: break;
  }
  return NULL;
}

inline const char* plain_text_for_key(i32 key_code) {
  return plain_text_for_key(key_code, keyboard_layout::ACTIVE);
}

inline u16 line_start_for_cursor(const char* source, u16 cursor) {
  if(source == NULL) return 0;
  u16 start = cursor;
  while(start > 0 && source[start - 1] != '\n' && source[start - 1] != '\r') start--;
  return start;
}

inline u16 line_end_for_start(const char* source, u16 start, u16 len) {
  if(source == NULL) return 0;
  if(start > len) start = len;
  u16 end = start;
  while(end < len && source[end] != '\n' && source[end] != '\r') end++;
  return end;
}

inline u16 line_separator_end(const char* source, u16 start, u16 len) {
  if(source == NULL || start >= len || (source[start] != '\n' && source[start] != '\r')) return start;
  const char first = source[start++];
  if(start < len && (source[start] == '\n' || source[start] == '\r') && source[start] != first) start++;
  return start;
}

inline u16 next_line_start(const char* source, u16 start, u16 len) {
  if(source == NULL) return 0;
  if(start > len) start = len;
  u16 pos = start;
  while(pos < len && source[pos] != '\n' && source[pos] != '\r') pos++;
  return line_separator_end(source, pos, len);
}

inline u16 previous_line_start(const char* source, u16 start) {
  if(source == NULL || start == 0) return 0;
  u16 pos = start;
  if(source[pos - 1] == '\n' || source[pos - 1] == '\r') {
    const char last = source[--pos];
    if(pos > 0 && (source[pos - 1] == '\n' || source[pos - 1] == '\r') && source[pos - 1] != last) pos--;
  }
  while(pos > 0 && source[pos - 1] != '\n' && source[pos - 1] != '\r') pos--;
  return pos;
}

inline bool move_cursor_left(const char* source, u16& cursor) {
  if(source == NULL) return false;
  const u16 line_start = line_start_for_cursor(source, cursor);
  if(cursor <= line_start) return false;
  cursor--;
  return true;
}

inline bool move_cursor_right(const char* source, u16 len, u16& cursor) {
  if(source == NULL) return false;
  if(cursor > len) cursor = len;
  const u16 line_start = line_start_for_cursor(source, cursor);
  const u16 line_end = line_end_for_start(source, line_start, len);
  if(cursor >= line_end) return false;
  cursor++;
  return true;
}

inline bool move_cursor_line(const char* source, u16 len, u16& cursor, int delta) {
  if(source == NULL) return false;
  if(cursor > len) cursor = len;
  const u16 line_start = line_start_for_cursor(source, cursor);
  const u16 line_end = line_end_for_start(source, line_start, len);
  const u16 column = cursor - line_start;
  u16 target_start = line_start;

  if(delta < 0) {
    if(line_start == 0) return false;
    target_start = previous_line_start(source, line_start);
  } else if(delta > 0) {
    if(line_end >= len) return false;
    target_start = next_line_start(source, line_start, len);
  } else {
    return false;
  }

  const u16 target_end = line_end_for_start(source, target_start, len);
  const u16 target_len = target_end - target_start;
  cursor = target_start + ((column < target_len) ? column : target_len);
  return true;
}

inline u8 visible_rows(MK61Display& display) {
  const u8 rows = display.rows();
  return rows < 2 ? 2 : rows;
}

inline void ensure_cursor_visible(MK61Display& display, const char* source, u16 len, u16 cursor, u16& view_top) {
  if(source == NULL) {
    view_top = 0;
    return;
  }
  if(cursor > len) cursor = len;
  if(view_top > len) view_top = len;
  view_top = line_start_for_cursor(source, view_top);

  const u16 cursor_line_start = line_start_for_cursor(source, cursor);
  if(cursor_line_start < view_top) {
    view_top = cursor_line_start;
    return;
  }

  const u8 rows = visible_rows(display);
  u16 line_start = view_top;
  for(u8 row = 0; row < rows; row++) {
    if(line_start == cursor_line_start) return;
    if(line_start >= len) break;
    const u16 next_line = next_line_start(source, line_start, len);
    if(next_line == line_start) break;
    line_start = next_line;
  }

  view_top = cursor_line_start;
  for(u8 row = 1; row < rows && view_top > 0; row++) {
    view_top = previous_line_start(source, view_top);
  }
}

inline u8 cursor_screen_row(MK61Display& display, const char* source, u16 len, u16 cursor, u16 view_top) {
  if(source == NULL) return 0;
  if(cursor > len) cursor = len;
  if(view_top > len) view_top = len;
  const u16 cursor_line_start = line_start_for_cursor(source, cursor);
  u16 line_start = view_top;
  const u8 rows = visible_rows(display);
  for(u8 row = 0; row < rows; row++) {
    if(line_start == cursor_line_start) return row;
    if(line_start >= len) break;
    const u16 next_line = next_line_start(source, line_start, len);
    if(next_line == line_start) break;
    line_start = next_line;
  }
  return 0;
}

inline void draw(MK61Display& display, const char* source, u16 len, u16 cursor, u16 view_top, bool sms_cursor = false) {
  static const char EMPTY[] = "";
  if(source == NULL) {
    source = EMPTY;
    len = 0;
  }
  const usize actual_len = bounded_length(source, len);
  if(actual_len < len) len = (u16) actual_len;
  if(cursor > len) cursor = len;
  if(view_top > len) view_top = len;

#if defined(MK61_DISPLAY_LCD1602) && !defined(TEXT_EDITOR_HOST_TEST)
  {
    lcd1602_editor_viewport::RowSpan row_spans[lcd1602_editor_viewport::ROWS] = {};
    u16 line_start = view_top;
    for(u8 row = 0; row < lcd1602_editor_viewport::ROWS; row++) {
      if(line_start > len) break;
      const u16 line_end = line_end_for_start(source, line_start, len);
      row_spans[row].text = source + line_start;
      row_spans[row].length = (u16) (line_end - line_start);
      if(line_start == len) break;
      line_start = next_line_start(source, line_start, len);
    }

    const u16 active_line_start = line_start_for_cursor(source, cursor);
    const u16 active_line_column = (u16) (cursor - active_line_start);
    const u8 cursor_row = cursor_screen_row(display, source, len, cursor, view_top);
    lcd1602_editor_viewport::Layout layout = {};
    lcd1602_editor_viewport::build(row_spans, cursor_row,
                                   active_line_column, layout);
    display.renderShiftedViewport(layout.cells, layout.shift);
    display.setCursor(layout.cursor_col, cursor_row);
    if(display.supportsCursor()) display.cursorOn();
    else display.write(sms_cursor ? SMS_CURSOR_ASCII : CURSOR_ASCII);
    return;
  }
#endif

  MK61DisplayUpdate update(display);
  display.clear();
  const u8 rows = visible_rows(display);
  u16 line_start = view_top;
  const u16 active_line_start = line_start_for_cursor(source, cursor);
  const u16 active_line_column = cursor - active_line_start;
  const u16 active_line_window = (active_line_column > 14) ? (active_line_column - 14) : 0;
  const u8 cursor_row = cursor_screen_row(display, source, len, cursor, view_top);
  const u8 cursor_col = (u8) (1 + active_line_column - active_line_window);

  for(u8 row = 0; row < rows; row++) {
    if(line_start > len) break;
    const bool empty_end_line = line_start == len;
    display.setCursor(0, row);
    const bool active_row = line_start == active_line_start;
    display.write((u8) (active_row ? '>' : ' '));
    u16 pos = line_start + (active_row ? active_line_window : 0);
    u8 col = 1;
    while(pos < len && source[pos] != '\n' && source[pos] != '\r' && col < 16) {
      display.write((u8) source[pos++]);
      col++;
    }
    while(col++ < 16) display.write((u8) ' ');
    if(empty_end_line) break;
    line_start = next_line_start(source, line_start, len);
  }

  display.setCursor(cursor_col, cursor_row);
  if(display.supportsCursor()) display.cursorOn();
  else display.write(sms_cursor ? SMS_CURSOR_ASCII : CURSOR_ASCII);
}

inline bool insert_text(char* source, u16& len, u16& cursor, u16 capacity, const char* text) {
  if(!valid_buffer(source, len, cursor, capacity) || text == NULL || text[0] == 0) return false;
  const usize remaining = (usize) capacity - len;
  const usize text_len = bounded_length(text, remaining);
  if(text_len == 0 || text_len >= remaining) return false;
  memmove(&source[cursor + text_len], &source[cursor], len - cursor + 1);
  memcpy(&source[cursor], text, text_len);
  cursor = (u16) (cursor + text_len);
  len = (u16) (len + text_len);
  return true;
}

inline bool backspace(char* source, u16& len, u16& cursor) {
  if(source == NULL || cursor == 0 || cursor > len || source[len] != 0) return false;
  memmove(&source[cursor - 1], &source[cursor], len - cursor + 1);
  cursor--;
  len--;
  return true;
}

inline bool apply_single_line_cx(char* source, u16& len, u16 capacity, bool clear_all) {
  if(source == NULL || capacity == 0 || len >= capacity || source[len] != 0) return false;
  if(clear_all) {
    len = 0;
    source[0] = 0;
    return true;
  }
  if(len > 0) source[--len] = 0;
  return true;
}

inline bool replace_range(char* source, u16& len, u16& cursor, u16 capacity, u16 start, u16 end, const char* replacement) {
  if(!valid_buffer(source, len, cursor, capacity) || replacement == NULL || start > end || end > len) return false;
  const usize old_len = (usize) (end - start);
  const usize base_len = (usize) len - old_len;
  const usize remaining = (usize) capacity - base_len;
  const usize replacement_len = bounded_length(replacement, remaining);
  if(replacement_len >= remaining) return false;
  memmove(&source[start + replacement_len], &source[end], len - end + 1);
  memcpy(&source[start], replacement, replacement_len);
  len = (u16) ((usize) len - old_len + replacement_len);
  cursor = (u16) (start + replacement_len);
  return true;
}

inline bool clear_current_line(char* source, u16& len, u16& cursor, u16 capacity) {
  if(!valid_buffer(source, len, cursor, capacity)) return false;

  const u16 start = line_start_for_cursor(source, cursor);
  const u16 end = line_end_for_start(source, start, len);
  if(start < end) return replace_range(source, len, cursor, capacity, start, end, "");

  // Уже пустая строка удаляется вместе со следующим за ней разделителем.
  // Для пустой строки в конце файла вместо него удаляется предыдущий разделитель.
  if(end < len) {
    return replace_range(source, len, cursor, capacity, start, line_separator_end(source, end, len), "");
  }
  if(start == 0) return false;

  u16 separator_start = start - 1;
  const char last = source[separator_start];
  if(separator_start > 0 && (source[separator_start - 1] == '\n' || source[separator_start - 1] == '\r') &&
      source[separator_start - 1] != last) {
    separator_start--;
  }
  return replace_range(source, len, cursor, capacity, separator_start, start, "");
}

inline bool sms_tap(char* source, u16& len, u16& cursor, u16 capacity, SmsState& sms, i32 key_code, u32 now) {
  const char* letters = sms_letters_for_key(key_code);
  if(letters == NULL || letters[0] == 0) {
    sms_reset(sms);
    return false;
  }

  if(!valid_buffer(source, len, cursor, capacity)) {
    sms_reset(sms);
    return false;
  }

  if(sms.active && sms.key_code == key_code && cursor > 0 && strchr(letters, source[cursor - 1]) != NULL) {
    const usize count = bounded_length(letters, 8);
    sms.index = (u8) ((sms.index + 1) % count);
    source[cursor - 1] = letters[sms.index];
    sms.deadline_ms = now + SMS_INPUT_TIMEOUT_MS;
    return true;
  }

  char text[2] = {letters[0], 0};
  if(!insert_text(source, len, cursor, capacity, text)) {
    sms_reset(sms);
    return false;
  }
  sms.active = true;
  sms.key_code = key_code;
  sms.index = 0;
  sms.deadline_ms = now + SMS_INPUT_TIMEOUT_MS;
  return true;
}

inline KeyResult handle_key(Buffer& editor, const KeyMap& keys, const Hooks& hooks, const Options& options, i32 key_code, u32 now) {
  sanitize(editor);
  const bool shifted_key = editor.shift != Shift::NONE;
  if(options.sms_enabled && !shifted_key && editor.sms.active) {
    if(sms_key_is_letters(key_code)) {
      return sms_tap(editor.source, editor.len, editor.cursor, editor.capacity, editor.sms, key_code, now)
        ? KeyResult::DIRTY : KeyResult::NONE;
    }
    if(sms_key_is_space(key_code)) {
      sms_reset(editor.sms);
      return insert_text(editor.source, editor.len, editor.cursor, editor.capacity, " ")
        ? KeyResult::DIRTY : KeyResult::NONE;
    }
    const int sms_digit = digit_from_key(key_code);
    if(sms_digit == 0) {
      sms_reset(editor.sms);
      return KeyResult::DIRTY;
    }
    if(key_code == keys.pp) {
      sms_reset(editor.sms);
      return insert_text(editor.source, editor.len, editor.cursor, editor.capacity, " ")
        ? KeyResult::DIRTY : KeyResult::NONE;
    }
    sms_reset(editor.sms);
  }

  if(!shifted_key && (key_code == keys.k || key_code == keys.alpha)) {
    editor.shift = (key_code == keys.k) ? Shift::K : Shift::ALPHA;
    return KeyResult::DIRTY;
  }

  if(options.sms_enabled && editor.shift == Shift::K && sms_key_is_letters(key_code)) {
    const bool changed = sms_tap(editor.source, editor.len, editor.cursor, editor.capacity, editor.sms, key_code, now);
    editor.shift = Shift::NONE;
    return changed ? KeyResult::DIRTY : KeyResult::NONE;
  }
  if(options.sms_enabled && editor.shift == Shift::K && sms_key_is_space(key_code)) {
    sms_reset(editor.sms);
    const bool changed = insert_text(editor.source, editor.len, editor.cursor, editor.capacity, " ");
    editor.shift = Shift::NONE;
    return changed ? KeyResult::DIRTY : KeyResult::NONE;
  }

  if(options.alpha_cx_clear_line && editor.shift == Shift::ALPHA &&
      key_code == keyboard_layout::ACTIVE.cx) {
    clear_current_line(editor.source, editor.len, editor.cursor, editor.capacity);
    sms_reset(editor.sms);
    editor.shift = Shift::NONE;
    return KeyResult::DIRTY;
  }

  if(editor.shift == Shift::ALPHA && hooks.apply_alpha_macro != NULL &&
      hooks.apply_alpha_macro(editor.source, editor.len, editor.cursor, editor.capacity, key_code, hooks.context)) {
    sanitize(editor);
    editor.shift = Shift::NONE;
    return KeyResult::DIRTY;
  }

  if(options.alpha_digit_symbols && editor.shift == Shift::ALPHA && digit_from_key(key_code) >= 0) {
    const bool changed = insert_text(editor.source, editor.len, editor.cursor, editor.capacity, symbol_for_digit_key(key_code));
    editor.shift = Shift::NONE;
    return changed ? KeyResult::DIRTY : KeyResult::NONE;
  }

  if(!shifted_key && (key_code == keys.esc || key_code == keys.esc_press)) {
    return KeyResult::SAVE;
  }

  if(!shifted_key && (key_code == keys.left || key_code == keys.left_press)) {
    if(hooks.move_cursor_horizontal != NULL) {
      hooks.move_cursor_horizontal(editor.source, editor.len, editor.cursor, -1, hooks.context);
    } else {
      move_cursor_left(editor.source, editor.cursor);
    }
  } else if(!shifted_key && (key_code == keys.right || key_code == keys.right_press)) {
    if(hooks.move_cursor_horizontal != NULL) {
      hooks.move_cursor_horizontal(editor.source, editor.len, editor.cursor, 1, hooks.context);
    } else {
      move_cursor_right(editor.source, editor.len, editor.cursor);
    }
  } else if(!shifted_key && key_code == keys.shg_left_press) {
    move_cursor_line(editor.source, editor.len, editor.cursor, -1);
  } else if(!shifted_key && key_code == keys.shg_right_press) {
    move_cursor_line(editor.source, editor.len, editor.cursor, 1);
  } else if(!shifted_key && key_code == options.backspace_key) {
    if(hooks.backspace != NULL) {
      hooks.backspace(editor.source, editor.len, editor.cursor, editor.capacity, hooks.context);
    } else {
      backspace(editor.source, editor.len, editor.cursor);
    }
  } else if(!shifted_key && (key_code == keys.ok || key_code == keys.ok_press)) {
    insert_text(editor.source, editor.len, editor.cursor, editor.capacity, options.ok_insert_text);
  } else {
    const char* text = NULL;
    if(hooks.insert_text_for_key != NULL) {
      text = hooks.insert_text_for_key(editor.shift, key_code, editor.source, editor.cursor, hooks.context);
    }
    insert_text(editor.source, editor.len, editor.cursor, editor.capacity, text);
  }
  editor.shift = Shift::NONE;
  sanitize(editor);
  return KeyResult::DIRTY;
}

inline KeyResult handle_key(Buffer& editor, const KeyMap& keys, const Hooks& hooks, i32 key_code, u32 now) {
  return handle_key(editor, keys, hooks, default_options(), key_code, now);
}

} // пространство имён text_editor

#endif
