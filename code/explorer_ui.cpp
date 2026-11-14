#if !defined(MK61_BUILD_EXPLORER_MODULE)
#include "config.h"
#include "Arduino.h"
#include "display.hpp"
#include "cross_hal.h"
#include "development.hpp"
#include "menu.hpp"
#include "lcd_ru.hpp"
extern void idle_main_process(void);
#endif
#if defined(MK61_BUILD_EXPLORER_MODULE) || MK61_EXPLORER_IS_BUILTIN

#include "explorer_ui.hpp"
#include "explorer_autoexec.hpp"
#include "explorer_home.hpp"
#include "explorer_view_config.hpp"
#if MK61_EXPLORER_GRAPHICS
#include "explorer_view.hpp"
#include "builtin_font.hpp"
#include "language_workspace.hpp"
#include "loadable_system_api.h"
#endif

#include "bounded_string.hpp"
#include "explorer_label.hpp"
#include "fat_name.hpp"
#include "mk8_literal.hpp"
#include "text_editor.hpp"

#include <string.h>
#include <stdio.h>

namespace explorer_ui {
namespace {

using loadable_module::ExplorerAction;
using loadable_module::ExplorerSession;
using explorer_home::Page;

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
// Private UI commands are handled before returning the stable host action.
static constexpr ExplorerAction OPEN_DIRECTORY = (ExplorerAction)250;
static constexpr ExplorerAction TOGGLE_VIEW = (ExplorerAction)251;
static constexpr ExplorerAction GAME_FILES = (ExplorerAction)252;
static constexpr u16 MISSING_DIRECTORY = 0xFFFE;
static constexpr u8 LIST_VIEW = 1;

struct Location {
  u16 directory;
  Page page = Page::DISK;
  Location(u16 id, Page view = Page::DISK) : directory(id), page(view) {}
  int count() const {
    if(page == Page::HOME) return explorer_home::COUNT;
    return directory == MISSING_DIRECTORY ? 0 : program_store::child_count(directory);
  }
};

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

static bool entry_at(Location location, int index, program_store::Entry& output) {
  if(index < 0) return false;
  if(location.page == Page::HOME) {
    if(index >= (int)explorer_home::COUNT) return false;
    output = {};
    output.id = (u16) index;
    output.kind = program_store::NodeKind::DIRECTORY;
    copy_text(output.name, sizeof(output.name), explorer_home::label(
        explorer_home::ITEMS[index], library_mk61::language_is_ru()));
    return true;
  }
  return location.directory != MISSING_DIRECTORY &&
      program_store::child(location.directory, index, output) &&
      (location.page != Page::GAMES || output.kind == program_store::NodeKind::DIRECTORY);
}

static u16 section_directory(Page page) {
  if(page == Page::DISK || page == Page::HOME) return program_store::ROOT_ID;
  program_store::Entry entry{};
  for(int i = 0; program_store::child(program_store::ROOT_ID, i, entry); ++i)
    if(entry.kind == program_store::NodeKind::DIRECTORY &&
       fat_name::equal(entry.name, explorer_home::folder(page))) return entry.id;
  return MISSING_DIRECTORY;
}

static void row_name(Location location, const program_store::Entry& entry,
                     char (&out)[explorer_label::SIZE], bool icons) {
  if(location.page == Page::HOME || location.page == Page::GAMES ||
     (location.page == Page::PROGRAMS && entry.type == program_store::ProgramType::APP) ||
     (icons && entry.kind == program_store::NodeKind::DIRECTORY))
    copy_text(out, sizeof(out), entry.name);
  else explorer_label::format(entry, out);
}

static const char* empty_text(Page page, bool filtered) {
  const bool russian = library_mk61::language_is_ru();
  if(filtered) return russian ? M8("Нет совпадений") : "No matches";
  if(page == Page::GAMES) return russian ? M8("Нет игр") : "No games";
  return russian ? M8("Папка пуста") : "Folder empty";
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

  const char* rows[MAX_LINES];
  const u8 columns = main_lcd().cols() < LINE_BYTES - 1
      ? main_lcd().cols() : (u8) (LINE_BYTES - 1);
  for(u8 row = 0; row < count; ++row) {
    char* text = lines[row].text;
    const u8 marker = columns && lines[row].marker ? 1 : 0;
    const usize length = bounded_length(text, columns - marker);
    if(marker) {
      memmove(text + 1, text, length);
      text[0] = lines[row].marker;
    }
    memset(text + marker + length, ' ', columns - marker - length);
    text[columns] = 0;
    rows[row] = text;
  }
#if defined(MK61_BUILD_EXPLORER_MODULE)
  portable_system::text_rows(rows, count);
#else
  MK61DisplayUpdate update(main_lcd());
  main_lcd().clear();
  lcd_ru::print_window(rows, count);
#endif
}

static bool search_active(const char* text) {
  return text != nullptr && text[0] != 0;
}

static bool contains_ci(const char* text, const char* needle) {
  if(!search_active(needle)) return true;
  if(text == nullptr) return false;
  for(; *text; ++text) {
    const char* left = text;
    const char* right = needle;
    while(*right && *left && mk8::fold_case((u8)*left) == mk8::fold_case((u8)*right)) {
      ++left; ++right;
    }
    if(!*right) return true;
  }
  return false;
}

static bool filtering(Location location, const char* search) {
  return location.page == Page::GAMES || search_active(search);
}

static bool matches(Location location, int index, const char* search) {
  if(!filtering(location, search)) return true;
  program_store::Entry entry = {};
  return entry_at(location, index, entry) && contains_ci(entry.name, search);
}

static int match_at(Location location, int rank, const char* search) {
  const int count = location.count();
  if(!filtering(location, search)) return rank >= 0 && rank < count ? rank : -1;
  int current = 0;
  for(int index = 0; index < count; ++index) {
    if(!matches(location, index, search)) continue;
    if(current++ == rank) return index;
  }
  return -1;
}

static int match_position(Location location, int active, const char* search) {
  if(!filtering(location, search)) return active;
  int rank = 0;
  for(int index = 0; index < active; ++index)
    rank += matches(location, index, search);
  return rank;
}

static int first_match(Location location, const char* search) {
  return match_at(location, 0, search);
}

static int move_match(Location location, int active, const char* search, int step) {
  const int count = location.count();
  int index = active;
  for(int i = 0; i < count; ++i) {
    index += step;
    if(index == count) index = 0;
    else if(index < 0) index = count - 1;
    if(matches(location, index, search)) return index;
  }
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

static u16 update_scroll(Scroll& scroll, int active, const char* name,
                         u8 maximum) {
  const u32 now = millis();
  if(scroll.active != active ||
     strncmp(scroll.name, name, sizeof(scroll.name)) != 0) {
    scroll.active = active;
    copy_text(scroll.name, sizeof(scroll.name), name);
    scroll.offset = 0;
    scroll.direction = 1;
    scroll.next_ms = now + SCROLL_START_MS;
  }
  if(maximum == 0) {
    scroll.offset = 0;
    scroll.direction = 1;
    scroll.next_ms = 0;
    return 0;
  }
  if(scroll.offset > maximum) scroll.offset = maximum;
  if(reached(now, scroll.next_ms)) {
    if(scroll.direction > 0 && scroll.offset < maximum) ++scroll.offset;
    else if(scroll.direction < 0 && scroll.offset) --scroll.offset;
    if(scroll.offset == maximum || scroll.offset == 0) {
      scroll.direction = -scroll.direction;
      scroll.next_ms = now + SCROLL_EDGE_MS;
    } else scroll.next_ms = now + SCROLL_STEP_MS;
  }
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

static u16 search_window_start(const char* text) {
  const u16 length = (u16) bounded_length(text, program_store::NAME_SIZE - 1);
  if(!main_lcd().uiTextActive()) {
    const u8 columns = main_lcd().cols();
    const u16 capacity = columns > 2 ? (u16) (columns - 2) : 0;
    return length > capacity ? (u16) (length - capacity) : 0;
  }
  const u16 width = main_lcd().uiTextWidth();
  const u16 capacity = width > 28 ? (u16) (width - 28) : 0;
  u16 start = 0;
  while(start < length && main_lcd().measureUiText(text + start) > capacity)
    ++start; // M8 characters and byte offsets are identical.
  return start;
}

static void draw_search_cursor(const char* text, u16 start) {
  if(!main_lcd().supportsCursor() || main_lcd().cols() == 0) return;
  const u16 length = (u16) bounded_length(text + start, program_store::NAME_SIZE - 1);
  const u16 column = length + 1;
  main_lcd().setCursor((u8) (column < main_lcd().cols()
      ? column : main_lcd().cols() - 1), 0);
  main_lcd().cursorOn();
}

#if MK61_EXPLORER_GRAPHICS
class GraphicalBrowser {
  struct CachedIcon { u16 id;bool valid;explorer_view::Icon image; };
  struct Workspace {
    u8 frame[1536];CachedIcon icons[3];
    u16 directory;int top;u32 revision;bool cached;
  };
  static_assert(sizeof(Workspace)<=language_workspace::SIZE,"Explorer uses the existing foreground workspace");
  language_workspace::Lease lease_;
  bool display_=false;
  u32 display_revision_=0;
  explorer_view::Mode mode_=explorer_view::Mode::ICONS;
  static bool glyph(void*,u8,u16 codepoint,explorer_view::Glyph& output) {
    builtin_font::Raster value{};
    if(!builtin_font::decode(builtin_font::FaceId::FONT_5X8,codepoint,value) &&
       !builtin_font::decode(builtin_font::FaceId::FONT_5X8,'?',value)) return false;
    output={};output.width=value.width;output.height=value.height;
    output.advance=6;output.bearing_y=8;memcpy(output.pixels,value.data,8);return true;
  }
  static u32 revision() {
#if defined(MK61_BUILD_EXPLORER_MODULE)
    return portable_system::call(MK61_SYS_USBDISK,MK61_USBDISK_CATALOG_REVISION);
#else
    return program_store::catalog_revision();
#endif
  }
 public:
  ~GraphicalBrowser() { suspend(); }
  void suspend() {if(display_) main_lcd().endFullscreenBitmap();display_=false;}
  void mode(bool list) {
    const auto next=list?explorer_view::Mode::LIST:explorer_view::Mode::ICONS;
    if(next!=mode_ && lease_.ok()) ((Workspace*)lease_.data())->cached=false;
    mode_=next;
  }
  bool list() const {return mode_==explorer_view::Mode::LIST;}
  bool draw(Location location,int active,const Search& search,Scroll& scroll,u16& timeout) {
    const auto directory = location.directory;
    if(display_ && display_revision_!=main_lcd().displayModeRevision()) suspend();
    if(!main_lcd().supportsFullscreenBitmap() || main_lcd().fullscreenBitmapWidth()!=192 ||
       main_lcd().fullscreenBitmapHeight()!=64) {suspend();return false;}
    // An older host may expose a bitmap surface without the glyph service.
    // Keep its established text renderer instead of drawing unlabeled icons.
    builtin_font::Raster probe{};
    if(!builtin_font::decode(builtin_font::FaceId::FONT_5X8,'?',probe)) {suspend();return false;}
    if(!lease_.ok()) {
      if(!lease_.acquire(language_workspace::Owner::IMAGE_VIEWER,sizeof(Workspace))) return false;
      memset(lease_.data(),0,sizeof(Workspace));
    }
    if(!display_) {
      if(!main_lcd().beginFullscreenBitmap()) return false;
      display_=true;display_revision_=main_lcd().displayModeRevision();
    }
    auto& work=*(Workspace*)lease_.data();
    const auto mode = location.page == Page::GAMES ? explorer_view::Mode::LIST : mode_;
    const explorer_view::Geometry geometry{192,64,mode};
    explorer_view::Canvas canvas(work.frame,sizeof(work.frame),geometry,explorer_view::Packing::PAGE_LSB,glyph);
    canvas.clear();
    const int count=match_position(location,location.count(),search.text);
    const int rank=match_position(location,active,search.text);
    const int top=(rank/geometry.page_size())*geometry.page_size();
    const u32 stamp=revision();
    const bool cache_valid=work.cached && work.directory==directory && work.top==top && work.revision==stamp;
    char title[48],progress[24]{};
    const bool russian = library_mk61::language_is_ru();
    if(search_active(search.text)) {
      title[0]='?';copy_text(title+1,sizeof(title)-1,search.text);
    } else if(location.page == Page::GAMES ||
              directory == program_store::ROOT_ID || directory == MISSING_DIRECTORY)
      copy_text(title, sizeof(title), explorer_home::label(location.page, russian));
    else {
      program_store::Entry current{};
      if(program_store::entry_by_id(directory,current)) copy_text(title,sizeof(title),current.name);
      else title[0]=0;
    }
    if(count>geometry.page_size()) {
      const unsigned page=(unsigned)top/geometry.page_size()+1;
      const unsigned pages=((unsigned)count+geometry.page_size()-1)/geometry.page_size();
      snprintf(progress,sizeof(progress),"%u/%u",page,pages);
    }
    canvas.header(title, progress, russian ? M8("Файл") : "File", true);
    timeout=0;
    for(u8 slot=0;slot<geometry.page_size() && top+slot<count;++slot) {
      const int index=match_at(location,top+slot,search.text);
      program_store::Entry entry{};if(!entry_at(location,index,entry)) continue;
      char name[explorer_label::SIZE];row_name(location,entry,name,true);
      const explorer_view::Icon* image=nullptr;
      if(mode==explorer_view::Mode::ICONS) {
        auto& icon=work.icons[slot];
        if(!cache_valid || icon.id!=entry.id) {
          icon.id=entry.id;icon.valid=false;
          program_store::Entry file{};
          if(entry.kind==program_store::NodeKind::DIRECTORY && explorer_autoexec::find_icon(entry.id,file) &&
             file.data_len && file.data_len<=explorer_view::MAX_ICON_FILE_BYTES) {
            u8 bytes[explorer_view::MAX_ICON_FILE_BYTES];u16 read=0;
            icon.valid=program_store::read_id(file.id,bytes,sizeof(bytes),&read) && read==file.data_len &&
                explorer_view::decode_icon(bytes,read,icon.image);
          }
        }
        if(icon.valid) image=&icon.image;
      }
      if(index==active) {
        const u8 length=(u8)bounded_length(name,sizeof(name)-1);
        const u8 chars=(u8)(geometry.label_width()/6);
        timeout=update_scroll(scroll,active,name,length>chars?(u8)(length-chars):0);
      }
      canvas.item(slot,name,entry.kind==program_store::NodeKind::DIRECTORY?explorer_view::Kind::DIRECTORY:explorer_view::Kind::FILE,
          image,index==active,index==active?scroll.offset:0);
    }
    if(!count) canvas.empty(empty_text(location.page, search_active(search.text)));
    work.cached=true;work.directory=directory;work.top=top;work.revision=stamp;
    if(main_lcd().showFullscreenBitmap(work.frame,sizeof(work.frame))) return true;
    suspend();return false;
  }
};
#endif

static u16 draw_browser(Location location, int active, const Search& search,
                        Scroll& scroll) {
  Line lines[MAX_LINES];
  clear_lines(lines);
  cursor_off();
  const int total = location.count();
  const bool russian = library_mk61::language_is_ru();
  const bool filtered = search_active(search.text);
  const u8 rows = main_lcd().rows() < MAX_LINES
      ? main_lcd().rows() : MAX_LINES;

  if(total <= 0) {
    copy_text(lines[0].text, LINE_BYTES, empty_text(location.page, filtered));
    if(rows > 1 && (location.page == Page::DISK || location.page == Page::DOCUMENTS))
      copy_text(lines[1].text, LINE_BYTES, russian ? M8("OK: нов. папка") : "OK: new folder");
    reset_scroll(scroll);
    render(lines);
    return 0;
  }

  const int first_row = filtered ? 1 : 0;
  const int list_rows = rows - first_row;
  const u16 search_start = filtered ? search_window_start(search.text) : 0;
  if(filtered) {
    copy_text(lines[0].text, LINE_BYTES, search.text + search_start);
    lines[0].marker = '?';
  }
  const int matches_count = match_position(location, total, search.text);
  if(matches_count <= 0 || list_rows <= 0) {
    if(list_rows > 0) copy_text(lines[first_row].text, LINE_BYTES, empty_text(location.page, filtered));
    reset_scroll(scroll);
    render(lines);
    if(filtered) draw_search_cursor(search.text, search_start);
    return 0;
  }

  const int active_position = match_position(location, active, search.text);
  const int visible = matches_count < list_rows ? matches_count : list_rows;
  int top = active_position - visible + 1;
  if(top < 0) top = 0;

  char name[explorer_label::SIZE];
  u16 timeout = 0;
  for(int row = 0; row < visible; ++row) {
    const int index = match_at(location, top + row, search.text);
    program_store::Entry entry = {};
    if(!entry_at(location, index, entry)) continue;
    row_name(location, entry, name, false);
    if(index == active) timeout = update_scroll(scroll, active, name, max_offset(name, name_width()));
    const u8 offset = index == active ? scroll.offset : 0;
    copy_text(lines[first_row + row].text, LINE_BYTES, name + offset);
    lines[first_row + row].marker = index == active ? '>' : ' ';
  }
  render(lines);
  if(filtered) draw_search_cursor(search.text, search_start);
  return timeout;
}

static int make_actions(const program_store::Entry& entry,
                        ExplorerAction (&output)[10], bool games = false) {
  if(games) {
    output[0] = ExplorerAction::PLAY;
    output[1] = ExplorerAction::VIEW;
    output[2] = GAME_FILES;
    return 3;
  }
  int count = 0;
  if(entry.kind == program_store::NodeKind::DIRECTORY) output[count++] = OPEN_DIRECTORY;
#if defined(MK61_BUILD_EXPLORER_MODULE)
  const u32 mask = program_store::explorer_actions(entry.id);
#else
  const u32 mask = program_store_explorer_actions(entry);
#endif
  for(unsigned i = 0; i < 4; ++i) {
    if(!(mask & (1U << i))) continue;
    const auto action = (ExplorerAction)((u8)ExplorerAction::LOAD + i);
    output[count++] = action == ExplorerAction::RUN && entry.kind == program_store::NodeKind::DIRECTORY
        ? ExplorerAction::PLAY : action;
  }
  output[count++] = ExplorerAction::NEW_DIRECTORY;
  output[count++] = ExplorerAction::RENAME;
  output[count++] = ExplorerAction::MOVE;
  output[count++] = ExplorerAction::DELETE_ENTRY;
#if MK61_EXPLORER_GRAPHICS
  if(main_lcd().supportsFullscreenBitmap() &&
     main_lcd().fullscreenBitmapWidth()==192 && main_lcd().fullscreenBitmapHeight()==64)
    output[count++] = TOGGLE_VIEW;
#endif
  return count;
}

static const char* action_text(ExplorerAction action, bool games) {
  const bool ru = library_mk61::language_is_ru();
  if(action==OPEN_DIRECTORY) return ru?M8("Открыть папку"):"Open folder";
  if(action==TOGGLE_VIEW) return ru?M8("Значки / список"):"Icons / list";
  if(action==GAME_FILES) return ru?M8("Файлы игры"):"Game files";
  if(games && action==ExplorerAction::VIEW) return ru?M8("Инструкция"):"Instructions";
  switch(action) {
    case ExplorerAction::LOAD: return ru ? M8("Загрузить") : "Load";
    case ExplorerAction::RUN: return ru ? M8("Запуск") : "Run";
    case ExplorerAction::PLAY: return ru ? M8("Играть") : "Play";
    case ExplorerAction::VIEW: return ru ? M8("Просмотр") : "View";
    case ExplorerAction::EDIT: return ru ? M8("Редактировать") : "Edit";
    case ExplorerAction::NEW_DIRECTORY: return ru ? M8("Новая папка") : "New folder";
    case ExplorerAction::RENAME: return ru ? M8("Переименовать") : "Rename";
    case ExplorerAction::MOVE: return ru ? M8("Переместить") : "Move";
    case ExplorerAction::DELETE_ENTRY: return ru ? M8("Удалить") : "Delete";
    default: return "";
  }
}

static void draw_action_menu(const ExplorerAction* actions, int count, int active, bool games) {
  Line lines[MAX_LINES];
  clear_lines(lines);
  const int rows = main_lcd().rows() < MAX_LINES ? main_lcd().rows() : MAX_LINES;
  const int visible = count < rows ? count : rows;
  int top = active - visible + 1;
  if(top < 0) top = 0;
  for(int row = 0; row < visible; ++row) {
    const int index = top + row;
    copy_text(lines[row].text, LINE_BYTES, action_text(actions[index], games));
    lines[row].marker = active == index ? '>' : ' ';
  }
  render(lines);
}

static ExplorerAction choose_action(const program_store::Entry& entry, bool games) {
  ExplorerAction actions[10];
  const int count = make_actions(entry, actions, games);
  int active = 0;
  bool initial_release = true;
  while(count > 0) {
    draw_action_menu(actions, count, active, games);
    if(initial_release) {
      if(!wait_ok_release()) continue;
      initial_release = false;
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

static void set_result(ExplorerSession& session, ExplorerAction action,
                       u16 selected = program_store::INVALID_ID) {
  session.action = action;
  session.selected_id = selected;
}

} // namespace

bool select(ExplorerSession& session) {
  if(session.size != sizeof(session)) return false;
  Page page = explorer_home::session_page(session.reserved);
  program_store::Entry directory = {};
  if(session.directory_id != program_store::ROOT_ID &&
     (!program_store::entry_by_id(session.directory_id, directory) ||
      directory.kind != program_store::NodeKind::DIRECTORY)) {
    if(page == Page::GAME_FILES) page = Page::GAMES;
    session.directory_id = section_directory(page);
    session.reserved = explorer_home::session_flags(page, session.reserved);
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
#if MK61_EXPLORER_GRAPHICS
  GraphicalBrowser graphics;
  graphics.mode((session.reserved & LIST_VIEW) != 0);
#endif
  auto location = [&] { return Location(session.directory_id, page); };
  auto change_page = [&](Page next, u16 id, int row = 0) {
    page = next;
    session.reserved = explorer_home::session_flags(page, session.reserved);
    session.directory_id = id;
    active = row;
    search_reset(search);
    reset_scroll(scroll);
  };
  wait_handoff();

  while(true) {
    if(text_editor::sms_expired(search.sms, millis()))
      text_editor::sms_reset(search.sms);
    const auto current = location();
    const int count = current.count();
    if(active >= count) active = count > 0 ? count - 1 : 0;
    if(active < 0) active = 0;
    if(!matches(current, active, search.text)) {
      const int first = first_match(current, search.text);
      if(first >= 0) active = first;
    }

    u16 timeout=0;
#if MK61_EXPLORER_GRAPHICS
    if(page == Page::HOME) graphics.suspend();
    if(page == Page::HOME || !graphics.draw(current,active,search,scroll,timeout))
#endif
      timeout=draw_browser(current,active,search,scroll);
    const i32 key = wait_key(count > 0 && page != Page::HOME, timeout);
    if(key == KEY_TICK || key == KEY_REDRAW) continue;
    if(key == KEY_ESCAPE) {
      if(search_active(search.text)) {
        search_reset(search);
        reset_scroll(scroll);
        continue;
      }
      if(page == Page::GAME_FILES && session.directory_id != MISSING_DIRECTORY &&
         program_store::entry_by_id(session.directory_id, directory) &&
         directory.parent_id == section_directory(Page::GAMES)) {
        const u16 games = directory.parent_id;
        program_store::Entry child{};
        int index = 0;
        while(program_store::child(games, index, child) && child.id != directory.id) ++index;
        change_page(Page::GAMES, games, index);
        continue;
      }
      if(page != Page::HOME && (page == Page::GAMES ||
         session.directory_id == section_directory(page) ||
         session.directory_id == MISSING_DIRECTORY)) {
        int index = 0;
        while(index + 1 < (int)explorer_home::COUNT && explorer_home::ITEMS[index] != page) ++index;
        change_page(Page::HOME, program_store::ROOT_ID, index);
        wait_handoff();
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
    if(page != Page::HOME && handle_search_key(search, key)) {
      const int first = first_match(current, search.text);
      if(first >= 0) active = first;
      reset_scroll(scroll);
      continue;
    }

    if(key == KEY_DOWN || key == KEY_UP) {
      active = move_match(current, active, search.text, key == KEY_UP ? -1 : 1);
      reset_scroll(scroll);
      continue;
    }

    if(page == Page::HOME && key == KEY_OK_SHORT) {
      const auto next = explorer_home::ITEMS[active];
      change_page(next, section_directory(next));
      continue;
    }
    if(count <= 0 && (page == Page::DISK || page == Page::DOCUMENTS) &&
       (key == KEY_OK_SHORT || key == KEY_OK_LONG)) {
      session.active = active;
      copy_text(session.search, sizeof(session.search), search.text);
      set_result(session, session.directory_id == MISSING_DIRECTORY
          ? ExplorerAction::OPEN_DOCUMENTS : ExplorerAction::NEW_DIRECTORY);
      return true;
    }

    program_store::Entry entry = {};
    if(!entry_at(current, active, entry) || !contains_ci(entry.name, search.text)) continue;
    ExplorerAction requested = ExplorerAction::NONE;
    if(key == KEY_OK_SHORT) {
      if(page == Page::GAMES) requested = ExplorerAction::PLAY;
      else if(entry.kind == program_store::NodeKind::DIRECTORY) {
        session.directory_id = entry.id;
        active = 0;
        search_reset(search);
        reset_scroll(scroll);
        continue;
      } else {
#if defined(MK61_BUILD_EXPLORER_MODULE)
        const u32 mask = program_store::explorer_actions(entry.id);
#else
        const u32 mask = program_store_explorer_actions(entry);
#endif
        requested = mask & loadable_module::EXPLORER_CAN_LOAD ? ExplorerAction::LOAD :
            mask & loadable_module::EXPLORER_CAN_RUN ? ExplorerAction::RUN : ExplorerAction::VIEW;
      }
    } else if(key == KEY_OK_LONG) {
      cursor_off();
#if MK61_EXPLORER_GRAPHICS
      graphics.suspend();
#endif
      requested = choose_action(entry, page == Page::GAMES);
      if(requested == ExplorerAction::NONE) {
        reset_scroll(scroll);
        continue;
      }
    } else continue;

    if(requested == OPEN_DIRECTORY || requested == GAME_FILES) {
      change_page(requested == GAME_FILES ? Page::GAME_FILES : page, entry.id);
      continue;
    }
#if MK61_EXPLORER_GRAPHICS
    if(requested==TOGGLE_VIEW) {
      graphics.mode(!graphics.list());session.reserved=(u8)((session.reserved&~1U)|(graphics.list()?1U:0U));
      reset_scroll(scroll);continue;
    }
#endif

    session.active = active;
    copy_text(session.search, sizeof(session.search), search.text);
    cursor_off();
    set_result(session, requested, entry.id);
    return true;
  }
}

uint32_t flow_step(mk61_app_flow* flow) {
  if(!mk61_app_flow_compatible(flow) ||
     flow->context_size != sizeof(ExplorerSession) || flow->current.phase > 1) return 0;
  auto& session = *(ExplorerSession*)flow->context;
  if(flow->current.phase == 1) {
    if(flow->status != MK61_FLOW_OK) {
      mk61_app_flow_exit(flow, 0, flow->status); return 1;
    }
    if(flow->result && (session.action == ExplorerAction::LOAD ||
        session.action == ExplorerAction::RUN || session.action == ExplorerAction::AUTOEXEC ||
        session.action == ExplorerAction::PLAY)) {
      mk61_app_flow_exit(flow, 1, MK61_FLOW_OK); return 1;
    }
    session.action = ExplorerAction::NONE;
    session.selected_id = program_store::INVALID_ID;
  }
  if(!select(session)) return 0;
  if(session.action == ExplorerAction::EXIT) mk61_app_flow_exit(flow, 0, MK61_FLOW_OK);
  else mk61_app_flow_call(flow,
      mk61_app_flow_to(MK61_APP_FLOW_HOST, MK61_APP_FLOW_SYSTEM_FILE,
                       (uint32_t)session.action), 1);
  return 1;
}

} // namespace explorer_ui

#endif
