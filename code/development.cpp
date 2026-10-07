#include "development.hpp"

#include "Arduino.h"
#include "bounded_string.hpp"
#include "config.h"
#include "loadable_module_runtime.hpp"
#include "explorer_ui.hpp"
#include "explorer_label.hpp"
#include "exclusive_buffer.hpp"
#include "file_handlers.hpp"
#include "cross_hal.h"
#include "focal.hpp"
#include "fmk_font.hpp"
#include "setup_ui.hpp"
#include "tinybasic.hpp"
#include "keyboard.h"
#include "lcd_gui.hpp"
#include "lcd_ru.hpp"
#include "language_workspace.hpp"
#include "menu.hpp"
#include "mk8_literal.hpp"
#include "program_store.hpp"
#include "shared_scratch.hpp"
#include "storage_path.hpp"
#include "text_editor.hpp"
#include "tools.hpp"
#include "ui_font_catalog.hpp"
#include "m8_view.hpp"

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
static constexpr u16 FILE_DIALOG_SCROLL_START_MS = 900;
static constexpr u16 FILE_DIALOG_SCROLL_STEP_MS = 450;
static constexpr u16 FILE_DIALOG_SCROLL_EDGE_MS = 900;
static constexpr u8 FILE_DIALOG_NAME_COL = 1;

static u16 current_mk61_entry_id = program_store::INVALID_ID;
static u16 current_mk61_directory_id = program_store::ROOT_ID;

#if defined(MK61_DISPLAY_UC1609)
enum class AppliedFontRole : u8 { TEXT, UI };
static u16 applied_font_id = program_store::INVALID_ID;
static AppliedFontRole applied_font_role = AppliedFontRole::TEXT;
static u8 applied_ui_height = 0;
#if MK61_PROPORTIONAL_UI_FONTS
static u32 applied_ui_key = 0;
#endif
static bool applied_font_suspended = false;

struct AppliedFontSnapshot {
  u16 id;
  AppliedFontRole role;
  u8 ui_height;
#if MK61_PROPORTIONAL_UI_FONTS
  u32 ui_key;
  u8 ui_family;
  u8 ui_size;
  bool ui_context;
#endif
  lcd_display::TextProfile text_profile;
  bool external;
};

struct TextFontSession {
  bool active;
  bool override_loaded;
  AppliedFontSnapshot original;
};

static TextFontSession text_font_session = {};
#endif

static_assert(shared_scratch::SIZE >= program_store::MAX_IMAGE1_SIZE,
              "shared scratch too small for explorer view");
static_assert(program_store::MAX_FONT_SIZE <= fmk::MAX_FILE_SIZE,
              "storage must not accept fonts the parser cannot validate");


enum class NamePrompt : u8 {
  RENAME,
  NEW_DIRECTORY,
  SAVE
};

enum class DialogMode : u8 {
  FILE,
  DIRECTORY
};


struct FileDialogScroll {
  int active;
  char name[explorer_label::SIZE];
  u8 offset;
  i8 direction;
  u32 next_ms;
};

static const char* type_label(program_store::ProgramType type) {
  return program_store::type_magic_text(type);
}

static void print_line(u8 row, const char* text) {
#if MK61_PROPORTIONAL_UI_FONTS
  if(main_lcd().uiTextActive()) { main_lcd().printUiLine(row, text); return; }
#endif
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
  const i32 scan_code = kbd::poll_event().code();
  if(scan_code < 0) return -1;

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

    (void) kbd::scan();

    // Терминальные команды `kbd` — это завершённые нажатия: в отличие от
    // физических и двоичных USB-клавиш, у них намеренно нет отдельного отпускания.
    if(!kbd::is_key_pressed(KEY_OK)) {
      kbd::clear_hold_key();
      return true;
    }
    delay(10);
  }
}

static void wait_input_handoff(void) {
  while(kbd::handoff_pending()) {
    idle_main_process();
    (void) kbd::scan();
    delay(10);
  }
}

static bool explorer_time_reached(u32 now, u32 target) {
  return (i32) (now - target) >= 0;
}

static void explorer_cursor_off(void) {
  if(main_lcd().supportsCursor()) main_lcd().cursorOff();
}

static i32 wait_explorer_key(bool allow_long_ok, u16 tick_ms = 0) {
  bool ok_down = false;
  u32 long_ok_at = 0;
  const u32 tick_at = tick_ms == 0 ? 0 : millis() + tick_ms;
  const u32 display_mode_revision = main_lcd().displayModeRevision();

  while(true) {
    idle_main_process();
    if(main_lcd().displayModeRevision() != display_mode_revision) {
      explorer_cursor_off();
      return EXPLORER_KEY_REDRAW;
    }

    const u32 now = millis();
    if(tick_ms != 0 && !ok_down && explorer_time_reached(now, tick_at)) return EXPLORER_KEY_TICK;
    if(allow_long_ok && ok_down && explorer_time_reached(now, long_ok_at)) {
      kbd::handoff(kbd::Event(KEY_OK));
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
    if(code == (i32) KEY_ESC) {
      kbd::handoff(kbd::Event(scan_code));
      return EXPLORER_KEY_ESC;
    }
    if(code == (i32) KEY_RIGHT || code == (i32) KEY_SHG_RIGHT_PRESS) return EXPLORER_KEY_DOWN;
    if(code == (i32) KEY_LEFT || code == (i32) KEY_SHG_LEFT_PRESS) return EXPLORER_KEY_UP;
    return code;
  }
}

static i32 wait_explorer_raw_key(void) {
  const u32 display_mode_revision = main_lcd().displayModeRevision();

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
    kbd::handoff(kbd::Event(scan_code));
    return scan_code & ~(i32) key_state::RELEASED;
  }
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

#if MK61_PROPORTIONAL_UI_FONTS
static bool root_entry_by_type_name(program_store::ProgramType type,
                                    const char* name,
                                    program_store::Entry& out) {
  if(name == NULL || name[0] == 0) return false;
  const int count = program_store::child_count(program_store::ROOT_ID);
  for(int index = 0; index < count; ++index) {
    program_store::Entry entry;
    if(!program_store::child(program_store::ROOT_ID, index, entry)) continue;
    if(entry.kind == program_store::NodeKind::FILE && entry.type == type &&
       strncmp(entry.name, name, program_store::NAME_SIZE) == 0) {
      out = entry;
      return true;
    }
  }
  return false;
}
#endif

#if defined(MK61_DISPLAY_UC1609)
static bool ui_font_directory(u16& out_id) {
  const int count = program_store::child_count(program_store::ROOT_ID);
  for(int index = 0; index < count; ++index) {
    program_store::Entry entry;
    if(program_store::child(program_store::ROOT_ID, index, entry) &&
       entry.kind == program_store::NodeKind::DIRECTORY &&
       ui_font_catalog::name_equal(entry.name,
                                   ui_font_catalog::DIRECTORY_NAME)) {
      out_id = entry.id;
      return true;
    }
  }
  return false;
}
#endif

#if MK61_PROPORTIONAL_UI_FONTS
static bool ui_font_candidate(const program_store::Entry& entry,
                              u8& out_height) {
  if(entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::FONT ||
     entry.data_len < fmk::HEADER_SIZE ||
     entry.data_len > program_store::MAX_FONT_SIZE) return false;
  u8 header[fmk::HEADER_SIZE];
  u16 actual = 0;
  return program_store::read_range_id(entry.id, 0, header, sizeof(header),
                                      &actual) &&
      actual == sizeof(header) &&
      ui_font_catalog::inspect_header(header, sizeof(header), entry.data_len,
                                      out_height);
}

static bool next_ui_font_entry(u16 directory_id, const char* after,
                               program_store::Entry& out_entry,
                               u8& out_height) {
  bool found = false;
  const int count = program_store::child_count(directory_id);
  for(int index = 0; index < count; ++index) {
    program_store::Entry entry;
    u8 height = 0;
    if(!program_store::child(directory_id, index, entry) ||
       !ui_font_candidate(entry, height) ||
       (after != NULL &&
        ui_font_catalog::name_compare(entry.name, after) <= 0)) continue;
    if(!found ||
       ui_font_catalog::name_compare(entry.name, out_entry.name) < 0) {
      out_entry = entry;
      out_height = height;
      found = true;
    }
  }
  return found;
}

static bool ui_font_entry_at(u16 index, program_store::Entry& out_entry,
                             u8& out_height) {
  u16 directory_id = program_store::INVALID_ID;
  if(!ui_font_directory(directory_id)) return false;
  char after[program_store::NAME_SIZE] = {};
  const char* cursor = NULL;
  for(u16 rank = 0; rank <= index; ++rank) {
    program_store::Entry entry;
    u8 height = 0;
    if(!next_ui_font_entry(directory_id, cursor, entry, height)) return false;
    if(rank == index) {
      out_entry = entry;
      out_height = height;
      return true;
    }
    memcpy(after, entry.name, sizeof(after));
    after[sizeof(after) - 1] = 0;
    cursor = after;
  }
  return false;
}

static bool ui_font_entry_by_key(u32 key, program_store::Entry& out_entry,
                                 u8& out_height) {
  if(key == 0 || key == 0xFFFFFFFFUL) return false;
  u16 directory_id = program_store::INVALID_ID;
  if(!ui_font_directory(directory_id)) return false;
  bool found = false;
  const int count = program_store::child_count(directory_id);
  for(int index = 0; index < count; ++index) {
    program_store::Entry entry;
    u8 height = 0;
    if(!program_store::child(directory_id, index, entry) ||
       !ui_font_candidate(entry, height) ||
       ui_font_catalog::name_key(entry.name) != key) continue;
    // Treat the astronomically unlikely hash collision as an invalid saved
    // choice instead of silently loading a different face.
    if(found) return false;
    out_entry = entry;
    out_height = height;
    found = true;
  }
  return found;
}
#endif

#if MK61_PROPORTIONAL_UI_FONTS
// Keep the insertion point inside the viewport, not merely the beginning of
// the name. Bound every temporary by C6's filename capacity and move only at
// M8 character boundaries. The spare right margin includes the caret's next glyph.
static u16 ui_editor_window_start(const char* text, u16 length, u16 cursor) {
  if(text == NULL) return 0;
  if(length >= program_store::NAME_SIZE) length = program_store::NAME_SIZE - 1;
  if(cursor > length) cursor = length;
  char prefix[program_store::NAME_SIZE];
  u16 start = 0;
  while(start < cursor) {
    const u16 count = (u16) (cursor - start);
    memcpy(prefix, text + start, count);
    prefix[count] = 0;
    if(main_lcd().measureUiText(prefix) <= 160) break;
    start = m8_view::next_offset((const u8*) text, length, start);
  }
  return start;
}
#endif

static void file_dialog_scroll_reset(FileDialogScroll& scroll) {
  scroll.active = -1;
  scroll.name[0] = 0;
  scroll.offset = 0;
  scroll.direction = 1;
  scroll.next_ms = 0;
}

static u8 file_dialog_name_width(void) {
#if MK61_PROPORTIONAL_UI_FONTS
  if(main_lcd().uiTextActive()) {
    const u16 pixels = main_lcd().uiTextWidth();
    return pixels > 12 ? (u8) (pixels - 12) : 0; // selection gutter
  }
#endif
  const u8 cols = main_lcd().cols();
  return cols > FILE_DIALOG_NAME_COL ? (u8) (cols - FILE_DIALOG_NAME_COL) : 0;
}

static u8 file_dialog_name_len(const char* name) {
  const usize len = m8_view::codepoint_count(name,
                                               explorer_label::SIZE - 1);
  return len > 255 ? 255 : (u8) len;
}

static bool file_dialog_name_overflows(const char* name, u8 width) {
#if MK61_PROPORTIONAL_UI_FONTS
  if(main_lcd().uiTextActive()) return main_lcd().measureUiText(name) > width;
#endif
  return width != 0 && file_dialog_name_len(name) > width;
}

static u8 file_dialog_scroll_max_offset(const char* name, u8 width) {
#if MK61_PROPORTIONAL_UI_FONTS
  if(main_lcd().uiTextActive()) {
    const u16 bytes = (u16) text_editor::bounded_length(name, explorer_label::SIZE);
    u16 offset = 0;
    u8 skipped = 0;
    while(offset < bytes && main_lcd().measureUiText(name + offset) > width) {
      offset = m8_view::next_offset((const u8*) name, bytes, offset);
      ++skipped;
    }
    return skipped;
  }
#endif
  const u8 len = file_dialog_name_len(name);
  return (width != 0 && len > width) ? (u8) (len - width) : 0;
}

static void file_dialog_scroll_track(FileDialogScroll& scroll, int active, const char* name, u8 width, u32 now) {
  const bool same = scroll.active == active && strncmp(scroll.name, name, sizeof(scroll.name)) == 0;
  if(!same) {
    scroll.active = active;
    bounded_string::copy(scroll.name, name);
    scroll.offset = 0;
    scroll.direction = 1;
    scroll.next_ms = now + FILE_DIALOG_SCROLL_START_MS;
  }

  const u8 max_offset = file_dialog_scroll_max_offset(name, width);
  if(max_offset == 0) {
    scroll.offset = 0;
    scroll.direction = 1;
    scroll.next_ms = 0;
    return;
  }

  if(scroll.offset > max_offset) scroll.offset = max_offset;
  if(scroll.next_ms == 0) scroll.next_ms = now + FILE_DIALOG_SCROLL_START_MS;
  if(!explorer_time_reached(now, scroll.next_ms)) return;

  if(scroll.direction >= 0) {
    if(scroll.offset < max_offset) scroll.offset++;
    if(scroll.offset >= max_offset) {
      scroll.direction = -1;
      scroll.next_ms = now + FILE_DIALOG_SCROLL_EDGE_MS;
    } else {
      scroll.next_ms = now + FILE_DIALOG_SCROLL_STEP_MS;
    }
  } else {
    if(scroll.offset > 0) scroll.offset--;
    if(scroll.offset == 0) {
      scroll.direction = 1;
      scroll.next_ms = now + FILE_DIALOG_SCROLL_EDGE_MS;
    } else {
      scroll.next_ms = now + FILE_DIALOG_SCROLL_STEP_MS;
    }
  }
}

static u16 file_dialog_scroll_timeout(const FileDialogScroll& scroll, const char* name, u8 width, u32 now) {
  if(!file_dialog_name_overflows(name, width) || scroll.next_ms == 0) return 0;
  if(explorer_time_reached(now, scroll.next_ms)) return 1;
  const u32 delta = scroll.next_ms - now;
  return delta > 1000 ? 1000 : (u16) delta;
}

static void file_dialog_name_window(const char* name, u8 offset, u8 width,
                                 bool mark_overflow, char* out,
                                 usize capacity) {
  if(out == NULL || capacity == 0) return;
  out[0] = 0;
  if(name == NULL || width == 0) return;
  const u16 byte_len = (u16) text_editor::bounded_length(
      name, explorer_label::SIZE);
  const u8 codepoints = file_dialog_name_len(name);
  if(offset > codepoints) offset = codepoints;
  const bool marker = mark_overflow && offset == 0 && codepoints > width;
  const u8 text_width = marker && width > 0 ? (u8) (width - 1) : width;
  u16 source = m8_view::byte_offset(name, offset, byte_len);
  usize target = 0;
  for(u8 used = 0; used < text_width && source < byte_len; used++) {
    const u16 next = m8_view::next_offset((const u8*) name, byte_len,
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

static void draw_file_dialog_name(const lcd_ru::font_map_t& map,
                               const char* name, u8 row, u8 offset,
                               bool selected) {
#if MK61_PROPORTIONAL_UI_FONTS
  if(main_lcd().uiTextActive()) {
    main_lcd().printUiLine(row,
        name + m8_view::byte_offset(name, offset, explorer_label::SIZE - 1),
        selected ? '>' : ' ');
    return;
  }
#endif
  const u8 width = file_dialog_name_width();
  if(width == 0) return;
  char window[explorer_label::SIZE];
  file_dialog_name_window(name, offset, width, true, window, sizeof(window));
  main_lcd().setCursor(0, row);
  main_lcd().write((u8) (selected ? '>' : ' '));
  main_lcd().setCursor(FILE_DIALOG_NAME_COL, row);
  lcd_ru::write_text(map, window, width);
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
  return m8_view::next_offset(data, len, offset);
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

  lcd_ru::font_map_t map = {};
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
  // Both rows must share one LCD1602 CGRAM map.  On UC1609 the same entry
  // point also guarantees that a modal message uses the selected UI face.
  lcd_ru::print_lines(library_mk61::language_is_ru() ? ru0 : en0,
                      library_mk61::language_is_ru() ? ru1 : en1);
}

static void show_graphics_unavailable() {
  show_message("Graphics", M8("Графика"),
               "unavailable", M8("недоступна"));
}

#if defined(MK61_DISPLAY_UC1609)
static bool apply_font_entry_once(const program_store::Entry& entry,
                                  AppliedFontRole role,
                                  u8 expected_height,
                                  bool persist_settings = true,
                                  bool* read_failed = NULL) {
  if(entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::FONT ||
     entry.data_len < fmk::HEADER_SIZE ||
     entry.data_len > program_store::MAX_FONT_SIZE) return false;
  const u8 flags = persist_settings ? MK61_PREPARED_FONT_PERSIST : 0;
  const i32 result = setup_ui::compile_font(
      entry.id,
      role == AppliedFontRole::UI ? MK61_PREPARED_FONT_UI
                                  : MK61_PREPARED_FONT_TEXT,
      expected_height, 0, flags);
  if(read_failed != NULL) *read_failed = result == MK61_TEXT_FONT_UNAVAILABLE;
  return result == MK61_TEXT_FONT_OK;
}

static bool restore_applied_font(u16 id, AppliedFontRole role,
                                 u8 expected_height,
                                 bool persist_settings = true) {
  program_store::Entry old_entry;
  return id != program_store::INVALID_ID &&
      program_store::entry_by_id(id, old_entry) &&
      apply_font_entry_once(old_entry, role, expected_height,
                            persist_settings);
}

static bool capture_applied_font(AppliedFontSnapshot& out) {
  if(applied_font_suspended) return false;
  out.id = applied_font_id;
  out.role = applied_font_role;
  out.ui_height = applied_ui_height;
#if MK61_PROPORTIONAL_UI_FONTS
  out.ui_key = applied_ui_key;
  out.ui_family = main_lcd().uiFontFamily();
  out.ui_size = main_lcd().uiFontSize();
  out.ui_context = main_lcd().uiTextContext();
#endif
  out.text_profile = main_lcd().textProfile();
  out.external = main_lcd().externalFontActive();
  if(!out.external) return true;
  program_store::Entry entry;
  return out.id != program_store::INVALID_ID &&
      program_store::entry_by_id(out.id, entry) &&
      entry.kind == program_store::NodeKind::FILE &&
      entry.type == program_store::ProgramType::FONT;
}

static bool restore_applied_font(const AppliedFontSnapshot& saved) {
#if MK61_PROPORTIONAL_UI_FONTS
  // Stop the proportional renderer before replacing the bytes backing its
  // current Face. The saved context is re-entered only after the old face and
  // its exact settings are valid again.
  main_lcd().endUiText();
#endif
  bool restored = true;
  if(saved.external) {
    restored = restore_applied_font(saved.id, saved.role, saved.ui_height,
                                    false);
  } else {
    main_lcd().useBuiltinFont();
    applied_font_id = program_store::INVALID_ID;
    applied_font_role = AppliedFontRole::TEXT;
    applied_ui_height = 0;
#if MK61_PROPORTIONAL_UI_FONTS
    applied_ui_key = 0;
#endif
    applied_font_suspended = false;
  }
  if(!restored) return false;
#if MK61_PROPORTIONAL_UI_FONTS
  applied_ui_key = saved.ui_key;
  main_lcd().setUiFont(saved.ui_family, saved.ui_size);
  if(saved.ui_context) main_lcd().beginUiText();
#endif
  main_lcd().restoreTextProfile(saved.text_profile);
  return true;
}

static bool font_leaf_name(const char* name) {
  return name != NULL && name[0] != 0 &&
      strchr(name, '/') == NULL && strchr(name, '\\') == NULL;
}

static bool font_catalog_entry(const char* name,
                               program_store::Entry& out) {
  if(!font_leaf_name(name)) return false;
  u16 directory = program_store::INVALID_ID;
  if(!ui_font_directory(directory)) return false;
  return storage_path::resolve_file(directory, name,
      program_store::ProgramType::FONT, out) == storage_path::Status::OK;
}

enum class TextFontPreflight : i8 { UNAVAILABLE = -3, INVALID = -1, OK = 1 };

static TextFontPreflight preflight_text_font(
    const program_store::Entry& entry) {
  if(entry.data_len < fmk::HEADER_SIZE ||
     entry.data_len > program_store::MAX_FONT_SIZE ||
     entry.data_len > fmk::MAX_FILE_SIZE) return TextFontPreflight::INVALID;
  u8 header[fmk::HEADER_SIZE];
  u16 actual = 0;
  if(!program_store::read_range_id(entry.id, 0, header, sizeof(header),
                                   &actual)) {
    return TextFontPreflight::UNAVAILABLE;
  }
  if(actual != sizeof(header)) return TextFontPreflight::INVALID;
  return fmk::plausibleHeader(header, entry.data_len)
      ? TextFontPreflight::OK : TextFontPreflight::INVALID;
}
#endif

static bool apply_font_entry(const program_store::Entry& entry) {
#if !defined(MK61_DISPLAY_UC1609)
  (void) entry;
  return false;
#else
  const u16 old_id = applied_font_id;
  const AppliedFontRole old_role = applied_font_role;
  const u8 old_height = applied_ui_height;
  if(apply_font_entry_once(entry, AppliedFontRole::TEXT, 0)) {
#if MK61_PROPORTIONAL_UI_FONTS
    if(old_role == AppliedFontRole::UI) {
      // A single arena cannot retain two FMKs. An explicit Run of a generic
      // font wins, while the UI moves to its guaranteed resident fallback.
      (void) library_mk61::set_ui_font(1, old_height);
      library_mk61::mark_settings_dirty();
    }
#endif
    return true;
  }
  if(!main_lcd().externalFontActive()) {
    (void) restore_applied_font(old_id, old_role, old_height);
  }
  return false;
#endif
}

static bool reject_unavailable_chip8(const program_store::Entry& entry) {
  if(entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::CHIP8 ||
     file_handlers::available(entry)) return false;
  // A ROM is not text. The short-OK fallback must explain the missing
  // interpreter rather than feed opcodes to the generic text preview.
  show_message("CHIP-8", "CHIP-8", "unavailable", M8("недоступен"));
  (void) wait_explorer_key(false);
  return true;
}

static bool view_entry(const program_store::Entry& entry) {
  if(reject_unavailable_chip8(entry)) return false;
  if(entry.type == program_store::ProgramType::IMAGE1 ||
     entry.type == program_store::ProgramType::MARKDOWN) {
    const loadable_module::FileOpenResult result =
        file_handlers::open(entry);
    if(result == loadable_module::FileOpenResult::OK) return true;

    const bool markdown =
        entry.type == program_store::ProgramType::MARKDOWN;
    const char* en = markdown ? "Markdown error" : "Image error";
    const char* ru = markdown ? M8("Ошибка Markdown") : M8("Ошибка картинки");
    if(result == loadable_module::FileOpenResult::BUSY) {
      en = "Busy";
      ru = M8("Занято");
    } else if(result == loadable_module::FileOpenResult::IO_ERROR) {
      en = "Read error";
      ru = M8("Ошибка чтения");
    } else if(result == loadable_module::FileOpenResult::INVALID_FILE) {
      en = markdown ? "Invalid Markdown" : "Invalid WBMP";
      ru = markdown ? M8("Неверный Markdown") : M8("Неверный WBMP");
    } else if(result == loadable_module::FileOpenResult::RUNTIME_ERROR) {
      en = "Display error";
      ru = M8("Ошибка экрана");
    } else if(result ==
              loadable_module::FileOpenResult::UNSUPPORTED_DISPLAY) {
      show_graphics_unavailable();
      (void) wait_explorer_key(false);
      return false;
    }
    show_message(en, ru, entry.name, entry.name);
    (void) wait_explorer_key(false);
    return false;
  }

  // The generic explorer preview intentionally lives in the compact SCRATCH
  // arena. F411 UI packages may be much larger and are previewed safely by
  // the Fonts settings screen, which streams them into the shared BULK arena.
  // Report that workflow explicitly instead of misdiagnosing a valid file as
  // an I/O failure merely because it cannot fit in this modal preview buffer.
  if(entry.type == program_store::ProgramType::FONT &&
     entry.data_len > shared_scratch::SIZE) {
    show_message("Use Fonts menu", M8("Меню Шрифты"),
                 entry.name, entry.name);
    (void) wait_explorer_key(false);
    return true;
  }

  shared_scratch::Lease scratch;
  language_workspace::Lease workspace;
  u8* data = NULL;
  usize capacity = 0;
  if(entry.type == program_store::ProgramType::TINYBASIC &&
     entry.data_len > shared_scratch::SIZE) {
    if(workspace.acquire(language_workspace::Owner::APPLICATION,
                         program_store::MAX_TINYBASIC_TEXT_SIZE)) {
      data = (u8*) workspace.data();
      capacity = workspace.size();
    }
  } else if(scratch.acquire(shared_scratch::Owner::EXPLORER_VIEW,
                            program_store::MAX_MK61_TEXT_SIZE)) {
    data = scratch.data();
    capacity = scratch.size();
  }
  if(data == NULL) {
    show_message("Busy", M8("Занято"), entry.name, entry.name);
    (void) wait_explorer_key(false);
    return false;
  }

  u16 len = 0;
  if(!read_entry_data(entry, data, capacity, len)) {
    show_message("Read error", M8("Ошибка чтения"), entry.name, entry.name);
    (void) wait_explorer_key(false);
    return false;
  }

  if(entry.type == program_store::ProgramType::FONT) {
    MK61DisplayTextScope text_scope(main_lcd(), false);
    setup_ui::preview(entry.name, data, len);
    return true;
  }

  // Raw source/state/text views retain their 16-column layout. Markdown has
  // its own measured layout above, and is intentionally not in this scope.
  MK61DisplayTextScope text_scope(main_lcd(), false);
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
                 tree ? M8("Удалить всё?") : M8("Удалить?"),
                 entry.name, entry.name);
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
  show_message(ok ? "Deleted" : "Delete error",
               ok ? M8("Удалено") : M8("Ошибка"),
               entry.name, entry.name);
  delay(700);
}

static void draw_name_editor(const char* name, u16 cursor, NamePrompt prompt) {
  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();
  const char* en = "Rename";
  const char* ru = M8("Новое имя");
  if(prompt == NamePrompt::NEW_DIRECTORY) {
    en = "New folder";
    ru = M8("Новая папка");
  } else if(prompt == NamePrompt::SAVE) {
    en = "File name";
    ru = M8("Имя файла");
  }
  const char* title = library_mk61::language_is_ru() ? ru : en;
  const u16 byte_len = (u16) strlen(name);
  if(cursor > byte_len) cursor = byte_len;
  const u16 cursor_chars = m8_view::codepoint_count(name, cursor);
#if MK61_PROPORTIONAL_UI_FONTS
  if(main_lcd().uiTextActive()) {
    const u16 start = ui_editor_window_start(name, byte_len, cursor);
    const u16 skipped = m8_view::codepoint_count(name, start);
    main_lcd().printUiLine(0, title);
    main_lcd().printUiLine(1, name + start, '>');
    main_lcd().setCursor((u8) (1U + cursor_chars - skipped), 1);
    main_lcd().cursorOn();
    return;
  }
#endif
  const u16 window = cursor_chars > lcd_display::COLS - 2
      ? (u16) (cursor_chars - (lcd_display::COLS - 2)) : 0;
  char line[program_store::NAME_SIZE + 2];
  line[0] = '>';
  file_dialog_name_window(name, (u8) window,
                       (u8) (lcd_display::COLS - 1), false,
                       line + 1, sizeof(line) - 1);

  lcd_ru::font_map_t map = {};
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
  cursor = m8_view::previous_offset((const u8*) name, len, cursor);
  return true;
}

static bool name_move_right(const char* name, u16 len, u16& cursor) {
  if(name == NULL || cursor >= len) return false;
  const u16 next = m8_view::next_offset((const u8*) name, len, cursor);
  cursor = next > cursor ? next : (u16) (cursor + 1);
  return true;
}

static bool name_backspace(char* name, u16& len, u16& cursor) {
  if(name == NULL || cursor == 0 || cursor > len || name[len] != 0) {
    return false;
  }
  const u16 previous = m8_view::previous_offset((const u8*) name, len,
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
  show_message(ok ? "Renamed" : "Rename error",
               ok ? M8("Переимен.") : M8("Ошибка"), name, name);
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
      show_message("Name exists", M8("Уже есть"), name, name);
      delay(900);
      return false;
    }
  }

  u16 id = program_store::INVALID_ID;
  const bool ok = program_store::create_directory(parent_id, name,
                                                    program_store::INVALID_ID,
                                                    &id);
  show_message(ok ? "Folder created" : "Create error",
               ok ? M8("Папка создана") : M8("Ошибка"),
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
               ok ? M8("Перемещено") : M8("Ошибка"),
               entry.name, entry.name);
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

static void dialog_item_name(const DialogItem& item,
                             char (&out)[explorer_label::SIZE]) {
  const char* text = "?";
  switch(item.kind) {
    case DialogItemKind::THIS_DIRECTORY:
      text = library_mk61::text("This folder", M8("Эта папка"));
      break;
    case DialogItemKind::NEW_FILE:
      text = library_mk61::text("New file", M8("Новый файл"));
      break;
    case DialogItemKind::NEW_DIRECTORY:
      text = library_mk61::text("New folder", M8("Новая папка"));
      break;
    case DialogItemKind::ENTRY:
      explorer_label::format(item.entry, out);
      return;
  }
  bounded_string::copy(out, text);
}

static void draw_dialog_row(const lcd_ru::font_map_t& map, u8 row,
                            const DialogItem& item, u8 scroll_offset,
                            bool selected) {
  char name[explorer_label::SIZE];
  dialog_item_name(item, name);
  draw_file_dialog_name(map, name, row, scroll_offset, selected);
}

static u16 draw_storage_dialog(u16 directory_id, DialogMode mode,
                               program_store::ProgramType type,
                               bool allow_new, u16 forbidden_tree,
                               int active, int count, FileDialogScroll& scroll) {
  explorer_cursor_off();
  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();
  if(count <= 0) {
    file_dialog_scroll_reset(scroll);
    print_localized_line(0, "Folder empty", M8("Папка пуста"));
    print_localized_line(1, "ESC: parent", M8("ESC: наверх"));
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
    char name[explorer_label::SIZE];
    dialog_item_name(active_item, name);
    const u8 width = file_dialog_name_width();
    file_dialog_scroll_track(scroll, active, name, width, now);
    timeout = file_dialog_scroll_timeout(scroll, name, width, now);
  } else {
    file_dialog_scroll_reset(scroll);
  }

  lcd_ru::font_map_t name_map = {};
  for(int row = 0; row < visible; row++) {
    DialogItem item;
    const int index = top + row;
    if(!dialog_item_at(directory_id, mode, type, allow_new, forbidden_tree,
                       index, item)) continue;
    char name[explorer_label::SIZE];
    dialog_item_name(item, name);
    char window[explorer_label::SIZE];
    file_dialog_name_window(name,
                         index == active ? scroll.offset : 0,
                         file_dialog_name_width(), true, window,
                         sizeof(window));
    lcd_ru::scan_text(name_map, window, file_dialog_name_width());
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
                    selected ? scroll.offset : 0, selected);
  }
  for(int row = visible; row < rows; row++) print_line((u8) row, "");
  return timeout;
}

static ProgramStoreFileDialogResult run_storage_dialog(
    DialogMode mode, program_store::ProgramType type, u16 start_directory,
    bool allow_new, u16 forbidden_tree, program_store::Entry& out_entry,
    u16& out_directory) {
  MK61DisplayTextScope text_scope(main_lcd());
  u16 directory_id = start_directory;
  if(directory_id != program_store::ROOT_ID) {
    program_store::Entry directory;
    if(!program_store::entry_by_id(directory_id, directory) ||
       directory.kind != program_store::NodeKind::DIRECTORY) {
      directory_id = program_store::ROOT_ID;
    }
  }

  int active = 0;
  FileDialogScroll scroll;
  file_dialog_scroll_reset(scroll);
  wait_input_handoff();
  while(true) {
    int count = dialog_count(directory_id, mode, type, allow_new,
                             forbidden_tree);
    if(active >= count) active = count > 0 ? count - 1 : 0;
    const u16 timeout = draw_storage_dialog(directory_id, mode, type,
        allow_new, forbidden_tree, active, count, scroll);
    const i32 key = wait_explorer_key(true, timeout);
    if(key == EXPLORER_KEY_TICK || key == EXPLORER_KEY_REDRAW) continue;
    if(key == EXPLORER_KEY_DOWN && count > 0) {
      active = (active + 1) % count;
      file_dialog_scroll_reset(scroll);
      continue;
    }
    if(key == EXPLORER_KEY_UP && count > 0) {
      active = active > 0 ? active - 1 : count - 1;
      file_dialog_scroll_reset(scroll);
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
      file_dialog_scroll_reset(scroll);
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
      file_dialog_scroll_reset(scroll);
      continue;
    }
    if(item.entry.kind == program_store::NodeKind::DIRECTORY) {
      directory_id = item.entry.id;
      active = 0;
      file_dialog_scroll_reset(scroll);
      continue;
    }
    out_entry = item.entry;
    out_directory = directory_id;
    explorer_cursor_off();
    return ProgramStoreFileDialogResult::EXISTING;
  }
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
#if MK61_APP_RUNTIME_AVAILABLE
    case program_store::ProgramType::APP:
      return true;
#endif
#if defined(MK61_DISPLAY_UC1609)
    case program_store::ProgramType::FONT:
      return true;
#endif
    case program_store::ProgramType::IMAGE1:
    case program_store::ProgramType::CHIP8:
    case program_store::ProgramType::MARKDOWN:
      return file_handlers::available(entry);
    default:
      return false;
  }
}

static bool run_entry(const program_store::Entry& entry) {
  loadable_module::FileOpenResult file_result =
      loadable_module::FileOpenResult::OK;
  const bool file_handler =
      entry.type == program_store::ProgramType::IMAGE1 ||
      entry.type == program_store::ProgramType::CHIP8 ||
      entry.type == program_store::ProgramType::MARKDOWN;
  bool ok;
  if(entry.type == program_store::ProgramType::FONT) ok = apply_font_entry(entry);
  else if(file_handler) {
    ok = (file_result = file_handlers::open(entry)) == loadable_module::FileOpenResult::OK;
  } else {
    MK61DisplayTextScope text_scope(main_lcd(), false);
    ok = OpenStoredEntry(entry);
  }
  if(!ok) {
    if(file_handler &&
       file_result == loadable_module::FileOpenResult::UNSUPPORTED_DISPLAY) {
      show_graphics_unavailable();
    } else {
      show_message("Run error", M8("Ошибка запуска"), entry.name, entry.name);
    }
    delay(900);
  } else if(entry.type == program_store::ProgramType::FONT) {
    show_message("Font applied", M8("Шрифт применен"),
                 entry.name, entry.name);
    delay(700);
  }
  return ok;
}


static bool load_mk61_entry(const program_store::Entry& entry) {
  bool loaded = false;
  if(entry_can_load(entry)) {
    MK61DisplayTextScope text_scope(main_lcd(), false);
    loaded = LoadProgram(entry.id);
  }
  if(!loaded) {
    show_message("Load error", M8("Ошибка чтения"), entry.name, entry.name);
    delay(900);
    return false;
  }
  current_mk61_entry_id = entry.id;
  current_mk61_directory_id = entry.parent_id;
  return true;
}

static void edit_entry(const program_store::Entry& entry) {
  bool ok = false;
  {
    MK61DisplayTextScope text_scope(main_lcd(), false);
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
  }
  if(!ok) {
    show_message("Edit error", M8("Ошибка правки"), entry.name, entry.name);
    delay(900);
  }
}


static bool explorer_action(void) {
  return program_store_explorer_select();
}

#if MK61_ENABLE_FOCAL
static bool focal_action(void) {
  FOCAL_menu_select();
  return action::MENU_BACK;
}
#endif

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
    show_message("Save error", M8("Ошибка записи"), name, name);
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
  show_message("Program saved", M8("Программа сохр."), name, name);
  delay(700);
  return action::MENU_EXIT;
}

static constexpr t_punct M61_LOAD_PUNCT = {
    .size = 13, .action = &m61_load_action, .text = "Open M61 file"};
static constexpr t_punct M61_SAVE_PUNCT = {
    .size = 13, .action = &m61_save_action, .text = "Save M61 file"};
static constexpr auto RU_M61_LOAD_PUNCT = M8_PUNCT(15, &m61_load_action, "Открыть МК-61");
static constexpr auto RU_M61_SAVE_PUNCT = M8_PUNCT(15, &m61_save_action, "Сохранить МК-61");

static bool m61_storage_action(void) {
  t_punct* items[] = {
    (t_punct*) (library_mk61::language_is_ru()
        ? mk8::punct_view<t_punct>(RU_M61_LOAD_PUNCT) : &M61_LOAD_PUNCT),
    (t_punct*) (library_mk61::language_is_ru()
        ? mk8::punct_view<t_punct>(RU_M61_SAVE_PUNCT) : &M61_SAVE_PUNCT),
  };
  class_menu menu(items, sizeof(items) / sizeof(items[0]));
  return menu.select();
}

static constexpr t_punct EXPLORER_PUNCT = {.size = 8, .action = &explorer_action, .text = "Explorer"};
static constexpr auto RU_EXPLORER_PUNCT = M8_PUNCT(15, &explorer_action, "Проводник");
static constexpr t_punct M61_STORAGE_PUNCT = {.size = 9, .action = &m61_storage_action, .text = "M61 files"};
static constexpr auto RU_M61_STORAGE_PUNCT = M8_PUNCT(15, &m61_storage_action, "Файлы МК-61");

#if MK61_ENABLE_USB_SCREEN
static constexpr t_punct USB_SCREEN_DEV_PUNCT = {
    .size = 10, .action = &UsbScreenMode, .text = "USB Screen"};
static constexpr auto RU_USB_SCREEN_DEV_PUNCT = M8_PUNCT(15, &UsbScreenMode, "USB-экран");
#endif

#if MK61_ENABLE_FOCAL
static constexpr t_punct FOCAL_DEV_PUNCT = {.size = 11, .action = &focal_action, .text = "FOCAL tools"};
static constexpr auto RU_FOCAL_DEV_PUNCT = M8_PUNCT(15, &focal_action, "ФОКАЛ");
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

u32 program_store_explorer_actions(const program_store::Entry& entry) {
  u32 result = 0;
  if(entry_can_load(entry)) result |= loadable_module::EXPLORER_CAN_LOAD;
  if(entry_can_run(entry)) result |= loadable_module::EXPLORER_CAN_RUN;
  if(entry.kind == program_store::NodeKind::FILE)
    result |= loadable_module::EXPLORER_CAN_VIEW;
  if(entry_can_edit(entry)) result |= loadable_module::EXPLORER_CAN_EDIT;
  return result;
}

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
    show_message("Invalid name", M8("Ошибка имени"),
                 candidate, candidate);
    delay(900);
  }
  memcpy(name, candidate, strlen(candidate) + 1);
  out_directory = directory;
  return true;
}

static loadable_module::RuntimeStatus explorer_flow_action(
    void* context, u32 operation, u32& result) {
  auto& session = *(loadable_module::ExplorerSession*)context;
  if(operation != (u32)session.action) return loadable_module::RuntimeStatus::CORRUPT_MODULE;
  result = 0;
  program_store::Entry entry = {};
  const bool has_entry = session.selected_id != program_store::INVALID_ID &&
      program_store::entry_by_id(session.selected_id, entry);
  switch(session.action) {
    case loadable_module::ExplorerAction::LOAD:
      result = has_entry && load_mk61_entry(entry); break;
    case loadable_module::ExplorerAction::RUN:
    case loadable_module::ExplorerAction::AUTOEXEC:
      result = has_entry && run_entry(entry); break;
    case loadable_module::ExplorerAction::VIEW:
      if(has_entry) view_entry(entry);
      break;
    case loadable_module::ExplorerAction::EDIT:
      if(has_entry) edit_entry(entry);
      break;
    case loadable_module::ExplorerAction::NEW_DIRECTORY:
      create_directory(session.directory_id); break;
    case loadable_module::ExplorerAction::RENAME:
      if(has_entry) rename_entry(entry);
      break;
    case loadable_module::ExplorerAction::MOVE:
      if(has_entry) move_entry(entry);
      break;
    case loadable_module::ExplorerAction::DELETE_ENTRY:
      if(has_entry) delete_entry(entry);
      break;
    default: return loadable_module::RuntimeStatus::CORRUPT_MODULE;
  }
  return loadable_module::RuntimeStatus::OK;
}
#if MK61_EXPLORER_IS_BUILTIN
static app_flow::Status builtin_explorer_flow(
    void*, const app_flow::Target& target, app_flow::Step& step) {
  if(target.kind == MK61_APP_KIND_EXPLORER)
    return explorer_ui::flow_step(&step) ? MK61_FLOW_OK : MK61_FLOW_CORRUPT;
  if(target.kind != MK61_APP_FLOW_HOST) return MK61_FLOW_INVALID_MODULE;
  u32 result = 0;
  const auto status = explorer_flow_action(step.context, target.phase, result);
  mk61_app_flow_return(&step, result, (u32)status);
  return MK61_FLOW_OK;
}
#endif
bool program_store_explorer_select(void) {
  MK61DisplayTextScope text_scope(main_lcd());
  loadable_module::ExplorerSession session = {
      sizeof(loadable_module::ExplorerSession), program_store::ROOT_ID,
      program_store::INVALID_ID, 0, loadable_module::ExplorerAction::NONE, 0, {0}};
  const auto first = mk61_app_flow_to(
      MK61_APP_KIND_EXPLORER, MK61_APP_FLOW_SYSTEM_FILE, 0);
  u32 result = 0;
#if MK61_EXPLORER_IS_BUILTIN
  const auto status = (loadable_module::RuntimeStatus)app_flow::run(
      first, &session, sizeof(session), result, builtin_explorer_flow);
#else
  const auto status = loadable_module::run_flow(
      first, &session, sizeof(session), result, explorer_flow_action);
#endif
  if(status != loadable_module::RuntimeStatus::OK) {
    show_message("Explorer error", M8("Нет проводника"),
                 loadable_module::status_text(status), M8("System/EXPLORER.APP"));
    kbd::get_key_wait();
    return action::MENU_BACK;
  }
  return result ? action::MENU_EXIT : action::MENU_BACK;
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

i32 program_store_install_prepared_font(
    u16 source_id, const u8* data, u16 size, u8 role, u8 expected_height,
    u32 ui_key, u8 flags) {
#if !defined(MK61_DISPLAY_UC1609)
  (void) source_id; (void) data; (void) size; (void) role;
  (void) expected_height; (void) ui_key; (void) flags;
  return MK61_TEXT_FONT_UNSUPPORTED;
#else
  static constexpr u8 KNOWN_FLAGS = MK61_PREPARED_FONT_PERSIST |
                                    MK61_PREPARED_FONT_SELECT_UI;
  if(data == nullptr || size < prepared_font::HEADER_SIZE ||
     size > exclusive_buffer::SIZE || (flags & ~KNOWN_FLAGS) != 0 ||
     role > MK61_PREPARED_FONT_UI ||
     ((flags & MK61_PREPARED_FONT_SELECT_UI) != 0 &&
      role != MK61_PREPARED_FONT_UI)) return MK61_TEXT_FONT_INVALID;

  program_store::Entry entry = {};
  if(!program_store::entry_by_id(source_id, entry) ||
     entry.kind != program_store::NodeKind::FILE ||
     entry.type != program_store::ProgramType::FONT) {
    return MK61_TEXT_FONT_UNAVAILABLE;
  }

#if MK61_PROPORTIONAL_UI_FONTS
  if((flags & MK61_PREPARED_FONT_SELECT_UI) != 0) {
    program_store::Entry selected = {};
    u8 selected_height = 0;
    if(ui_key == 0 || !ui_font_entry_by_key(ui_key, selected,
                                             selected_height) ||
       selected.id != source_id || selected_height != expected_height) {
      return MK61_TEXT_FONT_INVALID;
    }
  }
#else
  if(role == MK61_PREPARED_FONT_UI) return MK61_TEXT_FONT_UNSUPPORTED;
#endif

  prepared_font::Face candidate;
  if(!candidate.open(data, size)) return MK61_TEXT_FONT_INVALID;
  const exclusive_buffer::Owner owner = exclusive_buffer::current_owner();
  if(owner != exclusive_buffer::Owner::NONE &&
     owner != exclusive_buffer::Owner::DISPLAY_FONT) {
    return MK61_TEXT_FONT_UNAVAILABLE;
  }

  const bool replaced_text_font = role == MK61_PREPARED_FONT_UI &&
      main_lcd().externalTextFontActive();
  const bool installed = role == MK61_PREPARED_FONT_UI
#if MK61_PROPORTIONAL_UI_FONTS
      ? main_lcd().installPreparedUiFont(data, size, expected_height)
#else
      ? false
#endif
      : main_lcd().installPreparedFont(data, size);
  if(!installed) return MK61_TEXT_FONT_INVALID;

  applied_font_id = source_id;
  applied_font_role = role == MK61_PREPARED_FONT_UI
      ? AppliedFontRole::UI : AppliedFontRole::TEXT;
  applied_ui_height = role == MK61_PREPARED_FONT_UI ? expected_height : 0;
#if MK61_PROPORTIONAL_UI_FONTS
  if(role == MK61_PREPARED_FONT_TEXT) applied_ui_key = 0;
  if((flags & MK61_PREPARED_FONT_SELECT_UI) != 0) {
    applied_ui_key = ui_key;
    if(!library_mk61::adopt_external_ui_font(expected_height, ui_key)) {
      main_lcd().useBuiltinFont();
      applied_font_id = program_store::INVALID_ID;
      applied_font_role = AppliedFontRole::TEXT;
      applied_ui_height = 0;
      applied_ui_key = 0;
      return MK61_TEXT_FONT_INVALID;
    }
  }
#endif
  applied_font_suspended = false;

  if((flags & MK61_PREPARED_FONT_PERSIST) != 0) {
    if(role == MK61_PREPARED_FONT_TEXT) {
      library_mk61::set_display_text_profile(main_lcd().textProfile());
      library_mk61::refresh_menu_text();
      library_mk61::defer_settings_state_save();
    } else if(replaced_text_font) {
      // UI and generic text PFK2 share BULK. Replacing the latter also
      // replaces its geometry; do not retain a stale text profile.
      library_mk61::set_display_text_profile(main_lcd().textProfile());
      library_mk61::refresh_menu_text();
      library_mk61::mark_settings_dirty();
    }
#if MK61_PROPORTIONAL_UI_FONTS
    if((flags & MK61_PREPARED_FONT_SELECT_UI) != 0)
      library_mk61::mark_settings_dirty();
#endif
  }
  return MK61_TEXT_FONT_OK;
#endif
}

i32 program_store_text_font_begin(void) {
#if !defined(MK61_DISPLAY_UC1609)
  return -2;
#else
  if(text_font_session.active || !program_store::ready() ||
     !capture_applied_font(text_font_session.original)) return -3;
  text_font_session.active = true;
  text_font_session.override_loaded = false;
  return 1;
#endif
}

#if defined(MK61_DISPLAY_UC1609)
static i32 program_store_text_font_load_entry(
    const program_store::Entry& entry) {
  const TextFontPreflight preflight = preflight_text_font(entry);
  if(preflight != TextFontPreflight::OK) return (i32) preflight;

  const exclusive_buffer::Owner owner = exclusive_buffer::current_owner();
  if(owner != exclusive_buffer::Owner::NONE &&
     owner != exclusive_buffer::Owner::DISPLAY_FONT) return -3;

  bool read_failed = false;
#if MK61_PROPORTIONAL_UI_FONTS
  const AppliedFontRole runtime_role = AppliedFontRole::UI;
#else
  const AppliedFontRole runtime_role = AppliedFontRole::TEXT;
#endif
  if(apply_font_entry_once(entry, runtime_role, 0, false, &read_failed)) {
#if MK61_PROPORTIONAL_UI_FONTS
    // A runtime face is a flowing graphical text surface, not a 16-cell
    // calculator font. Family 3 selects the just-installed FMK; its own
    // metrics, rather than this nominal size, determine rows and advances.
    applied_ui_key = 0;
    main_lcd().setUiFont(3, 12);
    main_lcd().beginUiText();
#endif
    text_font_session.override_loaded = true;
    return 1;
  }

  // SETUP compiles into its own workspace and the resident validates the
  // complete PFK2 image before touching BULK, so a rejected replacement
  // leaves the active face intact and needs no second C6 read.
  return read_failed ? -3 : -1;
}
#endif

i32 program_store_text_font_load(const char* name) {
#if !defined(MK61_DISPLAY_UC1609)
  (void) name;
  return -2;
#else
  if(!text_font_session.active || !program_store::ready() ||
     name == NULL || name[0] == 0) return -3;
  program_store::Entry entry;
  if(!font_catalog_entry(name, entry)) return 0;
  return program_store_text_font_load_entry(entry);
#endif
}

i32 program_store_text_font_load_from(const char* name,
                                      u16 preferred_directory) {
#if !defined(MK61_DISPLAY_UC1609)
  (void) name;
  (void) preferred_directory;
  return -2;
#else
  if(!text_font_session.active || !program_store::ready() ||
     name == NULL || name[0] == 0) return -3;
  program_store::Entry entry;
  const storage_path::Status local = storage_path::resolve_file(
      preferred_directory, name, program_store::ProgramType::FONT, entry);
  if(local == storage_path::Status::OK) {
    return program_store_text_font_load_entry(entry);
  }
  if(local != storage_path::Status::NOT_FOUND) return -1;
  if(!font_leaf_name(name)) return 0;
  if(!font_catalog_entry(name, entry)) return 0;
  return program_store_text_font_load_entry(entry);
#endif
}

i32 program_store_text_font_restore(void) {
#if !defined(MK61_DISPLAY_UC1609)
  return -2;
#else
  if(!text_font_session.active) return -3;
  AppliedFontSnapshot previous;
  if(!capture_applied_font(previous)) return -3;
  if(restore_applied_font(text_font_session.original)) {
    text_font_session.override_loaded = false;
    return 1;
  }
  (void) restore_applied_font(previous);
  return -3;
#endif
}

i32 program_store_text_font_activate(void) {
#if !defined(MK61_DISPLAY_UC1609)
  return -2;
#else
  if(!text_font_session.active || !text_font_session.override_loaded) {
    return -3;
  }
#if MK61_PROPORTIONAL_UI_FONTS
  if(applied_font_role != AppliedFontRole::UI ||
     applied_font_id == program_store::INVALID_ID ||
     !main_lcd().externalFontActive()) return -3;
  main_lcd().setUiFont(3, 12);
  main_lcd().beginUiText();
#endif
  return 1;
#endif
}

i32 program_store_text_font_end(void) {
#if !defined(MK61_DISPLAY_UC1609)
  return -2;
#else
  if(!text_font_session.active) return -3;
  const i32 result = program_store_text_font_restore();
  if(result != 1) {
    // Never leak a language-runtime override into the caller even if the
    // original C6 file disappeared or became unreadable during the run.
    main_lcd().useBuiltinFont();
    applied_font_id = program_store::INVALID_ID;
    applied_font_role = AppliedFontRole::TEXT;
    applied_ui_height = 0;
#if MK61_PROPORTIONAL_UI_FONTS
    applied_ui_key = 0;
    main_lcd().setUiFont(text_font_session.original.ui_family,
                         text_font_session.original.ui_size);
    if(text_font_session.original.ui_context) main_lcd().beginUiText();
    else main_lcd().endUiText();
#endif
    applied_font_suspended = false;
    main_lcd().restoreTextProfile(
        text_font_session.original.text_profile);
  }
  text_font_session.active = false;
  text_font_session.override_loaded = false;
  return result;
#endif
}

#if MK61_PROPORTIONAL_UI_FONTS
static const char* ui_font_entry_name(u8 size) {
  return size == 12 ? "UI12" : (size == 16 ? "UI16" : "UI14");
}

static void describe_ui_font(const program_store::Entry& entry, u8 height,
                             ProgramStoreUiFont& out) {
  out.key = ui_font_catalog::name_key(entry.name);
  out.height = height;
  memcpy(out.name, entry.name, sizeof(out.name));
  out.name[sizeof(out.name) - 1] = 0;
}

u16 program_store_ui_font_count(void) {
  u16 directory_id = program_store::INVALID_ID;
  if(!ui_font_directory(directory_id)) return 0;
  u16 result = 0;
  const int count = program_store::child_count(directory_id);
  for(int index = 0; index < count && result != 0xFFFFU; ++index) {
    program_store::Entry entry;
    u8 height = 0;
    if(program_store::child(directory_id, index, entry) &&
       ui_font_candidate(entry, height)) ++result;
  }
  return result;
}

bool program_store_ui_font_at(u16 index, ProgramStoreUiFont& out) {
  program_store::Entry entry;
  u8 height = 0;
  if(!ui_font_entry_at(index, entry, height)) return false;
  describe_ui_font(entry, height, out);
  return true;
}

bool program_store_describe_ui_font(u32 key, ProgramStoreUiFont& out) {
  program_store::Entry entry;
  u8 height = 0;
  if(!ui_font_entry_by_key(key, entry, height)) return false;
  describe_ui_font(entry, height, out);
  return true;
}

bool program_store_ui_font_source(u32 key, u16& out_id, u8& out_height) {
  program_store::Entry entry = {};
  if(!ui_font_entry_by_key(key, entry, out_height)) return false;
  out_id = entry.id;
  return true;
}

bool program_store_step_ui_font(u32 key, i8 delta, ProgramStoreUiFont& out) {
  if(delta != -1 && delta != 1) return false;
  u16 directory_id = program_store::INVALID_ID;
  if(!ui_font_directory(directory_id)) return false;

  program_store::Entry current = {};
  u8 current_height = 0;
  const char* current_name = NULL;
  if(key != 0) {
    if(!ui_font_entry_by_key(key, current, current_height)) return false;
    current_name = current.name;
  }

  bool found = false;
  program_store::Entry selected = {};
  u8 selected_height = 0;
  const int count = program_store::child_count(directory_id);
  for(int index = 0; index < count; ++index) {
    program_store::Entry entry;
    u8 height = 0;
    if(!program_store::child(directory_id, index, entry) ||
       !ui_font_candidate(entry, height)) continue;
    if(current_name != NULL) {
      const int side = ui_font_catalog::name_compare(entry.name, current_name);
      if((delta > 0 && side <= 0) || (delta < 0 && side >= 0)) continue;
    }
    if(!found) {
      selected = entry;
      selected_height = height;
      found = true;
      continue;
    }
    const int order = ui_font_catalog::name_compare(entry.name, selected.name);
    if((delta > 0 && order < 0) || (delta < 0 && order > 0)) {
      selected = entry;
      selected_height = height;
    }
  }
  if(!found) return false;
  describe_ui_font(selected, selected_height, out);
  return true;
}

bool program_store_apply_ui_font(u32 key, u8& out_height) {
  program_store::Entry entry;
  u8 height = 0;
  if(!ui_font_entry_by_key(key, entry, height)) return false;
  const u16 old_id = applied_font_id;
  const AppliedFontRole old_role = applied_font_role;
  const u8 old_height = applied_ui_height;
  const u32 old_key = applied_ui_key;
  if(apply_font_entry_once(entry, AppliedFontRole::UI, height)) {
    applied_ui_key = key;
    out_height = height;
    return true;
  }
  if(!main_lcd().externalFontActive() &&
     restore_applied_font(old_id, old_role, old_height)) {
    applied_ui_key = old_key;
  }
  return false;
}

bool program_store_apply_legacy_ui_font(u8 size) {
  if(size != 12 && size != 14 && size != 16) return false;
  program_store::Entry entry;
  if(!root_entry_by_type_name(program_store::ProgramType::FONT,
                              ui_font_entry_name(size), entry)) return false;
  const u16 old_id = applied_font_id;
  const AppliedFontRole old_role = applied_font_role;
  const u8 old_height = applied_ui_height;
  const u32 old_key = applied_ui_key;
  if(apply_font_entry_once(entry, AppliedFontRole::UI, size)) {
    applied_ui_key = 0;
    return true;
  }
  if(!main_lcd().externalFontActive() &&
     restore_applied_font(old_id, old_role, old_height)) {
    applied_ui_key = old_key;
  }
  return false;
}

void program_store_clear_ui_font(void) {
  if(applied_font_role != AppliedFontRole::UI) return;
  main_lcd().clearExternalUiFont();
  applied_font_id = program_store::INVALID_ID;
  applied_font_role = AppliedFontRole::TEXT;
  applied_ui_height = 0;
  applied_ui_key = 0;
  applied_font_suspended = false;
}
#endif

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
  bool restored = false;
#if MK61_PROPORTIONAL_UI_FONTS
  if(applied_font_role == AppliedFontRole::UI && applied_ui_key != 0) {
    u8 height = 0;
    restored = ui_font_entry_by_key(applied_ui_key, entry, height) &&
        height == applied_ui_height &&
        apply_font_entry_once(entry, applied_font_role, height);
  } else
#endif
  {
    restored = program_store::entry_by_id(applied_font_id, entry) &&
        entry.type == program_store::ProgramType::FONT &&
        apply_font_entry_once(entry, applied_font_role, applied_ui_height);
#if MK61_PROPORTIONAL_UI_FONTS
    if(!restored && applied_font_role == AppliedFontRole::UI &&
       applied_ui_key == 0) {
      restored = root_entry_by_type_name(program_store::ProgramType::FONT,
                                         ui_font_entry_name(applied_ui_height),
                                         entry) &&
          apply_font_entry_once(entry, applied_font_role, applied_ui_height);
    }
#endif
  }
  if(!restored) {
    const AppliedFontRole failed_role = applied_font_role;
#if MK61_PROPORTIONAL_UI_FONTS
    const u8 failed_height = applied_ui_height;
#endif
    applied_font_id = program_store::INVALID_ID;
    applied_font_role = AppliedFontRole::TEXT;
    applied_ui_height = 0;
#if MK61_PROPORTIONAL_UI_FONTS
    applied_ui_key = 0;
#endif
    main_lcd().useBuiltinFont();
    if(failed_role == AppliedFontRole::UI) {
#if MK61_PROPORTIONAL_UI_FONTS
      (void) library_mk61::set_ui_font(
          1, failed_height == 12 || failed_height == 16 ? failed_height : 14);
      library_mk61::mark_settings_dirty();
#endif
    } else {
      library_mk61::set_display_text_profile(main_lcd().textProfile());
    }
  }
#endif
}

bool development_select(void) {
  t_punct* items[] = {
    (t_punct*) (library_mk61::language_is_ru() ? mk8::punct_view<t_punct>(RU_EXPLORER_PUNCT) : &EXPLORER_PUNCT),
    (t_punct*) (library_mk61::language_is_ru() ? mk8::punct_view<t_punct>(RU_M61_STORAGE_PUNCT) : &M61_STORAGE_PUNCT),
#if MK61_ENABLE_FOCAL
    (t_punct*) (library_mk61::language_is_ru() ? mk8::punct_view<t_punct>(RU_FOCAL_DEV_PUNCT) : &FOCAL_DEV_PUNCT),
#endif
#if MK61_ENABLE_TINYBASIC
    (t_punct*) (library_mk61::language_is_ru() ? &RU_TINYBASIC_DEV_PUNCT : &TINYBASIC_DEV_PUNCT),
#endif
#if MK61_ENABLE_USB_SCREEN
    (t_punct*) (library_mk61::language_is_ru()
        ? mk8::punct_view<t_punct>(RU_USB_SCREEN_DEV_PUNCT) : &USB_SCREEN_DEV_PUNCT),
#endif
  };

  class_menu menu = class_menu(items, sizeof(items) / sizeof(items[0]));
  return menu.select();
}
