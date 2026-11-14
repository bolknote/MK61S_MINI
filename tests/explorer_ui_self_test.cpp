#include "explorer_label.hpp"
#include "m8_view.hpp"
#include "mk8_literal.hpp"
#include "loadable_system_api.h"
#include "explorer_autoexec.hpp"
#include "explorer_home.hpp"
#include "fat_name.hpp"
#include "storage_path.hpp"
#include "keyboard_layout.hpp"
#include "loadable_module_abi.hpp"
#include "app_flow.hpp"
#include "explorer_view.hpp"
#include "builtin_font.hpp"

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
static u32 fixture_revision=1;
static unsigned icon_reads=0;
static u8 icon_file[132];
static const char* play_file;
namespace program_store {
u32 catalog_revision() {return fixture_revision;}
bool read_id(u16 id,u8* out,u16 capacity,u16* copied) {
  ++icon_reads;
  if(id!=104 || capacity<sizeof(icon_file)) return false;
  memcpy(out,icon_file,sizeof(icon_file));*copied=sizeof(icon_file);return true;
}
bool read_range_id(u16 id, u16 offset, u8* out, u16 capacity, u16* copied) {
  if(id!=106 || offset || !play_file || strlen(play_file)>capacity) return false;
  *copied=(u16)strlen(play_file);
  memcpy(out,play_file,*copied);
  return true;
}
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

static u32 now,revision_change_at;
u32 millis() { return now; }
void delay(u32 duration) { now += duration; }
void idle_main_process() {
  now += 10;
  if(revision_change_at && now>=revision_change_at) {++fixture_revision;revision_change_at=0;}
}
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
  u8 bitmap[1536]{};
  unsigned frames=0;
  bool fullscreen=false;
  bool supportsFullscreenBitmap() const {return graphical;}
  u16 fullscreenBitmapWidth() const {return graphical?192:0;}
  u16 fullscreenBitmapHeight() const {return graphical?64:0;}
  bool beginFullscreenBitmap() {fullscreen=graphical;return fullscreen;}
  bool showFullscreenBitmap(const u8* bytes,usize count) {
    assert(count==sizeof(bitmap));memcpy(bitmap,bytes,count);++frames;return fullscreen;
  }
  void endFullscreenBitmap() {fullscreen=false;}
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
#if MK61_EXPLORER_GRAPHICS
namespace language_workspace {
constexpr usize SIZE=8192;
enum class Owner {IMAGE_VIEWER};
static bool active=false,available=true;
static u8 memory[SIZE];
struct Lease {
  bool held=false;
  ~Lease() {if(held) active=false;}
  bool acquire(Owner,usize size) {if(!available || active || size>SIZE) return false;active=held=true;return true;}
  bool ok() const {return held;}
  void* data() {return held?memory:nullptr;}
};
}
#endif
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
u32 call(u32 operation,u32 a=0,u32=0,u32=0,void* =nullptr) {
  return operation==MK61_SYS_USBDISK && a==MK61_USBDISK_CATALOG_REVISION ? fixture_revision : 0;
}
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

static bool legacy_launcher(u16 parent, u16& id) {
  program_store::Entry game{};
  if(!explorer_autoexec::find_game(parent,game)) return false;
  id=game.id;
  return true;
}

static void test_game_launcher() {
  auto script=entry("AUTOEXEC",ProgramType::MK61);script.id=101;script.parent_id=17;
  auto basic=entry("autoexec",ProgramType::TINYBASIC);basic.id=102;basic.parent_id=17;
  auto text=entry("autoexec",ProgramType::TEXT);text.id=103;text.parent_id=17;
  entries={basic,text,script};
  u16 id=program_store::INVALID_ID;
  assert(legacy_launcher(17,id) && id==script.id);
  entries={text,basic};
  assert(legacy_launcher(17,id) && id==basic.id);
  entries={text};id=123;
  assert(!legacy_launcher(17,id) && id==123);
  script.parent_id=22;entries={script};resolve_from_parent=true;
  assert(!legacy_launcher(17,id) && id==123);
  resolve_from_parent=false;
  assert(!legacy_launcher(0x7ffe,id) && id==123);
  auto directory=entry("autoexec",ProgramType::MK61,true);
  directory.parent_id=17;entries={directory};
  assert(!legacy_launcher(17,id));
  auto icon=entry("autoexec",ProgramType::IMAGE1);icon.id=104;icon.parent_id=17;
  entries={icon};program_store::Entry image{};
  assert(explorer_autoexec::find_icon(17,image) && image.id==104);
  assert(!legacy_launcher(17,id));
  icon.parent_id=22;entries={icon};resolve_from_parent=true;
  assert(!explorer_autoexec::find_icon(17,image));
  resolve_from_parent=false;

  auto play=entry("Play",ProgramType::TEXT);play.id=106;play.parent_id=17;
  auto quest=entry("game",ProgramType::URQ);quest.id=107;quest.parent_id=17;
  play_file="GAME.URQ\r\n";play.data_len=strlen(play_file);entries={play,quest};
  assert(legacy_launcher(17,id) && id==quest.id);
  play_file="../game.urq\n";entries[0].data_len=strlen(play_file);
  assert(!legacy_launcher(17,id));
  play_file="game.urq\n";entries[0].data_len=strlen(play_file);entries[1].parent_id=22;
  assert(!legacy_launcher(17,id));
  play_file=nullptr;
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
    {ProgramType::MK61_BINARY, ".bin"}, {ProgramType::SHEET, ".mks"},
    {ProgramType::URQ, ".urq"}, {ProgramType::URQ_DATA, ".uqd"},
    {ProgramType::URQ_SAVE, ".urs"}, {ProgramType::EXTERNAL_BINARY, ".bin"}
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
  auto game = entry("Chess", ProgramType::TEXT, true);game.id=22;game.parent_id=17;
  script.parent_id=22;basic.parent_id=22;
  auto icon=entry("autoexec",ProgramType::IMAGE1);icon.id=104;icon.parent_id=17;
  entries = {folder, icon, game, script, basic};
  auto home = session();home.reserved=explorer_home::session_flags(explorer_home::Page::HOME);
  kbd::events({{KEY_OK}, {KEY_OK}});
  assert(app::select(home));
  assert(home.action == ExplorerAction::PLAY && home.directory_id == 17 && home.selected_id == 22);
  kbd::events({{KEY_OK,0,true},{KEY_OK|(i32)key_state::RELEASED,1300},
               {KEY_RIGHT,1301},{KEY_RIGHT,1302},{KEY_OK,1303},{KEY_OK,1304}});
  assert(app::select(home) && home.action==ExplorerAction::LOAD && home.selected_id==101);

  auto documents = session();documents.reserved=explorer_home::session_flags(explorer_home::Page::HOME);
  kbd::events({{KEY_RIGHT},{KEY_RIGHT},{KEY_OK},{KEY_OK}});
  assert(app::select(documents) && documents.action==ExplorerAction::OPEN_DOCUMENTS);

  auto program = entry("game1", ProgramType::MK61); program.id = 201;
  entries = {folder, program};
  auto state = session(); kbd::events({{KEY_OK}, {KEY_ESC}, {KEY_RIGHT}, {KEY_OK}});
  assert(app::select(state) && state.action == ExplorerAction::LOAD);
  assert(state.directory_id == program_store::ROOT_ID && state.selected_id == 201);

  state = session(); kbd::events({{KEY_OK}, {KEY_ESC}, {KEY_ESC}, {KEY_ESC}});
  assert(app::select(state) && state.action == ExplorerAction::EXIT);

  entries = {folder}; state = session(); kbd::events({{KEY_OK}, {KEY_OK}});
  assert(app::select(state) && state.action == ExplorerAction::NEW_DIRECTORY);
  assert(state.directory_id == 17 && state.selected_id == program_store::INVALID_ID);

  program.type = ProgramType::TINYBASIC; entries = {folder, program};
  state = session(); kbd::events({{keyboard_layout::active().digit[1]}, {KEY_OK}});
  assert(app::select(state) && state.action == ExplorerAction::RUN);
  assert(state.selected_id == 201 && strcmp(state.search, "1") == 0);
  kbd::events({{KEY_ESC}, {KEY_ESC}, {KEY_ESC}});
  assert(app::select(state) && state.action == ExplorerAction::EXIT && state.search[0] == 0);

  program.type = ProgramType::MK61; entries = {program}; state = session();
  kbd::events({{KEY_OK, 0, true}, {KEY_OK | (i32) key_state::RELEASED, 1300},
               {KEY_RIGHT, 1301}, {KEY_OK, 1302}});
  assert(app::select(state) && state.action == ExplorerAction::VIEW && state.selected_id == 201);

  state = session(12345); bounded_string::copy(state.search, "stale");
  kbd::events({{KEY_ESC}, {KEY_ESC}});
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
  kbd::events({{KEY_OK}, {KEY_ESC}, {KEY_ESC}});
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

#if MK61_EXPLORER_GRAPHICS
static void test_native_browser() {
  auto first=entry("Chess",ProgramType::MK61,true);first.id=17;
  auto second=entry("High Noon",ProgramType::MK61,true);second.id=22;
  auto third=entry("Eliza",ProgramType::MK61,true);third.id=23;
  auto fourth=entry("Next page",ProgramType::MK61,true);fourth.id=24;
  auto icon=entry("autoexec",ProgramType::IMAGE1);icon.id=104;icon.parent_id=17;icon.data_len=132;
  auto script=entry("autoexec",ProgramType::MK61);script.id=105;script.parent_id=17;
  entries={first,second,third,fourth,icon,script};directory_tree=true;
  memset(icon_file,0xFF,sizeof(icon_file));icon_file[0]=icon_file[1]=0;icon_file[2]=icon_file[3]=32;icon_file[4]=0x7F;
  surface.graphical=true;icon_reads=0;surface.frames=0;
  loadable_module::ExplorerSession session{};session.size=sizeof(session);session.directory_id=program_store::ROOT_ID;
  kbd::events({{KEY_RIGHT},{KEY_RIGHT},{KEY_LEFT},{KEY_LEFT},{KEY_ESC},{KEY_ESC}});
  assert(app::select(session));assert(session.action==loadable_module::ExplorerAction::EXIT);
  assert(icon_reads==1 && surface.frames>=5 && !surface.fullscreen && !language_workspace::active);
  assert(surface.bitmap[(16/8)*192+16]&(1U<<(16&7)));
  for(unsigned x=0;x<192;++x) assert(surface.bitmap[192+x]&8U); // native header, y=11
  // Page transitions reuse the same foreground allocation, never a resident array.
  session.reserved=0;session.active=0;
  kbd::events({{KEY_RIGHT},{KEY_RIGHT},{KEY_RIGHT},{KEY_ESC},{KEY_ESC}});
  assert(app::select(session));assert(session.active==3 && !language_workspace::active);
  // Both the file menu and short OK can browse a launchable folder.
  session.reserved=0;session.active=0;kbd::events({{KEY_OK,0,true},{KEY_OK|(i32)key_state::RELEASED,1400,false},
      {KEY_OK,1450,false},{KEY_ESC,1460},{KEY_ESC,1470},{KEY_ESC,1480}});
  assert(app::select(session));assert(session.action==loadable_module::ExplorerAction::EXIT);
  assert(session.directory_id==program_store::ROOT_ID && !surface.fullscreen && !language_workspace::active);
  session.reserved=0;session.active=0;
  kbd::events({{KEY_OK},{KEY_RIGHT},{KEY_OK}});assert(app::select(session));
  assert(session.action==loadable_module::ExplorerAction::LOAD && session.selected_id==105);
  assert(!surface.fullscreen && !language_workspace::active);
  // Revision changes invalidate an otherwise identical icon cache page.
  first.name[0]=0;bounded_string::copy(first.name,"a-very-long-folder-name");entries[0]=first;
  session.directory_id=program_store::ROOT_ID;session.active=0;icon_reads=0;revision_change_at=500;
  kbd::events({{KEY_ESC,1100},{KEY_ESC}});assert(app::select(session));assert(icon_reads==2);
  // Invalid WBMP falls back and a busy shared arena retains the old text UI.
  icon_file[2]=31;session.reserved=0;session.active=0;kbd::events({{KEY_ESC},{KEY_ESC}});assert(app::select(session));
  assert(!(surface.bitmap[(16/8)*192+16]&(1U<<(16&7))));
  language_workspace::available=false;const unsigned frames=surface.frames;
  session.reserved=0;
  kbd::events({{KEY_ESC},{KEY_ESC}});assert(app::select(session));assert(surface.frames==frames && !language_workspace::active);
  language_workspace::available=true;directory_tree=false;
  puts("Explorer native state machine: cached icons/revision, paging, folder bypass, autoexec, modal cleanup and busy-arena fallback PASS");
}
#endif
int main() {
  test_game_launcher();
  test_extensions();
#if MK61_EXPLORER_GRAPHICS
  test_native_browser();
#else
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
#endif
  printf("Explorer labels and selection: resident/APP, graphical=%d OK\n",
         MK61_PROPORTIONAL_UI_FONTS);
}
