#include "development.hpp"

#include "Arduino.h"
#include "basic.hpp"
#include "config.h"
#include "cross_hal.h"
#include "focal.hpp"
#include "keyboard.h"
#include "lcd_gui.hpp"
#include "lcd_ru.hpp"
#include "menu.hpp"
#include "program_store.hpp"
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

static u8 explorer_buffer[768];

enum class ItemMenuAction : u8 {
  RUN,
  VIEW,
  EDIT,
  DELETE
};

static char type_char(program_store::ProgramType type) {
  switch(type) {
    case program_store::ProgramType::MK61:  return 'M';
    case program_store::ProgramType::BASIC: return 'B';
    case program_store::ProgramType::FOCAL: return 'F';
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
  }
}

static int total_file_count(void) {
  return program_store::count(program_store::ProgramType::MK61) +
         program_store::count(program_store::ProgramType::BASIC) +
         program_store::count(program_store::ProgramType::FOCAL);
}

static bool explorer_entry(int index, program_store::Entry& out) {
  if(index < 0) return false;
  const program_store::ProgramType types[] = {
    program_store::ProgramType::MK61,
    program_store::ProgramType::BASIC,
    program_store::ProgramType::FOCAL
  };

  for(usize i = 0; i < sizeof(types) / sizeof(types[0]); i++) {
    const int count = program_store::count(types[i]);
    if(index < count) return program_store::entry(types[i], index, out);
    index -= count;
  }
  return false;
}

static void draw_explorer(int active) {
  MK61DisplayUpdate update(lcd);
  lcd.clear();

  const int count = total_file_count();
  if(count <= 0) {
    print_localized_line(0, "FS is empty", "ФС пуста");
    print_localized_line(1, "ESC", "ESC");
    return;
  }

  const int visible = (count < lcd_display::ROWS) ? count : lcd_display::ROWS;
  const int max_top = count - visible;
  int top = active - visible + 1;
  if(top < 0) top = 0;
  if(top > max_top) top = max_top;

  for(int row = 0; row < visible; row++) {
    const int index = top + row;
    program_store::Entry entry;
    char line[24];
    if(explorer_entry(index, entry)) {
      snprintf(line, sizeof(line), "%c %-11s %u", type_char(entry.type), entry.name, (u32) entry.data_len);
    } else {
      strcpy(line, "?");
    }

    if(library_mk61::language_is_ru()) {
      lcd_ru::print_menu_line((u8) row, active == index ? '>' : ' ', line);
    } else {
      char out[18];
      snprintf(out, sizeof(out), "%c%s", active == index ? '>' : ' ', line);
      print_line((u8) row, out);
    }
  }
}

static bool read_entry_data(const program_store::Entry& entry, u16& out_len) {
  memset(explorer_buffer, 0, sizeof(explorer_buffer));
  out_len = 0;
  const u16 capacity = (entry.type == program_store::ProgramType::MK61) ? core_61::MAX_PROGRAM_STEP : sizeof(explorer_buffer);
  return program_store::read(entry.type, entry.name, explorer_buffer, capacity, &out_len);
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

static void draw_text_payload_row(u8 row, const u8* data, u16 len, u16 offset) {
  char line[17];
  u8 pos = 0;
  for(; pos < 16 && offset + pos < len; pos++) {
    const char ch = (char) data[offset + pos];
    line[pos] = (ch == '\n' || ch == '\r') ? '|' : ch;
  }
  line[pos] = 0;
  print_line(row, line);
}

static void draw_file_view(const program_store::Entry& entry, const u8* data, u16 len, u16 offset) {
  MK61DisplayUpdate update(lcd);
  lcd.clear();

  char header[24];
  snprintf(header, sizeof(header), "%c %s %u", type_char(entry.type), entry.name, (u32) len);
  print_line(0, header);

  const u8 payload_rows = lcd_display::ROWS > 1 ? lcd_display::ROWS - 1 : 1;
  const u8 bytes_per_row = (entry.type == program_store::ProgramType::MK61) ? 8 : 16;
  for(u8 row = 0; row < payload_rows; row++) {
    const u16 row_offset = (u16) (offset + row * bytes_per_row);
    if(entry.type == program_store::ProgramType::MK61) draw_hex_payload_row((u8) (row + 1), data, len, row_offset);
    else draw_text_payload_row((u8) (row + 1), data, len, row_offset);
  }
}

static void show_message(const char* en0, const char* ru0, const char* en1 = "", const char* ru1 = "") {
  MK61DisplayUpdate update(lcd);
  lcd.clear();
  print_localized_line(0, en0, ru0);
  print_localized_line(1, en1, ru1);
}

static void view_entry(const program_store::Entry& entry) {
  u16 len = 0;
  if(!read_entry_data(entry, len)) {
    show_message("Read error", "Ошибка чтения", entry.name, entry.name);
    kbd::get_key_wait();
    return;
  }

  const u8 rows = lcd_display::ROWS > 1 ? lcd_display::ROWS - 1 : 1;
  const u16 page = (u16) ((entry.type == program_store::ProgramType::MK61) ? rows * 8 : rows * 16);
  u16 offset = 0;
  while(true) {
    draw_file_view(entry, explorer_buffer, len, offset);
    const i32 key = wait_explorer_key(false);
    if(key == EXPLORER_KEY_ESC || key == EXPLORER_KEY_OK) return;
    if(key == EXPLORER_KEY_DOWN && offset + page < len) offset = (u16) (offset + page);
    if(key == EXPLORER_KEY_UP) offset = (offset > page) ? (u16) (offset - page) : 0;
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
    default:
      return false;
  }
}

static int item_menu_actions(const program_store::Entry& entry, ItemMenuAction* actions, int capacity) {
  int count = 0;
  if(entry_can_run(entry) && count < capacity) actions[count++] = ItemMenuAction::RUN;
  if(count < capacity) actions[count++] = ItemMenuAction::VIEW;
  if(entry_can_edit(entry) && count < capacity) actions[count++] = ItemMenuAction::EDIT;
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
    case ItemMenuAction::DELETE:
      return ru ? "Удалить" : "Delete";
  }
  return "";
}

static void draw_item_menu(const program_store::Entry& entry, int active) {
  ItemMenuAction actions[4];
  const int count = item_menu_actions(entry, actions, 4);
  const int visible = (count < lcd_display::ROWS) ? count : lcd_display::ROWS;
  int top = active - visible + 1;
  if(top < 0) top = 0;
  if(top > count - visible) top = count - visible;

  MK61DisplayUpdate update(lcd);
  lcd.clear();

  if(library_mk61::language_is_ru()) {
    const int index0 = top;
    const int index1 = top + 1;
    lcd_ru::print_menu_window(
      active == index0 ? '>' : ' ',
      item_menu_text(actions[index0], true),
      (visible > 1 && index1 < count && active == index1) ? '>' : ' ',
      (visible > 1 && index1 < count) ? item_menu_text(actions[index1], true) : ""
    );
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
    default:
      break;
  }
  if(!ok) {
    show_message("Edit error", "Ошибка правки", entry.name, entry.name);
    delay(900);
  }
}

static bool explorer_item_menu(const program_store::Entry& entry) {
  ItemMenuAction actions[4];
  const int count = item_menu_actions(entry, actions, 4);
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

} // namespace

bool program_store_explorer_select(void) {
  int active = 0;

  while(true) {
    const int count = total_file_count();
    if(count <= 0) {
      draw_explorer(0);
      if(wait_explorer_key(false) == EXPLORER_KEY_ESC) return action::MENU_BACK;
      return action::MENU_BACK;
    }
    if(active >= count) active = count - 1;
    if(active < 0) active = 0;

    draw_explorer(active);
    const i32 key = wait_explorer_key(true);
    if(key == EXPLORER_KEY_ESC) return action::MENU_BACK;
    if(key == EXPLORER_KEY_DOWN && active < count - 1) active++;
    else if(key == EXPLORER_KEY_UP && active > 0) active--;
    else if(key == EXPLORER_KEY_OK) {
      program_store::Entry entry;
      if(explorer_entry(active, entry)) view_entry(entry);
    } else if(key == EXPLORER_KEY_LONG_OK) {
      program_store::Entry entry;
      if(explorer_entry(active, entry) && explorer_item_menu(entry) == action::MENU_EXIT) return action::MENU_EXIT;
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
  };

  class_menu menu = class_menu(items, sizeof(items) / sizeof(items[0]));
  menu.select();
  return action::MENU_BACK;
}
