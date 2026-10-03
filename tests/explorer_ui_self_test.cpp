#include "explorer_label.hpp"
#include "m8_view.hpp"
#include "mk8_literal.hpp"
#include "loadable_system_api.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <vector>

#include "explorer_editor.inc"
#include "explorer_extensions.inc"

static std::vector<program_store::Entry> entries;
namespace program_store {
int child_count(u16) { return (int) entries.size(); }
bool child(u16, int index, Entry& out) {
  if(index < 0 || (usize) index >= entries.size()) return false;
  out = entries[index];
  return true;
}
}

static u32 now;
u32 millis() { return now; }
namespace lcd_display { static constexpr u8 COLS = 16; }
struct Surface {
  bool graphical;
  u8 x = 0, y = 0;
  unsigned cursor_calls = 0;
  std::string lines[4];
  void beginUiText() {}
  bool uiTextActive() const { return graphical; }
  u8 rows() const { return graphical ? 4 : 2; }
  u8 cols() const { return graphical ? 64 : 16; }
  u16 uiTextWidth() const { return 188; }
  u16 measureUiText(const char* text) const {
    u16 width = 0;
    while(*text) width += *text++ == 'i' ? 3 : 8;
    return width;
  }
  bool supportsCursor() const { return true; }
  void cursorOff() {}
  void cursorOn() { ++cursor_calls; }
  void blinkOn() { ++cursor_calls; }
  void clear() { for(auto& line : lines) line.assign(cols(), ' '); }
  void setCursor(u8 col, u8 row) { assert(col < cols() && row < rows()); x = col; y = row; }
  void write(u8 value) { assert(x < cols()); lines[y][x++] = (char) value; }
  void printUiLine(u8 row, const char* text, char marker = 0, u16 trailing = 0) {
    assert(row < rows());
    assert(trailing == 0); // no right-aligned type/directory column
    lines[row] = (marker ? std::string(1, marker) : "") + text;
    lines[row].resize(cols(), ' ');
  }
} surface;
Surface& main_lcd() { return surface; }
struct MK61DisplayUpdate { explicit MK61DisplayUpdate(Surface&) {} };
namespace lcd_ru {
struct font_map_t {};
void scan_text(font_map_t&, const char*, u8) {}
void load_custom_font(const font_map_t&) {}
void write_text(const font_map_t&, const char* text, u8 width) {
  while(width--) {
    surface.write((u8) (*text ? *text : ' '));
    if(*text) ++text;
  }
}
}
namespace library_mk61 {
bool language_is_ru() { return false; }
const char* text(const char* en, const char*) { return en; }
void print_localized_at(u8 col, u8 row, const char*, const char* en, u8 width) {
  surface.setCursor(col, row);
  lcd_ru::write_text({}, en, width);
}
}
namespace portable_system {
void text_rows(const char* const* rows, u32 count) {
  for(u32 row = 0; row < count; ++row) surface.lines[row] = rows[row];
}
}
namespace resident {
// Search editor drawing is unrelated to file-row formatting.
void draw_search_header(const char* query) { surface.printUiLine(0, query, '?'); }
void draw_search_cursor(const char*) { surface.cursorOn(); }
#include "resident_explorer_ui.inc"
}
namespace app {
#include "app_explorer_ui.inc"
}

using program_store::Entry;
using program_store::NodeKind;
using program_store::ProgramType;

static Entry entry(const char* name, ProgramType type, bool directory = false) {
  Entry result = {};
  bounded_string::copy(result.name, name);
  result.type = type;
  result.kind = directory ? NodeKind::DIRECTORY : NodeKind::FILE;
  return result;
}

static void expect_line(u8 row, const std::string& expected) {
  std::string padded = expected;
  padded.resize(surface.cols(), ' ');
  assert(surface.lines[row] == padded);
}

static void test_extensions() {
  const struct { ProgramType type; const char* suffix; } cases[] = {
    {ProgramType::MK61, ".m61"}, {ProgramType::FOCAL, ".foc"},
    {ProgramType::TINYBASIC, ".tbi"}, {ProgramType::TEXT, ".txt"},
    {ProgramType::MK61_STATE, ".state.txt"}, {ProgramType::FONT, ".fmk"},
    {ProgramType::IMAGE1, ".wbmp"}, {ProgramType::APP, ".app"},
    {ProgramType::CHIP8, ".ch8"}, {ProgramType::MARKDOWN, ".md"},
    {ProgramType::MK61_BINARY, ".bin"}
  };
  for(const auto& item : cases) {
    assert(strcmp(program_store::file_extension(item.type),
                  app_store::file_extension(item.type)) == 0);
    for(const char* name : {"manual", "revision.2", M8("Ферзи")}) {
      char label[explorer_label::SIZE];
      explorer_label::format(entry(name, item.type), label);
      assert(label == std::string(name) + item.suffix);
    }
  }
  char label[explorer_label::SIZE];
  explorer_label::format(entry("games", ProgramType::TEXT, true), label);
  assert(strcmp(label, "games/") == 0);
  const std::string longest(31, 'a');
  explorer_label::format(entry(longest.c_str(), ProgramType::MK61_STATE), label);
  assert(label == longest + ".state.txt");
}

static void test_browser(bool graphical) {
  surface.graphical = graphical;
  surface.cursor_calls = 0;
  entries = {entry("manual", ProgramType::MARKDOWN),
             entry("games", ProgramType::TEXT, true)};
  resident::ExplorerScroll resident_scroll = {};
  resident::explorer_scroll_reset(resident_scroll);
  app::Scroll app_scroll = {};
  app::reset_scroll(app_scroll);
  app::Search search = {};
  for(int active : {0, 1, 0}) {
    assert(resident::draw_explorer(0, active, resident_scroll) == 0);
    expect_line(0, std::string(active == 0 ? ">" : " ") + "manual.md");
    expect_line(1, std::string(active == 1 ? ">" : " ") + "games/");
    assert(app::draw_browser(0, active, search, app_scroll) == 0);
    expect_line(0, std::string(active == 0 ? ">" : " ") + "manual.md");
    expect_line(1, std::string(active == 1 ? ">" : " ") + "games/");
  }
  assert(surface.cursor_calls == 0); // selection does not need cursor/blink

  // Search results still have a left selection marker.
  bounded_string::copy(search.text, "games");
  resident::draw_explorer(0, 1, resident_scroll, search.text);
  expect_line(1, ">games/");
  app::draw_browser(0, 1, search, app_scroll);
  expect_line(1, ">games/");

  // Dialogs used by LOAD/SAVE and editors use the very same labels.
  resident::DialogItem item = {resident::DialogItemKind::ENTRY, entries[0]};
  surface.clear();
  resident::draw_dialog_row({}, 0, item, 0, true);
  expect_line(0, ">manual.md");
  item.entry = entries[1];
  resident::draw_dialog_row({}, 1, item, 0, false);
  expect_line(1, " games/");
  item.kind = resident::DialogItemKind::NEW_FILE;
  resident::draw_dialog_row({}, 0, item, 0, true);
  expect_line(0, ">New file");
}

static void test_scrolling(bool graphical) {
  surface.graphical = graphical;
  for(bool directory : {false, true}) {
    const std::string longest(31, 'a');
    entries = {entry(longest.c_str(), ProgramType::MK61_STATE, directory)};
    char label[explorer_label::SIZE];
    explorer_label::format(entries[0], label);
    const u8 offset = resident::explorer_scroll_max_offset(label,
        resident::explorer_name_width());
    assert(offset == app::max_offset(label, app::name_width()));
    assert(offset > 0);
    resident::ExplorerScroll resident_scroll = {};
    resident::explorer_scroll_reset(resident_scroll);
    app::Scroll app_scroll = {};
    app::reset_scroll(app_scroll);
    app::Search search = {};
    now = 0;
    assert(resident::draw_explorer(0, 0, resident_scroll) != 0);
    assert(app::draw_browser(0, 0, search, app_scroll) != 0);
    for(unsigned step = 0; step < offset; ++step) {
      now += 1000;
      resident::draw_explorer(0, 0, resident_scroll);
      assert(resident_scroll.offset == step + 1);
      app::draw_browser(0, 0, search, app_scroll);
      assert(app_scroll.offset == step + 1);
    }
    const std::string expected = std::string(">") + (label + offset);
    expect_line(0, expected);
    resident::draw_explorer(0, 0, resident_scroll);
    expect_line(0, expected); // the suffix is reachable in both implementations
  }
}

int main() {
  test_extensions();
  test_browser(false);
  test_scrolling(false);
#if MK61_PROPORTIONAL_UI_FONTS
  test_browser(true);
  test_scrolling(true);
#endif
  printf("Explorer labels and selection: resident/APP, graphical=%d OK\n",
         MK61_PROPORTIONAL_UI_FONTS);
}
