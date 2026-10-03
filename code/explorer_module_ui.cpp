#if defined(MK61_BUILD_EXPLORER_MODULE)

#include "explorer_module_ui.hpp"

#include "bounded_string.hpp"
#include "explorer_label.hpp"
#include "mk8_literal.hpp"
#include "m8_view.hpp"
#include "text_editor.hpp"

#include <stdio.h>
#include <string.h>

namespace explorer_module {
namespace {

using loadable_module::ExplorerAction;
using loadable_module::ExplorerSession;

static constexpr u32 LONG_OK_MS = 1200;
static constexpr i32 KEY_UP = -2;
static constexpr i32 KEY_DOWN = -3;
static constexpr i32 KEY_OK_SHORT = -4;
static constexpr i32 KEY_OK_LONG = -5;
static constexpr i32 KEY_ESCAPE = -6;
static constexpr i32 KEY_TICK = -7;
static constexpr i32 KEY_REDRAW = -8;
static constexpr u16 SCROLL_START_MS = 900;
static constexpr u16 SCROLL_STEP_MS = 450;
static constexpr u16 SCROLL_EDGE_MS = 900;
static constexpr u8 MAX_LINES = MK61_SYSTEM_MAX_ROWS;
static constexpr usize LINE_BYTES = explorer_label::SIZE;

struct Search {
  char text[program_store::NAME_SIZE];
  u16 length;
  text_editor::SmsState sms;
  text_editor::Shift shift;
};

struct Scroll {
  int active;
  char name[explorer_label::SIZE];
  u8 offset;
  i8 direction;
  u32 next_ms;
};

struct Line {
  char text[LINE_BYTES];
  char marker;
};

static bool reached(u32 now, u32 target) {
  return (i32) (now - target) >= 0;
}

static usize bounded_length(const char* text, usize capacity) {
  return text_editor::bounded_length(text, capacity);
}

static void copy_text(char* output, usize capacity, const char* input) {
  if(output == nullptr || capacity == 0) return;
  const usize length = bounded_length(input, capacity - 1);
  memcpy(output, input, length);
  output[length] = 0;
}

static bool entry_at(u16 directory, int index, program_store::Entry& output) {
  return index >= 0 && program_store::child(directory, index, output);
}

static void cursor_off() {
  if(main_lcd().supportsCursor()) main_lcd().cursorOff();
}

static i32 wait_key(bool allow_long_ok, u16 tick_ms = 0) {
  bool ok_down = false;
  u32 long_ok_at = 0;
  const u32 tick_at = tick_ms == 0 ? 0 : millis() + tick_ms;
  const u32 revision = main_lcd().displayModeRevision();

  while(true) {
    idle_main_process();
    if(main_lcd().displayModeRevision() != revision) {
      cursor_off();
      return KEY_REDRAW;
    }
    const u32 now = millis();
    if(tick_ms != 0 && !ok_down && reached(now, tick_at)) return KEY_TICK;
    if(allow_long_ok && ok_down && reached(now, long_ok_at)) {
      kbd::handoff(kbd::Event(KEY_OK));
      return KEY_OK_LONG;
    }

    const i32 event = kbd::poll_event().code();
    if(event < 0) {
      delay(10);
      continue;
    }
    const bool released = (event & (i32) key_state::RELEASED) != 0;
    const i32 key = event & ~(i32) key_state::RELEASED;
    if(released) {
      if(ok_down && key == (i32) KEY_OK) {
        kbd::clear_hold_key();
        return KEY_OK_SHORT;
      }
      continue;
    }
    if(key == (i32) KEY_OK) {
      if(!kbd::is_key_pressed(KEY_OK)) return KEY_OK_SHORT;
      ok_down = true;
      long_ok_at = millis() + LONG_OK_MS;
      continue;
    }
    if(key == (i32) KEY_ESC) {
      kbd::handoff(kbd::Event(event));
      return KEY_ESCAPE;
    }
    if(key == (i32) KEY_RIGHT || key == (i32) KEY_SHG_RIGHT_PRESS)
      return KEY_DOWN;
    if(key == (i32) KEY_LEFT || key == (i32) KEY_SHG_LEFT_PRESS)
      return KEY_UP;
    return key;
  }
}

static bool wait_ok_release() {
  const u32 revision = main_lcd().displayModeRevision();
  while(true) {
    idle_main_process();
    if(main_lcd().displayModeRevision() != revision) return false;
    (void) kbd::scan();
    if(!kbd::is_key_pressed(KEY_OK)) {
      kbd::clear_hold_key();
      return true;
    }
    delay(10);
  }
}

static void wait_handoff() {
  while(kbd::handoff_pending()) {
    idle_main_process();
    (void) kbd::scan();
    delay(10);
  }
}

static void clear_lines(Line (&lines)[MAX_LINES]) {
  memset(lines, 0, sizeof(lines));
}

static void render(Line (&lines)[MAX_LINES]) {
  const u8 count = main_lcd().rows() < MAX_LINES
      ? main_lcd().rows() : MAX_LINES;
  main_lcd().beginUiText();
  if(main_lcd().uiTextActive()) {
    MK61DisplayUpdate update(main_lcd());
    main_lcd().clear();
    for(u8 row = 0; row < count; ++row) {
      main_lcd().printUiLine(row, lines[row].text,
                             lines[row].marker);
    }
    return;
  }

  char fixed[MAX_LINES][LINE_BYTES];
  const char* rows[MAX_LINES];
  const u8 columns = main_lcd().cols() < LINE_BYTES - 1
      ? main_lcd().cols() : (u8) (LINE_BYTES - 1);
  for(u8 row = 0; row < count; ++row) {
    memset(fixed[row], ' ', columns);
    fixed[row][columns] = 0;
    const u8 first = lines[row].marker != 0 ? 1 : 0;
    if(lines[row].marker != 0 && columns != 0)
      fixed[row][0] = lines[row].marker;
    const usize source = bounded_length(lines[row].text, LINE_BYTES - 1);
    const usize capacity = columns > first ? columns - first : 0;
    const usize copied = source < capacity ? source : capacity;
    memcpy(fixed[row] + first, lines[row].text, copied);
    rows[row] = fixed[row];
  }
  portable_system::text_rows(rows, count);
}

static bool search_active(const char* text) {
  return text != nullptr && text[0] != 0;
}

static char ascii_upper(char value) {
  return value >= 'a' && value <= 'z'
      ? (char) (value - 'a' + 'A') : value;
}

static bool contains_ci(const char* text, const char* needle) {
  if(!search_active(needle)) return true;
  if(text == nullptr) return false;
  const usize text_length = bounded_length(text, program_store::NAME_SIZE);
  const usize needle_length = bounded_length(needle, program_store::NAME_SIZE);
  for(usize start = 0; start < text_length; ++start) {
    usize index = 0;
    while(index < needle_length && start + index < text_length &&
          ascii_upper(text[start + index]) == ascii_upper(needle[index]))
      ++index;
    if(index == needle_length) return true;
  }
  return false;
}

static bool matches(u16 directory, int index, const char* search) {
  if(!search_active(search)) return true;
  program_store::Entry entry = {};
  return entry_at(directory, index, entry) && contains_ci(entry.name, search);
}

static int match_count(u16 directory, const char* search) {
  const int count = program_store::child_count(directory);
  if(!search_active(search)) return count;
  int result = 0;
  for(int index = 0; index < count; ++index)
    if(matches(directory, index, search)) ++result;
  return result;
}

static int match_at(u16 directory, int rank, const char* search) {
  const int count = program_store::child_count(directory);
  if(!search_active(search)) return rank >= 0 && rank < count ? rank : -1;
  int current = 0;
  for(int index = 0; index < count; ++index) {
    if(!matches(directory, index, search)) continue;
    if(current++ == rank) return index;
  }
  return -1;
}

static int match_position(u16 directory, int active, const char* search) {
  if(!search_active(search)) return active;
  const int count = program_store::child_count(directory);
  int rank = 0;
  for(int index = 0; index < count; ++index) {
    if(!matches(directory, index, search)) continue;
    if(index == active) return rank;
    ++rank;
  }
  return -1;
}

static int first_match(u16 directory, const char* search) {
  return match_at(directory, 0, search);
}

static int next_match(u16 directory, int active, const char* search) {
  const int count = program_store::child_count(directory);
  if(count <= 0) return active;
  if(!search_active(search)) return active + 1 < count ? active + 1 : 0;
  for(int index = active + 1; index < count; ++index)
    if(matches(directory, index, search)) return index;
  for(int index = 0; index < active; ++index)
    if(matches(directory, index, search)) return index;
  return active;
}

static int previous_match(u16 directory, int active, const char* search) {
  const int count = program_store::child_count(directory);
  if(count <= 0) return active;
  if(!search_active(search)) return active > 0 ? active - 1 : count - 1;
  for(int index = active - 1; index >= 0; --index)
    if(matches(directory, index, search)) return index;
  for(int index = count - 1; index > active; --index)
    if(matches(directory, index, search)) return index;
  return active;
}

static void reset_scroll(Scroll& scroll) {
  scroll.active = -1;
  scroll.name[0] = 0;
  scroll.offset = 0;
  scroll.direction = 1;
  scroll.next_ms = 0;
}

static u16 name_width() {
  if(main_lcd().uiTextActive()) {
    const u16 pixels = main_lcd().uiTextWidth();
    return pixels > 12 ? (u16) (pixels - 12) : 0;
  }
  const u8 columns = main_lcd().cols();
  return columns > 0 ? (u16) (columns - 1) : 0;
}

static u8 max_offset(const char* name, u16 width) {
  const u8 length = (u8) bounded_length(name, explorer_label::SIZE - 1);
  if(main_lcd().uiTextActive()) {
    u8 offset = 0;
    while(offset < length && main_lcd().measureUiText(name + offset) > width)
      ++offset;
    return offset;
  }
  return length > width ? (u8) (length - width) : 0;
}

static void update_scroll(Scroll& scroll, int active, const char* name,
                          u16 width, u32 now) {
  if(scroll.active != active ||
     strncmp(scroll.name, name, sizeof(scroll.name)) != 0) {
    scroll.active = active;
    copy_text(scroll.name, sizeof(scroll.name), name);
    scroll.offset = 0;
    scroll.direction = 1;
    scroll.next_ms = now + SCROLL_START_MS;
  }
  const u8 maximum = max_offset(name, width);
  if(maximum == 0) {
    scroll.offset = 0;
    scroll.direction = 1;
    scroll.next_ms = 0;
    return;
  }
  if(scroll.offset > maximum) scroll.offset = maximum;
  if(!reached(now, scroll.next_ms)) return;
  if(scroll.direction > 0) {
    if(scroll.offset < maximum) ++scroll.offset;
    if(scroll.offset == maximum) {
      scroll.direction = -1;
      scroll.next_ms = now + SCROLL_EDGE_MS;
    } else scroll.next_ms = now + SCROLL_STEP_MS;
  } else {
    if(scroll.offset > 0) --scroll.offset;
    if(scroll.offset == 0) {
      scroll.direction = 1;
      scroll.next_ms = now + SCROLL_EDGE_MS;
    } else scroll.next_ms = now + SCROLL_STEP_MS;
  }
}

static u16 scroll_timeout(const Scroll& scroll, const char* name,
                          u16 width, u32 now) {
  if(max_offset(name, width) == 0 || scroll.next_ms == 0) return 0;
  if(reached(now, scroll.next_ms)) return 1;
  const u32 delta = scroll.next_ms - now;
  return delta > 1000 ? 1000 : (u16) delta;
}

static void search_reset(Search& search) {
  search.text[0] = 0;
  search.length = 0;
  search.shift = text_editor::Shift::NONE;
  text_editor::sms_reset(search.sms);
}

static bool search_insert(Search& search, char value) {
  if((usize) search.length + 1U >= sizeof(search.text)) return false;
  search.text[search.length++] = value;
  search.text[search.length] = 0;
  return true;
}

static bool handle_search_key(Search& search, i32 key) {
  const u32 now = millis();
  if(text_editor::sms_expired(search.sms, now))
    text_editor::sms_reset(search.sms);
  const bool shifted = search.shift != text_editor::Shift::NONE;
  const int digit = text_editor::digit_from_key(key);
  u16 cursor = search.length;

  if(!shifted && search.sms.active) {
    if(text_editor::sms_key_is_letters(key)) {
      return text_editor::sms_tap(search.text, search.length, cursor,
          sizeof(search.text), search.sms, key, now);
    }
    if(text_editor::sms_key_is_space(key) || key == KEY_PP) {
      text_editor::sms_reset(search.sms);
      return search_insert(search, ' ');
    }
    if(digit == 0) {
      text_editor::sms_reset(search.sms);
      return true;
    }
    text_editor::sms_reset(search.sms);
  }
  if(!shifted && (key == KEY_K || key == KEY_ALPHA)) {
    search.shift = key == KEY_K ? text_editor::Shift::K
                                : text_editor::Shift::ALPHA;
    text_editor::sms_reset(search.sms);
    return true;
  }
  if(key == KEY_CX && (search.shift == text_editor::Shift::ALPHA ||
                       kbd::is_key_pressed(KEY_ALPHA))) {
    search_reset(search);
    return true;
  }
  if((key == KEY_UP || key == (i32) KEY_LEFT ||
      key == (i32) KEY_LEFT_PRESS) &&
     (search.shift == text_editor::Shift::ALPHA ||
      kbd::is_key_pressed(KEY_ALPHA))) {
    search.shift = text_editor::Shift::NONE;
    text_editor::sms_reset(search.sms);
    return true;
  }
  if(search.shift == text_editor::Shift::ALPHA && digit >= 0) {
    const char* symbol = text_editor::symbol_for_digit_key(key);
    if(symbol != nullptr && symbol[0] != 0) (void) search_insert(search, symbol[0]);
    search.shift = text_editor::Shift::NONE;
    text_editor::sms_reset(search.sms);
    return true;
  }
  if(search.shift == text_editor::Shift::ALPHA) {
    search.shift = text_editor::Shift::NONE;
    text_editor::sms_reset(search.sms);
    return true;
  }
  if(search.shift == text_editor::Shift::K &&
     text_editor::sms_key_is_letters(key)) {
    (void) text_editor::sms_tap(search.text, search.length,
        cursor, sizeof(search.text), search.sms, key, now);
    search.shift = text_editor::Shift::NONE;
    return true;
  }
  if(search.shift == text_editor::Shift::K &&
     text_editor::sms_key_is_space(key)) {
    text_editor::sms_reset(search.sms);
    (void) search_insert(search, ' ');
    search.shift = text_editor::Shift::NONE;
    return true;
  }
  if(search.shift == text_editor::Shift::K) {
    const char* punctuation = text_editor::kshift_text_for_key(key);
    if(punctuation != nullptr && punctuation[0] != 0 &&
       punctuation[1] == 0) (void) search_insert(search, punctuation[0]);
    text_editor::sms_reset(search.sms);
    search.shift = text_editor::Shift::NONE;
    return true;
  }
  if(!shifted && key == KEY_CX) {
    if(search.length > 0) {
      cursor = search.length;
      (void) text_editor::backspace(search.text, search.length, cursor);
    }
    text_editor::sms_reset(search.sms);
    return true;
  }
  if(key == KEY_PP) {
    text_editor::sms_reset(search.sms);
    (void) search_insert(search, ' ');
    search.shift = text_editor::Shift::NONE;
    return true;
  }
  if(digit >= 0) {
    text_editor::sms_reset(search.sms);
    (void) search_insert(search, (char) ('0' + digit));
    search.shift = text_editor::Shift::NONE;
    return true;
  }
  search.shift = text_editor::Shift::NONE;
  return false;
}

static u16 draw_browser(u16 directory, int active, const Search& search,
                        Scroll& scroll) {
  Line lines[MAX_LINES];
  clear_lines(lines);
  cursor_off();
  const int total = program_store::child_count(directory);
  const bool filtered = search_active(search.text);
  const u8 rows = main_lcd().rows() < MAX_LINES
      ? main_lcd().rows() : MAX_LINES;

  if(total <= 0) {
    copy_text(lines[0].text, LINE_BYTES,
              directory == program_store::ROOT_ID
                  ? (library_mk61::language_is_ru() ? M8("ФС пуста") : "FS is empty")
                  : (library_mk61::language_is_ru() ? M8("Папка пуста") : "Folder empty"));
    if(rows > 1) copy_text(lines[1].text, LINE_BYTES,
        library_mk61::language_is_ru() ? M8("OK: нов. папка") : "OK: new folder");
    reset_scroll(scroll);
    render(lines);
    return 0;
  }

  const int first_row = filtered ? 1 : 0;
  const int list_rows = rows - first_row;
  if(filtered) snprintf(lines[0].text, LINE_BYTES, "?%s", search.text);
  const int matches_count = match_count(directory, search.text);
  if(matches_count <= 0 || list_rows <= 0) {
    if(list_rows > 0) copy_text(lines[first_row].text, LINE_BYTES,
        library_mk61::language_is_ru() ? M8("Нет совпад.") : "No match");
    reset_scroll(scroll);
    render(lines);
    return 0;
  }

  int active_position = match_position(directory, active, search.text);
  if(active_position < 0) active_position = 0;
  const int visible = matches_count < list_rows ? matches_count : list_rows;
  int top = active_position - visible + 1;
  if(top < 0) top = 0;
  if(top > matches_count - visible) top = matches_count - visible;

  const u32 now = millis();
  const u16 width = name_width();
  program_store::Entry selected = {};
  char name[explorer_label::SIZE];
  u16 timeout = 0;
  if(entry_at(directory, active, selected)) {
    explorer_label::format(selected, name);
    update_scroll(scroll, active, name, width, now);
    timeout = scroll_timeout(scroll, name, width, now);
  } else reset_scroll(scroll);

  for(int row = 0; row < visible; ++row) {
    const int index = match_at(directory, top + row, search.text);
    program_store::Entry entry = {};
    if(!entry_at(directory, index, entry)) continue;
    explorer_label::format(entry, name);
    const u8 offset = index == active ? scroll.offset : 0;
    copy_text(lines[first_row + row].text, LINE_BYTES, name + offset);
    lines[first_row + row].marker = index == active ? '>' : ' ';
  }
  render(lines);
  return timeout;
}

static int make_actions(const program_store::Entry& entry,
                        ExplorerAction* output, int capacity) {
  int count = 0;
  const u32 mask = program_store::explorer_actions(entry.id);
  if((mask & loadable_module::EXPLORER_CAN_LOAD) && count < capacity)
    output[count++] = ExplorerAction::LOAD;
  if((mask & loadable_module::EXPLORER_CAN_RUN) && count < capacity)
    output[count++] = ExplorerAction::RUN;
  if((mask & loadable_module::EXPLORER_CAN_VIEW) && count < capacity)
    output[count++] = ExplorerAction::VIEW;
  if((mask & loadable_module::EXPLORER_CAN_EDIT) && count < capacity)
    output[count++] = ExplorerAction::EDIT;
  if(count < capacity) output[count++] = ExplorerAction::NEW_DIRECTORY;
  if(count < capacity) output[count++] = ExplorerAction::RENAME;
  if(count < capacity) output[count++] = ExplorerAction::MOVE;
  if(count < capacity) output[count++] = ExplorerAction::DELETE_ENTRY;
  return count;
}

static const char* action_text(ExplorerAction action) {
  const bool ru = library_mk61::language_is_ru();
  switch(action) {
    case ExplorerAction::LOAD: return ru ? M8("Загрузить") : "Load";
    case ExplorerAction::RUN: return ru ? M8("Запуск") : "Run";
    case ExplorerAction::VIEW: return ru ? M8("Просмотр") : "View";
    case ExplorerAction::EDIT: return ru ? M8("Редактировать") : "Edit";
    case ExplorerAction::NEW_DIRECTORY: return ru ? M8("Новая папка") : "New folder";
    case ExplorerAction::RENAME: return ru ? M8("Переименовать") : "Rename";
    case ExplorerAction::MOVE: return ru ? M8("Переместить") : "Move";
    case ExplorerAction::DELETE_ENTRY: return ru ? M8("Удалить") : "Delete";
    default: return "";
  }
}

static void draw_action_menu(const program_store::Entry& entry, int active) {
  ExplorerAction actions[8];
  const int count = make_actions(entry, actions, 8);
  Line lines[MAX_LINES];
  clear_lines(lines);
  const int rows = main_lcd().rows() < MAX_LINES ? main_lcd().rows() : MAX_LINES;
  const int visible = count < rows ? count : rows;
  int top = active - visible + 1;
  if(top < 0) top = 0;
  if(top > count - visible) top = count - visible;
  for(int row = 0; row < visible; ++row) {
    const int index = top + row;
    copy_text(lines[row].text, LINE_BYTES, action_text(actions[index]));
    lines[row].marker = active == index ? '>' : ' ';
  }
  render(lines);
}

static ExplorerAction choose_action(const program_store::Entry& entry) {
  ExplorerAction actions[8];
  const int count = make_actions(entry, actions, 8);
  int active = 0;
  bool initial_release = true;
  while(count > 0) {
    draw_action_menu(entry, active);
    if(initial_release) {
      if(!wait_ok_release()) continue;
      initial_release = false;
      draw_action_menu(entry, active);
    }
    const i32 key = wait_key(false);
    if(key == KEY_REDRAW) continue;
    if(key == KEY_ESCAPE) return ExplorerAction::NONE;
    if(key == KEY_UP) active = active > 0 ? active - 1 : count - 1;
    else if(key == KEY_DOWN) active = (active + 1) % count;
    else if(key == KEY_OK_SHORT) return actions[active];
  }
  return ExplorerAction::NONE;
}

static bool autoexec(u16 directory, u16& id) {
  const int count = program_store::child_count(directory);
  for(int pass = 0; pass < 2; ++pass) {
    const char* name = pass == 0 ? "autoexec.m61" : "autoexec.tbi";
    const auto type = pass == 0 ? program_store::ProgramType::MK61
                                : program_store::ProgramType::TINYBASIC;
    for(int index = 0; index < count; ++index) {
      program_store::Entry entry = {};
      if(entry_at(directory, index, entry) &&
         entry.kind == program_store::NodeKind::FILE && entry.type == type &&
         strncmp(entry.name, name, program_store::NAME_SIZE) == 0) {
        id = entry.id;
        return true;
      }
    }
  }
  return false;
}

static void set_result(ExplorerSession& session, ExplorerAction action,
                       u16 selected = program_store::INVALID_ID) {
  session.action = action;
  session.selected_id = selected;
}

} // namespace

bool select(ExplorerSession& session) {
  if(session.size != sizeof(session)) return false;
  program_store::Entry directory = {};
  if(session.directory_id != program_store::ROOT_ID &&
     (!program_store::entry_by_id(session.directory_id, directory) ||
      directory.kind != program_store::NodeKind::DIRECTORY)) {
    session.directory_id = program_store::ROOT_ID;
    session.active = 0;
    session.search[0] = 0;
  }
  session.action = ExplorerAction::NONE;
  session.selected_id = program_store::INVALID_ID;

  Search search = {};
  copy_text(search.text, sizeof(search.text), session.search);
  search.length = (u16) bounded_length(search.text, sizeof(search.text));
  search.shift = text_editor::Shift::NONE;
  text_editor::sms_reset(search.sms);
  Scroll scroll;
  reset_scroll(scroll);
  int active = session.active;
  wait_handoff();

  while(true) {
    if(text_editor::sms_expired(search.sms, millis()))
      text_editor::sms_reset(search.sms);
    const int count = program_store::child_count(session.directory_id);
    if(active >= count) active = count > 0 ? count - 1 : 0;
    if(active < 0) active = 0;
    if(search_active(search.text) && !matches(session.directory_id, active, search.text)) {
      const int first = first_match(session.directory_id, search.text);
      if(first >= 0) active = first;
    }

    const u16 timeout = draw_browser(session.directory_id, active, search,
                                     scroll);
    const i32 key = wait_key(count > 0, timeout);
    if(key == KEY_TICK || key == KEY_REDRAW) continue;
    if(key == KEY_ESCAPE) {
      if(search_active(search.text)) {
        search_reset(search);
        reset_scroll(scroll);
        continue;
      }
      if(session.directory_id != program_store::ROOT_ID &&
         program_store::entry_by_id(session.directory_id, directory)) {
        session.directory_id = directory.parent_id;
        active = 0;
        reset_scroll(scroll);
        continue;
      }
      cursor_off();
      session.active = active;
      copy_text(session.search, sizeof(session.search), search.text);
      set_result(session, ExplorerAction::EXIT);
      return true;
    }
    if(handle_search_key(search, key)) {
      const int first = first_match(session.directory_id, search.text);
      if(first >= 0) active = first;
      reset_scroll(scroll);
      continue;
    }

    const int visible = match_count(session.directory_id, search.text);
    if(key == KEY_DOWN && visible > 0) {
      active = next_match(session.directory_id, active, search.text);
      reset_scroll(scroll);
      continue;
    }
    if(key == KEY_UP && visible > 0) {
      active = previous_match(session.directory_id, active, search.text);
      reset_scroll(scroll);
      continue;
    }

    if(count <= 0 && (key == KEY_OK_SHORT || key == KEY_OK_LONG)) {
      session.active = active;
      copy_text(session.search, sizeof(session.search), search.text);
      set_result(session, ExplorerAction::NEW_DIRECTORY);
      return true;
    }

    program_store::Entry entry = {};
    if(visible <= 0 || !entry_at(session.directory_id, active, entry)) continue;
    ExplorerAction requested = ExplorerAction::NONE;
    if(key == KEY_OK_SHORT) {
      if(entry.kind == program_store::NodeKind::DIRECTORY) {
        session.directory_id = entry.id;
        active = 0;
        search_reset(search);
        reset_scroll(scroll);
        u16 autoexec_id = program_store::INVALID_ID;
        if(autoexec(session.directory_id, autoexec_id)) {
          session.active = active;
          session.search[0] = 0;
          set_result(session, ExplorerAction::AUTOEXEC, autoexec_id);
          return true;
        }
        continue;
      }
      const u32 actions = program_store::explorer_actions(entry.id);
      requested = (actions & loadable_module::EXPLORER_CAN_LOAD)
          ? ExplorerAction::LOAD
          : (actions & loadable_module::EXPLORER_CAN_RUN)
              ? ExplorerAction::RUN : ExplorerAction::VIEW;
    } else if(key == KEY_OK_LONG) {
      cursor_off();
      requested = choose_action(entry);
      if(requested == ExplorerAction::NONE) {
        reset_scroll(scroll);
        continue;
      }
    } else continue;

    session.active = active;
    copy_text(session.search, sizeof(session.search), search.text);
    set_result(session, requested, entry.id);
    return true;
  }
}

} // namespace explorer_module

#endif
