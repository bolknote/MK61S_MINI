#include "explorer_label.hpp"
#include "m8_view.hpp"
#include "mk8_literal.hpp"
#include "loadable_system_api.h"
#include "explorer_autoexec.hpp"
#include "storage_path.hpp"
#include "keyboard_layout.hpp"
#include "loadable_module_abi.hpp"
#include "app_flow.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <vector>

#define KEY_LEFT (keyboard_layout::active().left)
#define KEY_RIGHT (keyboard_layout::active().right)
#define KEY_OK (keyboard_layout::active().ok)
#define KEY_ESC (keyboard_layout::active().esc)
#define KEY_K (keyboard_layout::active().k)
#define KEY_ALPHA (keyboard_layout::active().alpha)
#define KEY_CX (keyboard_layout::active().cx)
#define KEY_PP (keyboard_layout::active().pp)
#define KEY_LEFT_PRESS KEY_LEFT
#define KEY_SHG_LEFT_PRESS (keyboard_layout::active().shg_left)
#define KEY_SHG_RIGHT_PRESS (keyboard_layout::active().shg_right)

#include "explorer_editor.inc"
#include "explorer_extensions.inc"

static std::vector<program_store::Entry> entries;
static bool resolve_from_parent;
static bool directory_tree;
namespace program_store {
int child_count(u16 directory) {
  int count = 0;
  for(const auto& entry : entries)
    if(!directory_tree || entry.parent_id == directory) ++count;
  return count;
}
bool child(u16 directory, int index, Entry& out) {
  if(index < 0) return false;
  for(const auto& entry : entries) {
    if(directory_tree && entry.parent_id != directory) continue;
    if(index-- == 0) { out = entry; return true; }
  }
  return false;
}
bool entry_by_id(u16 id, Entry& out) {
  for(const auto& entry : entries)
    if(entry.id == id) { out = entry; return true; }
  if(id!=17 && id!=22) return false;
  out={};out.id=id;out.kind=NodeKind::DIRECTORY;
  return true;
}
u32 explorer_actions(u16 id) {
  Entry entry = {};
  if(!entry_by_id(id, entry) || entry.kind == NodeKind::DIRECTORY) return 0;
  using namespace loadable_module;
  if(entry.type == ProgramType::MK61) return EXPLORER_CAN_LOAD | EXPLORER_CAN_VIEW;
  if(entry.type == ProgramType::TINYBASIC) return EXPLORER_CAN_RUN | EXPLORER_CAN_VIEW;
  return EXPLORER_CAN_VIEW;
}
}
u32 program_store_explorer_actions(const program_store::Entry& entry) {
  return program_store::explorer_actions(entry.id);
}
namespace storage_path {
Status resolve_file(u16 directory,const char* name,program_store::ProgramType type,
                    program_store::Entry& out) {
  for(const auto& e:entries) {
    if(e.kind!=program_store::NodeKind::FILE || e.type!=type ||
       (!resolve_from_parent && e.parent_id!=directory))continue;
    char label[explorer_label::SIZE];explorer_label::format(e,label);
    if(strcasecmp(label,name)==0) { out=e;return Status::OK; }
  }
  return Status::NOT_FOUND;
}
}

static u32 now;
u32 millis() { return now; }
void delay(u32 duration) { now += duration; }
void idle_main_process() { now += 10; }
enum class key_state { RELEASED = 0x40 };
namespace kbd {
struct Event {
  i32 value;
  explicit Event(i32 value) : value(value) {}
  i32 code() const { return value; }
};
struct Input { i32 key; u32 at = 0; bool held = false; };
std::vector<Input> input;
usize position;
bool ok_held;
unsigned polls;
Event poll_event() {
  assert(++polls < 10000); // A missing/consumed event must fail, not hang CI.
  if(position == input.size() || now < input[position].at) return Event(-1);
  const Input next = input[position++];
  if((next.key & ~(i32) key_state::RELEASED) == KEY_OK)
    ok_held = next.held;
  return Event(next.key);
}
bool is_key_pressed(i32 key) { return key == KEY_OK && ok_held; }
void clear_hold_key() {}
void handoff(Event) {}
bool handoff_pending() { return false; }
Event scan() {
  if(position < input.size() && now >= input[position].at &&
     (input[position].key & (i32) key_state::RELEASED)) return poll_event();
  return Event(-1);
}
void events(std::initializer_list<Input> keys) {
  input = keys; position = polls = 0; now = 0; ok_held = false;
}
}
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
  u32 displayModeRevision() const { return 0; }
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
void print_window(const char* const* rows,u8 count) {
  for(u8 row=0;row<count;++row) surface.lines[row]=rows[row];
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
  result.parent_id = program_store::ROOT_ID;
  return result;
}

static void test_app_autoexec_uses_basename_and_type() {
  auto script=entry("AUTOEXEC",ProgramType::MK61);script.id=101;script.parent_id=17;
  auto basic=entry("autoexec",ProgramType::TINYBASIC);basic.id=102;basic.parent_id=17;
  auto text=entry("autoexec",ProgramType::TEXT);text.id=103;text.parent_id=17;
  entries={basic,text,script};
  u16 id=program_store::INVALID_ID;
  assert(app::autoexec(17,id) && id==script.id); // M61 priority, case-insensitive.
  entries={text,basic};
  assert(app::autoexec(17,id) && id==basic.id);
  entries={text};id=123;
  assert(!app::autoexec(17,id) && id==123);
  script.parent_id=22;entries={script};resolve_from_parent=true;
  assert(!app::autoexec(17,id) && id==123); // Never inherit a parent's autoexec.
  resolve_from_parent=false;
  assert(!app::autoexec(0x7ffe,id) && id==123);
  auto directory=entry("autoexec",ProgramType::MK61,true);
  directory.parent_id=17;entries={directory};
  assert(!app::autoexec(17,id));
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
  app::Scroll app_scroll = {};
  app::reset_scroll(app_scroll);
  app::Search search = {};
  for(int active : {0, 1, 0}) {
    assert(app::draw_browser(0, active, search, app_scroll) == 0);
    expect_line(0, std::string(active == 0 ? ">" : " ") + "manual.md");
    expect_line(1, std::string(active == 1 ? ">" : " ") + "games/");
  }
  assert(surface.cursor_calls == 0); // selection does not need cursor/blink

  // Search results still have a left selection marker.
  bounded_string::copy(search.text, "games");
  app::draw_browser(0, 1, search, app_scroll);
  expect_line(1, ">games/");
  assert(surface.cursor_calls == 1 && surface.x == 6 && surface.y == 0);
  bounded_string::copy(search.text, "1234567890123456789012345678901");
  app::draw_browser(0, 1, search, app_scroll);
  const u16 start = app::search_window_start(search.text);
  assert(start > 0 && surface.x < surface.cols());
  expect_line(0, std::string("?") + (search.text + start));

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

static loadable_module::ExplorerSession session(u16 directory = program_store::ROOT_ID) {
  return {sizeof(loadable_module::ExplorerSession), directory,
          program_store::INVALID_ID, 0, loadable_module::ExplorerAction::NONE, 0, {0}};
}

static void test_select_flow(bool graphical) {
  using loadable_module::ExplorerAction;
  surface.graphical = graphical;
  directory_tree = true;
  auto folder = entry("games", ProgramType::TEXT, true); folder.id = 17;
  auto script = entry("AUTOEXEC", ProgramType::MK61); script.id = 101; script.parent_id = 17;
  auto basic = entry("autoexec", ProgramType::TINYBASIC); basic.id = 102; basic.parent_id = 17;
  for(const auto& files : {std::vector<Entry>{folder, basic, script},
                           std::vector<Entry>{folder, basic}}) {
    entries = files;
    auto state = session(); kbd::events({{KEY_OK}});
    assert(app::select(state));
    assert(state.action == ExplorerAction::AUTOEXEC && state.directory_id == 17);
    assert(state.selected_id == files.back().id && state.search[0] == 0);
  }

  auto program = entry("game1", ProgramType::MK61); program.id = 201;
  entries = {folder, program};
  auto state = session(); kbd::events({{KEY_OK}, {KEY_ESC}, {KEY_RIGHT}, {KEY_OK}});
  assert(app::select(state) && state.action == ExplorerAction::LOAD);
  assert(state.directory_id == program_store::ROOT_ID && state.selected_id == 201);

  state = session(); kbd::events({{KEY_OK}, {KEY_ESC}, {KEY_ESC}});
  assert(app::select(state) && state.action == ExplorerAction::EXIT);

  entries = {folder}; state = session(); kbd::events({{KEY_OK}, {KEY_OK}});
  assert(app::select(state) && state.action == ExplorerAction::NEW_DIRECTORY);
  assert(state.directory_id == 17 && state.selected_id == program_store::INVALID_ID);

  program.type = ProgramType::TINYBASIC; entries = {folder, program};
  state = session(); kbd::events({{keyboard_layout::active().digit[1]}, {KEY_OK}});
  assert(app::select(state) && state.action == ExplorerAction::RUN);
  assert(state.selected_id == 201 && strcmp(state.search, "1") == 0);
  kbd::events({{KEY_ESC}, {KEY_ESC}});
  assert(app::select(state) && state.action == ExplorerAction::EXIT && state.search[0] == 0);

  program.type = ProgramType::MK61; entries = {program}; state = session();
  kbd::events({{KEY_OK, 0, true}, {KEY_OK | (i32) key_state::RELEASED, 1300},
               {KEY_RIGHT, 1301}, {KEY_OK, 1302}});
  assert(app::select(state) && state.action == ExplorerAction::VIEW && state.selected_id == 201);

  state = session(12345); bounded_string::copy(state.search, "stale");
  kbd::events({{KEY_ESC}});
  assert(app::select(state) && state.directory_id == program_store::ROOT_ID && state.search[0] == 0);
  state.size = 0; kbd::events({});
  assert(!app::select(state) && kbd::position == 0);
  directory_tree = false;
}

struct ExplorerFlowBackend { unsigned actions = 0; bool leave = false; };
static app_flow::Status explorer_flow_backend(
    void* raw, const app_flow::Target& target, app_flow::Step& step) {
  auto& backend = *(ExplorerFlowBackend*)raw;
  if(target.kind == MK61_APP_KIND_EXPLORER)
    return app::flow_step(&step) ? MK61_FLOW_OK : MK61_FLOW_CORRUPT;
  assert(target.kind == MK61_APP_FLOW_HOST);
  auto& state = *(loadable_module::ExplorerSession*)step.context;
  assert(target.phase == (uint32_t)state.action);
  ++backend.actions;
  mk61_app_flow_return(&step, backend.leave ? 1 : 0, MK61_FLOW_OK);
  return MK61_FLOW_OK;
}
static void test_generic_explorer_flow(bool graphical) {
  surface.graphical = graphical; directory_tree = true;
  auto file = entry("manual", ProgramType::TEXT); file.id = 201;
  entries = {file};
  auto state = session(); ExplorerFlowBackend backend;
  uint32_t result = 42;
  kbd::events({{KEY_OK}, {KEY_ESC}});
  assert(app_flow::run(mk61_app_flow_to(MK61_APP_KIND_EXPLORER, 0xFFFF, 0),
      &state, sizeof(state), result, explorer_flow_backend, &backend) == MK61_FLOW_OK);
  assert(!result && backend.actions == 1 && state.action == loadable_module::ExplorerAction::EXIT);
  file.type = ProgramType::TINYBASIC; entries = {file};
  state = session(); backend = {}; backend.leave = true;
  kbd::events({{KEY_OK}});
  assert(app_flow::run(mk61_app_flow_to(MK61_APP_KIND_EXPLORER, 0xFFFF, 0),
      &state, sizeof(state), result, explorer_flow_backend, &backend) == MK61_FLOW_OK);
  assert(result == 1 && backend.actions == 1);
  directory_tree = false;
}

static void test_scrolling(bool graphical) {
  surface.graphical = graphical;
  for(bool directory : {false, true}) {
    const std::string longest(31, 'a');
    entries = {entry(longest.c_str(), ProgramType::MK61_STATE, directory)};
    char label[explorer_label::SIZE];
    explorer_label::format(entries[0], label);
    const u8 offset = resident::file_dialog_scroll_max_offset(label,
        resident::file_dialog_name_width());
    assert(offset == app::max_offset(label, app::name_width()));
    assert(offset > 0);
    app::Scroll app_scroll = {};
    app::reset_scroll(app_scroll);
    app::Search search = {};
    now = 0;
    assert(app::draw_browser(0, 0, search, app_scroll) != 0);
    for(unsigned step = 0; step < offset; ++step) {
      now += 1000;
      app::draw_browser(0, 0, search, app_scroll);
      assert(app_scroll.offset == step + 1);
    }
    const std::string expected = std::string(">") + (label + offset);
    expect_line(0, expected);
    app::draw_browser(0,0,search,app_scroll);
    expect_line(0, expected); // The same UI is compiled into resident and APP.
  }
}

int main() {
  test_app_autoexec_uses_basename_and_type();
  test_extensions();
  test_browser(false);
  test_scrolling(false);
  test_select_flow(false);
  test_generic_explorer_flow(false);
#if MK61_PROPORTIONAL_UI_FONTS
  test_browser(true);
  test_scrolling(true);
  test_select_flow(true);
  test_generic_explorer_flow(true);
#endif
  printf("Explorer labels and selection: resident/APP, graphical=%d OK\n",
         MK61_PROPORTIONAL_UI_FONTS);
}
