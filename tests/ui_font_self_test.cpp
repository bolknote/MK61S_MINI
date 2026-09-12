#include "ui_font.hpp"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>

namespace {

void checkFace(ui_font::Face face) {
  const ui_font::Metrics m = ui_font::metrics(face);
  const unsigned height = face.size == ui_font::Size::PX14 ? 14U : 12U;
  assert(m.height == height);
  assert(m.ascent + m.descent == m.height);
  assert(m.line_gap == 2);
  assert(m.ppem == (height == 14 ? 11 : 10));
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
    assert(!ui_font::pixel(g, g.width, 0));
    assert(!ui_font::pixel(g, 0, g.height));
    assert(!ui_font::pixel(g, 255, 255));
    const bool arrowFallback = face.family == ui_font::Family::ROBOTO &&
      (cp == 0x2190 || cp == 0x2192);
    assert(g.fallback == arrowFallback);
    if (arrowFallback) {
      const ui_font::Glyph reference = ui_font::glyph(
        {ui_font::Family::DEJAVU, face.size}, cp);
      assert(g.bitmap == reference.bitmap && g.advance == reference.advance);
    }
    if (cp == ' ') {
      for (unsigned y = 0; y < g.height; ++y) {
        for (unsigned x = 0; x < g.width; ++x) {
          assert(!ui_font::pixel(g, static_cast<uint8_t>(x), static_cast<uint8_t>(y)));
        }
      }
    }
  }
  assert(supported == 169);
  for (uint32_t cp : {0U, 0x1FU, 0x7FU, 0xD800U, 0x1F600U, 0xFFFFFFFFU}) {
    assert(!ui_font::supports(face, cp));
    const ui_font::Glyph missing = ui_font::glyph(face, cp);
    const ui_font::Glyph question = ui_font::glyph(face, '?');
    assert(missing.fallback);
    assert(missing.bitmap == question.bitmap && missing.advance == question.advance);
  }
  const ui_font::Glyph empty = {};
  assert(!ui_font::pixel(empty, 0, 0));
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
        std::putchar(ui_font::pixel(g, x, y) ? '1' : '0');
      }
    }
    std::putchar('\n');
  }
}

} // namespace

int main(int argc, char** argv) {
  const bool dump = argc == 2 && std::strcmp(argv[1], "--dump") == 0;
  unsigned id = 0;
  for (const ui_font::Family family : {ui_font::Family::DEJAVU, ui_font::Family::ROBOTO}) {
    for (const ui_font::Size size : {ui_font::Size::PX12, ui_font::Size::PX14}) {
      const ui_font::Face face = {family, size};
      checkFace(face);
      if (dump) dumpFace(face, id);
      ++id;
    }
  }
  const ui_font::Face invalid = {static_cast<ui_font::Family>(255),
                                 static_cast<ui_font::Size>(255)};
  const ui_font::Face normal = {ui_font::Family::DEJAVU, ui_font::Size::PX12};
  assert(ui_font::metrics(invalid).height == 12);
  assert(ui_font::glyph(invalid, 'W').bitmap == ui_font::glyph(normal, 'W').bitmap);
  if (!dump) std::puts("UI font tests passed: four faces, 676 glyphs, bounds and fallbacks");
}
