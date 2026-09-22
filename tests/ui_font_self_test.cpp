#include "ui_font.hpp"
#include "ui_font_catalog.hpp"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>

namespace {

void checkUnifiedBitmapLayouts(void) {
  const uint8_t row_aligned[] = {0x80, 0x40};
  const uint8_t tight[] = {0x90};
  const font_glyph::Glyph row = {
    row_aligned, 2, 2, 0, 2, 3,
    font_glyph::BitmapLayout::ROW_MSB, false};
  const font_glyph::Glyph packed = {
    tight, 2, 2, 0, 2, 3,
    font_glyph::BitmapLayout::TIGHT_MSB, false};
  for(uint8_t y = 0; y < 2; ++y) {
    for(uint8_t x = 0; x < 2; ++x) {
      assert(font_glyph::pixel(row, x, y) ==
             font_glyph::pixel(packed, x, y));
    }
  }
}

void checkFace(ui_font::Face face) {
  const ui_font::Metrics m = ui_font::metrics(face);
  const unsigned height = face.size == ui_font::Size::PX16 ? 17U
                        : face.size == ui_font::Size::PX14 ? 14U : 12U;
  assert(m.height == height);
  assert(m.ascent + m.descent == m.height);
  assert(m.line_gap == (height == 12 ? 1 : 2));
  assert(m.ppem == (height == 17 ? 16 : (height == 14 ? 12 : 10)));
  unsigned supported = 0;
  for (unsigned cp = 0; cp <= 0xFFFF; ++cp) {
    if (!ui_font::supports(face, cp)) continue;
    ++supported;
    const ui_font::Glyph g = ui_font::glyph(face, cp);
    assert(g.bitmap != nullptr);
    assert(g.width >= 1 && g.width <= 16);
    assert(g.height >= 1 && g.height <= m.height);
    assert(g.bearing_x + g.width < g.advance);
    assert(m.ascent >= g.bearing_y);
    assert(static_cast<int>(g.height) - g.bearing_y <= m.descent);
    assert(!font_glyph::pixel(g, g.width, 0));
    assert(!font_glyph::pixel(g, 0, g.height));
    assert(!font_glyph::pixel(g, 255, 255));
    assert(!g.fallback);
    if (cp == ' ') {
      for (unsigned y = 0; y < g.height; ++y) {
        for (unsigned x = 0; x < g.width; ++x) {
          assert(!font_glyph::pixel(g, static_cast<uint8_t>(x),
                                   static_cast<uint8_t>(y)));
        }
      }
    }
  }
  assert(supported == 181);
  for (uint32_t cp : {0x2190U, 0x2192U, 0x2191U, 0x2193U,
                      0x03C0U, 0x221AU, 0x21BBU, 0x2260U,
                      0x00D7U, 0x00F7U, 0x00B2U, 0x02B8U,
                      0x02E3U, 0x22BBU, 0x207BU, 0x21B5U,
                      0x2264U, 0x2265U}) {
    assert(ui_font::supports(face, cp));
    assert(!ui_font::glyph(face, cp).fallback);
  }
  // A bare check mark is not a legible radical at these sizes: keep the bar.
  const ui_font::Glyph radical = ui_font::glyph(face, 0x221A);
  unsigned top_run = 0;
  unsigned longest_top_run = 0;
  for (uint8_t x = 0; x < radical.width; ++x) {
    top_run = font_glyph::pixel(radical, x, 0) ? top_run + 1 : 0;
    if (top_run > longest_top_run) longest_top_run = top_run;
  }
  assert(longest_top_run >= 4);
  // Both comparison signs must include a detached equals bar and be mirrors.
  const ui_font::Glyph le = ui_font::glyph(face, 0x2264);
  const ui_font::Glyph ge = ui_font::glyph(face, 0x2265);
  assert(le.width == ge.width && le.height == ge.height);
  assert(le.height >= 7);
  for (uint8_t y = 0; y < le.height; ++y) {
    for (uint8_t x = 0; x < le.width; ++x) {
      assert(font_glyph::pixel(le, x, y) ==
             font_glyph::pixel(ge, le.width - 1 - x, y));
      if (y == le.height - 2) assert(!font_glyph::pixel(le, x, y));
      if (y == le.height - 1) assert(font_glyph::pixel(le, x, y));
    }
  }
  // M8 0x1D uses the calculator's circled XOR, not Unicode's underlined V.
  const ui_font::Glyph xor_glyph = ui_font::glyph(face, 0x22BB);
  const uint8_t middle = xor_glyph.height / 2;
  for (uint8_t x = 0; x < xor_glyph.width; ++x) {
    assert(font_glyph::pixel(xor_glyph, x, middle));
  }
  assert(!font_glyph::pixel(xor_glyph, 0, 0));
  assert(!font_glyph::pixel(xor_glyph, xor_glyph.width - 1, 0));
  assert(!font_glyph::pixel(xor_glyph, 0, xor_glyph.height - 1));
  assert(!font_glyph::pixel(xor_glyph, xor_glyph.width - 1,
                            xor_glyph.height - 1));
  assert(font_glyph::pixel(xor_glyph, xor_glyph.width / 2, 1));
  assert(font_glyph::pixel(xor_glyph, xor_glyph.width / 2,
                           xor_glyph.height - 2));
  for (uint32_t cp : {0U, 0x1FU, 0x7FU, 0xD800U, 0x1F600U, 0xFFFFFFFFU}) {
    assert(!ui_font::supports(face, cp));
    const ui_font::Glyph missing = ui_font::glyph(face, cp);
    const ui_font::Glyph question = ui_font::glyph(face, '?');
    assert(missing.fallback);
    assert(missing.bitmap == question.bitmap && missing.advance == question.advance);
  }
  const ui_font::Glyph empty = {};
  assert(!font_glyph::pixel(empty, 0, 0));
}

void dumpFace(ui_font::Face face, unsigned id) {
  for (unsigned cp = 0; cp <= 0xFFFF; ++cp) {
    if (!ui_font::supports(face, cp)) continue;
    const ui_font::Glyph g = ui_font::glyph(face, cp);
    std::printf("%u %u %u %u %u %d %u %u ", id, cp,
                g.width, g.height, g.bearing_x, g.bearing_y, g.advance,
                static_cast<unsigned>(g.fallback));
    for (uint8_t y = 0; y < g.height; ++y) {
      for (uint8_t x = 0; x < g.width; ++x) {
        std::putchar(font_glyph::pixel(g, x, y) ? '1' : '0');
      }
    }
    std::putchar('\n');
  }
}

void checkCatalogIdentityAndHeader(void) {
  assert(ui_font_catalog::name_equal("Fonts", "fonts"));
  assert(!ui_font_catalog::name_equal("Font", "Fonts"));
  assert(ui_font_catalog::name_compare("Alpha-12", "beta-12") < 0);
  assert(ui_font_catalog::name_compare("same", "Same") != 0);
  assert(ui_font_catalog::name_key("DejaVu-14") ==
         ui_font_catalog::name_key("DEJAVU-14"));
  assert(ui_font_catalog::name_key("DejaVu-14") !=
         ui_font_catalog::name_key("DejaVu-16"));

  u8 header[fmk::HEADER_SIZE] = {};
  std::memcpy(header, "FMK2", 4);
  header[5] = 12;
  header[6] = 14;
  header[7] = 0xD2;
  header[8] = 1;
  header[10] = 1;
  header[12] = (u8) sizeof(header);
  u8 height = 0;
  assert(ui_font_catalog::inspect_header(header, sizeof(header),
                                         sizeof(header), height));
  assert(height == 14);
  header[6] = 13;
  assert(!ui_font_catalog::inspect_header(header, sizeof(header),
                                          sizeof(header), height));
  header[6] = 14;
  header[12]++;
  assert(!ui_font_catalog::inspect_header(header, sizeof(header),
                                          sizeof(header), height));
}

} // namespace

int main(int argc, char** argv) {
  checkUnifiedBitmapLayouts();
  checkCatalogIdentityAndHeader();
  const bool dump = argc == 2 && std::strcmp(argv[1], "--dump") == 0;
  unsigned id = 0;
  for (const ui_font::Size size : {ui_font::Size::PX12, ui_font::Size::PX14,
                                   ui_font::Size::PX16}) {
    const ui_font::Face face = {ui_font::Family::PIXEL, size};
    checkFace(face);
    if (dump) dumpFace(face, id);
    ++id;
  }
  const ui_font::Face invalid = {static_cast<ui_font::Family>(255),
                                 static_cast<ui_font::Size>(255)};
  const ui_font::Face normal = {ui_font::Family::PIXEL, ui_font::Size::PX12};
  assert(ui_font::metrics(invalid).height == 12);
  assert(ui_font::glyph(invalid, 'W').bitmap == ui_font::glyph(normal, 'W').bitmap);
  if (!dump) std::puts("UI font tests passed: three faces, 543 glyphs, bounds and fallbacks");
}
