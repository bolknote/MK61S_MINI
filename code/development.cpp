#include "development.hpp"

#include "Arduino.h"
#include "basic.hpp"
#include "config.h"
#include "cross_hal.h"
#include "focal.hpp"
#include "tinybasic.hpp"
#include "keyboard.h"
#include "lcd_gui.hpp"
#include "lcd_ru.hpp"
#include "menu.hpp"
#include "program_store.hpp"
#include "shared_scratch.hpp"
#include "text_editor.hpp"
#include "tools.hpp"

#include <stdio.h>
#include <string.h>

extern MK61Display lcd;
extern void idle_main_process(void);

namespace {

static constexpr u32 EXPLORER_LONG_OK_MS = 1200;
static constexpr i32 EXPLORER_KEY_UP = -2;
static constexpr i32 EXPLORER_KEY_DOWN = -3;
static constexpr i32 EXPLORER_KEY_OK = -4;
static constexpr i32 EXPLORER_KEY_LONG_OK = -5;
static constexpr i32 EXPLORER_KEY_ESC = -6;

static_assert(shared_scratch::SIZE >= program_store::MAX_MK61_TEXT_SIZE, "shared scratch too small for explorer view");

enum class ItemMenuAction : u8 {
  RUN,
  VIEW,
  EDIT,
  RENAME,
  DELETE
};

struct ExplorerSearch {
  char text[program_store::NAME_SIZE];
  u16 len;
  text_editor::SmsState sms;
  text_editor::Shift shift;
};

static char type_char(program_store::ProgramType type) {
  switch(type) {
    case program_store::ProgramType::MK61:  return 'M';
    case program_store::ProgramType::BASIC: return 'B';
    case program_store::ProgramType::FOCAL: return 'F';
    case program_store::ProgramType::TINYBASIC: return 'T';
  }
  return '?';
}

static void print_line(u8 row, const char* text) {
  lcd.setCursor(0, row);
  u8 used = 0;
  while(text != NULL && text[used] != 0 && used < lcd_display::COLS) {
    lcd.write((u8) text[used++]);
  }
  while(used++ < lcd_display::COLS) lcd.write((u8) ' ');
}

static void print_localized_line(u8 row, const char* en, const char* ru) {
  if(library_mk61::language_is_ru()) {
    library_mk61::print_localized_at(0, row, ru, en, lcd_display::COLS);
  } else {
    print_line(row, en);
  }
}

static i32 scan_direct_key(void) {
  const i32 scan_code = kbd::scan_and_debounced();
  if(scan_code < 0) return -1;
  kbd::exclude_before(scan_code);
  return scan_code;
}

static void wait_ok_release(void) {
  while(true) {
    idle_main_process();
    const i32 scan_code = scan_direct_key();
    if(scan_code >= 0) {
      const bool released = (scan_code & (i32) key_state::RELEASED) != 0;
      const i32 code = scan_code & ~(i32) key_state::RELEASED;
      if(released && code == (i32) KEY_OK) {
        kbd::clear_hold_key();
        return;
      }
    }
    delay(10);
  }
}

static i32 wait_explorer_key(bool allow_long_ok) {
  bool ok_down = false;
  u32 long_ok_at = 0;
  kbd::debounce_init();

  while(true) {
    idle_main_process();
    if(allow_long_ok && ok_down && (i32) (millis() - long_ok_at) >= 0) {
      kbd::clear_hold_key();
      return EXPLORER_KEY_LONG_OK;
    }

    const i32 scan_code = scan_direct_key();
    if(scan_code < 0) {
      delay(10);
      continue;
    }

    const bool released = (scan_code & (i32) key_state::RELEASED) != 0;
    const i32 code = scan_code & ~(i32) key_state::RELEASED;
    if(released) {
      if(ok_down && code == (i32) KEY_OK) {
        kbd::clear_hold_key();
        return EXPLORER_KEY_OK;
      }
      continue;
    }

    if(code == (i32) KEY_OK) {
      ok_down = true;
      long_ok_at = millis() + EXPLORER_LONG_OK_MS;
      continue;
    }
    if(code == (i32) KEY_ESC) return EXPLORER_KEY_ESC;
    if(code == (i32) KEY_RIGHT || code == (i32) KEY_SHG_RIGHT_PRESS) return EXPLORER_KEY_DOWN;
    if(code == (i32) KEY_LEFT || code == (i32) KEY_SHG_LEFT_PRESS) return EXPLORER_KEY_UP;
    return code;
  }
}

static int total_file_count(void) {
  return program_store::count(program_store::ProgramType::MK61) +
         program_store::count(program_store::ProgramType::BASIC) +
         program_store::count(program_store::ProgramType::FOCAL)
#if MK61_ENABLE_TINYBASIC
         + program_store::count(program_store::ProgramType::TINYBASIC)
#endif
         ;
}

static bool explorer_entry(int index, program_store::Entry& out) {
  if(index < 0) return false;
  const program_store::ProgramType types[] = {
    program_store::ProgramType::MK61,
    program_store::ProgramType::BASIC,
    program_store::ProgramType::FOCAL
#if MK61_ENABLE_TINYBASIC
    ,
    program_store::ProgramType::TINYBASIC
#endif
  };

  for(usize i = 0; i < sizeof(types) / sizeof(types[0]); i++) {
    const int count = program_store::count(types[i]);
    if(index < count) return program_store::entry(types[i], index, out);
    index -= count;
  }
  return false;
}

static char ascii_upper(char ch) {
  return (ch >= 'a' && ch <= 'z') ? (char) (ch - 'a' + 'A') : ch;
}

static bool search_active(const char* search_text) {
  return search_text != NULL && search_text[0] != 0;
}

static bool text_contains_case_insensitive(const char* text, const char* needle) {
  if(!search_active(needle)) return true;
  if(text == NULL) return false;

  for(u8 start = 0; text[start] != 0; start++) {
    u8 pos = 0;
    while(needle[pos] != 0 && text[start + pos] != 0 &&
          ascii_upper(text[start + pos]) == ascii_upper(needle[pos])) {
      pos++;
    }
    if(needle[pos] == 0) return true;
  }
  return false;
}

static bool entry_matches_search(int index, const char* search_text) {
  if(!search_active(search_text)) return true;
  program_store::Entry entry;
  if(!explorer_entry(index, entry)) return false;
  return text_contains_case_insensitive(entry.name, search_text);
}

static int matching_file_count(const char* search_text) {
  const int count = total_file_count();
  if(!search_active(search_text)) return count;

  int matches = 0;
  for(int index = 0; index < count; index++) {
    if(entry_matches_search(index, search_text)) matches++;
  }
  return matches;
}

static int matching_index_at(int match_index, const char* search_text) {
  const int count = total_file_count();
  if(!search_active(search_text)) return (match_index >= 0 && match_index < count) ? match_index : -1;

  int current = 0;
  for(int index = 0; index < count; index++) {
    if(!entry_matches_search(index, search_text)) continue;
    if(current == match_index) return index;
    current++;
  }
  return -1;
}

static int matching_position(int active, const char* search_text) {
  if(!search_active(search_text)) return active;
  const int count = total_file_count();
  int position = 0;
  for(int index = 0; index < count; index++) {
    if(!entry_matches_search(index, search_text)) continue;
    if(index == active) return position;
    position++;
  }
  return -1;
}

static int first_matching_index(const char* search_text) {
  return matching_index_at(0, search_text);
}

static int next_matching_index(int active, const char* search_text) {
  const int count = total_file_count();
  if(!search_active(search_text)) return (active + 1 < count) ? active + 1 : active;
  for(int index = active + 1; index < count; index++) {
    if(entry_matches_search(index, search_text)) return index;
  }
  return active;
}

static int previous_matching_index(int active, const char* search_text) {
  if(!search_active(search_text)) return (active > 0) ? active - 1 : active;
  for(int index = active - 1; index >= 0; index--) {
    if(entry_matches_search(index, search_text)) return index;
  }
  return active;
}

static void draw_search_header(const char* search_text) {
  char line[18];
  snprintf(line, sizeof(line), "?%s", search_text);
  print_line(0, line);
}

static void draw_search_cursor(const char* search_text) {
  const usize len = strlen(search_text);
  const u8 cursor_col = (len + 1 < lcd_display::COLS) ? (u8) (len + 1) : (u8) (lcd_display::COLS - 1);
  lcd.setCursor(cursor_col, 0);
  lcd.cursorOn();
}

static void draw_explorer(int active, const char* search_text = NULL) {
  MK61DisplayUpdate update(lcd);
  lcd.clear();

  const int count = total_file_count();
  if(count <= 0) {
    print_localized_line(0, "FS is empty", "ФС пуста");
    print_localized_line(1, "ESC", "ESC");
    return;
  }

  const bool filtered = search_active(search_text);
  const int display_rows = lcd.rows();
  const int first_row = filtered ? 1 : 0;
  const int list_rows = display_rows - first_row;
  if(filtered) draw_search_header(search_text);
  if(list_rows <= 0) {
    if(filtered) draw_search_cursor(search_text);
    return;
  }

  const int visible_count = filtered ? matching_file_count(search_text) : count;
  if(visible_count <= 0) {
    print_localized_line((u8) first_row, "No match", "Нет совпад.");
    for(int row = first_row + 1; row < display_rows; row++) print_line((u8) row, "");
    if(filtered) draw_search_cursor(search_text);
    return;
  }

  int active_pos = filtered ? matching_position(active, search_text) : active;
  if(active_pos < 0) active_pos = 0;

  const int visible = (visible_count < list_rows) ? visible_count : list_rows;
  const int max_top = visible_count - visible;
  int top = active_pos - visible + 1;
  if(top < 0) top = 0;
  if(top > max_top) top = max_top;

  for(int row = 0; row < visible; row++) {
    const int index = filtered ? matching_index_at(top + row, search_text) : top + row;
    program_store::Entry entry;
    char line[24];
    if(explorer_entry(index, entry)) {
      snprintf(line, sizeof(line), "%c %-11s %u", type_char(entry.type), entry.name, (u32) entry.data_len);
    } else {
      strcpy(line, "?");
    }

    if(library_mk61::language_is_ru()) {
      lcd_ru::print_menu_line((u8) (first_row + row), active == index ? '>' : ' ', line);
    } else {
      char out[18];
      snprintf(out, sizeof(out), "%c%s", active == index ? '>' : ' ', line);
      print_line((u8) (first_row + row), out);
    }
  }

  for(int row = first_row + visible; row < display_rows; row++) print_line((u8) row, "");
  if(filtered) draw_search_cursor(search_text);
}

static bool read_entry_data(const program_store::Entry& entry, u8* data, usize capacity, u16& out_len) {
  memset(data, 0, capacity);
  out_len = 0;
  return program_store::read(entry.type, entry.name, data, capacity, &out_len);
}

static char hex_digit(u8 value) {
  value &= 0x0F;
  return (value < 10) ? (char) ('0' + value) : (char) ('A' + value - 10);
}

static void draw_hex_payload_row(u8 row, const u8* data, u16 len, u16 offset) {
  char line[17];
  u8 pos = 0;
  for(u8 i = 0; i < 8 && offset + i < len && pos + 1 < sizeof(line); i++) {
    const u8 value = data[offset + i];
    line[pos++] = hex_digit((u8) (value >> 4));
    line[pos++] = hex_digit(value);
  }
  line[pos] = 0;
  print_line(row, line);
}

static bool is_line_break(u8 value) {
  return value == '\n' || value == '\r';
}

static u16 consume_line_break(const u8* data, u16 len, u16 offset) {
  if(offset >= len) return offset;
  if(data[offset] == '\r') {
    offset++;
    if(offset < len && data[offset] == '\n') offset++;
    return offset;
  }
  if(data[offset] == '\n') return (u16) (offset + 1);
  return offset;
}

static u16 next_visual_line_offset(const u8* data, u16 len, u16 offset) {
  if(offset >= len) return len;

  u8 used = 0;
  while(offset < len) {
    if(is_line_break(data[offset])) return consume_line_break(data, len, offset);

    offset++;
    used++;
    if(used >= lcd_display::COLS) {
      if(offset < len && is_line_break(data[offset])) offset = consume_line_break(data, len, offset);
      return offset;
    }
  }
  return offset;
}

static u16 visual_line_count(const u8* data, u16 len) {
  if(len == 0) return 1;

  u16 count = 0;
  u16 offset = 0;
  while(offset < len) {
    count++;
    const u16 next = next_visual_line_offset(data, len, offset);
    if(next <= offset) break;
    offset = next;
  }
  return count == 0 ? 1 : count;
}

static u16 visual_line_offset(const u8* data, u16 len, u16 line_index) {
  u16 offset = 0;
  while(line_index > 0 && offset < len) {
    const u16 next = next_visual_line_offset(data, len, offset);
    if(next <= offset) break;
    offset = next;
    line_index--;
  }
  return offset;
}

static void draw_text_payload_line(u8 row, const u8* data, u16 len, u16 line_index) {
  u16 offset = visual_line_offset(data, len, line_index);
  char line[17];
  u8 pos = 0;
  while(pos < lcd_display::COLS && offset < len && !is_line_break(data[offset])) {
    line[pos++] = (char) data[offset++];
  }
  line[pos] = 0;
  print_line(row, line);
}

static void draw_file_view(const program_store::Entry& entry, const u8* data, u16 len, u16 top_line) {
  MK61DisplayUpdate update(lcd);
  lcd.clear();

  char header[24];
  snprintf(header, sizeof(header), "%c %s %u", type_char(entry.type), entry.name, (u32) len);
  print_line(0, header);

  const u8 display_rows = lcd.rows();
  const u8 payload_rows = display_rows > 1 ? (u8) (display_rows - 1) : 1;
  const u16 total_lines = visual_line_count(data, len);
  for(u8 row = 0; row < payload_rows; row++) {
    const u16 line_index = (u16) (top_line + row);
    if(line_index < total_lines) draw_text_payload_line((u8) (row + 1), data, len, line_index);
    else print_line((u8) (row + 1), "");
  }
}

static void show_message(const char* en0, const char* ru0, const char* en1 = "", const char* ru1 = "") {
  MK61DisplayUpdate update(lcd);
  lcd.clear();
  print_localized_line(0, en0, ru0);
  print_localized_line(1, en1, ru1);
}

static void view_entry(const program_store::Entry& entry) {
  shared_scratch::Lease scratch(shared_scratch::Owner::EXPLORER_VIEW, program_store::MAX_MK61_TEXT_SIZE);
  if(!scratch.ok()) {
    show_message("Busy", "Занято", entry.name, entry.name);
    kbd::get_key_wait();
    return;
  }

  u8* data = scratch.data();
  u16 len = 0;
  if(!read_entry_data(entry, data, scratch.size(), len)) {
    show_message("Read error", "Ошибка чтения", entry.name, entry.name);
    kbd::get_key_wait();
    return;
  }

  const u8 display_rows = lcd.rows();
  const u8 rows = display_rows > 1 ? (u8) (display_rows - 1) : 1;
  const u16 page = rows;
  u16 top_line = 0;
  while(true) {
    const u16 total_lines = visual_line_count(data, len);
    const u16 max_top = (total_lines > rows) ? (u16) (total_lines - rows) : 0;
    if(top_line > max_top) top_line = max_top;

    draw_file_view(entry, data, len, top_line);
    const i32 key = wait_explorer_key(false);
    if(key == EXPLORER_KEY_ESC || key == EXPLORER_KEY_OK) return;
    if(key == EXPLORER_KEY_DOWN && top_line < max_top) {
      top_line = (u16) (top_line + page);
      if(top_line > max_top) top_line = max_top;
    }
    if(key == EXPLORER_KEY_UP) top_line = (top_line > page) ? (u16) (top_line - page) : 0;
  }
}

static bool confirm_delete(const program_store::Entry& entry) {
  show_message("Delete?", "Удалить?", entry.name, entry.name);
  while(true) {
    const i32 key = wait_explorer_key(false);
    if(key == EXPLORER_KEY_OK) return true;
    if(key == EXPLORER_KEY_ESC) return false;
  }
}

static void delete_entry(const program_store::Entry& entry) {
  if(!confirm_delete(entry)) return;

  const bool ok = program_store::remove(entry.type, entry.name);
  show_message(ok ? "Deleted" : "Delete error", ok ? "Удалено" : "Ошибка", entry.name, entry.name);
  delay(700);
}

static void draw_rename_editor(const char* name) {
  MK61DisplayUpdate update(lcd);
  lcd.clear();
  print_localized_line(0, "Rename", "Имя файла");

  char line[18];
  snprintf(line, sizeof(line), ">%s", name);
  print_line(1, line);

  const usize len = strlen(name);
  const u8 cursor_col = (len + 1 < lcd_display::COLS) ? (u8) (len + 1) : (u8) (lcd_display::COLS - 1);
  lcd.setCursor(cursor_col, 1);
  lcd.cursorOn();
}

static bool name_insert_char(char* name, u16& len, u16& cursor, char ch) {
  if(ch == 0) return false;
  if(ch == ' ' && len == 0) return false;
  char text[2] = {ch, 0};
  return text_editor::insert_text(name, len, cursor, program_store::NAME_SIZE, text);
}

static bool input_entry_name(char* name) {
  u16 len = (u16) strlen(name);
  if(len >= program_store::NAME_SIZE) len = (u16) (program_store::NAME_SIZE - 1);
  name[len] = 0;
  u16 cursor = len;
  text_editor::SmsState sms = {};
  text_editor::Shift shift = text_editor::Shift::NONE;
  text_editor::sms_reset(sms);

  while(true) {
    const u32 draw_now = millis();
    if(sms.active && draw_now >= sms.deadline_ms) text_editor::sms_reset(sms);
    draw_rename_editor(name);

    const i32 key = kbd::get_key_wait();
    const u32 key_now = millis();
    if(sms.active && key_now >= sms.deadline_ms) text_editor::sms_reset(sms);
    cursor = len;
    const bool shifted_key = shift != text_editor::Shift::NONE;

    if(!shifted_key && (key == KEY_K || key == KEY_ALPHA)) {
      shift = (key == KEY_K) ? text_editor::Shift::K : text_editor::Shift::ALPHA;
      text_editor::sms_reset(sms);
      continue;
    }
    if(!shifted_key && (key == KEY_OK || key == KEY_OK_PRESS)) return len > 0;
    if(!shifted_key && (key == KEY_ESC || key == KEY_ESC_PRESS)) return false;
    if(!shifted_key && key == KEY_DEGREE) {
      text_editor::sms_reset(sms);
      text_editor::backspace(name, len, cursor);
      continue;
    }
    if(!shifted_key && key == 0) {
      text_editor::sms_reset(sms);
      len = 0;
      cursor = 0;
      name[0] = 0;
      continue;
    }

    if(shift == text_editor::Shift::ALPHA && (key == KEY_LEFT || key == KEY_LEFT_PRESS)) {
      text_editor::sms_reset(sms);
      text_editor::backspace(name, len, cursor);
      shift = text_editor::Shift::NONE;
      continue;
    }

    const int digit = text_editor::digit_from_key(key);
    if(shift == text_editor::Shift::ALPHA && digit >= 0) {
      const char* symbol = text_editor::symbol_for_digit_key(key);
      if(symbol != NULL && symbol[0] != 0) name_insert_char(name, len, cursor, symbol[0]);
      shift = text_editor::Shift::NONE;
      text_editor::sms_reset(sms);
      continue;
    }

    if(text_editor::sms_key_is_letters(key)) {
      text_editor::sms_tap(name, len, cursor, program_store::NAME_SIZE, sms, key, key_now);
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(text_editor::sms_key_is_space(key)) {
      text_editor::sms_reset(sms);
      name_insert_char(name, len, cursor, ' ');
      shift = text_editor::Shift::NONE;
      continue;
    }

    if(digit == 0 || key == KEY_PP) {
      text_editor::sms_reset(sms);
      name_insert_char(name, len, cursor, '0');
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(digit == 1) {
      text_editor::sms_reset(sms);
      name_insert_char(name, len, cursor, '1');
      shift = text_editor::Shift::NONE;
      continue;
    }

    text_editor::sms_reset(sms);
    shift = text_editor::Shift::NONE;
  }
}

static bool rename_entry(const program_store::Entry& entry) {
  char name[program_store::NAME_SIZE];
  strncpy(name, entry.name, sizeof(name) - 1);
  name[sizeof(name) - 1] = 0;

  if(!input_entry_name(name)) return false;
  if(strncmp(name, entry.name, program_store::NAME_SIZE) == 0) return true;

  if(program_store::exists(entry.type, name)) {
    show_message("Name exists", "Уже есть", name, name);
    delay(900);
    return false;
  }

  const bool ok = program_store::rename(entry.type, entry.name, name);
  show_message(ok ? "Renamed" : "Rename error", ok ? "Переимен." : "Ошибка", name, name);
  delay(700);
  return ok;
}

static void explorer_search_reset(ExplorerSearch& search) {
  search.text[0] = 0;
  search.len = 0;
  search.shift = text_editor::Shift::NONE;
  text_editor::sms_reset(search.sms);
}

static void explorer_search_expire_sms(ExplorerSearch& search, u32 now) {
  if(search.sms.active && now >= search.sms.deadline_ms) text_editor::sms_reset(search.sms);
}

static bool explorer_search_insert_char(ExplorerSearch& search, char ch) {
  u16 cursor = search.len;
  if(!name_insert_char(search.text, search.len, cursor, ch)) return false;
  return true;
}

static void explorer_search_backspace(ExplorerSearch& search) {
  u16 cursor = search.len;
  if(search.len > 0) text_editor::backspace(search.text, search.len, cursor);
}

static bool explorer_search_handle_key(ExplorerSearch& search, i32 key) {
  const u32 now = millis();
  explorer_search_expire_sms(search, now);

  const bool shifted_key = search.shift != text_editor::Shift::NONE;
  if(!shifted_key && (key == KEY_K || key == KEY_ALPHA)) {
    search.shift = (key == KEY_K) ? text_editor::Shift::K : text_editor::Shift::ALPHA;
    text_editor::sms_reset(search.sms);
    return true;
  }

  u16 cursor = search.len;
  if(search.shift == text_editor::Shift::ALPHA &&
      (key == EXPLORER_KEY_UP || key == (i32) KEY_LEFT || key == (i32) KEY_LEFT_PRESS)) {
    text_editor::sms_reset(search.sms);
    explorer_search_backspace(search);
    search.shift = text_editor::Shift::NONE;
    return true;
  }

  const int digit = text_editor::digit_from_key(key);
  if(search.shift == text_editor::Shift::ALPHA && digit >= 0) {
    const char* symbol = text_editor::symbol_for_digit_key(key);
    if(symbol != NULL && symbol[0] != 0) explorer_search_insert_char(search, symbol[0]);
    search.shift = text_editor::Shift::NONE;
    text_editor::sms_reset(search.sms);
    return true;
  }

  if(text_editor::sms_key_is_letters(key)) {
    text_editor::sms_tap(search.text, search.len, cursor, program_store::NAME_SIZE, search.sms, key, now);
    search.shift = text_editor::Shift::NONE;
    return true;
  }
  if(text_editor::sms_key_is_space(key)) {
    text_editor::sms_reset(search.sms);
    explorer_search_insert_char(search, ' ');
    search.shift = text_editor::Shift::NONE;
    return true;
  }
  if(!shifted_key && key == KEY_DEGREE) {
    text_editor::sms_reset(search.sms);
    const bool had_text = search.len > 0;
    explorer_search_backspace(search);
    return had_text;
  }
  if(!shifted_key && key == 0 && search.len > 0) {
    explorer_search_reset(search);
    return true;
  }

  if(digit == 0 || key == KEY_PP) {
    text_editor::sms_reset(search.sms);
    explorer_search_insert_char(search, '0');
    search.shift = text_editor::Shift::NONE;
    return true;
  }
  if(digit == 1) {
    text_editor::sms_reset(search.sms);
    explorer_search_insert_char(search, '1');
    search.shift = text_editor::Shift::NONE;
    return true;
  }

  search.shift = text_editor::Shift::NONE;
  return false;
}

static bool entry_can_edit(const program_store::Entry& entry) {
  switch(entry.type) {
#if MK61_ENABLE_BASIC
    case program_store::ProgramType::BASIC:
      return true;
#endif
#if MK61_ENABLE_FOCAL
    case program_store::ProgramType::FOCAL:
      return true;
#endif
#if MK61_ENABLE_TINYBASIC
    case program_store::ProgramType::TINYBASIC:
      return true;
#endif
    default:
      return false;
  }
}

static bool entry_can_run(const program_store::Entry& entry) {
  switch(entry.type) {
    case program_store::ProgramType::MK61:
      return true;
#if MK61_ENABLE_BASIC
    case program_store::ProgramType::BASIC:
      return true;
#endif
#if MK61_ENABLE_FOCAL
    case program_store::ProgramType::FOCAL:
      return true;
#endif
#if MK61_ENABLE_TINYBASIC
    case program_store::ProgramType::TINYBASIC:
      return true;
#endif
    default:
      return false;
  }
}

static int item_menu_actions(const program_store::Entry& entry, ItemMenuAction* actions, int capacity) {
  int count = 0;
  if(entry_can_run(entry) && count < capacity) actions[count++] = ItemMenuAction::RUN;
  if(count < capacity) actions[count++] = ItemMenuAction::VIEW;
  if(entry_can_edit(entry) && count < capacity) actions[count++] = ItemMenuAction::EDIT;
  if(count < capacity) actions[count++] = ItemMenuAction::RENAME;
  if(count < capacity) actions[count++] = ItemMenuAction::DELETE;
  return count;
}

static const char* item_menu_text(ItemMenuAction action, bool ru) {
  switch(action) {
    case ItemMenuAction::RUN:
      return ru ? "Запуск" : "Run";
    case ItemMenuAction::VIEW:
      return ru ? "Просмотр" : "View";
    case ItemMenuAction::EDIT:
      return ru ? "Редактировать" : "Edit";
    case ItemMenuAction::RENAME:
      return ru ? "Переименовать" : "Rename";
    case ItemMenuAction::DELETE:
      return ru ? "Удалить" : "Delete";
  }
  return "";
}

static void draw_item_menu(const program_store::Entry& entry, int active) {
  ItemMenuAction actions[5];
  const int count = item_menu_actions(entry, actions, 5);
  const int display_rows = lcd.rows();
  const int visible = (count < display_rows) ? count : display_rows;
  int top = active - visible + 1;
  if(top < 0) top = 0;
  if(top > count - visible) top = count - visible;

  MK61DisplayUpdate update(lcd);
  lcd.clear();

  if(library_mk61::language_is_ru()) {
    const int index0 = top;
    const int index1 = top + 1;
    if(visible == 2) {
      lcd_ru::print_menu_window(
        active == index0 ? '>' : ' ',
        item_menu_text(actions[index0], true),
        (index1 < count && active == index1) ? '>' : ' ',
        (index1 < count) ? item_menu_text(actions[index1], true) : ""
      );
    } else {
      for(int row = 0; row < visible; row++) {
        const int index = top + row;
        lcd_ru::print_menu_line((u8) row, active == index ? '>' : ' ', item_menu_text(actions[index], true));
      }
    }
  } else {
    for(int row = 0; row < visible; row++) {
      const int index = top + row;
      char line[18];
      snprintf(line, sizeof(line), "%c%s", active == index ? '>' : ' ', item_menu_text(actions[index], false));
      print_line((u8) row, line);
    }
  }
}

static bool run_entry(const program_store::Entry& entry) {
  bool ok = false;
  switch(entry.type) {
    case program_store::ProgramType::MK61:
      ok = LoadProgram(entry.name);
      break;
#if MK61_ENABLE_BASIC
    case program_store::ProgramType::BASIC:
      ok = RunBasicProgram(entry.name);
      break;
#endif
#if MK61_ENABLE_FOCAL
    case program_store::ProgramType::FOCAL:
      ok = RunFocalProgram(entry.name);
      break;
#endif
#if MK61_ENABLE_TINYBASIC
    case program_store::ProgramType::TINYBASIC:
      ok = RunTinyBasicProgram(entry.name);
      break;
#endif
    default:
      break;
  }
  if(!ok) {
    show_message("Run error", "Ошибка запуска", entry.name, entry.name);
    delay(900);
  }
  return ok;
}

static void edit_entry(const program_store::Entry& entry) {
  bool ok = false;
  switch(entry.type) {
#if MK61_ENABLE_BASIC
    case program_store::ProgramType::BASIC:
      ok = EditBasicProgram(entry.name);
      break;
#endif
#if MK61_ENABLE_FOCAL
    case program_store::ProgramType::FOCAL:
      ok = EditFocalProgram(entry.name);
      break;
#endif
#if MK61_ENABLE_TINYBASIC
    case program_store::ProgramType::TINYBASIC:
      ok = EditTinyBasicProgram(entry.name);
      break;
#endif
    default:
      break;
  }
  if(!ok) {
    show_message("Edit error", "Ошибка правки", entry.name, entry.name);
    delay(900);
  }
}

static bool explorer_item_menu(const program_store::Entry& entry) {
  ItemMenuAction actions[5];
  const int count = item_menu_actions(entry, actions, 5);
  int active = 0;
  bool wait_initial_ok_release = true;
  while(true) {
    draw_item_menu(entry, active);
    if(wait_initial_ok_release) {
      wait_ok_release();
      wait_initial_ok_release = false;
    }
    const i32 key = wait_explorer_key(false);
    if(key == EXPLORER_KEY_ESC) return action::MENU_BACK;
    if(key == EXPLORER_KEY_UP) active = (active <= 0) ? count - 1 : active - 1;
    if(key == EXPLORER_KEY_DOWN) active = (active + 1) % count;
    if(key == EXPLORER_KEY_OK) {
      switch(actions[active]) {
        case ItemMenuAction::RUN:
          if(run_entry(entry)) return action::MENU_EXIT;
          return action::MENU_BACK;
        case ItemMenuAction::VIEW:
          view_entry(entry);
          break;
        case ItemMenuAction::EDIT:
          edit_entry(entry);
          break;
        case ItemMenuAction::RENAME:
          rename_entry(entry);
          break;
        case ItemMenuAction::DELETE:
          delete_entry(entry);
          break;
      }
      return action::MENU_BACK;
    }
  }
}

static bool explorer_action(void) {
  return program_store_explorer_select();
}

static bool basic_action(void) {
  BASIC_menu_select();
  return action::MENU_BACK;
}

static bool focal_action(void) {
  FOCAL_menu_select();
  return action::MENU_BACK;
}

static constexpr t_punct EXPLORER_PUNCT = {.size = 8, .action = &explorer_action, .text = "Explorer"};
static constexpr t_punct RU_EXPLORER_PUNCT = {.size = 15, .action = &explorer_action, .text = "Проводник"};

#if MK61_ENABLE_BASIC
static constexpr t_punct BASIC_DEV_PUNCT = {.size = 11, .action = &basic_action, .text = "BASIC tools"};
static constexpr t_punct RU_BASIC_DEV_PUNCT = {.size = 15, .action = &basic_action, .text = "БЕЙСИК"};
#endif

#if MK61_ENABLE_FOCAL
static constexpr t_punct FOCAL_DEV_PUNCT = {.size = 11, .action = &focal_action, .text = "FOCAL tools"};
static constexpr t_punct RU_FOCAL_DEV_PUNCT = {.size = 15, .action = &focal_action, .text = "ФОКАЛ"};
#endif

#if MK61_ENABLE_TINYBASIC
static bool tinybasic_action(void) {
  TinyBASIC_menu_select();
  return action::MENU_BACK;
}

static constexpr t_punct TINYBASIC_DEV_PUNCT = {.size = 11, .action = &tinybasic_action, .text = "TinyBASIC"};
static constexpr t_punct RU_TINYBASIC_DEV_PUNCT = {.size = 15, .action = &tinybasic_action, .text = "TinyBASIC"};
#endif

} // namespace

bool program_store_explorer_select(void) {
  int active = 0;
  ExplorerSearch search;
  explorer_search_reset(search);

  while(true) {
    explorer_search_expire_sms(search, millis());
    const int count = total_file_count();
    if(count <= 0) {
      draw_explorer(0);
      const i32 key = wait_explorer_key(false);
      if(key == EXPLORER_KEY_ESC || key == EXPLORER_KEY_OK) return action::MENU_BACK;
      explorer_search_handle_key(search, key);
      continue;
    }
    if(active >= count) active = count - 1;
    if(active < 0) active = 0;
    if(search_active(search.text) && !entry_matches_search(active, search.text)) {
      const int first = first_matching_index(search.text);
      if(first >= 0) active = first;
    }

    draw_explorer(active, search.text);
    const i32 key = wait_explorer_key(true);
    if(key == EXPLORER_KEY_ESC) {
      if(search_active(search.text)) {
        explorer_search_reset(search);
        continue;
      }
      return action::MENU_BACK;
    }
    if(explorer_search_handle_key(search, key)) {
      const int first = first_matching_index(search.text);
      if(first >= 0) active = first;
      continue;
    }

    const int visible_count = matching_file_count(search.text);
    if(key == EXPLORER_KEY_DOWN && visible_count > 0) active = next_matching_index(active, search.text);
    else if(key == EXPLORER_KEY_UP && visible_count > 0) active = previous_matching_index(active, search.text);
    else if(key == EXPLORER_KEY_OK) {
      program_store::Entry entry;
      if(visible_count > 0 && explorer_entry(active, entry)) {
        if(entry_can_run(entry)) {
          if(run_entry(entry)) return action::MENU_EXIT;
        } else {
          view_entry(entry);
        }
      }
    } else if(key == EXPLORER_KEY_LONG_OK) {
      program_store::Entry entry;
      if(visible_count > 0 && explorer_entry(active, entry) && explorer_item_menu(entry) == action::MENU_EXIT) {
        return action::MENU_EXIT;
      }
    }
  }
}

bool development_select(void) {
  t_punct* items[] = {
    (t_punct*) (library_mk61::language_is_ru() ? &RU_EXPLORER_PUNCT : &EXPLORER_PUNCT),
#if MK61_ENABLE_BASIC
    (t_punct*) (library_mk61::language_is_ru() ? &RU_BASIC_DEV_PUNCT : &BASIC_DEV_PUNCT),
#endif
#if MK61_ENABLE_FOCAL
    (t_punct*) (library_mk61::language_is_ru() ? &RU_FOCAL_DEV_PUNCT : &FOCAL_DEV_PUNCT),
#endif
#if MK61_ENABLE_TINYBASIC
    (t_punct*) (library_mk61::language_is_ru() ? &RU_TINYBASIC_DEV_PUNCT : &TINYBASIC_DEV_PUNCT),
#endif
  };

  class_menu menu = class_menu(items, sizeof(items) / sizeof(items[0]));
  return menu.select();
}
