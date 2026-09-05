#include "rust_types.h"
#include "rtc_idle_clock_core.hpp"
#include "startup_splash.hpp"
#include "virtual_fat_diagnostic.hpp"
#include "markdown_document.hpp"
#include "markdown_plain.hpp"
#include "markdown_scroll.hpp"
#include "ws0010_charset.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include "ui_geometry.inc"

namespace {
bool russian = false;
lcd_display::TextProfile settings = lcd_display::textProfile5x8();
std::vector<std::string> calls;
std::vector<u32> phases;
struct Surface {
  bool external = false;
  lcd_display::TextProfile profile = lcd_display::textProfile10x16();
  std::string lines[10];
  u8 row = 0;
  u8 rows() const { return profile.rows; }
  void setCursor(u8 x, u8 y) { assert(x == 0 && y < rows()); row = y; lines[row].clear(); }
  void write(u8 byte) { lines[row] += (char) byte; assert(lines[row].size() <= 16); }
  bool externalFontActive() const { return external; }
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

static void expect(const char* scenario, const std::string& actual, const std::string& expected) {
  if(actual != expected) {
    std::fprintf(stderr, "%s\nEXPECTED: [%s]\nACTUAL:   [%s]\n", scenario, expected.c_str(), actual.c_str());
    assert(false);
  }
}

int main() {
  using namespace lcd_display;
  auto profile = textProfile5x8();
  const u8 expected_rows[] = {6, 7, 10, 4};
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

  drawFontSetup(0, four);
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  expect("font dialog EN", surface.lines[0], ">Rows:4         ");
#else
  expect("font dialog EN", surface.lines[0], ">Font:10x16     ");
#endif
  russian = true;
  drawFontSetup(0, four);
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  expect("font dialog RU", surface.lines[0], ">Строки:4");
#else
  expect("font dialog RU", surface.lines[0], ">Шрифт:10x16");
#endif
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
  std::puts("UI contracts: four rows/font confirmation/splash/clock/USB/Markdown/mixed WS0010 PASS");
}
