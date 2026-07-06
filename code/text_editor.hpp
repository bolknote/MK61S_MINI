#ifndef TEXT_EDITOR_HPP
#define TEXT_EDITOR_HPP

#include "rust_types.h"

#ifndef TEXT_EDITOR_HOST_TEST
#include "lcd_gui.hpp"
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
  void* context;
};

enum class KeyResult : u8 {
  NONE,
  DIRTY,
  SAVE
};

inline void sms_reset(SmsState& sms) {
  sms.active = false;
  sms.key_code = -1;
  sms.index = 0;
  sms.deadline_ms = 0;
}

inline void init(Buffer& editor, char* source, u16 capacity) {
  editor.source = source;
  editor.capacity = capacity;
  editor.len = (source == NULL) ? 0 : (u16) strlen(source);
  if(editor.len >= capacity) editor.len = (capacity == 0) ? 0 : (u16) (capacity - 1);
  editor.cursor = 0;
  editor.view_top = 0;
  editor.shift = Shift::NONE;
  sms_reset(editor.sms);
}

inline int digit_from_key(i32 key_code) {
  switch(key_code) {
    case 20: return 0;
    case 21: return 1;
    case 16: return 2;
    case 11: return 3;
    case 22: return 4;
    case 17: return 5;
    case 12: return 6;
    case 23: return 7;
    case 18: return 8;
    case 13: return 9;
    default: break;
  }
  return -1;
}

inline const char* sms_letters_for_key(i32 key_code) {
  switch(digit_from_key(key_code)) {
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

inline bool sms_key_is_letters(i32 key_code) {
  return sms_letters_for_key(key_code) != NULL;
}

inline bool sms_key_is_space(i32 key_code) {
  return digit_from_key(key_code) == 7;
}

inline const char* symbol_for_digit_key(i32 key_code) {
  switch(digit_from_key(key_code)) {
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

inline u16 line_start_for_cursor(const char* source, u16 cursor) {
  u16 start = cursor;
  while(start > 0 && source[start - 1] != '\n' && source[start - 1] != '\r') start--;
  return start;
}

inline u16 line_end_for_start(const char* source, u16 start, u16 len) {
  u16 end = start;
  while(end < len && source[end] != '\n' && source[end] != '\r') end++;
  return end;
}

inline u16 next_line_start(const char* source, u16 start, u16 len) {
  u16 pos = start;
  while(pos < len && source[pos] != '\n' && source[pos] != '\r') pos++;
  while(pos < len && (source[pos] == '\n' || source[pos] == '\r')) pos++;
  return pos;
}

inline u16 previous_line_start(const char* source, u16 start) {
  if(start == 0) return 0;
  u16 pos = start;
  while(pos > 0 && (source[pos - 1] == '\n' || source[pos - 1] == '\r')) pos--;
  while(pos > 0 && source[pos - 1] != '\n' && source[pos - 1] != '\r') pos--;
  return pos;
}

inline bool move_cursor_left(const char* source, u16& cursor) {
  const u16 line_start = line_start_for_cursor(source, cursor);
  if(cursor <= line_start) return false;
  cursor--;
  return true;
}

inline bool move_cursor_right(const char* source, u16 len, u16& cursor) {
  const u16 line_start = line_start_for_cursor(source, cursor);
  const u16 line_end = line_end_for_start(source, line_start, len);
  if(cursor >= line_end) return false;
  cursor++;
  return true;
}

inline bool move_cursor_line(const char* source, u16 len, u16& cursor, int delta) {
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
  if(source == NULL || capacity == 0 || text == NULL || text[0] == 0) return false;
  const usize text_len = strlen(text);
  if((usize) len + text_len >= capacity) return false;
  memmove(&source[cursor + text_len], &source[cursor], len - cursor + 1);
  memcpy(&source[cursor], text, text_len);
  cursor = (u16) (cursor + text_len);
  len = (u16) (len + text_len);
  return true;
}

inline bool backspace(char* source, u16& len, u16& cursor) {
  if(source == NULL || cursor == 0) return false;
  memmove(&source[cursor - 1], &source[cursor], len - cursor + 1);
  cursor--;
  len--;
  return true;
}

inline bool replace_range(char* source, u16& len, u16& cursor, u16 capacity, u16 start, u16 end, const char* replacement) {
  if(source == NULL || replacement == NULL || start > end || end > len) return false;
  const usize replacement_len = strlen(replacement);
  const usize old_len = (usize) (end - start);
  if((usize) len - old_len + replacement_len >= capacity) return false;
  memmove(&source[start + replacement_len], &source[end], len - end + 1);
  memcpy(&source[start], replacement, replacement_len);
  len = (u16) ((usize) len - old_len + replacement_len);
  cursor = (u16) (start + replacement_len);
  return true;
}

inline bool sms_tap(char* source, u16& len, u16& cursor, u16 capacity, SmsState& sms, i32 key_code, u32 now) {
  const char* letters = sms_letters_for_key(key_code);
  if(letters == NULL || letters[0] == 0) {
    sms_reset(sms);
    return false;
  }

  if(sms.active && sms.key_code == key_code && cursor > 0) {
    const usize count = strlen(letters);
    sms.index = (u8) ((sms.index + 1) % count);
    source[cursor - 1] = letters[sms.index];
    sms.deadline_ms = now + SMS_INPUT_TIMEOUT_MS;
    return true;
  }

  sms.active = true;
  sms.key_code = key_code;
  sms.index = 0;
  sms.deadline_ms = now + SMS_INPUT_TIMEOUT_MS;
  char text[2] = {letters[0], 0};
  return insert_text(source, len, cursor, capacity, text);
}

inline KeyResult handle_key(Buffer& editor, const KeyMap& keys, const Hooks& hooks, i32 key_code, u32 now) {
  const bool shifted_key = editor.shift != Shift::NONE;
  if(!shifted_key && editor.sms.active) {
    if(sms_key_is_letters(key_code)) {
      sms_tap(editor.source, editor.len, editor.cursor, editor.capacity, editor.sms, key_code, now);
      return KeyResult::DIRTY;
    }
    if(sms_key_is_space(key_code)) {
      sms_reset(editor.sms);
      insert_text(editor.source, editor.len, editor.cursor, editor.capacity, " ");
      return KeyResult::DIRTY;
    }
    const int sms_digit = digit_from_key(key_code);
    if(sms_digit == 0) {
      sms_reset(editor.sms);
      return KeyResult::DIRTY;
    }
    if(key_code == keys.pp) {
      sms_reset(editor.sms);
      insert_text(editor.source, editor.len, editor.cursor, editor.capacity, " ");
      return KeyResult::DIRTY;
    }
    sms_reset(editor.sms);
  }

  if(!shifted_key && (key_code == keys.k || key_code == keys.alpha)) {
    editor.shift = (key_code == keys.k) ? Shift::K : Shift::ALPHA;
    return KeyResult::DIRTY;
  }

  if(editor.shift == Shift::K && sms_key_is_letters(key_code)) {
    sms_tap(editor.source, editor.len, editor.cursor, editor.capacity, editor.sms, key_code, now);
    editor.shift = Shift::NONE;
    return KeyResult::DIRTY;
  }
  if(editor.shift == Shift::K && sms_key_is_space(key_code)) {
    sms_reset(editor.sms);
    insert_text(editor.source, editor.len, editor.cursor, editor.capacity, " ");
    editor.shift = Shift::NONE;
    return KeyResult::DIRTY;
  }

  if(editor.shift == Shift::ALPHA && digit_from_key(key_code) >= 0) {
    insert_text(editor.source, editor.len, editor.cursor, editor.capacity, symbol_for_digit_key(key_code));
    editor.shift = Shift::NONE;
    return KeyResult::DIRTY;
  }

  if(editor.shift == Shift::ALPHA && (key_code == keys.left || key_code == keys.left_press)) {
    backspace(editor.source, editor.len, editor.cursor);
    editor.shift = Shift::NONE;
    return KeyResult::DIRTY;
  }

  if(editor.shift == Shift::ALPHA && hooks.apply_alpha_macro != NULL &&
      hooks.apply_alpha_macro(editor.source, editor.len, editor.cursor, editor.capacity, key_code, hooks.context)) {
    editor.shift = Shift::NONE;
    return KeyResult::DIRTY;
  }

  if(!shifted_key && (key_code == keys.esc || key_code == keys.esc_press)) {
    return KeyResult::SAVE;
  }

  if(!shifted_key && (key_code == keys.left || key_code == keys.left_press)) {
    move_cursor_left(editor.source, editor.cursor);
  } else if(!shifted_key && (key_code == keys.right || key_code == keys.right_press)) {
    move_cursor_right(editor.source, editor.len, editor.cursor);
  } else if(!shifted_key && key_code == keys.shg_left_press) {
    move_cursor_line(editor.source, editor.len, editor.cursor, -1);
  } else if(!shifted_key && key_code == keys.shg_right_press) {
    move_cursor_line(editor.source, editor.len, editor.cursor, 1);
  } else if(!shifted_key && key_code == 0) {
    if(editor.source != NULL && editor.capacity > 0) editor.source[0] = 0;
    editor.len = 0;
    editor.cursor = 0;
    editor.view_top = 0;
    sms_reset(editor.sms);
  } else if(!shifted_key && (key_code == keys.ok || key_code == keys.ok_press)) {
    insert_text(editor.source, editor.len, editor.cursor, editor.capacity, "\n");
  } else {
    const char* text = NULL;
    if(hooks.insert_text_for_key != NULL) {
      text = hooks.insert_text_for_key(editor.shift, key_code, editor.source, editor.cursor, hooks.context);
    }
    insert_text(editor.source, editor.len, editor.cursor, editor.capacity, text);
  }
  editor.shift = Shift::NONE;
  return KeyResult::DIRTY;
}

} // namespace text_editor

#endif
