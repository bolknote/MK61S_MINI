#include "development.hpp"

#include "Arduino.h"
#include "bounded_string.hpp"
#include "config.h"
#include "cross_hal.h"
#include "focal.hpp"
#include "fmk_font.hpp"
#if MK61_ENABLE_WBMP_VIEWER
  #include "image1_viewer.hpp"
#endif
#include "tinybasic.hpp"
#include "keyboard.h"
#include "lcd_gui.hpp"
#include "lcd_ru.hpp"
#include "menu.hpp"
#include "program_store.hpp"
#include "shared_scratch.hpp"
#include "storage_path.hpp"
#include "text_editor.hpp"
#include "tools.hpp"
#include "utf8_view.hpp"

#include <stdio.h>
#include <string.h>

extern void idle_main_process(void);

namespace {

static constexpr u32 EXPLORER_LONG_OK_MS = 1200;
static constexpr i32 EXPLORER_KEY_UP = -2;
static constexpr i32 EXPLORER_KEY_DOWN = -3;
static constexpr i32 EXPLORER_KEY_OK = -4;
static constexpr i32 EXPLORER_KEY_LONG_OK = -5;
static constexpr i32 EXPLORER_KEY_ESC = -6;
static constexpr i32 EXPLORER_KEY_TICK = -7;
static constexpr i32 EXPLORER_KEY_REDRAW = -8;
static constexpr u16 EXPLORER_SCROLL_START_MS = 900;
static constexpr u16 EXPLORER_SCROLL_STEP_MS = 450;
static constexpr u16 EXPLORER_SCROLL_EDGE_MS = 900;
static constexpr u8 EXPLORER_NAME_COL = 0;
static constexpr u8 EXPLORER_NO_CURSOR_ROW = 0xFF;
static constexpr int ITEM_MENU_ACTION_CAPACITY = 7;

static u16 current_mk61_entry_id = program_store::INVALID_ID;
static u16 current_mk61_directory_id = program_store::ROOT_ID;

#if defined(MK61_DISPLAY_UC1609)
static u16 applied_font_id = program_store::INVALID_ID;
static bool applied_font_suspended = false;
#endif

static_assert(shared_scratch::SIZE >= program_store::MAX_IMAGE1_SIZE,
              "shared scratch too small for explorer view");
static_assert(fmk::MAX_FILE_SIZE == program_store::MAX_FONT_SIZE, "font parser and storage limits must match");

enum class ItemMenuAction : u8 {
  LOAD,
  RUN,
  VIEW,
  EDIT,
  NEW_DIRECTORY,
  RENAME,
  MOVE,
  DELETE
};

enum class NamePrompt : u8 {
  RENAME,
  NEW_DIRECTORY,
  SAVE
};

enum class DialogMode : u8 {
  FILE,
  DIRECTORY
};

struct ExplorerSearch {
  char text[program_store::NAME_SIZE];
  u16 len;
  text_editor::SmsState sms;
  text_editor::Shift shift;
};

struct ExplorerScroll {
  int active;
  char name[program_store::NAME_SIZE];
  u8 offset;
  i8 direction;
  u32 next_ms;
};

static const char* type_label(program_store::ProgramType type) {
  switch(type) {
    case program_store::ProgramType::MK61: return "M1";
    case program_store::ProgramType::FOCAL: return "F1";
    case program_store::ProgramType::TINYBASIC: return "B2";
    case program_store::ProgramType::TEXT: return "T1";
    case program_store::ProgramType::MK61_STATE: return "M2";
    case program_store::ProgramType::FONT: return "f1";
    case program_store::ProgramType::IMAGE1: return "I1";
  }
  return "??";
}

static char type_marker(program_store::ProgramType type) {
  const char* label = type_label(type);
  return (label != NULL && label[0] != 0) ? label[0] : '?';
}

static void print_line(u8 row, const char* text) {
  main_lcd().setCursor(0, row);
  u8 used = 0;
  while(text != NULL && used < lcd_display::COLS && text[used] != 0) {
    main_lcd().write((u8) text[used++]);
  }
  while(used++ < lcd_display::COLS) main_lcd().write((u8) ' ');
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

// Возвращает false, если подсистема дисплея сменилась при удержании OK.
// Вызывающий код может перерисовать экран и продолжить ожидание, не показывая
// символы Unicode с USB-поверхности как '?' на физическом LCD1602.
static bool wait_ok_release(void) {
  const u32 display_mode_revision = main_lcd().displayModeRevision();
  while(true) {
    idle_main_process();
    if(main_lcd().displayModeRevision() != display_mode_revision) return false;

    const i32 scan_code = scan_direct_key();
    if(scan_code >= 0) {
      const bool released = (scan_code & (i32) key_state::RELEASED) != 0;
      const i32 code = scan_code & ~(i32) key_state::RELEASED;
      if(released && code == (i32) KEY_OK) {
        kbd::clear_hold_key();
        return true;
      }
    }

    // Терминальные команды `kbd` — это завершённые нажатия: в отличие от
    // физических и двоичных USB-клавиш, у них намеренно нет отдельного отпускания.
    if(!kbd::is_key_pressed(KEY_OK)) {
      kbd::clear_hold_key();
      return true;
    }
    delay(10);
  }
}

static void wait_all_keys_released(void) {
  kbd::clear_hold_key();

  while(true) {
    idle_main_process();
    const i32 scan_code = kbd::scan_and_debounced();
    if(scan_code >= 0) kbd::exclude_before(scan_code);

    if(!kbd::any_key_pressed() && kbd::last_key() < 0) {
      kbd::clear_hold_key();
      return;
    }
    delay(10);
  }
}

static bool explorer_time_reached(u32 now, u32 target) {
  return (i32) (now - target) >= 0;
}

static u8 explorer_type_col(void) {
  const u8 cols = main_lcd().cols();
  return cols > 0 ? (u8) (cols - 1) : 0;
}

static void explorer_cursor_off(void) {
  if(main_lcd().supportsCursor()) main_lcd().cursorOff();
}

static void explorer_cursor_on(u8 cursor_row) {
  if(cursor_row == EXPLORER_NO_CURSOR_ROW || cursor_row >= main_lcd().rows() || !main_lcd().supportsCursor()) return;
  main_lcd().cursorOff();
  main_lcd().setCursor(explorer_type_col(), cursor_row);
  main_lcd().blinkOn();
}

static i32 wait_explorer_key(bool allow_long_ok, u16 tick_ms = 0, u8 cursor_row = EXPLORER_NO_CURSOR_ROW) {
  bool ok_down = false;
  u32 long_ok_at = 0;
  const u32 tick_at = tick_ms == 0 ? 0 : millis() + tick_ms;
  const u32 display_mode_revision = main_lcd().displayModeRevision();
  kbd::debounce_init();
  explorer_cursor_on(cursor_row);

  while(true) {
    idle_main_process();
    if(main_lcd().displayModeRevision() != display_mode_revision) {
      explorer_cursor_off();
      return EXPLORER_KEY_REDRAW;
    }

    const u32 now = millis();
    if(tick_ms != 0 && !ok_down && explorer_time_reached(now, tick_at)) return EXPLORER_KEY_TICK;
    if(allow_long_ok && ok_down && explorer_time_reached(now, long_ok_at)) {
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
      // Терминальная команда `kbd` обозначает уже завершённое нажатие. Долго
      // удерживаться могут только физические клавиши и двоичные нажатия KEY_EVENT.
      if(!kbd::is_key_pressed(KEY_OK)) return EXPLORER_KEY_OK;
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

static i32 wait_explorer_raw_key(void) {
  const u32 display_mode_revision = main_lcd().displayModeRevision();
  kbd::debounce_init();
  while(true) {
    idle_main_process();
    if(main_lcd().displayModeRevision() != display_mode_revision) {
      explorer_cursor_off();
      return EXPLORER_KEY_REDRAW;
    }

    const i32 scan_code = scan_direct_key();
    if(scan_code < 0) {
      delay(10);
      continue;
    }
    if((scan_code & (i32) key_state::RELEASED) != 0) continue;
    return scan_code & ~(i32) key_state::RELEASED;
  }
}

static int explorer_count(u16 directory_id) {
  return program_store::child_count(directory_id);
}

static bool explorer_entry(u16 directory_id, int index,
                           program_store::Entry& out) {
  return index >= 0 && program_store::child(directory_id, index, out);
}

static bool entry_by_type_name(program_store::ProgramType type, const char* name, program_store::Entry& out) {
  if(name == NULL || name[0] == 0) return false;
  const int count = program_store::count(type);
  for(int i = 0; i < count; i++) {
    program_store::Entry entry;
    if(!program_store::entry(type, i, entry)) continue;
    if(strncmp(entry.name, name, program_store::NAME_SIZE) == 0) {
      out = entry;
      return true;
    }
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

  const usize text_len = text_editor::bounded_length(text, program_store::NAME_SIZE);
  const usize needle_len = text_editor::bounded_length(needle, program_store::NAME_SIZE);
  for(usize start = 0; start < text_len; start++) {
    usize pos = 0;
    while(pos < needle_len && start + pos < text_len &&
          ascii_upper(text[start + pos]) == ascii_upper(needle[pos])) {
      pos++;
    }
    if(pos == needle_len) return true;
  }
  return false;
}

static bool entry_matches_search(u16 directory_id, int index,
                                 const char* search_text) {
  if(!search_active(search_text)) return true;
  program_store::Entry entry;
  if(!explorer_entry(directory_id, index, entry)) return false;
  return text_contains_case_insensitive(entry.name, search_text);
}

static int matching_entry_count(u16 directory_id, const char* search_text) {
  const int count = explorer_count(directory_id);
  if(!search_active(search_text)) return count;

  int matches = 0;
  for(int index = 0; index < count; index++) {
    if(entry_matches_search(directory_id, index, search_text)) matches++;
  }
  return matches;
}

static int matching_index_at(u16 directory_id, int match_index,
                             const char* search_text) {
  const int count = explorer_count(directory_id);
  if(!search_active(search_text)) return (match_index >= 0 && match_index < count) ? match_index : -1;

  int current = 0;
  for(int index = 0; index < count; index++) {
    if(!entry_matches_search(directory_id, index, search_text)) continue;
    if(current == match_index) return index;
    current++;
  }
  return -1;
}

static int matching_position(u16 directory_id, int active,
                             const char* search_text) {
  if(!search_active(search_text)) return active;
  const int count = explorer_count(directory_id);
  int position = 0;
  for(int index = 0; index < count; index++) {
    if(!entry_matches_search(directory_id, index, search_text)) continue;
    if(index == active) return position;
    position++;
  }
  return -1;
}

static int first_matching_index(u16 directory_id, const char* search_text) {
  return matching_index_at(directory_id, 0, search_text);
}

static int next_matching_index(u16 directory_id, int active,
                               const char* search_text) {
  const int count = explorer_count(directory_id);
  if(count <= 0) return active;
  if(!search_active(search_text)) return (active + 1 < count) ? active + 1 : 0;
  for(int index = active + 1; index < count; index++) {
    if(entry_matches_search(directory_id, index, search_text)) return index;
  }
  for(int index = 0; index < active; index++) {
    if(entry_matches_search(directory_id, index, search_text)) return index;
  }
  return active;
}

static int previous_matching_index(u16 directory_id, int active,
                                   const char* search_text) {
  const int count = explorer_count(directory_id);
  if(count <= 0) return active;
  if(!search_active(search_text)) return (active > 0) ? active - 1 : count - 1;
  for(int index = active - 1; index >= 0; index--) {
    if(entry_matches_search(directory_id, index, search_text)) return index;
  }
  for(int index = count - 1; index > active; index--) {
    if(entry_matches_search(directory_id, index, search_text)) return index;
  }
  return active;
}

static void draw_search_header(const char* search_text) {
  char line[18];
  snprintf(line, sizeof(line), "?%s", search_text);
  print_line(0, line);
}

static void draw_search_cursor(const char* search_text) {
  const usize len = text_editor::bounded_length(search_text, program_store::NAME_SIZE);
  const u8 cursor_col = (len + 1 < lcd_display::COLS) ? (u8) (len + 1) : (u8) (lcd_display::COLS - 1);
  main_lcd().setCursor(cursor_col, 0);
  main_lcd().cursorOn();
}

static void explorer_scroll_reset(ExplorerScroll& scroll) {
  scroll.active = -1;
  scroll.name[0] = 0;
  scroll.offset = 0;
  scroll.direction = 1;
  scroll.next_ms = 0;
}

static u8 explorer_name_width(void) {
  const u8 type_col = explorer_type_col();
  return type_col > EXPLORER_NAME_COL ? (u8) (type_col - EXPLORER_NAME_COL) : 0;
}

static u8 explorer_name_len(const char* name) {
  const usize len = utf8_view::codepoint_count(name,
                                               program_store::NAME_SIZE - 1);
  return len > 255 ? 255 : (u8) len;
}

static bool explorer_name_overflows(const char* name, u8 width) {
  return width != 0 && explorer_name_len(name) > width;
}

static u8 explorer_scroll_max_offset(const char* name, u8 width) {
  const u8 len = explorer_name_len(name);
  return (width != 0 && len > width) ? (u8) (len - width) : 0;
}

static void explorer_scroll_track(ExplorerScroll& scroll, int active, const char* name, u8 width, u32 now) {
  const bool same = scroll.active == active && strncmp(scroll.name, name, program_store::NAME_SIZE) == 0;
  if(!same) {
    scroll.active = active;
    bounded_string::copy(scroll.name, name);
    scroll.offset = 0;
    scroll.direction = 1;
    scroll.next_ms = now + EXPLORER_SCROLL_START_MS;
  }

  const u8 max_offset = explorer_scroll_max_offset(name, width);
  if(max_offset == 0) {
    scroll.offset = 0;
    scroll.direction = 1;
    scroll.next_ms = 0;
    return;
  }

  if(scroll.offset > max_offset) scroll.offset = max_offset;
  if(scroll.next_ms == 0) scroll.next_ms = now + EXPLORER_SCROLL_START_MS;
  if(!explorer_time_reached(now, scroll.next_ms)) return;

  if(scroll.direction >= 0) {
    if(scroll.offset < max_offset) scroll.offset++;
    if(scroll.offset >= max_offset) {
      scroll.direction = -1;
      scroll.next_ms = now + EXPLORER_SCROLL_EDGE_MS;
    } else {
      scroll.next_ms = now + EXPLORER_SCROLL_STEP_MS;
    }
  } else {
    if(scroll.offset > 0) scroll.offset--;
    if(scroll.offset == 0) {
      scroll.direction = 1;
      scroll.next_ms = now + EXPLORER_SCROLL_EDGE_MS;
    } else {
      scroll.next_ms = now + EXPLORER_SCROLL_STEP_MS;
    }
  }
}

static u16 explorer_scroll_timeout(const ExplorerScroll& scroll, const char* name, u8 width, u32 now) {
  if(!explorer_name_overflows(name, width) || scroll.next_ms == 0) return 0;
  if(explorer_time_reached(now, scroll.next_ms)) return 1;
  const u32 delta = scroll.next_ms - now;
  return delta > 1000 ? 1000 : (u16) delta;
}

static void explorer_name_window(const char* name, u8 offset, u8 width,
                                 bool mark_overflow, char* out,
                                 usize capacity) {
  if(out == NULL || capacity == 0) return;
  out[0] = 0;
  if(name == NULL || width == 0) return;
  const u16 byte_len = (u16) text_editor::bounded_length(
      name, program_store::NAME_SIZE);
  const u8 codepoints = explorer_name_len(name);
  if(offset > codepoints) offset = codepoints;
  const bool marker = mark_overflow && offset == 0 && codepoints > width;
  const u8 text_width = marker && width > 0 ? (u8) (width - 1) : width;
  u16 source = utf8_view::byte_offset(name, offset, byte_len);
  usize target = 0;
  for(u8 used = 0; used < text_width && source < byte_len; used++) {
    const u16 next = utf8_view::next_offset((const u8*) name, byte_len,
                                            source);
    const u16 bytes = next > source ? (u16) (next - source) : 1;
    if(target + bytes >= capacity) break;
    memcpy(out + target, name + source, bytes);
    target += bytes;
    source = (u16) (source + bytes);
  }
  if(marker && target + 1 < capacity) out[target++] = '>';
  out[target] = 0;
}

static void draw_explorer_name(const lcd_ru::font_map_t& map,
                               const char* name, u8 row, u8 offset) {
  const u8 width = explorer_name_width();
  if(width == 0) return;
  char window[program_store::NAME_SIZE];
  explorer_name_window(name, offset, width, true, window, sizeof(window));
  main_lcd().setCursor(EXPLORER_NAME_COL, row);
  lcd_ru::write_text(map, window, width);
}

static void draw_explorer_row(const lcd_ru::font_map_t& map, u8 row,
                              const program_store::Entry& entry,
                              u8 scroll_offset) {
  draw_explorer_name(map, entry.name, row, scroll_offset);
  main_lcd().setCursor(explorer_type_col(), row);
  main_lcd().write((u8) (entry.kind == program_store::NodeKind::DIRECTORY
                    ? '/'
                    : type_marker(entry.type)));
}

static u16 draw_explorer(u16 directory_id, int active, ExplorerScroll& scroll,
                         const char* search_text = NULL,
                         u8* cursor_row_out = NULL) {
  if(cursor_row_out != NULL) *cursor_row_out = EXPLORER_NO_CURSOR_ROW;
  explorer_cursor_off();

  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();

  const int count = explorer_count(directory_id);
  if(count <= 0) {
    explorer_scroll_reset(scroll);
    print_localized_line(0,
                         directory_id == program_store::ROOT_ID ? "FS is empty" : "Folder empty",
                         directory_id == program_store::ROOT_ID ? "ФС пуста" : "Папка пуста");
    print_localized_line(1, "OK: new folder", "OK: нов. папка");
    return 0;
  }

  const bool filtered = search_active(search_text);
  const int display_rows = main_lcd().rows();
  const int first_row = filtered ? 1 : 0;
  const int list_rows = display_rows - first_row;
  if(filtered) draw_search_header(search_text);
  if(list_rows <= 0) {
    explorer_scroll_reset(scroll);
    if(filtered) draw_search_cursor(search_text);
    return 0;
  }

  const int visible_count = filtered
    ? matching_entry_count(directory_id, search_text)
    : count;
  if(visible_count <= 0) {
    explorer_scroll_reset(scroll);
    print_localized_line((u8) first_row, "No match", "Нет совпад.");
    for(int row = first_row + 1; row < display_rows; row++) print_line((u8) row, "");
    if(filtered) draw_search_cursor(search_text);
    return 0;
  }

  int active_pos = filtered
    ? matching_position(directory_id, active, search_text)
    : active;
  if(active_pos < 0) active_pos = 0;

  const int visible = (visible_count < list_rows) ? visible_count : list_rows;
  const int max_top = visible_count - visible;
  int top = active_pos - visible + 1;
  if(top < 0) top = 0;
  if(top > max_top) top = max_top;

  u16 scroll_timeout = 0;
  const u32 now = millis();
  program_store::Entry active_entry;
  if(explorer_entry(directory_id, active, active_entry)) {
    const u8 width = explorer_name_width();
    explorer_scroll_track(scroll, active, active_entry.name, width, now);
    scroll_timeout = explorer_scroll_timeout(scroll, active_entry.name, width, now);
  } else {
    explorer_scroll_reset(scroll);
  }

  lcd_ru::font_map_t name_map = {{0}, 0, false};
  for(int row = 0; row < visible; row++) {
    const int index = filtered
      ? matching_index_at(directory_id, top + row, search_text)
      : top + row;
    program_store::Entry entry;
    if(!explorer_entry(directory_id, index, entry)) continue;
    char window[program_store::NAME_SIZE];
    explorer_name_window(entry.name, active == index ? scroll.offset : 0,
                         explorer_name_width(), true, window,
                         sizeof(window));
    lcd_ru::scan_text(name_map, window, explorer_name_width());
  }
  lcd_ru::load_custom_font(name_map);

  for(int row = 0; row < visible; row++) {
    const int index = filtered
      ? matching_index_at(directory_id, top + row, search_text)
      : top + row;
    program_store::Entry entry;
    if(explorer_entry(directory_id, index, entry)) {
      const u8 scroll_offset = (active == index) ? scroll.offset : 0;
      const u8 screen_row = (u8) (first_row + row);
      const bool selected = active == index;
      draw_explorer_row(name_map, screen_row, entry, scroll_offset);
      if(selected && cursor_row_out != NULL) *cursor_row_out = screen_row;
    } else {
      print_line((u8) (first_row + row), "?");
    }
  }

  for(int row = first_row + visible; row < display_rows; row++) print_line((u8) row, "");
  if(filtered && (cursor_row_out == NULL || *cursor_row_out == EXPLORER_NO_CURSOR_ROW)) {
    draw_search_cursor(search_text);
  }
  return scroll_timeout;
}

static bool read_entry_data(const program_store::Entry& entry, u8* data, usize capacity, u16& out_len) {
  if(data == NULL || capacity == 0 || capacity > 0xFFFF || entry.data_len > capacity) {
    out_len = 0;
    return false;
  }
  memset(data, 0, capacity);
  out_len = 0;
  if(entry.kind != program_store::NodeKind::FILE ||
     !program_store::read_id(entry.id, data, (u16) capacity, &out_len) ||
     out_len > capacity || out_len != entry.data_len) {
    memset(data, 0, capacity);
    out_len = 0;
    return false;
  }
  return true;
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

static u16 next_text_char_offset(const u8* data, u16 len, u16 offset) {
  return utf8_view::next_offset(data, len, offset);
}

static u16 next_visual_line_offset(const u8* data, u16 len, u16 offset) {
  if(offset >= len) return len;

  u8 used = 0;
  while(offset < len) {
    if(is_line_break(data[offset])) return consume_line_break(data, len, offset);

    offset = next_text_char_offset(data, len, offset);
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

static void append_text_view_char(const u8* data, u16 len, u16& offset, char* line, u8 capacity, u8& pos) {
  const u16 next = next_text_char_offset(data, len, offset);
  const u16 bytes = (u16) (next - offset);
  if(bytes == 1) {
    const u8 value = data[offset];
    line[pos++] = (value >= 0x20 && value < 0x7F) ? (char) value : '?';
    offset = next;
    return;
  }

  if(bytes == 2 || bytes == 3) {
    if(pos + bytes < capacity) {
      for(u16 i = 0; i < bytes; i++) line[pos++] = (char) data[offset + i];
    } else {
      line[pos++] = '?';
    }
    offset = next;
    return;
  }

  line[pos++] = '?';
  offset = next;
}

static void build_text_payload_line(const u8* data, u16 len, u16 line_index, char* line, u8 capacity) {
  u16 offset = visual_line_offset(data, len, line_index);
  u8 pos = 0;
  u8 used = 0;
  while(used < lcd_display::COLS && offset < len && !is_line_break(data[offset])) {
    if(pos + 4 >= capacity) {
      line[pos++] = '?';
      offset = next_text_char_offset(data, len, offset);
    } else {
      append_text_view_char(data, len, offset, line, capacity, pos);
    }
    used++;
  }
  line[pos] = 0;
}

static void draw_file_view(const program_store::Entry& entry, const u8* data, u16 len, u16 top_line) {
  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();

  char header[24];
  snprintf(header, sizeof(header), "%s %u %.14s", type_label(entry.type),
           (unsigned) len, entry.name);
  print_line(0, header);

  const u8 display_rows = main_lcd().rows();
  const u8 payload_rows = display_rows > 1 ? (u8) (display_rows - 1) : 1;
  const u16 total_lines = visual_line_count(data, len);

  static constexpr u8 TEXT_VIEW_LINE_BYTES = lcd_display::COLS * 3 + 1;
  char rows[lcd_display::RUNTIME_MAX_ROWS][TEXT_VIEW_LINE_BYTES];
  for(u8 row = 0; row < payload_rows; row++) {
    const u16 line_index = (u16) (top_line + row);
    if(line_index < total_lines) build_text_payload_line(data, len, line_index, rows[row], TEXT_VIEW_LINE_BYTES);
    else rows[row][0] = 0;
  }

  lcd_ru::font_map_t map = {{0}, 0, false};
  for(u8 row = 0; row < payload_rows; row++) lcd_ru::scan_text(map, rows[row], lcd_display::COLS);
  lcd_ru::load_custom_font(map);
  for(u8 row = 0; row < payload_rows; row++) {
    main_lcd().setCursor(0, (u8) (row + 1));
    lcd_ru::write_text(map, rows[row], lcd_display::COLS);
  }
}

static void show_message(const char* en0, const char* ru0, const char* en1 = "", const char* ru1 = "") {
  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();
  print_localized_line(0, en0, ru0);
  print_localized_line(1, en1, ru1);
}

static void draw_font_preview_header(const program_store::Entry& entry, const fmk::Face& face) {
  char header[24];
  snprintf(header, sizeof(header), "f1 %ux%u %.12s",
    (unsigned) face.metrics().max_width, (unsigned) face.metrics().height,
    entry.name);
  print_line(0, header);
}

static void view_font_entry(const program_store::Entry& entry, const u8* data, u16 len) {
  fmk::Face face;
  if(!face.open(data, len)) {
    show_message("Bad font", "Ошибка шрифта", entry.name, entry.name);
    wait_explorer_key(false);
    return;
  }
  if(!main_lcd().graphicsMode() && !face.metrics().monospaced) {
    show_message("Proportional", "Пропорциональный", "Not supported", "Не поддержан");
    wait_explorer_key(false);
    return;
  }

  if(main_lcd().graphicsMode()) {
    if(!main_lcd().setFontPreview(data, len)) {
      show_message("Preview error", "Ошибка просмотра", entry.name, entry.name);
      wait_explorer_key(false);
      return;
    }

    {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().clear();
      draw_font_preview_header(entry, face);
      if(main_lcd().rows() > 1) print_line(1, "0123456789+-*/");
      if(main_lcd().rows() > 2) print_line(2, "ABCDEFGHIJKLMNO");
      if(main_lcd().rows() > 3) print_line(3, "abcdefghijklmno");
      if(main_lcd().rows() > 4) lcd_ru::print_at(0, 4, "АБВГДЕЖЗИЙКЛМНО", lcd_display::COLS);
      if(main_lcd().rows() > 5) lcd_ru::print_at(0, 5, "абвгдежзийклмно", lcd_display::COLS);
      for(u8 row = 6; row < main_lcd().rows(); row++) print_line(row, "");
    }
    wait_explorer_key(false);
    main_lcd().clearFontPreview();
    main_lcd().clear();
    return;
  }

#if defined(MK61_DISPLAY_LCD1602)
  fmk::Glyph glyphs[8];
  if(fmk::selectPreviewGlyphs(face, glyphs) != 8) {
    show_message("No glyphs", "Нет символов", entry.name, entry.name);
    wait_explorer_key(false);
    return;
  }

  u8 rows[8][8];
  for(u8 slot = 0; slot < 8; slot++) {
    if(!fmk::scaleToLcd5x8(face, glyphs[slot], rows[slot])) {
      show_message("Preview error", "Ошибка просмотра", entry.name, entry.name);
      wait_explorer_key(false);
      return;
    }
    main_lcd().createChar(slot, rows[slot]);
  }

  {
    MK61DisplayUpdate update(main_lcd());
    main_lcd().clear();
    draw_font_preview_header(entry, face);
    main_lcd().setCursor(0, 1);
    for(u8 slot = 0; slot < 8; slot++) main_lcd().write(slot);
    for(u8 col = 8; col < lcd_display::COLS; col++) main_lcd().write((u8) ' ');
  }
  wait_explorer_key(false);
  lcd_ru::restore_default_font();
  main_lcd().clear();
#else
  show_message("Preview error", "Ошибка просмотра", entry.name, entry.name);
  wait_explorer_key(false);
#endif
}

static bool apply_font_entry(const program_store::Entry& entry) {
#if !defined(MK61_DISPLAY_UC1609)
  (void) entry;
  return false;
#else
  shared_scratch::Lease scratch(shared_scratch::Owner::EXPLORER_VIEW, program_store::MAX_FONT_SIZE);
  if(!scratch.ok()) return false;
  u16 len = 0;
  if(!read_entry_data(entry, scratch.data(), scratch.size(), len)) return false;
  if(!main_lcd().installFont(scratch.data(), len)) return false;
  applied_font_id = entry.id;
  applied_font_suspended = false;
  library_mk61::set_display_text_profile(main_lcd().textProfile());
  library_mk61::refresh_menu_text();
  library_mk61::defer_settings_state_save();
  return true;
#endif
}

static bool view_entry(const program_store::Entry& entry) {
  if(entry.type == program_store::ProgramType::IMAGE1) {
#if MK61_ENABLE_WBMP_VIEWER
    const image1_viewer::Result result =
      image1_viewer::view_entry(main_lcd(), entry);
    if(result == image1_viewer::Result::OK) return true;

    const char* en = "Image error";
    const char* ru = "Ошибка картинки";
    if(result == image1_viewer::Result::BUSY) {
      en = "Busy";
      ru = "Занято";
    } else if(result == image1_viewer::Result::READ_ERROR) {
      en = "Read error";
      ru = "Ошибка чтения";
    } else if(result == image1_viewer::Result::INVALID_IMAGE) {
      en = "Invalid WBMP";
      ru = "Неверный WBMP";
    } else if(result == image1_viewer::Result::DISPLAY_ERROR) {
      en = "Display error";
      ru = "Ошибка экрана";
    }
    show_message(en, ru, entry.name, entry.name);
    (void) wait_explorer_key(false);
    return false;
#else
    show_message("Viewer disabled", "Просмотр выключен",
                 entry.name, entry.name);
    (void) wait_explorer_key(false);
    return false;
#endif
  }

  shared_scratch::Lease scratch(shared_scratch::Owner::EXPLORER_VIEW, program_store::MAX_MK61_TEXT_SIZE);
  if(!scratch.ok()) {
    show_message("Busy", "Занято", entry.name, entry.name);
    (void) wait_explorer_key(false);
    return false;
  }

  u8* data = scratch.data();
  u16 len = 0;
  if(!read_entry_data(entry, data, scratch.size(), len)) {
    show_message("Read error", "Ошибка чтения", entry.name, entry.name);
    (void) wait_explorer_key(false);
    return false;
  }

  if(entry.type == program_store::ProgramType::FONT) {
    view_font_entry(entry, data, len);
    return true;
  }

  u16 top_line = 0;
  while(true) {
    const u8 display_rows = main_lcd().rows();
    const u8 rows = display_rows > 1 ? (u8) (display_rows - 1) : 1;
    const u16 page = rows;
    const u16 total_lines = visual_line_count(data, len);
    const u16 max_top = (total_lines > rows) ? (u16) (total_lines - rows) : 0;
    if(top_line > max_top) top_line = max_top;

    draw_file_view(entry, data, len, top_line);
    const i32 key = wait_explorer_key(false);
    if(key == EXPLORER_KEY_REDRAW) continue;
    if(key == EXPLORER_KEY_ESC || key == EXPLORER_KEY_OK) return true;
    if(key == EXPLORER_KEY_DOWN && top_line < max_top) {
      top_line = (u16) (top_line + page);
      if(top_line > max_top) top_line = max_top;
    }
    if(key == EXPLORER_KEY_UP) top_line = (top_line > page) ? (u16) (top_line - page) : 0;
  }
}

static bool confirm_delete(const program_store::Entry& entry) {
  const bool tree = entry.kind == program_store::NodeKind::DIRECTORY &&
                    program_store::child_count(entry.id) != 0;
  while(true) {
    show_message(tree ? "Delete tree?" : "Delete?",
                 tree ? "Удалить всё?" : "Удалить?", entry.name, entry.name);
    const i32 key = wait_explorer_key(false);
    if(key == EXPLORER_KEY_REDRAW) continue;
    if(key == EXPLORER_KEY_OK) return true;
    if(key == EXPLORER_KEY_ESC) return false;
  }
}

static void delete_entry(const program_store::Entry& entry) {
  if(!confirm_delete(entry)) return;

  u16 removed = 0;
  const bool ok = program_store::remove_tree(entry.id, &removed);
  show_message(ok ? "Deleted" : "Delete error", ok ? "Удалено" : "Ошибка", entry.name, entry.name);
  delay(700);
}

static void draw_name_editor(const char* name, u16 cursor, NamePrompt prompt) {
  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();
  const char* en = "Rename";
  const char* ru = "Новое имя";
  if(prompt == NamePrompt::NEW_DIRECTORY) {
    en = "New folder";
    ru = "Новая папка";
  } else if(prompt == NamePrompt::SAVE) {
    en = "File name";
    ru = "Имя файла";
  }
  const char* title = library_mk61::language_is_ru() ? ru : en;
  const u16 byte_len = (u16) strlen(name);
  if(cursor > byte_len) cursor = byte_len;
  const u16 cursor_chars = utf8_view::codepoint_count(name, cursor);
  const u16 window = cursor_chars > lcd_display::COLS - 2
      ? (u16) (cursor_chars - (lcd_display::COLS - 2)) : 0;
  char line[program_store::NAME_SIZE + 2];
  line[0] = '>';
  explorer_name_window(name, (u8) window,
                       (u8) (lcd_display::COLS - 1), false,
                       line + 1, sizeof(line) - 1);

  lcd_ru::font_map_t map = {{0}, 0, false};
  lcd_ru::scan_text(map, title, lcd_display::COLS);
  lcd_ru::scan_text(map, line, lcd_display::COLS);
  lcd_ru::load_custom_font(map);
  main_lcd().setCursor(0, 0);
  lcd_ru::write_text(map, title, lcd_display::COLS);
  main_lcd().setCursor(0, 1);
  lcd_ru::write_text(map, line, lcd_display::COLS);

  const u8 cursor_col = (u8) (1 + cursor_chars - window);
  main_lcd().setCursor(cursor_col, 1);
  main_lcd().cursorOn();
}

static bool name_move_left(const char* name, u16 len, u16& cursor) {
  if(name == NULL || cursor == 0 || cursor > len) return false;
  cursor = utf8_view::previous_offset((const u8*) name, len, cursor);
  return true;
}

static bool name_move_right(const char* name, u16 len, u16& cursor) {
  if(name == NULL || cursor >= len) return false;
  const u16 next = utf8_view::next_offset((const u8*) name, len, cursor);
  cursor = next > cursor ? next : (u16) (cursor + 1);
  return true;
}

static bool name_backspace(char* name, u16& len, u16& cursor) {
  if(name == NULL || cursor == 0 || cursor > len || name[len] != 0) {
    return false;
  }
  const u16 previous = utf8_view::previous_offset((const u8*) name, len,
                                                  cursor);
  memmove(name + previous, name + cursor, len - cursor + 1);
  len = (u16) (len - (cursor - previous));
  cursor = previous;
  return true;
}

static bool name_insert_char(char* name, u16& len, u16& cursor, char ch,
                             usize capacity = program_store::NAME_SIZE) {
  if(ch == 0) return false;
  if(ch == ' ' && len == 0) return false;
  char text[2] = {ch, 0};
  return text_editor::insert_text(name, len, cursor, capacity, text);
}

static bool input_entry_name(char* name, usize capacity,
                             NamePrompt prompt = NamePrompt::RENAME) {
  if(name == NULL || capacity < 2 || capacity > program_store::NAME_SIZE) {
    return false;
  }
  u16 len = (u16) text_editor::bounded_length(name, capacity);
  if(len >= capacity) len = (u16) (capacity - 1);
  name[len] = 0;
  u16 cursor = len;
  text_editor::SmsState sms = {};
  text_editor::Shift shift = text_editor::Shift::NONE;
  text_editor::sms_reset(sms);

  while(true) {
    const u32 draw_now = millis();
    if(text_editor::sms_expired(sms, draw_now)) text_editor::sms_reset(sms);
    draw_name_editor(name, cursor, prompt);

    const i32 key = wait_explorer_raw_key();
    if(key == EXPLORER_KEY_REDRAW) continue;
    const u32 key_now = millis();
    if(text_editor::sms_expired(sms, key_now)) text_editor::sms_reset(sms);
    const bool shifted_key = shift != text_editor::Shift::NONE;
    const int digit = text_editor::digit_from_key(key);

    if(!shifted_key && sms.active) {
      if(text_editor::sms_key_is_letters(key)) {
        text_editor::sms_tap(name, len, cursor, capacity, sms, key, key_now);
        continue;
      }
      if(text_editor::sms_key_is_space(key)) {
        text_editor::sms_reset(sms);
        name_insert_char(name, len, cursor, ' ', capacity);
        continue;
      }
      if(digit == 0) {
        text_editor::sms_reset(sms);
        continue;
      }
      if(key == KEY_PP) {
        text_editor::sms_reset(sms);
        name_insert_char(name, len, cursor, ' ', capacity);
        continue;
      }
      text_editor::sms_reset(sms);
    }

    if(!shifted_key && (key == KEY_K || key == KEY_ALPHA)) {
      shift = (key == KEY_K) ? text_editor::Shift::K : text_editor::Shift::ALPHA;
      text_editor::sms_reset(sms);
      continue;
    }
    if(!shifted_key && (key == KEY_OK || key == KEY_OK_PRESS)) return len > 0;
    if(!shifted_key && (key == KEY_ESC || key == KEY_ESC_PRESS)) return false;
    if(key == KEY_CX &&
        (shift == text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(sms);
      len = 0;
      cursor = 0;
      name[0] = 0;
      shift = text_editor::Shift::NONE;
      continue;
    }
    if((key == KEY_LEFT || key == KEY_LEFT_PRESS) &&
        (shift == text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(sms);
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(!shifted_key && (key == KEY_LEFT || key == KEY_LEFT_PRESS)) {
      text_editor::sms_reset(sms);
      name_move_left(name, len, cursor);
      continue;
    }
    if(!shifted_key && (key == KEY_RIGHT || key == KEY_RIGHT_PRESS)) {
      text_editor::sms_reset(sms);
      name_move_right(name, len, cursor);
      continue;
    }
    if(!shifted_key && key == KEY_CX) {
      text_editor::sms_reset(sms);
      name_backspace(name, len, cursor);
      continue;
    }

    if(shift == text_editor::Shift::ALPHA && digit >= 0) {
      const char* symbol = text_editor::symbol_for_digit_key(key);
      if(symbol != NULL && symbol[0] != 0) {
        name_insert_char(name, len, cursor, symbol[0], capacity);
      }
      shift = text_editor::Shift::NONE;
      text_editor::sms_reset(sms);
      continue;
    }
    if(shift == text_editor::Shift::ALPHA) {
      shift = text_editor::Shift::NONE;
      text_editor::sms_reset(sms);
      continue;
    }
    if(shift == text_editor::Shift::K && text_editor::sms_key_is_letters(key)) {
      text_editor::sms_tap(name, len, cursor, capacity, sms, key, key_now);
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(shift == text_editor::Shift::K && text_editor::sms_key_is_space(key)) {
      text_editor::sms_reset(sms);
      name_insert_char(name, len, cursor, ' ', capacity);
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(shift == text_editor::Shift::K) {
      const char* punctuation = text_editor::kshift_text_for_key(key);
      text_editor::sms_reset(sms);
      if(punctuation != NULL && punctuation[0] != 0 && punctuation[1] == 0) {
        name_insert_char(name, len, cursor, punctuation[0], capacity);
      }
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(key == KEY_PP) {
      text_editor::sms_reset(sms);
      name_insert_char(name, len, cursor, ' ', capacity);
      shift = text_editor::Shift::NONE;
      continue;
    }
    if(digit >= 0) {
      text_editor::sms_reset(sms);
      name_insert_char(name, len, cursor, (char) ('0' + digit), capacity);
      shift = text_editor::Shift::NONE;
      continue;
    }

    text_editor::sms_reset(sms);
    shift = text_editor::Shift::NONE;
  }
}

static bool rename_entry(const program_store::Entry& entry) {
  char name[program_store::NAME_SIZE];
  bounded_string::copy(name, entry.name);

  if(!input_entry_name(name, sizeof(name), NamePrompt::RENAME)) return false;
  if(strncmp(name, entry.name, program_store::NAME_SIZE) == 0) return true;

  const bool ok = program_store::move_rename(entry.id, entry.parent_id, name);
  show_message(ok ? "Renamed" : "Rename error", ok ? "Переимен." : "Ошибка", name, name);
  delay(700);
  return ok;
}

static bool create_directory(u16 parent_id) {
  char name[program_store::NAME_SIZE] = "Folder";
  if(!input_entry_name(name, sizeof(name), NamePrompt::NEW_DIRECTORY)) return false;

  const int count = program_store::child_count(parent_id);
  for(int i = 0; i < count; i++) {
    program_store::Entry child;
    if(program_store::child(parent_id, i, child) &&
       child.kind == program_store::NodeKind::DIRECTORY &&
       strncmp(child.name, name, program_store::NAME_SIZE) == 0) {
      show_message("Name exists", "Уже есть", name, name);
      delay(900);
      return false;
    }
  }

  u16 id = program_store::INVALID_ID;
  const bool ok = program_store::create_directory(parent_id, name,
                                                    program_store::INVALID_ID,
                                                    &id);
  show_message(ok ? "Folder created" : "Create error",
               ok ? "Папка создана" : "Ошибка",
               name, name);
  delay(700);
  return ok;
}

static bool move_entry(const program_store::Entry& entry) {
  const u16 forbidden = entry.kind == program_store::NodeKind::DIRECTORY
      ? entry.id : program_store::INVALID_ID;
  u16 destination = entry.parent_id;
  if(!program_store_choose_directory(entry.parent_id, forbidden,
                                     destination)) return false;
  if(destination == entry.parent_id) return true;
  const bool ok = program_store::move_rename(entry.id, destination,
                                             entry.name);
  show_message(ok ? "Moved" : "Move error",
               ok ? "Перемещено" : "Ошибка", entry.name, entry.name);
  delay(700);
  return ok;
}

enum class DialogItemKind : u8 {
  THIS_DIRECTORY,
  NEW_FILE,
  NEW_DIRECTORY,
  ENTRY
};

struct DialogItem {
  DialogItemKind kind;
  program_store::Entry entry;
};

static int dialog_pseudo_count(DialogMode mode, bool allow_new) {
  if(mode == DialogMode::DIRECTORY) return 2; // Этот каталог, новый каталог
  return allow_new ? 2 : 0;                  // Новый файл, новый каталог
}

static bool dialog_entry_visible(const program_store::Entry& entry,
                                 DialogMode mode,
                                 program_store::ProgramType type,
                                 u16 forbidden_tree) {
  if(entry.kind == program_store::NodeKind::DIRECTORY) {
    return forbidden_tree == program_store::INVALID_ID ||
           !storage_path::directory_within(entry.id, forbidden_tree);
  }
  return mode == DialogMode::FILE &&
         entry.kind == program_store::NodeKind::FILE && entry.type == type;
}

static int dialog_count(u16 directory_id, DialogMode mode,
                        program_store::ProgramType type, bool allow_new,
                        u16 forbidden_tree) {
  int result = dialog_pseudo_count(mode, allow_new);
  const int children = program_store::child_count(directory_id);
  for(int index = 0; index < children; index++) {
    program_store::Entry entry;
    if(program_store::child(directory_id, index, entry) &&
       dialog_entry_visible(entry, mode, type, forbidden_tree)) result++;
  }
  return result;
}

static bool dialog_item_at(u16 directory_id, DialogMode mode,
                           program_store::ProgramType type, bool allow_new,
                           u16 forbidden_tree, int wanted,
                           DialogItem& out) {
  const int pseudo = dialog_pseudo_count(mode, allow_new);
  if(wanted < 0) return false;
  if(wanted < pseudo) {
    memset(&out.entry, 0, sizeof(out.entry));
    if(mode == DialogMode::DIRECTORY) {
      out.kind = wanted == 0 ? DialogItemKind::THIS_DIRECTORY
                             : DialogItemKind::NEW_DIRECTORY;
    } else {
      out.kind = wanted == 0 ? DialogItemKind::NEW_FILE
                             : DialogItemKind::NEW_DIRECTORY;
    }
    return true;
  }

  int visible = pseudo;
  const int children = program_store::child_count(directory_id);
  for(int index = 0; index < children; index++) {
    program_store::Entry entry;
    if(!program_store::child(directory_id, index, entry)) return false;
    if(!dialog_entry_visible(entry, mode, type, forbidden_tree)) continue;
    if(visible++ != wanted) continue;
    out.kind = DialogItemKind::ENTRY;
    out.entry = entry;
    return true;
  }
  return false;
}

static const char* dialog_item_name(const DialogItem& item) {
  switch(item.kind) {
    case DialogItemKind::THIS_DIRECTORY:
      return library_mk61::text("This folder", "Эта папка");
    case DialogItemKind::NEW_FILE:
      return library_mk61::text("New file", "Новый файл");
    case DialogItemKind::NEW_DIRECTORY:
      return library_mk61::text("New folder", "Новая папка");
    case DialogItemKind::ENTRY: return item.entry.name;
  }
  return "?";
}

static char dialog_item_marker(const DialogItem& item) {
  switch(item.kind) {
    case DialogItemKind::THIS_DIRECTORY: return '*';
    case DialogItemKind::NEW_FILE:
    case DialogItemKind::NEW_DIRECTORY: return '+';
    case DialogItemKind::ENTRY:
      return item.entry.kind == program_store::NodeKind::DIRECTORY
          ? '/' : type_marker(item.entry.type);
  }
  return '?';
}

static void draw_dialog_row(const lcd_ru::font_map_t& map, u8 row,
                            const DialogItem& item, u8 scroll_offset) {
  draw_explorer_name(map, dialog_item_name(item), row, scroll_offset);
  main_lcd().setCursor(explorer_type_col(), row);
  main_lcd().write((u8) dialog_item_marker(item));
}

static u16 draw_storage_dialog(u16 directory_id, DialogMode mode,
                               program_store::ProgramType type,
                               bool allow_new, u16 forbidden_tree,
                               int active, int count, ExplorerScroll& scroll,
                               u8& cursor_row) {
  cursor_row = EXPLORER_NO_CURSOR_ROW;
  explorer_cursor_off();
  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();
  if(count <= 0) {
    explorer_scroll_reset(scroll);
    print_localized_line(0, "Folder empty", "Папка пуста");
    print_localized_line(1, "ESC: parent", "ESC: наверх");
    return 0;
  }

  const int rows = main_lcd().rows();
  const int visible = count < rows ? count : rows;
  int top = active - visible + 1;
  if(top < 0) top = 0;
  if(top > count - visible) top = count - visible;

  DialogItem active_item;
  const u32 now = millis();
  u16 timeout = 0;
  if(dialog_item_at(directory_id, mode, type, allow_new, forbidden_tree,
                    active, active_item)) {
    const char* name = dialog_item_name(active_item);
    const u8 width = explorer_name_width();
    explorer_scroll_track(scroll, active, name, width, now);
    timeout = explorer_scroll_timeout(scroll, name, width, now);
  } else {
    explorer_scroll_reset(scroll);
  }

  lcd_ru::font_map_t name_map = {{0}, 0, false};
  for(int row = 0; row < visible; row++) {
    DialogItem item;
    const int index = top + row;
    if(!dialog_item_at(directory_id, mode, type, allow_new, forbidden_tree,
                       index, item)) continue;
    char window[program_store::NAME_SIZE];
    explorer_name_window(dialog_item_name(item),
                         index == active ? scroll.offset : 0,
                         explorer_name_width(), true, window,
                         sizeof(window));
    lcd_ru::scan_text(name_map, window, explorer_name_width());
  }
  lcd_ru::load_custom_font(name_map);

  for(int row = 0; row < visible; row++) {
    DialogItem item;
    const int index = top + row;
    if(!dialog_item_at(directory_id, mode, type, allow_new, forbidden_tree,
                       index, item)) {
      print_line((u8) row, "?");
      continue;
    }
    const bool selected = index == active;
    draw_dialog_row(name_map, (u8) row, item,
                    selected ? scroll.offset : 0);
    if(selected) cursor_row = (u8) row;
  }
  for(int row = visible; row < rows; row++) print_line((u8) row, "");
  return timeout;
}

static ProgramStoreFileDialogResult run_storage_dialog(
    DialogMode mode, program_store::ProgramType type, u16 start_directory,
    bool allow_new, u16 forbidden_tree, program_store::Entry& out_entry,
    u16& out_directory) {
  u16 directory_id = start_directory;
  if(directory_id != program_store::ROOT_ID) {
    program_store::Entry directory;
    if(!program_store::entry_by_id(directory_id, directory) ||
       directory.kind != program_store::NodeKind::DIRECTORY) {
      directory_id = program_store::ROOT_ID;
    }
  }

  int active = 0;
  ExplorerScroll scroll;
  explorer_scroll_reset(scroll);
  wait_all_keys_released();
  while(true) {
    int count = dialog_count(directory_id, mode, type, allow_new,
                             forbidden_tree);
    if(active >= count) active = count > 0 ? count - 1 : 0;
    u8 cursor_row = EXPLORER_NO_CURSOR_ROW;
    const u16 timeout = draw_storage_dialog(directory_id, mode, type,
        allow_new, forbidden_tree, active, count, scroll, cursor_row);
    const i32 key = wait_explorer_key(true, timeout, cursor_row);
    if(key == EXPLORER_KEY_TICK || key == EXPLORER_KEY_REDRAW) continue;
    if(key == EXPLORER_KEY_DOWN && count > 0) {
      active = (active + 1) % count;
      explorer_scroll_reset(scroll);
      continue;
    }
    if(key == EXPLORER_KEY_UP && count > 0) {
      active = active > 0 ? active - 1 : count - 1;
      explorer_scroll_reset(scroll);
      continue;
    }
    if(key == EXPLORER_KEY_ESC) {
      if(directory_id == program_store::ROOT_ID) {
        explorer_cursor_off();
        return ProgramStoreFileDialogResult::CANCELLED;
      }
      program_store::Entry directory;
      if(!program_store::entry_by_id(directory_id, directory)) {
        directory_id = program_store::ROOT_ID;
      } else {
        directory_id = directory.parent_id;
      }
      active = 0;
      explorer_scroll_reset(scroll);
      continue;
    }
    if((key != EXPLORER_KEY_OK && key != EXPLORER_KEY_LONG_OK) ||
       count <= 0) continue;

    DialogItem item;
    if(!dialog_item_at(directory_id, mode, type, allow_new, forbidden_tree,
                       active, item)) continue;
    if(item.kind == DialogItemKind::THIS_DIRECTORY) {
      out_directory = directory_id;
      explorer_cursor_off();
      return ProgramStoreFileDialogResult::EXISTING;
    }
    if(item.kind == DialogItemKind::NEW_FILE) {
      out_directory = directory_id;
      explorer_cursor_off();
      return ProgramStoreFileDialogResult::NEW_FILE;
    }
    if(item.kind == DialogItemKind::NEW_DIRECTORY) {
      explorer_cursor_off();
      (void) create_directory(directory_id);
      active = 0;
      explorer_scroll_reset(scroll);
      continue;
    }
    if(item.entry.kind == program_store::NodeKind::DIRECTORY) {
      directory_id = item.entry.id;
      active = 0;
      explorer_scroll_reset(scroll);
      continue;
    }
    out_entry = item.entry;
    out_directory = directory_id;
    explorer_cursor_off();
    return ProgramStoreFileDialogResult::EXISTING;
  }
}

static void explorer_search_reset(ExplorerSearch& search) {
  search.text[0] = 0;
  search.len = 0;
  search.shift = text_editor::Shift::NONE;
  text_editor::sms_reset(search.sms);
}

static void explorer_search_expire_sms(ExplorerSearch& search, u32 now) {
  if(text_editor::sms_expired(search.sms, now)) text_editor::sms_reset(search.sms);
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
  const int digit = text_editor::digit_from_key(key);

  if(!shifted_key && search.sms.active) {
    u16 cursor = search.len;
    if(text_editor::sms_key_is_letters(key)) {
      text_editor::sms_tap(search.text, search.len, cursor, program_store::NAME_SIZE, search.sms, key, now);
      return true;
    }
    if(text_editor::sms_key_is_space(key)) {
      text_editor::sms_reset(search.sms);
      explorer_search_insert_char(search, ' ');
      return true;
    }
    if(digit == 0) {
      text_editor::sms_reset(search.sms);
      return true;
    }
    if(key == KEY_PP) {
      text_editor::sms_reset(search.sms);
      explorer_search_insert_char(search, ' ');
      return true;
    }
    text_editor::sms_reset(search.sms);
  }

  if(!shifted_key && (key == KEY_K || key == KEY_ALPHA)) {
    search.shift = (key == KEY_K) ? text_editor::Shift::K : text_editor::Shift::ALPHA;
    text_editor::sms_reset(search.sms);
    return true;
  }

  u16 cursor = search.len;
  if(key == KEY_CX &&
      (search.shift == text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
    text_editor::sms_reset(search.sms);
    explorer_search_reset(search);
    search.shift = text_editor::Shift::NONE;
    return true;
  }
  if((key == EXPLORER_KEY_UP || key == (i32) KEY_LEFT || key == (i32) KEY_LEFT_PRESS) &&
      (search.shift == text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
    text_editor::sms_reset(search.sms);
    search.shift = text_editor::Shift::NONE;
    return true;
  }

  if(search.shift == text_editor::Shift::ALPHA && digit >= 0) {
    const char* symbol = text_editor::symbol_for_digit_key(key);
    if(symbol != NULL && symbol[0] != 0) explorer_search_insert_char(search, symbol[0]);
    search.shift = text_editor::Shift::NONE;
    text_editor::sms_reset(search.sms);
    return true;
  }
  if(search.shift == text_editor::Shift::ALPHA) {
    search.shift = text_editor::Shift::NONE;
    text_editor::sms_reset(search.sms);
    return true;
  }
  if(search.shift == text_editor::Shift::K && text_editor::sms_key_is_letters(key)) {
    text_editor::sms_tap(search.text, search.len, cursor, program_store::NAME_SIZE, search.sms, key, now);
    search.shift = text_editor::Shift::NONE;
    return true;
  }
  if(search.shift == text_editor::Shift::K && text_editor::sms_key_is_space(key)) {
    text_editor::sms_reset(search.sms);
    explorer_search_insert_char(search, ' ');
    search.shift = text_editor::Shift::NONE;
    return true;
  }
  if(search.shift == text_editor::Shift::K) {
    const char* punctuation = text_editor::kshift_text_for_key(key);
    text_editor::sms_reset(search.sms);
    if(punctuation != NULL && punctuation[0] != 0 && punctuation[1] == 0) {
      explorer_search_insert_char(search, punctuation[0]);
    }
    search.shift = text_editor::Shift::NONE;
    return true;
  }
  if(!shifted_key && key == KEY_CX) {
    text_editor::sms_reset(search.sms);
    explorer_search_backspace(search);
    return true;
  }

  if(key == KEY_PP) {
    text_editor::sms_reset(search.sms);
    explorer_search_insert_char(search, ' ');
    search.shift = text_editor::Shift::NONE;
    return true;
  }
  if(digit >= 0) {
    text_editor::sms_reset(search.sms);
    explorer_search_insert_char(search, (char) ('0' + digit));
    search.shift = text_editor::Shift::NONE;
    return true;
  }

  search.shift = text_editor::Shift::NONE;
  return false;
}

static bool entry_can_edit(const program_store::Entry& entry) {
  if(entry.kind != program_store::NodeKind::FILE) return false;
  switch(entry.type) {
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

static bool entry_can_load(const program_store::Entry& entry) {
  return entry.kind == program_store::NodeKind::FILE &&
         entry.type == program_store::ProgramType::MK61;
}

static bool entry_can_run(const program_store::Entry& entry) {
  if(entry.kind != program_store::NodeKind::FILE) return false;
  switch(entry.type) {
#if MK61_ENABLE_FOCAL
    case program_store::ProgramType::FOCAL:
      return true;
#endif
#if MK61_ENABLE_TINYBASIC
    case program_store::ProgramType::TINYBASIC:
      return true;
#endif
#if defined(MK61_DISPLAY_UC1609)
    case program_store::ProgramType::FONT:
      return true;
#endif
    default:
      return false;
  }
}

static int item_menu_actions(const program_store::Entry& entry, ItemMenuAction* actions, int capacity) {
  int count = 0;
  if(entry.kind == program_store::NodeKind::FILE) {
    if(entry_can_load(entry) && count < capacity) actions[count++] = ItemMenuAction::LOAD;
    if(entry_can_run(entry) && count < capacity) actions[count++] = ItemMenuAction::RUN;
    if(count < capacity) actions[count++] = ItemMenuAction::VIEW;
    if(entry_can_edit(entry) && count < capacity) actions[count++] = ItemMenuAction::EDIT;
  }
  if(count < capacity) actions[count++] = ItemMenuAction::NEW_DIRECTORY;
  if(count < capacity) actions[count++] = ItemMenuAction::RENAME;
  if(count < capacity) actions[count++] = ItemMenuAction::MOVE;
  if(count < capacity) actions[count++] = ItemMenuAction::DELETE;
  return count;
}

static const char* item_menu_text(ItemMenuAction action, bool ru) {
  switch(action) {
    case ItemMenuAction::LOAD:
      return ru ? "Загрузить" : "Load";
    case ItemMenuAction::RUN:
      return ru ? "Запуск" : "Run";
    case ItemMenuAction::VIEW:
      return ru ? "Просмотр" : "View";
    case ItemMenuAction::EDIT:
      return ru ? "Редактировать" : "Edit";
    case ItemMenuAction::NEW_DIRECTORY:
      return ru ? "Новая папка" : "New folder";
    case ItemMenuAction::RENAME:
      return ru ? "Переименовать" : "Rename";
    case ItemMenuAction::MOVE:
      return ru ? "Переместить" : "Move";
    case ItemMenuAction::DELETE:
      return ru ? "Удалить" : "Delete";
  }
  return "";
}

static void draw_item_menu(const program_store::Entry& entry, int active) {
  ItemMenuAction actions[ITEM_MENU_ACTION_CAPACITY];
  const int count = item_menu_actions(entry, actions,
                                      ITEM_MENU_ACTION_CAPACITY);
  const int display_rows = main_lcd().rows();
  const int visible = (count < display_rows) ? count : display_rows;
  int top = active - visible + 1;
  if(top < 0) top = 0;
  if(top > count - visible) top = count - visible;

  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();

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
  const bool ok = entry.type == program_store::ProgramType::FONT
    ? apply_font_entry(entry)
    : OpenStoredEntry(entry);
  if(!ok) {
    show_message("Run error", "Ошибка запуска", entry.name, entry.name);
    delay(900);
  } else if(entry.type == program_store::ProgramType::FONT) {
    show_message("Font applied", "Шрифт применен", entry.name, entry.name);
    delay(700);
  }
  return ok;
}

static bool load_mk61_entry(const program_store::Entry& entry) {
  if(!entry_can_load(entry) || !LoadProgram(entry.id)) {
    show_message("Load error", "Ошибка чтения", entry.name, entry.name);
    delay(900);
    return false;
  }
  current_mk61_entry_id = entry.id;
  current_mk61_directory_id = entry.parent_id;
  return true;
}

static void edit_entry(const program_store::Entry& entry) {
  bool ok = false;
  switch(entry.type) {
#if MK61_ENABLE_FOCAL
    case program_store::ProgramType::FOCAL:
      ok = EditFocalProgram(entry.id);
      break;
#endif
#if MK61_ENABLE_TINYBASIC
    case program_store::ProgramType::TINYBASIC:
      ok = EditTinyBasicProgram(entry.id);
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

static bool explorer_item_menu(u16 directory_id,
                               const program_store::Entry& entry) {
  ItemMenuAction actions[ITEM_MENU_ACTION_CAPACITY];
  const int count = item_menu_actions(entry, actions,
                                      ITEM_MENU_ACTION_CAPACITY);
  int active = 0;
  bool wait_initial_ok_release = true;
  while(true) {
    draw_item_menu(entry, active);
    if(wait_initial_ok_release) {
      if(!wait_ok_release()) continue;
      wait_initial_ok_release = false;
      // Первая отрисовка может произойти до классификации терминального нажатия
      // или отпускания удерживаемой двоичной клавиши. Повторная отрисовка не даст
      // восстановленному физическому LCD сохранить непредставимые символы Unicode.
      draw_item_menu(entry, active);
    }
    const i32 key = wait_explorer_key(false);
    if(key == EXPLORER_KEY_REDRAW) continue;
    if(key == EXPLORER_KEY_ESC) return action::MENU_BACK;
    if(key == EXPLORER_KEY_UP) active = (active <= 0) ? count - 1 : active - 1;
    if(key == EXPLORER_KEY_DOWN) active = (active + 1) % count;
    if(key == EXPLORER_KEY_OK) {
      switch(actions[active]) {
        case ItemMenuAction::LOAD:
          if(load_mk61_entry(entry)) return action::MENU_EXIT;
          return action::MENU_BACK;
        case ItemMenuAction::RUN:
          if(run_entry(entry)) return action::MENU_EXIT;
          return action::MENU_BACK;
        case ItemMenuAction::VIEW:
          view_entry(entry);
          break;
        case ItemMenuAction::EDIT:
          edit_entry(entry);
          break;
        case ItemMenuAction::NEW_DIRECTORY:
          create_directory(directory_id);
          break;
        case ItemMenuAction::RENAME:
          rename_entry(entry);
          break;
        case ItemMenuAction::MOVE:
          move_entry(entry);
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

static bool focal_action(void) {
  FOCAL_menu_select();
  return action::MENU_BACK;
}

static bool m61_load_action(void) {
  program_store::Entry entry = {};
  u16 directory = current_mk61_directory_id;
  const ProgramStoreFileDialogResult result = program_store_choose_file(
      program_store::ProgramType::MK61, directory, false, entry, directory);
  if(result != ProgramStoreFileDialogResult::EXISTING) {
    return action::MENU_BACK;
  }
  return load_mk61_entry(entry) ? action::MENU_EXIT : action::MENU_BACK;
}

static bool m61_save_action(void) {
  char name[program_store::NAME_SIZE] = "Program";
  u16 directory = current_mk61_directory_id;
  program_store::Entry current = {};
  if(current_mk61_entry_id != program_store::INVALID_ID &&
     program_store::entry_by_id(current_mk61_entry_id, current) &&
     current.kind == program_store::NodeKind::FILE &&
     current.type == program_store::ProgramType::MK61) {
    bounded_string::copy(name, current.name);
    directory = current.parent_id;
  }

  if(!program_store_choose_save_target(program_store::ProgramType::MK61,
                                       directory, name, sizeof(name),
                                       directory)) {
    return action::MENU_BACK;
  }
  if(!StoreProgram(directory, name)) {
    show_message("Save error", "Ошибка записи", name, name);
    delay(900);
    return action::MENU_BACK;
  }

  program_store::Entry saved = {};
  if(storage_path::resolve_file(directory, name,
                               program_store::ProgramType::MK61, saved) ==
     storage_path::Status::OK) {
    current_mk61_entry_id = saved.id;
  } else {
    current_mk61_entry_id = program_store::INVALID_ID;
  }
  current_mk61_directory_id = directory;
  show_message("Program saved", "Программа сохр.", name, name);
  delay(700);
  return action::MENU_EXIT;
}

static constexpr t_punct M61_LOAD_PUNCT = {
    .size = 13, .action = &m61_load_action, .text = "Open M61 file"};
static constexpr t_punct M61_SAVE_PUNCT = {
    .size = 13, .action = &m61_save_action, .text = "Save M61 file"};
static constexpr t_punct RU_M61_LOAD_PUNCT = {
    .size = 15, .action = &m61_load_action, .text = "Открыть МК-61"};
static constexpr t_punct RU_M61_SAVE_PUNCT = {
    .size = 15, .action = &m61_save_action, .text = "Сохранить МК-61"};

static bool m61_storage_action(void) {
  t_punct* items[] = {
    (t_punct*) (library_mk61::language_is_ru()
        ? &RU_M61_LOAD_PUNCT : &M61_LOAD_PUNCT),
    (t_punct*) (library_mk61::language_is_ru()
        ? &RU_M61_SAVE_PUNCT : &M61_SAVE_PUNCT),
  };
  class_menu menu(items, sizeof(items) / sizeof(items[0]));
  return menu.select();
}

static constexpr t_punct EXPLORER_PUNCT = {.size = 8, .action = &explorer_action, .text = "Explorer"};
static constexpr t_punct RU_EXPLORER_PUNCT = {.size = 15, .action = &explorer_action, .text = "Проводник"};
static constexpr t_punct M61_STORAGE_PUNCT = {.size = 9, .action = &m61_storage_action, .text = "M61 files"};
static constexpr t_punct RU_M61_STORAGE_PUNCT = {.size = 15, .action = &m61_storage_action, .text = "Файлы МК-61"};

#if MK61_ENABLE_USB_SCREEN
static constexpr t_punct USB_SCREEN_DEV_PUNCT = {
    .size = 10, .action = &UsbScreenMode, .text = "USB Screen"};
static constexpr t_punct RU_USB_SCREEN_DEV_PUNCT = {
    .size = 15, .action = &UsbScreenMode, .text = "USB-экран"};
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

} // анонимное пространство имён

ProgramStoreFileDialogResult program_store_choose_file(
    program_store::ProgramType type, u16 start_directory, bool allow_new,
    program_store::Entry& out_entry, u16& out_directory) {
  return run_storage_dialog(DialogMode::FILE, type, start_directory,
                            allow_new, program_store::INVALID_ID, out_entry,
                            out_directory);
}

bool program_store_choose_directory(u16 start_directory, u16 forbidden_tree,
                                    u16& out_directory) {
  program_store::Entry unused = {};
  return run_storage_dialog(DialogMode::DIRECTORY,
      program_store::ProgramType::MK61, start_directory, false,
      forbidden_tree, unused, out_directory) ==
      ProgramStoreFileDialogResult::EXISTING;
}

bool program_store_choose_save_target(program_store::ProgramType type,
                                      u16 start_directory, char* name,
                                      usize name_capacity,
                                      u16& out_directory) {
  (void) type;
  if(name == NULL || name_capacity < 2 ||
     name_capacity > program_store::NAME_SIZE) return false;
  u16 directory = start_directory;
  if(!program_store_choose_directory(start_directory,
                                     program_store::INVALID_ID,
                                     directory)) return false;

  char candidate[program_store::NAME_SIZE];
  const usize length = text_editor::bounded_length(name, name_capacity);
  if(length >= name_capacity) return false;
  memcpy(candidate, name, length + 1);
  while(true) {
    if(!input_entry_name(candidate, name_capacity, NamePrompt::SAVE)) {
      return false;
    }
    if(program_store::basename_valid(candidate)) break;
    show_message("Invalid name", "Ошибка имени", candidate, candidate);
    delay(900);
  }
  memcpy(name, candidate, strlen(candidate) + 1);
  out_directory = directory;
  return true;
}

bool program_store_explorer_select(void) {
  u16 directory_id = program_store::ROOT_ID;
  int active = 0;
  ExplorerSearch search;
  ExplorerScroll scroll;
  explorer_search_reset(search);
  explorer_scroll_reset(scroll);
  wait_all_keys_released();

  while(true) {
    explorer_search_expire_sms(search, millis());
    const int count = explorer_count(directory_id);
    if(count <= 0) {
      draw_explorer(directory_id, 0, scroll);
      const i32 key = wait_explorer_key(false);
      if(key == EXPLORER_KEY_REDRAW) continue;
      if(key == EXPLORER_KEY_ESC) {
        if(directory_id != program_store::ROOT_ID) {
          program_store::Entry directory;
          if(program_store::entry_by_id(directory_id, directory)) {
            directory_id = directory.parent_id;
            active = 0;
            explorer_search_reset(search);
            explorer_scroll_reset(scroll);
            continue;
          }
        }
        explorer_cursor_off();
        return action::MENU_BACK;
      }
      if(key == EXPLORER_KEY_OK || key == EXPLORER_KEY_LONG_OK) {
        create_directory(directory_id);
        explorer_search_reset(search);
        explorer_scroll_reset(scroll);
        continue;
      }
      explorer_search_handle_key(search, key);
      continue;
    }
    if(active >= count) active = count - 1;
    if(active < 0) active = 0;
    if(search_active(search.text) &&
       !entry_matches_search(directory_id, active, search.text)) {
      const int first = first_matching_index(directory_id, search.text);
      if(first >= 0) active = first;
    }

    u8 cursor_row = EXPLORER_NO_CURSOR_ROW;
    const u16 scroll_timeout = draw_explorer(directory_id, active, scroll,
                                              search.text, &cursor_row);
    const i32 key = wait_explorer_key(true, scroll_timeout, cursor_row);
    if(key == EXPLORER_KEY_TICK || key == EXPLORER_KEY_REDRAW) continue;
    if(key == EXPLORER_KEY_ESC) {
      if(search_active(search.text)) {
        explorer_search_reset(search);
        explorer_scroll_reset(scroll);
        continue;
      }
      if(directory_id != program_store::ROOT_ID) {
        program_store::Entry directory;
        if(program_store::entry_by_id(directory_id, directory)) {
          directory_id = directory.parent_id;
          active = 0;
          explorer_search_reset(search);
          explorer_scroll_reset(scroll);
          continue;
        }
      }
      explorer_cursor_off();
      return action::MENU_BACK;
    }
    if(explorer_search_handle_key(search, key)) {
      const int first = first_matching_index(directory_id, search.text);
      if(first >= 0) active = first;
      explorer_scroll_reset(scroll);
      continue;
    }

    const int visible_count = matching_entry_count(directory_id, search.text);
    if(key == EXPLORER_KEY_DOWN && visible_count > 0) {
      active = next_matching_index(directory_id, active, search.text);
      explorer_scroll_reset(scroll);
    } else if(key == EXPLORER_KEY_UP && visible_count > 0) {
      active = previous_matching_index(directory_id, active, search.text);
      explorer_scroll_reset(scroll);
    }
    else if(key == EXPLORER_KEY_OK) {
      program_store::Entry entry;
      if(visible_count > 0 && explorer_entry(directory_id, active, entry)) {
        explorer_cursor_off();
        if(entry.kind == program_store::NodeKind::DIRECTORY) {
          directory_id = entry.id;
          active = 0;
          explorer_search_reset(search);
          explorer_scroll_reset(scroll);
        } else if(entry_can_load(entry)) {
          if(load_mk61_entry(entry)) return action::MENU_EXIT;
        } else if(entry_can_run(entry)) {
          if(run_entry(entry)) return action::MENU_EXIT;
        } else {
          view_entry(entry);
        }
      }
    } else if(key == EXPLORER_KEY_LONG_OK) {
      program_store::Entry entry;
      if(visible_count > 0 && explorer_entry(directory_id, active, entry)) {
        explorer_cursor_off();
        if(explorer_item_menu(directory_id, entry) == action::MENU_EXIT) {
          return action::MENU_EXIT;
        }
      }
    }
  }
}

bool program_store_view_entry(const program_store::Entry& entry) {
  if(entry.kind != program_store::NodeKind::FILE) return false;
  return view_entry(entry);
}

bool program_store_view_entry(program_store::ProgramType type, const char* name) {
  program_store::Entry entry;
  if(!entry_by_type_name(type, name, entry)) return false;
  return program_store_view_entry(entry);
}

bool program_store_apply_font(const program_store::Entry& entry) {
  return entry.kind == program_store::NodeKind::FILE &&
         entry.type == program_store::ProgramType::FONT &&
         apply_font_entry(entry);
}

bool program_store_apply_font(const char* name) {
  program_store::Entry entry;
  if(!entry_by_type_name(program_store::ProgramType::FONT, name, entry)) return false;
  return program_store_apply_font(entry);
}

bool program_store_suspend_font_for_usb(void) {
#if defined(MK61_DISPLAY_UC1609)
  if(!main_lcd().externalFontActive()) {
    return true;
  }
  if(applied_font_id == program_store::INVALID_ID ||
     !main_lcd().suspendExternalFontForUsb()) return false;
  applied_font_suspended = true;
#endif
  return true;
}

void program_store_restore_font_after_usb(void) {
#if defined(MK61_DISPLAY_UC1609)
  if(!applied_font_suspended) return;
  applied_font_suspended = false;
  program_store::Entry entry;
  if(!program_store::entry_by_id(applied_font_id, entry) ||
     entry.type != program_store::ProgramType::FONT ||
     !apply_font_entry(entry)) {
    applied_font_id = program_store::INVALID_ID;
    main_lcd().useBuiltinFont();
    library_mk61::set_display_text_profile(main_lcd().textProfile());
  }
#endif
}

bool development_select(void) {
  t_punct* items[] = {
    (t_punct*) (library_mk61::language_is_ru() ? &RU_EXPLORER_PUNCT : &EXPLORER_PUNCT),
    (t_punct*) (library_mk61::language_is_ru() ? &RU_M61_STORAGE_PUNCT : &M61_STORAGE_PUNCT),
#if MK61_ENABLE_FOCAL
    (t_punct*) (library_mk61::language_is_ru() ? &RU_FOCAL_DEV_PUNCT : &FOCAL_DEV_PUNCT),
#endif
#if MK61_ENABLE_TINYBASIC
    (t_punct*) (library_mk61::language_is_ru() ? &RU_TINYBASIC_DEV_PUNCT : &TINYBASIC_DEV_PUNCT),
#endif
#if MK61_ENABLE_USB_SCREEN
    (t_punct*) (library_mk61::language_is_ru()
        ? &RU_USB_SCREEN_DEV_PUNCT : &USB_SCREEN_DEV_PUNCT),
#endif
  };

  class_menu menu = class_menu(items, sizeof(items) / sizeof(items[0]));
  return menu.select();
}
