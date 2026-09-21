#include "display.hpp"
#include "calculator_face.hpp"
#include "display_symbols.hpp"
#include "exclusive_buffer.hpp"
#include "lcd_ru.hpp"
#include "mk8_codec.hpp"
#include "mk8_strings.inc"
#include "rtc_idle_clock_core.hpp"
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
const u8* workspace_bytes = nullptr;
usize workspace_size = 0;
u8* bulk_bytes = nullptr;
usize bulk_size = 0;
bool bulk_owned = false;
}

MK61Display* main_lcd_pointer = nullptr;

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
Owner active_owner(Arena arena) {
  return arena == Arena::WORKSPACE && ui_display_test::workspace_bytes
      ? Owner::SETUP : Owner::NONE;
}
bool contains(Arena arena, const void* pointer, usize size) {
  if(arena == Arena::BULK) {
    return ui_display_test::bulk_owned && pointer == ui_display_test::bulk_bytes &&
        size <= ui_display_test::bulk_size;
  }
  if(arena == Arena::WORKSPACE) {
    return pointer == ui_display_test::workspace_bytes &&
        size <= ui_display_test::workspace_size;
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

u8 referenceUiRows(ui_font::Face face) {
  const auto metrics = ui_font::metrics(face);
  return (u8) ((64U + metrics.line_gap) /
               (metrics.height + metrics.line_gap));
}

u8 referenceUiTop(ui_font::Face face) {
  const auto metrics = ui_font::metrics(face);
  const u8 rows = referenceUiRows(face);
  const unsigned occupied = rows * metrics.height +
      (rows - 1U) * metrics.line_gap;
  return (u8) ((64U - occupied) / 2U);
}

// Independent full-frame reference: no page iteration, damage map or Grid.
// It uses the same atlas bytes so the comparison concerns display layout.
void referenceGlyph(Frame& frame, ui_font::Face face, u16 cp,
                     int pen, u8 row, int right = 190) {
  const auto metrics = ui_font::metrics(face);
  const auto glyph = ui_font::glyph(face, cp);
  const int top = referenceUiTop(face) +
      row * (metrics.height + metrics.line_gap) + metrics.ascent - glyph.bearing_y;
  for(u8 y = 0; y < glyph.height; ++y) {
    for(u8 x = 0; x < glyph.width; ++x) {
      const int px = pen + glyph.bearing_x + x;
      if(px >= right) continue;
      if(font_glyph::pixel(glyph, x, y)) putPixel(frame, px, top + y);
    }
  }
}

void referenceBuiltin(Frame& frame, ui_font::Face face, u16 cp,
                       int pen, u8 row) {
  builtin_font::Raster raster{};
  assert(builtin_font::decode(builtin_font::FaceId::FONT_5X8, cp, raster));
  const auto metrics = ui_font::metrics(face);
  const int top = referenceUiTop(face) +
      row * (metrics.height + metrics.line_gap) + metrics.ascent - 8;
  for(u8 y = 0; y < raster.height; ++y) {
    for(u8 x = 0; x < raster.width; ++x) {
      if(fmk::bitmapPixel(raster.data, raster.width, x, y)) putPixel(frame, pen + x, top + y);
    }
  }
}

void putMsbBit(u8* bytes, usize& bit, bool value) {
  if(value) bytes[bit / 8U] |= (u8) (0x80U >> (bit & 7U));
  ++bit;
}

// Minimal, valid FMK2 UI face: space plus '?'..'A', mono 3x12 with a four-pixel
// advance.  It is built without heap allocation so the display test keeps
// enforcing the firmware's allocation-free rendering contract.
void makeExternalUiFont(u8 (&font)[39]) {
  std::memset(font, 0, sizeof(font));
  std::memcpy(font, "FMK2", 4);
  font[4] = fmk::FLAG_MONOSPACED;
  font[5] = 3;
  font[6] = 12;
  font[7] = 0x31; // advance=4, line gap=1
  font[8] = 4;
  font[10] = 2;
  font[12] = (u8) sizeof(font);
  font[16] = ' ';
  font[17] = 0;
  font[18] = '?';
  font[19] = 2; // '?', '@', 'A'
  usize bit = 20U * 8U;
  for(u8 glyph = 0; glyph < 4; ++glyph) {
    putMsbBit(font, bit, false); // raw bitmap
    for(u8 y = 0; y < 12; ++y) {
      for(u8 x = 0; x < 3; ++x) {
        bool pixel = false;
        if(glyph == 1) { // '?'
          pixel = y == 0 || (x == 2 && y < 4) ||
              (x == 1 && (y == 4 || y == 7));
        } else if(glyph == 2) { // '@'
          pixel = y == 0 || y == 6 || x == 0 || x == 2;
        } else if(glyph == 3) { // 'A'
          pixel = (x == 1 && y == 0) ||
              ((x == 0 || x == 2) && y > 0) || y == 5;
        }
        putMsbBit(font, bit, pixel);
      }
    }
  }
  assert(bit <= sizeof(font) * 8U && bit > (sizeof(font) - 1U) * 8U);
  const u16 crc = fmk::checksum(font, sizeof(font));
  font[14] = (u8) crc;
  font[15] = (u8) (crc >> 8);
}

// The game face deliberately uses the smallest supported geometry. Four
// glyph records are exactly two bytes each at 3x5 (raw flag + 15 pixels).
void makeExternalRuntimeFont(u8 (&font)[28], u8 advance = 4) {
  std::memset(font, 0, sizeof(font));
  std::memcpy(font, "FMK2", 4);
  font[4] = fmk::FLAG_MONOSPACED;
  font[5] = 3;
  font[6] = 5;
  assert(advance >= 3 && advance <= 16);
  font[7] = (u8) (((advance - 1U) << 4U) | 1U);
  font[8] = 4;
  font[10] = 2;
  font[12] = (u8) sizeof(font);
  font[16] = ' ';
  font[17] = 0;
  font[18] = '?';
  font[19] = 2; // '?', '@', 'A'
  usize bit = 20U * 8U;
  for(u8 glyph = 0; glyph < 4; ++glyph) {
    putMsbBit(font, bit, false);
    for(u8 y = 0; y < 5; ++y) {
      for(u8 x = 0; x < 3; ++x) {
        const bool pixel = glyph != 0 &&
            (y == 0 || y == 4 || x == 0 || x == 2);
        putMsbBit(font, bit, pixel);
      }
    }
  }
  assert(bit == sizeof(font) * 8U);
  const u16 crc = fmk::checksum(font, sizeof(font));
  font[14] = (u8) crc;
  font[15] = (u8) (crc >> 8);
}

// Runtime proportional faces retain a nominal advance in their header. It is
// the cell-oriented COLS contract for BASIC even though rendering uses each
// glyph's own advance.
void makeExternalRuntimeProportionalFont(u8 (&font)[31]) {
  std::memset(font, 0, sizeof(font));
  std::memcpy(font, "FMK2", 4);
  font[5] = 3;
  font[6] = 5;
  font[7] = 0x31; // nominal advance=4, line gap=1
  font[8] = 4;
  font[10] = 2;
  font[12] = (u8) sizeof(font);
  font[16] = ' ';
  font[17] = 0;
  font[18] = '?';
  font[19] = 2; // '?', '@', 'A'
  usize bit = 20U * 8U;
  for(u8 glyph = 0; glyph < 4; ++glyph) {
    const u8 width = glyph == 0 ? 1U : 3U;
    const u8 advance = glyph == 0 ? 2U : 4U;
    for(i8 shift = 3; shift >= 0; --shift)
      putMsbBit(font, bit, ((width - 1U) & (1U << shift)) != 0);
    for(i8 shift = 3; shift >= 0; --shift)
      putMsbBit(font, bit, ((advance - 1U) & (1U << shift)) != 0);
    putMsbBit(font, bit, false);
    for(u8 y = 0; y < 5; ++y) {
      for(u8 x = 0; x < width; ++x) {
        const bool pixel = glyph != 0 &&
            (y == 0 || y == 4 || x == 0 || x + 1U == width);
        putMsbBit(font, bit, pixel);
      }
    }
  }
  assert(bit <= sizeof(font) * 8U && bit > (sizeof(font) - 1U) * 8U);
  const u16 crc = fmk::checksum(font, sizeof(font));
  font[14] = (u8) crc;
  font[15] = (u8) (crc >> 8);
}

void referenceExternal(Frame& frame, const prepared_font::Face& face, u16 cp,
                       int pen, u8 row, int right = 190) {
  prepared_font::Glyph glyph = {};
  if(!face.glyph(cp, glyph)) assert(face.glyph('?', glyph));
  u8 bitmap[fmk::MAX_BITMAP_SIZE] = {};
  assert(face.decode(glyph, bitmap, sizeof(bitmap)));
  const auto& metrics = face.metrics();
  const u8 rows = (u8) ((64U + metrics.line_gap) /
                        (metrics.height + metrics.line_gap));
  const unsigned occupied = rows * metrics.height +
      (rows - 1U) * metrics.line_gap;
  const int top = (64U - occupied) / 2U +
      row * (metrics.height + metrics.line_gap);
  for(u8 y = 0; y < glyph.height; ++y) {
    for(u8 x = 0; x < glyph.width; ++x) {
      if(pen + x < right && fmk::bitmapPixel(bitmap, glyph.width, x, y)) {
        putPixel(frame, pen + x, top + y);
      }
    }
  }
}

template<usize N>
usize prepareFont(const u8 (&source)[N], u8* output, usize capacity) {
  fmk::Face face;
  assert(face.open(source, N));
  usize size = 0;
  assert(fmk::prepare(face, output, capacity, size));
  return size;
}

void referenceMono(Frame& frame, u16 cp, int pen, u8 row) {
  builtin_font::Raster raster{};
  assert(builtin_font::decode(builtin_font::FaceId::FONT_5X8, cp, raster));
  const int top = 1 + row * 16 + 4;
  for(u8 y = 0; y < raster.height; ++y) {
    for(u8 x = 0; x < raster.width; ++x) {
      if(fmk::bitmapPixel(raster.data, raster.width, x, y)) {
        putPixel(frame, pen + x, top + y);
      }
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
  const u8 expected_rows = family == 0 ? 4U : referenceUiRows(display.uiFontFace());
  assert(display.uiTextActive() && display.rows() == expected_rows);
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
    assert(display.uiTextActive() && display.rows() == 5);
    assert(sameProfile(display.textProfile(), calculator));
    display.printUiLine(0, M8_TEST_MENU);
    {
      MK61DisplayTextScope code(display, false);
      assert(!display.uiTextActive() && display.rows() == 10);
      display.setCursor(15, 9);
      display.writeCodepoint('5');
      assert(display.cursorX() == 0 && display.cursorY() == 9);
    }
    assert(display.uiTextActive() && display.rows() == 5);
    display.setUiFont(2, 14);
    // A persisted/portable legacy Roboto value is migrated to Pixel at the
    // display boundary, so no stale third family can leak back into the UI.
    assert(display.uiFontFamily() == 1 && display.uiFontSize() == 14 &&
           display.rows() == 4);
    assert(sameProfile(display.textProfile(), calculator));
    display.setUiFont(0, 14);
    assert(display.uiTextActive() && display.rows() == 4);
    assert(sameProfile(display.textProfile(), calculator));
    display.setUiFont(1, 14);
    assert(display.uiTextActive() && display.rows() == 4);
    display.setUiFont(1, 16);
    assert(display.uiTextActive() && display.rows() == 3);
  }
  assert(!display.uiTextActive() && display.rows() == 10);
  assert(sameProfile(display.textProfile(), calculator));
}

void test_localized_message_selects_ui_renderer() {
  MK61Display display;
  main_lcd_pointer = &display;
  ui_display_test::reset();
  display.begin();
  display.setUiFont(1, 14);
  display.beginCalculatorFace();
  assert(!display.uiTextActive());

  lcd_ru::print_lines("USB Disk", "starting...");
  assert(display.uiTextActive());
  assert(display.uiFontFamily() == 1);

  lcd_ru::print_fixed_lines("CGRAM", "diagnostic");
  assert(!display.uiTextActive());
}

void test_preview_of_same_calculator_profile() {
  // One 3x5 A, same geometry as the calculator's profile. This deliberately
  // exercises the unchanged-profile path while UI mode changes underneath.
  u8 font[] = {'F','M','K','2',1,3,5,0x31,1,0,1,0,20,0,0,0,
               'A',0,0x2B,0xED};
  const u16 crc = fmk::checksum(font, sizeof(font));
  font[14] = (u8) crc;
  font[15] = (u8) (crc >> 8);
  u8 prepared[prepared_font::MAX_IMAGE_SIZE] = {};
  const usize prepared_size = prepareFont(font, prepared, sizeof(prepared));
  ui_display_test::workspace_bytes = prepared;
  ui_display_test::workspace_size = prepared_size;
  MK61Display display;
  startUi(display);
  display.endUiText();
  display.setTextProfile(lcd_display::textProfile3x5());
  display.beginUiText();
  assert(display.rows() == 4);
  assert(display.setFontPreview(prepared, (u16) prepared_size));
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
  ui_display_test::workspace_bytes = nullptr;
  ui_display_test::workspace_size = 0;
}

void test_live_ui_font_sample() {
  MK61Display display;
  display.begin();
  const auto calculator = lcd_display::textProfile3x5();
  display.setTextProfile(calculator);
  // The chooser renders its sample on the last UI row, aligned to the text
  // after the menu gutter. Use the real paged renderer, not a mock.
  const u8 faces[][2] = {{1, 12}, {1, 14}, {1, 16}, {2, 16}, {1, 16}};
  static constexpr u16 sample[] = {0x0410, 0x0430, ' ', 0x0411, 0x0431,
                                 ' ', 'W', 'i', ' ', '1', '2', '3'};
  Frame previous{};
  for(unsigned i = 0; i < sizeof(faces) / sizeof(faces[0]); ++i) {
    display.setUiFont(faces[i][0], faces[i][1]);
    display.beginUiText();
    display.clear();
    const u8 sample_row = (u8) (display.rows() - 1U);
    display.printUiLine(sample_row, M8_TEST_FONT_SAMPLE, ' ');
    Frame expected{};
    referenceText(expected, display.uiFontFace(), sample, sample_row, 14);
    expectFrame(expected);
    assert(sameProfile(display.textProfile(), calculator));
    if(i > 0 && i < 3) assert(ui_display_test::frame != previous);
    if(i >= 3) assert(ui_display_test::frame == previous);
    previous = ui_display_test::frame;
  }
  display.setUiFont(0, 14);
  assert(display.uiTextActive() && display.rows() == 4);
}

void test_mono_ui_is_fixed_and_independent() {
  MK61Display display;
  startUi(display, 0, 14);
  display.printUiLine(0, M8_TEST_AA_WI);
  Frame expected{};
  const u16 text[] = {0x0410, 0x0430, ' ', 'W', 'i'};
  int pen = 2;
  for(u16 cp : text) {
    referenceMono(expected, cp, pen, 0);
    pen += 6;
  }
  expectFrame(expected);
  const Frame at_14 = ui_display_test::frame;
  display.setUiFont(0, 12);
  display.printUiLine(0, M8_TEST_AA_WI);
  expectFrame(expected);
  assert(ui_display_test::frame == at_14);
  assert(display.measureUiText("WWW") == display.measureUiText("iii"));
}

void writeGridLine(text_screen::Grid& grid, u8 row, u8 column,
                   const char* text) {
  grid.setCursor(column, row);
  while(*text) grid.writeCodepoint((u8) *text++);
}

void writeDisplayLine(MK61Display& display, u8 row, u8 column,
                      const char* text) {
  display.setCursor(column, row);
  while(*text) display.writeCodepoint((u8) *text++);
}

bool framePixel(const Frame& frame, unsigned x, unsigned y) {
  return (frame[y / 8U * 192U + x] & (1U << (y & 7U))) != 0;
}

void test_fixed_calculator_face() {
  text_screen::Grid model;
  model.reset(6);
  writeGridLine(model, 0, 0, "RUN");
  model.setCursor(6, 0);
  model.writeCodepoint(display_symbol::uc1609::CYR_GHE);
  model.writeCodepoint('P');
  model.writeCodepoint(display_symbol::uc1609::CYR_DE);
  writeGridLine(model, 0, 10, "F SIN");
  writeGridLine(model, 1, 0, "-12.34567 -09");
  Frame expected{};
  calculator_face::renderFrame(model, expected.data());

  MK61Display display;
  display.begin();
  ui_display_test::reset();
  {
    MK61DisplayUpdate update(display);
    display.clear();
    writeDisplayLine(display, 0, 0, "RUN");
    display.setCursor(6, 0);
    display.writeCodepoint(display_symbol::uc1609::CYR_GHE);
    display.writeCodepoint('P');
    display.writeCodepoint(display_symbol::uc1609::CYR_DE);
    writeDisplayLine(display, 0, 10, "F SIN");
    writeDisplayLine(display, 1, 0, "-12.34567 -09");
    display.beginCalculatorFace();
  }
  assert(display.calculatorFaceActive());
  assert(ui_display_test::transfers == 8);
  expectFrame(expected);

  // В покое часы занимают правое поле текущей команды. Скрытие обязано
  // восстановить исходную мнемонику пиксель-в-пиксель и на новом фиксированном
  // лице калькулятора, а не только в обычном текстовом UI.
  const Frame without_clock = expected;
  u32 clock[rtc_idle_clock::GRAPHIC_CLOCK_HEIGHT] = {};
  assert(rtc_idle_clock::build_graphic_clock(12, 34, clock));
  assert(display.showTopRightOverlay(
      clock, rtc_idle_clock::GRAPHIC_CLOCK_WIDTH,
      rtc_idle_clock::GRAPHIC_CLOCK_HEIGHT,
      rtc_idle_clock::GRAPHIC_CLOCK_CLEAR_BORDER));
  const unsigned clock_total_width = rtc_idle_clock::GRAPHIC_CLOCK_WIDTH +
      rtc_idle_clock::GRAPHIC_CLOCK_CLEAR_BORDER * 2U;
  const unsigned clock_total_height = rtc_idle_clock::GRAPHIC_CLOCK_HEIGHT +
      rtc_idle_clock::GRAPHIC_CLOCK_CLEAR_BORDER * 2U;
  const unsigned clock_left = 192U - clock_total_width;
  expected = without_clock;
  for(unsigned y = 0; y < clock_total_height; ++y) {
    for(unsigned x = clock_left; x < 192U; ++x) {
      expected[y / 8U * 192U + x] &= (u8) ~(1U << (y & 7U));
    }
  }
  for(unsigned y = 0; y < rtc_idle_clock::GRAPHIC_CLOCK_HEIGHT; ++y) {
    for(unsigned x = 0; x < rtc_idle_clock::GRAPHIC_CLOCK_WIDTH; ++x) {
      if((clock[y] & ((u32) 1U << x)) != 0) {
        putPixel(expected,
                 (int) (clock_left + rtc_idle_clock::GRAPHIC_CLOCK_CLEAR_BORDER + x),
                 (int) (rtc_idle_clock::GRAPHIC_CLOCK_CLEAR_BORDER + y));
      }
    }
  }
  expectFrame(expected);
  display.hideTopRightOverlay();
  expected = without_clock;
  expectFrame(expected);

  // Twelve 16-pixel cells occupy the full 192-pixel glass. The 35-pixel
  // strike ends at y=58, including the decimal point on the last page.
  // Slot 2 owns the point, slot 3 begins at x=48, the exponent sign at x=144.
  assert(framePixel(expected, 46, 52) && framePixel(expected, 45, 58));
  assert(framePixel(expected, 53, 24));
  assert(framePixel(expected, 149, 37) && !framePixel(expected, 148, 37));

  // Preserve the asymmetric chamfers and widening of the supplied raster;
  // replacing it with a generic straight seven-segment face is a regression.
  text_screen::Grid one;
  one.reset(6);
  writeGridLine(one, 1, 0, "1");
  Frame straight{};
  calculator_face::renderFrame(one, straight.data());
  assert(framePixel(straight, 14, 26));
  assert(!framePixel(straight, 13, 26));
  assert(!framePixel(straight, 15, 26));
  assert(framePixel(straight, 13, 27));
  assert(framePixel(straight, 14, 27));
  assert(!framePixel(straight, 12, 27));
  assert(framePixel(straight, 12, 29));
  assert(framePixel(straight, 14, 29));
  assert(!framePixel(straight, 11, 29));
  assert(!framePixel(straight, 15, 29));
  assert(framePixel(straight, 9, 44));
  assert(framePixel(straight, 11, 44));
  assert(!framePixel(straight, 8, 44));
  assert(!framePixel(straight, 12, 44));

  // Г and L are full-height derivatives of E. In particular, Г must retain
  // E's lower-left segment and L must retain its upper-left segment.
  text_screen::Grid letters;
  letters.reset(6);
  letters.setCursor(0, 1);
  letters.writeCodepoint('E');
  letters.writeCodepoint(display_symbol::uc1609::CYR_GHE);
  letters.writeCodepoint('L');
  Frame letter_frame{};
  calculator_face::renderFrame(letters, letter_frame.data());
  assert(framePixel(letter_frame, 16 + 5, 24));  // Г: top
  assert(framePixel(letter_frame, 16 + 0, 44));  // Г: lower stem
  assert(!framePixel(letter_frame, 16 + 0, 47)); // Г: no bottom
  assert(!framePixel(letter_frame, 32 + 5, 24)); // L: no top
  assert(framePixel(letter_frame, 32 + 3, 29));  // L: upper stem
  assert(framePixel(letter_frame, 32 + 0, 49));  // L: bottom

  text_screen::Grid without_dot;
  without_dot.reset(6);
  writeGridLine(without_dot, 1, 0, "-1234567 -09");
  text_screen::Grid with_dot;
  with_dot.reset(6);
  writeGridLine(with_dot, 1, 0, "-12.34567 -09");
  Frame plain{};
  Frame dotted{};
  calculator_face::renderFrame(without_dot, plain.data());
  calculator_face::renderFrame(with_dot, dotted.data());
  unsigned changed_bits = 0;
  for(unsigned i = 0; i < plain.size(); ++i) {
    u8 bits = (u8) (plain[i] ^ dotted[i]);
    while(bits) { changed_bits += bits & 1U; bits >>= 1U; }
  }
  assert(changed_bits == 18);

  // A decimal after the twelfth (rightmost) digit still belongs to that
  // digit, and its last pixel must fit exactly inside the 192x64 framebuffer.
  text_screen::Grid rightmost;
  rightmost.reset(6);
  writeGridLine(rightmost, 1, 0, "012345678901.");
  Frame rightmost_frame{};
  calculator_face::renderFrame(rightmost, rightmost_frame.data());
  assert(framePixel(rightmost_frame, 176 + 14, 26));
  assert(framePixel(rightmost_frame, 191, 58));
  for(unsigned x = 0; x < 192; ++x) {
    assert(!framePixel(rightmost_frame, x, 59));
  }

#if MK61_ENABLE_USB_SCREEN
  assert(display.enterUsbScreen());
  assert(display.usbScreenActive() && display.calculatorFaceActive());
  assert(std::memcmp(display.usbScreenFramebuffer(), expected.data(),
                     expected.size()) == 0);
  display.setCursor(12, 1);
  display.writeCodepoint('8');
  model.setCursor(12, 1);
  model.writeCodepoint('8');
  calculator_face::renderFrame(model, expected.data());
  assert(std::memcmp(display.usbScreenFramebuffer(), expected.data(),
                     expected.size()) == 0);
  display.leaveUsbScreen();
  assert(display.calculatorFaceActive());
  expectFrame(expected);
#endif

  display.clear();
  assert(!display.calculatorFaceActive());
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
  u8 font[83] = {'F','M','K','2',1,16,32,0xF0,1,0,1,0,83,0,0,0,
                 '?',0};
  font[18] = 0x7F; // raw bitmap mode bit followed by seven foreground pixels
  std::memset(font + 19, 0xFF, 63);
  font[82] = 0x80; // last pixel and zero padding
  const u16 crc = fmk::checksum(font, sizeof(font));
  font[14] = (u8) crc;
  font[15] = (u8) (crc >> 8);
  u8 prepared[prepared_font::MAX_IMAGE_SIZE] = {};
  const usize prepared_size = prepareFont(font, prepared, sizeof(prepared));
  u8 bulk[prepared_font::MAX_IMAGE_SIZE]{};
  ui_display_test::bulk_bytes = bulk;
  ui_display_test::bulk_size = sizeof(bulk);
  MK61Display display;
  startUi(display);
  assert(display.installPreparedFont(prepared, (u16) prepared_size));
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

void test_external_ui_font_layout_fallback_and_lifetime() {
  u8 font[39];
  makeExternalUiFont(font);
  u8 prepared[prepared_font::MAX_IMAGE_SIZE] = {};
  const usize prepared_size = prepareFont(font, prepared, sizeof(prepared));
  u8 bulk[prepared_font::MAX_IMAGE_SIZE]{};
  ui_display_test::bulk_bytes = bulk;
  ui_display_test::bulk_size = sizeof(bulk);

  MK61Display display;
  ui_display_test::reset();
  display.begin();
  // A wrong size is rejected before it can evict an already active face.
  assert(!display.installPreparedUiFont(prepared, (u16) prepared_size, 14));
  assert(!display.externalFontActive() && !ui_display_test::bulk_owned);
  assert(display.installPreparedUiFont(prepared, (u16) prepared_size, 12));
  assert(display.externalFontActive() && display.externalUiFont() != nullptr);
  display.setUiFont(3, 12);
  display.beginUiText();
  assert(display.uiTextActive() && display.rows() == 5);
  assert(display.measureUiText("AA") == 8);

  // Cyrillic А is absent and has no legacy icon in this tiny FMK, so the FMK
  // '?' is used. A private right-arrow token deliberately keeps its familiar
  // resident art.
  static const char absent_m8[] = {'A', (char) 0xC0, 0};
  display.printUiLine(0, absent_m8);
  display.setCursor(0, 1);
  display.writeCodepoint(display_symbol::uc1609::RT_ARROW);
  display.writeCodepoint('A');
  Frame expected{};
  referenceExternal(expected, *display.externalUiFont(), 'A', 2, 0);
  referenceExternal(expected, *display.externalUiFont(), '?', 6, 0);
  referenceBuiltin(expected, display.uiFontFace(),
                   display_symbol::uc1609::RT_ARROW, 2, 1);
  referenceExternal(expected, *display.externalUiFont(), 'A', 8, 1);
  expectFrame(expected);

  // Calculator rendering stays its own fixed face even while an external UI
  // family owns BULK.
  display.beginCalculatorFace();
  display.clear();
  writeDisplayLine(display, 1, 0, "1.");
  display.beginCalculatorFace();
  text_screen::Grid model;
  model.reset(6);
  writeGridLine(model, 1, 0, "1.");
  calculator_face::renderFrame(model, expected.data());
  expectFrame(expected);

  display.clearExternalUiFont();
  assert(!display.externalFontActive() && display.externalUiFont() == nullptr &&
         !ui_display_test::bulk_owned);
  ui_display_test::bulk_bytes = nullptr;
  ui_display_test::bulk_size = 0;
}

void test_runtime_font_uses_full_47_by_10_grid() {
  u8 font[28];
  makeExternalRuntimeFont(font);
  u8 prepared[prepared_font::MAX_IMAGE_SIZE] = {};
  const usize prepared_size = prepareFont(font, prepared, sizeof(prepared));
  u8 bulk[prepared_font::MAX_IMAGE_SIZE]{};
  ui_display_test::bulk_bytes = bulk;
  ui_display_test::bulk_size = sizeof(bulk);

  MK61Display display;
  ui_display_test::reset();
  display.begin();
  assert(display.installPreparedUiFont(prepared, (u16) prepared_size, 0));
  display.setUiFont(3, 12);
  display.beginUiText();
  assert(display.rows() == 10 && display.cols() == 47);

  char full_row[48];
  std::memset(full_row, 'A', sizeof(full_row) - 1U);
  full_row[sizeof(full_row) - 1U] = 0;
  display.printUiLine(0, full_row);
  Frame expected{};
  for(u8 col = 0; col < 47; ++col) {
    referenceExternal(expected, *display.externalUiFont(), 'A',
                      (u8) (2U + col * 4U), 0);
  }
  expectFrame(expected);

  // Row nine proves the gutter/tail damage maps also cover all ten rows.
  display.printUiLine(9, "A", ' ', 'A');
  referenceExternal(expected, *display.externalUiFont(), 'A', 14, 9);
  referenceExternal(expected, *display.externalUiFont(), 'A', 178, 9);
  expectFrame(expected);

  display.clearExternalUiFont();
  ui_display_test::bulk_bytes = nullptr;
  ui_display_test::bulk_size = 0;
}

void test_runtime_font_columns_follow_advance() {
  u8 font[28];
  makeExternalRuntimeFont(font, 6);
  u8 prepared[prepared_font::MAX_IMAGE_SIZE] = {};
  const usize prepared_size = prepareFont(font, prepared, sizeof(prepared));
  u8 bulk[prepared_font::MAX_IMAGE_SIZE]{};
  ui_display_test::bulk_bytes = bulk;
  ui_display_test::bulk_size = sizeof(bulk);

  MK61Display display;
  ui_display_test::reset();
  display.begin();
  assert(display.installPreparedUiFont(prepared, (u16) prepared_size, 0));
  display.setUiFont(3, 12);
  display.beginUiText();
  assert(display.rows() == 10);
  assert(display.cols() == 31); // floor((192 - 2*2) / 6)

  display.clearExternalUiFont();
  ui_display_test::bulk_bytes = nullptr;
  ui_display_test::bulk_size = 0;
}

void test_runtime_proportional_font_keeps_nominal_columns() {
  u8 font[31];
  makeExternalRuntimeProportionalFont(font);
  u8 prepared[prepared_font::MAX_IMAGE_SIZE] = {};
  const usize prepared_size = prepareFont(font, prepared, sizeof(prepared));
  u8 bulk[prepared_font::MAX_IMAGE_SIZE]{};
  ui_display_test::bulk_bytes = bulk;
  ui_display_test::bulk_size = sizeof(bulk);

  MK61Display display;
  ui_display_test::reset();
  display.begin();
  assert(display.installPreparedUiFont(prepared, (u16) prepared_size, 0));
  display.setUiFont(3, 12);
  display.beginUiText();
  assert(display.rows() == 10);
  assert(display.cols() == 47); // nominal floor((192 - 2*2) / 4)
  assert(display.measureUiText("A A") == 10); // 4 + 2 + 4, truly proportional
  assert(display.uiTextWidth() == 188);

  char wrapped[52];
  std::memset(wrapped, 'A', 45);
  wrapped[45] = ' ';
  std::memset(wrapped + 46, 'A', 5);
  wrapped[51] = 0;
  assert(display.printWrappedText(wrapped, 51, 0, 3) == 2);
  Frame expected{};
  const prepared_font::Face* const external = display.externalUiFont();
  assert(external != nullptr);
  for(u8 column = 0; column < 45; ++column)
    referenceExternal(expected, *external, 'A', 2 + column * 4, 0);
  for(u8 column = 0; column < 5; ++column)
    referenceExternal(expected, *external, 'A', 2 + column * 4, 1);
  expectFrame(expected);

  display.clear();
  assert(display.printWrappedText(wrapped, 51, 0, 1, true) == 1);
  expected.fill(0);
  for(u8 column = 0; column < 5; ++column)
    referenceExternal(expected, *external, 'A', 2 + column * 4, 0);
  expectFrame(expected);

  display.clearExternalUiFont();
  ui_display_test::bulk_bytes = nullptr;
  ui_display_test::bulk_size = 0;
}

void test_mixed_text_and_page_parity() {
  static constexpr u16 mixed[] = {'A', 0x0416, 'i', 0x0451, ' ', 'W', '9', 0x0443};
  for(u8 size : {12, 14, 16}) {
    MK61Display display;
    startUi(display, 1, size);
    Frame expected{};
    for(u8 row = 0; row < display.rows(); ++row) {
      display.printUiLine(row, M8_TEST_MIXED_TEXT);
      referenceText(expected, display.uiFontFace(), mixed, row);
    }
    expectFrame(expected);
    u16 advance = 0;
    for(u16 cp : mixed) advance = (u16) (advance + ui_font::glyph(display.uiFontFace(), cp).advance);
    assert(display.measureUiText(M8_TEST_MIXED_TEXT) == advance);
    assert(display.measureUiText("WWW") > display.measureUiText("iii"));

    // Incremental writes invalidate only intersecting pages. They must
    // produce the same pixels as whole-row replacement on every visible row.
    display.clear();
    for(u8 row = 0; row < display.rows(); ++row) {
      display.setCursor(0, row);
      for(u16 cp : mixed) display.writeCodepoint(cp);
    }
    expectFrame(expected);
  }
}

void test_m8_ui_text_metrics_and_pixels_agree() {
  for(u8 family : {0, 1}) {
    MK61Display display;
    startUi(display, family, 14);
    u16 expected_width = 0;
    const char* cursor = M8_SETTINGS;
    while(*cursor != 0) {
      const u16 codepoint = mk8::next(cursor);
      expected_width = (u16) (expected_width + (family == 0 ? 6U :
          ui_font::glyph(display.uiFontFace(), codepoint).advance));
    }
    assert(display.measureUiText(M8_SETTINGS) == expected_width);
    display.printUiLine(0, M8_SETTINGS);
    const Frame expected = ui_display_test::frame;
    display.clear();
    display.printUiLine(0, M8_SETTINGS);
    expectFrame(expected);
  }
}

void test_short_replacement_and_gutters() {
  MK61Display display;
  startUi(display);
  display.printUiLine(0, M8_TEST_LONG_REPLACEMENT, '>','M');
  display.printUiLine(1, M8_TEST_LOWER_LINE);
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

void test_ellipsis_and_invalid_m8() {
  for(u8 size : {12, 14, 16}) {
    MK61Display display;
    startUi(display, 1, size);
    char text[101];
    for(char letter : {'W', 'i'}) {
      std::memset(text, letter, sizeof(text) - 1);
      text[sizeof(text) - 1] = 0;
      display.printUiLine(0, text);
      const auto face = display.uiFontFace();
      const unsigned advance = ui_font::glyph(face, letter).advance;
      const unsigned ellipsis = ui_font::glyph(face, 0x2026).advance;
      unsigned count = (188U - ellipsis) / advance;
      const unsigned token_limit = display.cols() - 1U;
      if(count > token_limit) count = token_limit;
      Frame expected{};
      int pen = 2;
      for(unsigned glyph = 0; glyph < count; ++glyph) {
        referenceGlyph(expected, face, letter, pen, 0);
        pen += advance;
      }
      referenceGlyph(expected, face, 0x2026, pen, 0);
      expectFrame(expected);
    }
    display.printUiLine(0, "\x01\x7F\x98");
    Frame expected{};
    static constexpr u16 invalid[] = {'?', '?', '?'};
    referenceText(expected, display.uiFontFace(), invalid, 0);
    expectFrame(expected);
    assert(display.measureUiText("\x01\x7F\x98") == display.measureUiText("???"));
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

void test_cursor_blinks_on_trailing_ui_marker() {
  MK61Display display;
  startUi(display);
  display.printUiLine(0, "Programs", 0, '/');
  const Frame no_cursor = ui_display_test::frame;
  assert(display.cols() > 40);

  display.setCursor((u8) (display.cols() - 1U), 0);
  display.blinkOn();
  const Frame with_cursor = ui_display_test::frame;
  assert(with_cursor != no_cursor);

  // The proportional trailing gutter starts at x=178.  The selected-row
  // cursor must blink there, not at the obsolete logical column 39 whose
  // accumulated proportional advance is already outside the panel.
  bool changed_in_trailing_gutter = false;
  for(unsigned y = 0; y < 16; ++y) {
    for(unsigned x = 178; x < 190; ++x) {
      const u8 bit = (u8) (1U << (y & 7U));
      const unsigned offset = y / 8U * 192U + x;
      if(((with_cursor[offset] ^ no_cursor[offset]) & bit) != 0) {
        changed_in_trailing_gutter = true;
      }
    }
  }
  assert(changed_in_trailing_gutter);
  display.blinkOff();
  expectFrame(no_cursor);
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
void test_usb_waits_for_physical_display_ack() {
  MK61Display display;
  startUi(display);

  // A failed AE must neither publish USB Screen as active nor poison the
  // logical physical-screen state. A later ATTACH can retry cleanly.
  ui_display_test::sleep_failures_remaining = 1;
  assert(!display.enterUsbScreen());
  assert(!display.usbScreenActive());
  assert(!ui_display_test::sleeping);
  assert(ui_display_test::sleep_calls == 1);
  assert(display.deepIdleReady());

  assert(display.enterUsbScreen());
  assert(display.usbScreenActive());
  assert(ui_display_test::sleeping);
  assert(ui_display_test::sleep_calls == 2);

  // AF is also acknowledged. If the first wake attempt fails, leave the
  // restored frame dirty and retry from the next regular display flush.
  ui_display_test::sleep_failures_remaining = 2;
  display.leaveUsbScreen();
  assert(!display.usbScreenActive());
  assert(ui_display_test::sleeping);
  assert(ui_display_test::sleep_calls == 4);
  display.flush();
  assert(!ui_display_test::sleeping);
  assert(ui_display_test::sleep_calls == 5);
  assert(display.deepIdleReady());
}

void test_usb_return_to_ui_geometry() {
  MK61Display display;
  startUi(display);
  const auto calculator = display.textProfile();
  display.printUiLine(0, "ABCD");
  Frame expected{};
  static constexpr u16 text[] = {'A', 'B', 'C', 'D'};
  referenceText(expected, display.uiFontFace(), text, 0);
  assert(display.enterUsbScreen());
  assert(display.usbScreenActive() && display.uiTextActive());
  assert(std::memcmp(display.usbScreenFramebuffer(), expected.data(),
                     expected.size()) == 0);
  assert(!display.deepIdleReady());
  display.printUiLine(0, "Wiii");
  expected.fill(0);
  static constexpr u16 narrow[] = {'W', 'i', 'i', 'i'};
  referenceText(expected, display.uiFontFace(), narrow, 0);
  assert(std::memcmp(display.usbScreenFramebuffer(), expected.data(),
                     expected.size()) == 0);
  display.clear();
  display.writeCodepoint('5');
  display.leaveUsbScreen();
  assert(!display.usbScreenActive() && display.uiTextActive());
  assert(display.rows() == 4);
  assert(sameProfile(display.textProfile(), calculator));
  display.printUiLine(0, "ABCD");
  expected.fill(0);
  referenceText(expected, display.uiFontFace(), text, 0);
  expectFrame(expected);
}

void test_usb_calculator_to_runtime_font_switches_renderer() {
  u8 font[28];
  makeExternalRuntimeFont(font);
  u8 prepared[prepared_font::MAX_IMAGE_SIZE] = {};
  const usize prepared_size = prepareFont(font, prepared, sizeof(prepared));
  u8 bulk[prepared_font::MAX_IMAGE_SIZE] = {};
  ui_display_test::bulk_bytes = bulk;
  ui_display_test::bulk_size = sizeof(bulk);

  MK61Display display;
  ui_display_test::reset();
  display.begin();
  display.clear();
  display.setCursor(0, 1);
  display.writeCodepoint('5');
  display.beginCalculatorFace();
  assert(display.enterUsbScreen());
  assert(display.usbScreenActive() && display.calculatorFaceActive());

  // This is the exact High Noon transition: LOADFONT installs a 3x5 runtime
  // face while USB Screen currently mirrors the fixed calculator renderer.
  assert(display.installPreparedUiFont(prepared, (u16) prepared_size, 0));
  display.setUiFont(3, 12);
  display.beginUiText();
  assert(!display.calculatorFaceActive());
  assert(display.rows() == 10 && display.cols() == 47);
  display.clear();
  display.setCursor(0, 0);
  display.writeCodepoint('A');

  const u8* frame = display.usbScreenFramebuffer();
  assert(frame != nullptr);
  bool first_glyph_visible = false;
  for(u8 y = 2; y < 7; ++y) {
    for(u8 x = 2; x < 5; ++x) {
      first_glyph_visible = first_glyph_visible ||
          (frame[(usize) (y / 8U) * 192U + x] & (u8) (1U << (y & 7U)));
    }
  }
  assert(first_glyph_visible);

  display.leaveUsbScreen();
  display.clearExternalUiFont();
  ui_display_test::bulk_bytes = nullptr;
  ui_display_test::bulk_size = 0;
}
#endif
}

int main() {
  static_assert(sizeof(text_screen::Grid) <= 1500,
                "UI must keep one bounded 64x10 grid");
  allocation_forbidden = true;
  test_profile_and_scope();
  test_localized_message_selects_ui_renderer();
  test_preview_of_same_calculator_profile();
  test_live_ui_font_sample();
  test_mono_ui_is_fixed_and_independent();
  test_fixed_calculator_face();
  test_invalid_custom_slot_uses_ui_fallback();
  test_external_calculator_font_is_isolated_from_ui();
  test_external_ui_font_layout_fallback_and_lifetime();
  test_runtime_font_uses_full_47_by_10_grid();
  test_runtime_font_columns_follow_advance();
  test_runtime_proportional_font_keeps_nominal_columns();
  test_mixed_text_and_page_parity();
  test_m8_ui_text_metrics_and_pixels_agree();
  test_short_replacement_and_gutters();
  test_ellipsis_and_invalid_m8();
  test_cursor_and_stop_redraw();
  test_cursor_blinks_on_trailing_ui_marker();
  test_partial_page_overlay_restoration();
#if MK61_ENABLE_USB_SCREEN
  test_usb_waits_for_physical_display_ack();
  test_usb_return_to_ui_geometry();
  test_usb_calculator_to_runtime_font_switches_renderer();
#endif
  allocation_forbidden = false;
  std::puts("ui_display_self_test: ok");
}
