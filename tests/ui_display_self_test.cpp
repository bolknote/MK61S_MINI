#include "display.hpp"
#include "exclusive_buffer.hpp"
#include "shared_scratch.hpp"
#include <cassert>
#include <cstdlib>
#include <cstdio>
#include <new>

static bool allocation_forbidden = false;
void* operator new(std::size_t bytes) {
  assert(!allocation_forbidden);
  if(void* value = std::malloc(bytes ? bytes : 1)) return value;
  throw std::bad_alloc();
}
void* operator new[](std::size_t bytes) { return ::operator new(bytes); }
void operator delete(void* value) noexcept { std::free(value); }
void operator delete[](void* value) noexcept { std::free(value); }
void operator delete(void* value, std::size_t) noexcept { std::free(value); }
void operator delete[](void* value, std::size_t) noexcept { std::free(value); }

namespace ui_display_test {
const u8* scratch_bytes = nullptr;
usize scratch_size = 0;
u8* bulk_bytes = nullptr;
usize bulk_size = 0;
bool bulk_owned = false;
}

namespace exclusive_buffer {
bool acquire(Owner owner, usize size) {
  if(owner != Owner::DISPLAY_FONT || !ui_display_test::bulk_bytes || size > ui_display_test::bulk_size) return false;
  ui_display_test::bulk_owned = true;
  return true;
}
void release(Owner owner) { if(owner == Owner::DISPLAY_FONT) ui_display_test::bulk_owned = false; }
u8* data(Owner owner) { return owner == Owner::DISPLAY_FONT && ui_display_test::bulk_owned ? ui_display_test::bulk_bytes : nullptr; }
Owner current_owner() { return ui_display_test::bulk_owned ? Owner::DISPLAY_FONT : Owner::NONE; }
}
namespace shared_scratch {
Owner current_owner() { return ui_display_test::scratch_bytes ? Owner::EXPLORER_VIEW : Owner::NONE; }
}
namespace shared_memory {
bool contains(Arena arena, const void* pointer, usize size) {
  if(arena == Arena::BULK) {
    return ui_display_test::bulk_owned && pointer == ui_display_test::bulk_bytes &&
        size <= ui_display_test::bulk_size;
  }
  return arena == Arena::SCRATCH && pointer == ui_display_test::scratch_bytes &&
      size <= ui_display_test::scratch_size;
}
}

namespace {
using ui_display_test::Frame;

bool sameProfile(lcd_display::TextProfile a, lcd_display::TextProfile b) {
  return a.rows == b.rows && a.glyph_width == b.glyph_width &&
      a.glyph_height == b.glyph_height && a.line_gap == b.line_gap;
}

void putPixel(Frame& frame, int x, int y) {
  assert(x >= 0 && x < 192 && y >= 0 && y < 64);
  frame[(unsigned) y / 8U * 192U + (unsigned) x] |= (u8) (1U << (y & 7));
}

// Independent full-frame reference: no page iteration, damage map or Grid.
// It uses the same atlas bytes so the comparison concerns display layout.
void referenceGlyph(Frame& frame, ui_font::Face face, u16 cp,
                     int pen, u8 row, int right = 190) {
  const auto metrics = ui_font::metrics(face);
  const auto glyph = ui_font::glyph(face, cp);
  const int top = 1 + row * (metrics.height + metrics.line_gap) + metrics.ascent - glyph.bearing_y;
  for(u8 y = 0; y < glyph.height; ++y) {
    for(u8 x = 0; x < glyph.width; ++x) {
      const int px = pen + glyph.bearing_x + x;
      if(px >= right) continue;
      if(ui_font::pixel(glyph, x, y)) putPixel(frame, px, top + y);
    }
  }
}

void referenceBuiltin(Frame& frame, ui_font::Face face, u16 cp,
                       int pen, u8 row) {
  builtin_font::Raster raster{};
  assert(builtin_font::decode(builtin_font::FaceId::FONT_5X8, cp, raster));
  const auto metrics = ui_font::metrics(face);
  const int top = 1 + row * (metrics.height + metrics.line_gap) + metrics.ascent - 8;
  for(u8 y = 0; y < raster.height; ++y) {
    for(u8 x = 0; x < raster.width; ++x) {
      if(fmk::bitmapPixel(raster.data, raster.width, x, y)) putPixel(frame, pen + x, top + y);
    }
  }
}

template<std::size_t N>
void referenceText(Frame& frame, ui_font::Face face, const u16 (&text)[N],
                    u8 row, int left = 2, int right = 190) {
  for(u16 cp : text) {
    referenceGlyph(frame, face, cp, left, row, right);
    left += ui_font::glyph(face, cp).advance;
  }
}

void expectFrame(const Frame& expected) {
  if(ui_display_test::frame != expected) {
    for(unsigned byte = 0; byte < expected.size(); ++byte) {
      if(ui_display_test::frame[byte] == expected[byte]) continue;
      std::fprintf(stderr, "frame mismatch: page=%u x=%u actual=%02x expected=%02x\n",
          byte / 192U, byte % 192U, ui_display_test::frame[byte], expected[byte]);
      break;
    }
    assert(false);
  }
}

void startUi(MK61Display& display, u8 family = 1, u8 size = 14) {
  ui_display_test::reset();
  display.begin();
  display.setUiFont(family, size);
  display.beginUiText();
  assert(display.uiTextActive() && display.rows() == 4);
}

void test_profile_and_scope() {
  MK61Display display;
  display.begin();
  const auto calculator = lcd_display::textProfile3x5();
  display.setTextProfile(calculator);
  assert(!display.uiTextActive() && display.rows() == 10);
  display.setUiFont(1, 12);
  {
    MK61DisplayTextScope ui(display);
    assert(display.uiTextActive() && display.rows() == 4);
    assert(sameProfile(display.textProfile(), calculator));
    display.printUiLine(0, "Меню");
    {
      MK61DisplayTextScope code(display, false);
      assert(!display.uiTextActive() && display.rows() == 10);
      display.setCursor(15, 9);
      display.writeCodepoint('5');
      assert(display.cursorX() == 0 && display.cursorY() == 9);
    }
    assert(display.uiTextActive() && display.rows() == 4);
    display.setUiFont(2, 14);
    assert(display.uiFontFamily() == 2 && display.uiFontSize() == 14);
    assert(sameProfile(display.textProfile(), calculator));
    display.setUiFont(0, 14);
    assert(!display.uiTextActive() && display.rows() == 10);
    display.setUiFont(1, 14);
    assert(display.uiTextActive() && display.rows() == 4);
  }
  assert(!display.uiTextActive() && display.rows() == 10);
  assert(sameProfile(display.textProfile(), calculator));
}

void test_preview_of_same_calculator_profile() {
  // One 3x5 A, same geometry as the calculator's profile. This deliberately
  // exercises the unchanged-profile path while UI mode changes underneath.
  u8 font[] = {'F','M','K','1',1,3,5,0x31,1,0,1,0,21,0,0,0,'A',0,0,0x2B,0xED};
  const u16 crc = fmk::checksum(font, sizeof(font));
  font[14] = (u8) crc;
  font[15] = (u8) (crc >> 8);
  ui_display_test::scratch_bytes = font;
  ui_display_test::scratch_size = sizeof(font);
  MK61Display display;
  startUi(display);
  display.endUiText();
  display.setTextProfile(lcd_display::textProfile3x5());
  display.beginUiText();
  assert(display.rows() == 4);
  assert(display.setFontPreview(font, sizeof(font)));
  assert(!display.uiTextActive() && display.rows() == 10);
  display.setCursor(15, 9);
  display.writeCodepoint('A');
  assert(display.cursorX() == 0 && display.cursorY() == 9);
  display.clearFontPreview();
  assert(display.uiTextActive() && display.rows() == 4);
  display.printUiLine(0, "A");
  Frame expected{};
  static constexpr u16 text[] = {'A'};
  referenceText(expected, display.uiFontFace(), text, 0);
  expectFrame(expected);
  ui_display_test::scratch_bytes = nullptr;
  ui_display_test::scratch_size = 0;
}

void test_invalid_custom_slot_uses_ui_fallback() {
  MK61Display display;
  startUi(display);
  display.endUiText();
  display.setTextProfile(lcd_display::textProfile3x5());
  display.beginUiText();
  u8 glyph[8] = {31,17,31,17,31,17,31,0};
  display.createChar(3, glyph);
  display.setCursor(0, 0);
  display.write(3);
  display.writeCodepoint('A');
  display.clearCustomChar(3);
  Frame expected{};
  referenceBuiltin(expected, display.uiFontFace(), '?', 2, 0);
  referenceGlyph(expected, display.uiFontFace(), 'A', 8, 0);
  expectFrame(expected);
}

void test_external_calculator_font_is_isolated_from_ui() {
  // Oversized solid '?' makes inherited calculator metrics visibly wrong.
  // The production FMK parser validates this fixture before installation.
  u8 font[84] = {'F','M','K','1',1,16,32,0xF0,1,0,1,0,84,0,0,0,'?',0,0};
  font[19] = 0x7F; // raw bitmap mode bit followed by seven foreground pixels
  std::memset(font + 20, 0xFF, 63);
  font[83] = 0x80; // last pixel and zero padding
  const u16 crc = fmk::checksum(font, sizeof(font));
  font[14] = (u8) crc;
  font[15] = (u8) (crc >> 8);
  u8 bulk[fmk::MAX_FILE_SIZE]{};
  ui_display_test::bulk_bytes = bulk;
  ui_display_test::bulk_size = sizeof(bulk);
  MK61Display display;
  startUi(display);
  assert(display.installFont(font, sizeof(font)));
  assert(display.externalFontActive() && display.uiTextActive());
  display.printUiLine(0, "A");
  Frame expected{};
  referenceGlyph(expected, display.uiFontFace(), 'A', 2, 0);
  expectFrame(expected);

  display.clear();
  u8 custom[8] = {31,31,31,31,31,31,31,31};
  display.createChar(1, custom);
  display.write(1);
  display.writeCodepoint('A');
  display.clearCustomChar(1);
  expected.fill(0);
  referenceBuiltin(expected, display.uiFontFace(), '?', 2, 0);
  referenceGlyph(expected, display.uiFontFace(), 'A', 8, 0);
  expectFrame(expected);

  display.endUiText();
  assert(display.externalFontActive());
  display.writeCodepoint('?');
  expected.fill(0);
  for(unsigned y = 0; y < 16; ++y) {
    for(unsigned x = 1; x < 11; ++x) putPixel(expected, (int) x, (int) y);
  }
  expectFrame(expected);
  display.useBuiltinFont();
  assert(!display.externalFontActive() && !ui_display_test::bulk_owned);
  ui_display_test::bulk_bytes = nullptr;
  ui_display_test::bulk_size = 0;
}

void test_mixed_text_and_page_parity() {
  static constexpr u16 mixed[] = {'A', 0x0416, 'i', 0x0451, ' ', 'W', '9', 0x0443};
  for(u8 family = 1; family <= 2; ++family) {
    for(u8 size : {12, 14}) {
      MK61Display display;
      startUi(display, family, size);
      Frame expected{};
      for(u8 row = 0; row < 4; ++row) {
        display.printUiLine(row, "AЖiё W9у");
        referenceText(expected, display.uiFontFace(), mixed, row);
      }
      expectFrame(expected);
      u16 advance = 0;
      for(u16 cp : mixed) advance = (u16) (advance + ui_font::glyph(display.uiFontFace(), cp).advance);
      assert(display.measureUiText("AЖiё W9у") == advance);
      assert(display.measureUiText("WWW") > display.measureUiText("iii"));

      // Incremental writes invalidate only intersecting pages. They must
      // produce the same pixels as whole-row replacement on all four rows.
      display.clear();
      for(u8 row = 0; row < 4; ++row) {
        display.setCursor(0, row);
        for(u16 cp : mixed) display.writeCodepoint(cp);
      }
      expectFrame(expected);
    }
  }
}

void test_short_replacement_and_gutters() {
  MK61Display display;
  startUi(display);
  display.printUiLine(0, "Очень длинная строка для замены", '>','M');
  display.printUiLine(1, "Нижняя строка");
  display.printUiLine(0, "A");
  Frame expected{};
  static constexpr u16 a[] = {'A'};
  static constexpr u16 lower[] = {0x041D,0x0438,0x0436,0x043D,0x044F,0x044F,' ',0x0441,0x0442,0x0440,0x043E,0x043A,0x0430};
  referenceText(expected, display.uiFontFace(), a, 0);
  referenceText(expected, display.uiFontFace(), lower, 1);
  expectFrame(expected);

  display.clear();
  display.printUiLine(0, "A", ' ', 'M');
  display.printUiLine(1, "A", '>', 'M');
  expected.fill(0);
  referenceText(expected, display.uiFontFace(), a, 0, 14, 178);
  referenceText(expected, display.uiFontFace(), a, 1, 14, 178);
  referenceGlyph(expected, display.uiFontFace(), '>', 2, 1);
  referenceGlyph(expected, display.uiFontFace(), 'M', 178, 0);
  referenceGlyph(expected, display.uiFontFace(), 'M', 178, 1);
  expectFrame(expected);
  display.printUiLine(0, nullptr);
  for(unsigned y = 0; y < 16; ++y) {
    for(unsigned x = 0; x < 192; ++x) {
      assert((ui_display_test::frame[y / 8U * 192U + x] & (1U << (y & 7U))) == 0);
    }
  }
}

void test_ellipsis_and_invalid_utf8() {
  for(u8 family = 1; family <= 2; ++family) {
    for(u8 size : {12, 14}) {
      MK61Display display;
      startUi(display, family, size);
      char text[101];
      for(char letter : {'W', 'i'}) {
        std::memset(text, letter, sizeof(text) - 1);
        text[sizeof(text) - 1] = 0;
        display.printUiLine(0, text);
        const auto face = display.uiFontFace();
        const unsigned advance = ui_font::glyph(face, letter).advance;
        const unsigned ellipsis = ui_font::glyph(face, 0x2026).advance;
        unsigned count = (188U - ellipsis) / advance;
        if(count > 39) count = 39;
        Frame expected{};
        int pen = 2;
        for(unsigned glyph = 0; glyph < count; ++glyph) {
          referenceGlyph(expected, face, letter, pen, 0);
          pen += advance;
        }
        referenceGlyph(expected, face, 0x2026, pen, 0);
        expectFrame(expected);
      }
      display.printUiLine(0, "\xC0\xAF\xF0\x9F\x98\x80");
      Frame expected{};
      static constexpr u16 invalid[] = {'?', '?', '?'};
      referenceText(expected, display.uiFontFace(), invalid, 0);
      expectFrame(expected);
      assert(display.measureUiText("\xC0\xAF\xF0\x9F\x98\x80") == display.measureUiText("???"));
    }
  }
}

void test_cursor_and_stop_redraw() {
  MK61Display display;
  startUi(display);
  display.printUiLine(0, "WiA");
  const Frame no_cursor = ui_display_test::frame;
  display.setCursor(2, 0);
  display.cursorOn();
  Frame expected = no_cursor;
  const auto face = display.uiFontFace();
  const auto metrics = ui_font::metrics(face);
  const unsigned pen = 2U + ui_font::glyph(face, 'W').advance + ui_font::glyph(face, 'i').advance;
  const unsigned width = ui_font::glyph(face, 'A').advance - 1U;
  for(unsigned x = 0; x < width; ++x) putPixel(expected, (int) (pen + x), metrics.height);
  expectFrame(expected);
  assert(display.deepIdleReady());
  assert(display.prepareDeepIdle());
  assert(ui_display_test::sleeping);
  ui_display_test::frame.fill(0xA5); // panel lost its RAM while asleep
  const unsigned before = ui_display_test::transfers;
  assert(display.resumeDeepIdle());
  assert(!ui_display_test::sleeping && ui_display_test::transfers == before + 8);
  expectFrame(expected);
  assert(display.uiTextActive() && display.cursorX() == 2 && display.cursorY() == 0);
  display.cursorOff();
  expectFrame(no_cursor);
  display.blinkOn();
  expected = no_cursor;
  for(unsigned y = 1; y < 1U + metrics.height; ++y) {
    for(unsigned x = 0; x < width; ++x) {
      expected[y / 8U * 192U + pen + x] ^= (u8) (1U << (y & 7U));
    }
  }
  expectFrame(expected);
  display.blinkOff();
  expectFrame(no_cursor);
  assert(display.beginFullscreenBitmap());
  assert(!display.deepIdleReady());
  display.endFullscreenBitmap();
  assert(display.deepIdleReady());
}

void test_partial_page_overlay_restoration() {
  MK61Display display;
  startUi(display);
  display.printUiLine(0, "WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW");
  const Frame original = ui_display_test::frame;
  const u32 overlay[] = {0x101,0x082,0x044,0x028,0x010,0x010,0x028,0x044,0x082,0x101};
  assert(display.showTopRightOverlay(overlay, 9, 10, 1));
  Frame expected = original;
  for(unsigned y = 0; y < 12; ++y) {
    for(unsigned x = 181; x < 192; ++x) {
      expected[y / 8U * 192U + x] &= (u8) ~(1U << (y & 7U));
    }
  }
  for(unsigned y = 0; y < 10; ++y) {
    for(unsigned x = 0; x < 9; ++x) {
      if(overlay[y] & (1U << x)) putPixel(expected, (int) (182 + x), (int) (1 + y));
    }
  }
  expectFrame(expected);
  display.hideTopRightOverlay();
  expectFrame(original);
}

#if MK61_ENABLE_USB_SCREEN
void test_usb_return_to_ui_geometry() {
  MK61Display display;
  startUi(display);
  const auto calculator = display.textProfile();
  display.printUiLine(0, "ABCD");
  assert(display.enterUsbScreen());
  assert(display.usbScreenActive() && !display.uiTextActive());
  assert(!display.deepIdleReady());
  display.clear();
  display.writeCodepoint('5');
  display.leaveUsbScreen();
  assert(!display.usbScreenActive() && display.uiTextActive());
  assert(display.rows() == 4);
  assert(sameProfile(display.textProfile(), calculator));
  display.printUiLine(0, "ABCD");
  Frame expected{};
  static constexpr u16 text[] = {'A', 'B', 'C', 'D'};
  referenceText(expected, display.uiFontFace(), text, 0);
  expectFrame(expected);
}
#endif
}

int main() {
  static_assert(sizeof(text_screen::Grid) <= 364, "UI must reuse the existing grid");
  allocation_forbidden = true;
  test_profile_and_scope();
  test_preview_of_same_calculator_profile();
  test_invalid_custom_slot_uses_ui_fallback();
  test_external_calculator_font_is_isolated_from_ui();
  test_mixed_text_and_page_parity();
  test_short_replacement_and_gutters();
  test_ellipsis_and_invalid_utf8();
  test_cursor_and_stop_redraw();
  test_partial_page_overlay_restoration();
#if MK61_ENABLE_USB_SCREEN
  test_usb_return_to_ui_geometry();
#endif
  allocation_forbidden = false;
  std::puts("ui_display_self_test: ok");
}
