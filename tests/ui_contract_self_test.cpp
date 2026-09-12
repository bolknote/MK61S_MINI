#include "rust_types.h"
#include "loadable_system_api.h"
#include "rtc_idle_clock_core.hpp"
#include "startup_splash.hpp"
#include "virtual_fat_diagnostic.hpp"
#include "markdown_document.hpp"
#include "markdown_plain.hpp"
#include "markdown_scroll.hpp"
#include "ws0010_charset.hpp"
#include "utf8_view.hpp"
#include "keyboard_core.hpp"
#include "keyboard_layout.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include "ui_geometry.inc"

namespace program_store { static constexpr usize NAME_SIZE = 32; }

namespace {
bool russian = false;
bool ui_fonts_available = false;
bool ui_text_mode_available = false;
lcd_display::TextProfile settings = lcd_display::textProfile5x8();
std::vector<std::string> calls;
std::vector<u32> phases;
struct Surface {
  bool external = false;
  bool ui_text_context = false;
  mk61_setup_ui_font ui_font = {0, 14};
  lcd_display::TextProfile profile = lcd_display::textProfile10x16();
  std::string lines[10];
  bool line_ui_context[10] = {};
  bool line_ui_active[10] = {};
  mk61_setup_ui_font line_fonts[10] = {};
  u8 row = 0;
  bool uiTextActive() const { return ui_text_context; }
  u8 rows() const { return uiTextActive() ? 4 : profile.rows; }
  void clear() {
    for(auto& line : lines) line.clear();
    std::memset(line_ui_context, 0, sizeof(line_ui_context));
    std::memset(line_ui_active, 0, sizeof(line_ui_active));
    std::memset(line_fonts, 0, sizeof(line_fonts));
    calls.emplace_back("clear");
  }
  void recordLine(u8 y, char mark, const char* text) {
    assert(y < rows());
    lines[y] = (mark ? std::string(1, mark) : "") + text;
    line_ui_context[y] = ui_text_context;
    line_ui_active[y] = uiTextActive();
    line_fonts[y] = ui_font;
  }
  void setCursor(u8 x, u8 y) { assert(x == 0 && y < rows()); row = y; lines[row].clear(); }
  void write(u8 byte) { lines[row] += (char) byte; assert(lines[row].size() <= 16); }
  bool externalFontActive() const { return external; }
  u16 measureUiText(const char* text) const {
    const u16 length = (u16) std::strlen(text);
    u16 width = 0;
    for(u16 offset = 0; offset < length;) {
      const u8 bytes = utf8_view::sequence_length((const u8*) text, length, offset);
      width = (u16) (width + (text[offset] == 'i' ? 3 : 13));
      offset = (u16) (offset + bytes);
    }
    return width;
  }
  void useBuiltinFont() { external = false; calls.emplace_back("drop-external"); }
  void setTextProfile(lcd_display::TextProfile value) {
    assert(!external); profile = value; calls.emplace_back("set-profile");
  }
} surface;
Surface& main_lcd() { return surface; }
struct MK61DisplayUpdate { explicit MK61DisplayUpdate(Surface&) {} };
u32 millis() { return 123; }
}
namespace lcd_ru {
void print_menu_line(u8 row, char mark, const char* text) {
  // Recording API only; encoding/CGRAM are covered separately below.
  assert(row < surface.rows()); surface.lines[row] = std::string(1, mark) + text;
}
}
namespace crash_dump {
constexpr u32 RUNTIME_MENU = 5;
void update_runtime(u32 state, u32 detail, u32) {
  assert(state == RUNTIME_MENU); phases.push_back(detail);
}
}
namespace library_mk61 {
bool language_is_ru() { return russian; }
lcd_display::TextProfile display_text_profile() { return settings; }
void set_display_text_profile(lcd_display::TextProfile value) { settings = value; }
void refresh_menu_text() { calls.emplace_back("refresh-menu"); }
void mark_settings_dirty() { calls.emplace_back("save-settings"); }
}
#include "ui_menu.inc"

// Compile the real parent-menu adjustment handler against recording actions.
// Ordinary arrows must reach the menu's navigation dispatcher unconsumed.
constexpr i32 KEY_LEFT_PRESS = keyboard_layout::ACTIVE.left;
constexpr i32 KEY_RIGHT_PRESS = keyboard_layout::ACTIVE.right;
constexpr i32 KEY_SHG_LEFT_PRESS = keyboard_layout::ACTIVE.shg_left;
constexpr i32 KEY_SHG_RIGHT_PRESS = keyboard_layout::ACTIVE.shg_right;
constexpr i32 KEY_OK_PRESS = keyboard_layout::ACTIVE.ok;
constexpr i32 KEY_ESC_PRESS = keyboard_layout::ACTIVE.esc;
namespace library_mk61 { int* SETTINGS_MENU[1] = {}; }
class class_menu {
public:
  int** puncts = library_mk61::SETTINGS_MENU;
  u8 active_punct = library_mk61::SETTINGS_DISPLAY_ROWS;
  void draw() { calls.emplace_back("draw-menu"); }
  bool handle_settings_adjustment(i32 key);
};
void CycleSoundVolumeUp() { assert(false); }
void StepSoundVolume(i8) { assert(false); }
void TurnSpeed() { assert(false); }
void StepSpeedMode(i8) { assert(false); }
void TurnProgramMemory() { assert(false); }
void StepProgramMemoryMode(i8) { assert(false); }
void TurnRandomMode() { assert(false); }
void StepRandomMode(i8) { assert(false); }
void TurnLanguage() { assert(false); }
void TurnIdleSignal() { assert(false); }
void FontSetup() { calls.emplace_back("open-font"); }
namespace setup_ui {
void step_font(i8 delta) {
  assert(delta == -1 || delta == 1);
  calls.emplace_back(delta > 0 ? "font-next" : "font-previous");
}
}
#include "ui_settings_adjustment.inc"

static void test_font_settings_key_dispatch() {
  class_menu menu;
  calls.clear();
  for(i32 key : {KEY_LEFT_PRESS, KEY_RIGHT_PRESS, KEY_ESC_PRESS, -1,
                 KEY_SHG_LEFT_PRESS | keyboard_core::RELEASE_MASK,
                 KEY_SHG_RIGHT_PRESS | keyboard_core::RELEASE_MASK}) {
    assert(!menu.handle_settings_adjustment(key));
    assert(calls.empty());
    assert(menu.active_punct == library_mk61::SETTINGS_DISPLAY_ROWS);
  }
  // UC1609 has a Fonts submenu: neither shifted arrow may silently adjust
  // the separate calculator profile from its parent menu entry.
  assert(!menu.handle_settings_adjustment(KEY_SHG_RIGHT_PRESS));
  assert(calls.empty());
  assert(!menu.handle_settings_adjustment(KEY_SHG_LEFT_PRESS));
  assert(calls.empty());
  assert(menu.handle_settings_adjustment(KEY_OK_PRESS));
  assert((calls == std::vector<std::string>{"open-font"}));

  calls.clear();
  menu.puncts = nullptr;
  for(i32 key : {KEY_LEFT_PRESS, KEY_RIGHT_PRESS, KEY_SHG_LEFT_PRESS,
                 KEY_SHG_RIGHT_PRESS, KEY_OK_PRESS}) {
    assert(!menu.handle_settings_adjustment(key));
    assert(calls.empty());
  }
}

static void expect(const char* scenario, const std::string& actual, const std::string& expected) {
  if(actual != expected) {
    std::fprintf(stderr, "%s\nEXPECTED: [%s]\nACTUAL:   [%s]\n", scenario, expected.c_str(), actual.c_str());
    assert(false);
  }
}

static void test_ui_font_capabilities() {
  for(bool family_service : {false, true}) {
    for(bool text_mode_service : {false, true}) {
      ui_fonts_available = family_service;
      ui_text_mode_available = text_mode_service;
      assert(uiFontSettingsAvailable() == (family_service && text_mode_service));
    }
  }
  ui_fonts_available = ui_text_mode_available = false;
}

static void test_ui_font_layout() {
  const auto saved_settings = settings;
  ui_fonts_available = ui_text_mode_available = true;
  for(bool ru : {false, true}) {
    russian = ru;
    for(u8 calculator_rows : {2, 4, 10}) {
      for(u8 family : {0, 1, 2}) {
        for(u8 size : {12, 14}) {
          const mk61_setup_ui_font font = {family, size};
          assert(uiFontFieldCount(font) == (family == 0 ? 1U : 2U));
          for(u8 active = 0; active < uiFontFieldCount(font); ++active) {
            surface.profile = {calculator_rows, 10,
                               (u8) (calculator_rows == 2 ? 32 : 5), 0};
            const auto calculator_profile = surface.profile;
            surface.external = true;
            surface.ui_text_context = false; // Every redraw must opt in itself.
            surface.ui_font = font;
            for(auto& line : surface.lines) line = "stale calculator text";
            calls.clear();
            phases.clear();
            drawUiFontSetup(active, font);

            const u8 rows = 4;
            assert(surface.rows() == rows);
            assert(surface.ui_text_context);
            assert(surface.uiTextActive());
            assert(surface.external);
            assert(std::memcmp(&surface.profile, &calculator_profile,
                               sizeof(calculator_profile)) == 0);
            assert(std::memcmp(&settings, &saved_settings, sizeof(settings)) == 0);
            assert((phases == std::vector<u32>{0x464E0001}));
            assert(calls.size() >= 3);
            assert(calls[0] == "text-mode-ui" && calls[1] == "clear");
            for(usize i = 2; i < calls.size(); ++i) assert(calls[i] == "text");

            const char* family_line = ru
              ? (family == 0 ? "Шрифт UI:моно" :
                 family == 1 ? "Шрифт UI:DejaVu" : "Шрифт UI:Roboto")
              : (family == 0 ? "UI font:Mono" :
                 family == 1 ? "UI font:DejaVu" : "UI font:Roboto");
            const char* size_line = ru
              ? (size == 12 ? "Размер UI:12" : "Размер UI:14")
              : (size == 12 ? "UI size:12" : "UI size:14");
            std::string expected[10];
            const u8 fields = uiFontFieldCount(font);
            const u8 available = rows > 1 ? (u8) (rows - 1) : 1;
            const u8 visible = available < fields ? available : fields;
            const u8 top = active < visible ? 0 : (u8) (active + 1 - visible);
            for(u8 row = 0; row < visible; ++row) {
              const u8 field = (u8) (top + row);
              char value[32];
              if(field == 0) snprintf(value, sizeof(value), "%s", family_line);
              else snprintf(value, sizeof(value), "%s", size_line);
              expected[row] = std::string(1, field == active ? '>' : ' ') + value;
            }
            expected[rows - 1] = ru ? " Аа Бб Wi 123" : " Aa Bb Wi 123";
            for(u8 row = 0; row < 10; ++row) {
              expect("live UI chooser layout", surface.lines[row], expected[row]);
              if(expected[row].empty()) continue;
              assert(surface.line_ui_context[row]);
              assert(surface.line_ui_active[row]);
              assert(surface.line_fonts[row].family == family);
              assert(surface.line_fonts[row].size == size);
            }
          }
        }
      }
    }
  }
  // Restore the recording surface for independent calculator-profile tests.
  surface = Surface{};
  russian = false;
  ui_fonts_available = ui_text_mode_available = false;
  calls.clear();
  phases.clear();
}

int main() {
  test_font_settings_key_dispatch();
  test_ui_font_capabilities();
  test_ui_font_layout();
  using namespace lcd_display;
  auto profile = textProfile5x8();
  const u8 expected_rows[] = {6, 10, 4};
  for(u8 rows : expected_rows) {
    assert(profile.rows == rows);
    assert((u16) profile.rows * profile.glyph_height + (profile.rows - 1) * profile.line_gap <= 64);
    auto next = library_mk61::nextFontPreset(profile, 1);
    assert(sameTextProfile(profile, library_mk61::nextFontPreset(next, -1)));
    profile = next;
  }
  assert(sameTextProfile(profile, textProfile5x8()));
  const auto four = textProfile10x16();
  assert(four.rows == 4 && four.glyph_width == 10 && four.glyph_height == 16);
  expect("four-line preset name", library_mk61::fontPresetName(four), "10x16");

  drawCalculatorFontSetup(0, four);
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  expect("font dialog EN", surface.lines[0], ">Rows:4         ");
#else
  expect("font dialog EN", surface.lines[0], ">Font:10x16     ");
#endif
  russian = true;
  drawCalculatorFontSetup(0, four);
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  expect("font dialog RU", surface.lines[0], ">Строки:4");
#else
  expect("font dialog RU", surface.lines[0], ">Шрифт:10x16");
#endif

  // The fallback dialog remains available to residents without live UI text.
  assert(sameTextProfile(surface.profile, four));

  const char narrow_name[] = "iiiiiiiiiiiiiiiiiiiiiiiiiiiiiii";
  const char wide_name[] = "WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW";
  const char russian_name[] = "ЩЩЩЩЩЩЩЩЩЩЩЩЩЩЩ";
  assert(ui_editor_window_start(narrow_name, 31, 31) == 0);
  assert(ui_editor_window_start(wide_name, 31, 31) == 19);
  assert(ui_editor_window_start(russian_name, 30, 30) == 6);
  assert(ui_editor_window_start(russian_name, 30, 20) == 0);
  assert(ui_editor_window_start(nullptr, 0, 0) == 0);

  surface.external = true;
  calls.clear(); phases.clear();
  applyFontSetupProfile(four);
  assert((calls == std::vector<std::string>{"drop-external", "set-profile", "refresh-menu", "save-settings"}));
  assert((phases == std::vector<u32>{0x464E0004, 0x464E0005, 0x464E0006}));
  calls.clear();
  applyFontSetupProfile(four);
  assert(calls.empty()); // unchanged confirmation is a no-op

  char error[10];
  virtual_fat::format_error_code(virtual_fat::ErrorCode::FILE_TOO_LARGE, error);
  expect("USB error", error, "USB E1221");
  u8 glyph[8];
  assert(rtc_idle_clock::build_pair_glyph(59, glyph));
  const u8 clock_expected[] = {0,27,19,25,9,27,0,0};
  assert(std::memcmp(glyph, clock_expected, 8) == 0);
  assert(!rtc_idle_clock::build_hour_tens_glyph(24, glyph));
  u32 clock[rtc_idle_clock::GRAPHIC_CLOCK_HEIGHT];
  assert(rtc_idle_clock::build_graphic_clock(23, 59, clock));
  for(u32 row : clock) assert(row >> rtc_idle_clock::GRAPHIC_CLOCK_WIDTH == 0);

  // Final splash cells are stable independently of the selected text profile.
  const char title[] = "0123456789ABCDEF";
  u8 logo[16] = {}, frame[16];
  startup_splash::composeRow(title, logo, startup_splash::FINAL_FRAME, frame);
  assert(std::memcmp(frame, title, 16) == 0);
  assert(startup_splash::escapeMaySkip(startup_splash::EscapePolicy::ALLOW_SKIP));
  assert(!startup_splash::escapeMaySkip(startup_splash::EscapePolicy::IGNORE));

  const char markdown[] = "# Заголовок\n\nEnglish **русский**\n";
  u8 document[512]; u16 size = 0, text_size = 0;
  assert(markdown::compile((const u8*) markdown, sizeof(markdown)-1, document, sizeof(document), size) == markdown::Status::OK);
  markdown::Reader reader(document, size);
  markdown::Event event{};
  assert(reader.next(event) == markdown::Status::OK);
  assert(event.kind == markdown::EventKind::BLOCK_BEGIN && event.block.kind == markdown::BlockKind::HEADING && event.block.level == 1);
  char text[128];
  assert(markdown_plain::convert((const u8*) markdown, sizeof(markdown)-1, text, sizeof(text), text_size) == markdown_plain::Status::OK);
  expect("Markdown header/text", text, "Заголовок\n\nEnglish русский");
  markdown_scroll::Probe probe(48, 64, 8);
  for(u16 y : {0,16,32,48,64,80,96}) probe.note(y);
  auto scroll = probe.finish(112);
  assert(scroll.maximum_top == 48 && scroll.next_anchor == 48 && scroll.previous_anchor == 32);

  const u16 mixed[] = {'X', '=', 0x0416, ' ', 'r', 'u', 'n'}; // X=Ж run
  for(u16 point : mixed) {
    u8 cell = 0;
    assert(ws0010_charset::unicodeToByte(point, cell));
    assert(point == ws0010_charset::canonicalForByte(cell));
  }
  std::puts("UI contracts: unified font values/sample alignment, splash/clock/USB/Markdown/mixed WS0010 PASS");
}
