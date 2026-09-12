#include "ui_font_service.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>

namespace {
uint8_t family = 1;
uint8_t size = 12;
bool capability = true;
bool corrupt = false;
unsigned glyph_calls = 0;
const fmk::Face* external_face = nullptr;

void put_msb_bit(uint8_t* bytes, size_t& bit, bool value) {
  if(value) bytes[bit / 8U] |= (uint8_t) (0x80U >> (bit & 7U));
  ++bit;
}

void make_external_ui_font(uint8_t (&font)[41]) {
  std::memset(font, 0, sizeof(font));
  std::memcpy(font, "FMK1", 4);
  font[4] = fmk::FLAG_MONOSPACED;
  font[5] = 3;
  font[6] = 12;
  font[7] = 0x31;
  font[8] = 4;
  font[10] = 2;
  font[12] = (uint8_t) sizeof(font);
  font[16] = ' ';
  font[19] = '?';
  font[21] = 2;
  size_t bit = 22U * 8U;
  for(uint8_t glyph = 0; glyph < 4; ++glyph) {
    put_msb_bit(font, bit, false);
    for(uint8_t y = 0; y < 12; ++y) {
      for(uint8_t x = 0; x < 3; ++x) {
        const bool pixel = glyph == 0 ? false :
            (glyph == 1 ? (y == 0 || (x == 2 && y < 4) ||
                           (x == 1 && (y == 4 || y == 7))) :
             glyph == 2 ? (y == 0 || y == 6 || x == 0 || x == 2) :
             ((x == 1 && y == 0) ||
              ((x == 0 || x == 2) && y > 0) || y == 5));
        put_msb_bit(font, bit, pixel);
      }
    }
  }
  const uint16_t crc = fmk::checksum(font, sizeof(font));
  font[14] = (uint8_t) crc;
  font[15] = (uint8_t) (crc >> 8);
}
}

#if defined(MK61_BUILD_PORTABLE_SYSTEM)
namespace portable_system {
const mk61_app_services dummy = {};
const mk61_app_services* api = &dummy;
uint32_t call(uint32_t op, uint32_t a = 0, uint32_t b = 0,
              uint32_t c = 0, void* payload = nullptr) {
  if(op == MK61_SERVICE_CAPABILITIES) return capability ? MK61_SERVICE_CAP_UI_FONT : 0;
  assert(op == MK61_SERVICE_UI_FONT);
  if(a == MK61_UI_FONT_GLYPH) ++glyph_calls;
  const uint32_t result = ui_font_service::call(
      family, size, a, b, c, payload, external_face);
  if(corrupt && result && a == MK61_UI_FONT_GLYPH) {
    static_cast<mk61_service_ui_glyph*>(payload)->height = 255;
  }
  return result;
}
} // namespace portable_system
#else
class MockDisplay {
 public:
  uint8_t uiFontFamily() const { return family; }
  uint8_t uiFontSize() const { return size; }
  const fmk::Face* externalUiFont() const { return external_face; }
};
MockDisplay& main_lcd() { static MockDisplay display; return display; }
#endif

#include "markdown_ui_font.hpp"

int main() {
  static_assert(MK61_SERVICE_CAPABILITIES == 26 && MK61_SERVICE_UI_FONT == 27,
                "existing operation numbers must not move");
  for(uint8_t f : {1, 2}) {
    for(uint8_t s : {12, 14, 16}) {
      family = f;
      size = s;
      const markdown_ui_font::Source source;
      const uint8_t expected_height = s == 16 ? 17 : s;
      assert(source.enabled() && source.height() == expected_height &&
             source.line_gap() == (s == 12 ? 1 : 2));
      for(unsigned cp = 0; cp <= 0xFFFF; cp++) {
        if(!ui_font::supports(ui_font_service::face(f, s), cp)) continue;
        mk61_service_ui_glyph glyph = {};
        assert(source.glyph(static_cast<uint16_t>(cp), glyph));
        const ui_font::Glyph native = ui_font::glyph(ui_font_service::face(f, s), cp);
        assert(glyph.width == native.width && glyph.height == native.height);
        for(bool bold : {false, true}) {
          for(bool italic : {false, true}) {
            const unsigned advance = markdown_ui_font::Source::advance(glyph, bold, italic);
            for(uint8_t y = 0; y < glyph.height; y++) {
              const unsigned shift = italic ? markdown_ui_font::Source::italic_shift(glyph, y) : 0;
              for(uint8_t x = 0; x < glyph.width; x++) {
                const bool pixel = markdown_ui_font::Source::pixel(glyph, x, y);
                assert(pixel == ui_font::pixel(native, x, y));
                if(pixel) {
                  // One clear column remains even with both emphasis styles.
                  assert(glyph.bearing_x + x + shift + (bold ? 1U : 0U) + 1U < advance);
                  assert(source.ascent() - glyph.bearing_y + y < source.height());
                }
              }
            }
          }
        }
      }
      // Rendering takes a settings snapshot. Later setting changes must not
      // invalidate the advance/baseline already used while wrapping text.
      family = family == 1 ? 2 : 1;
      size = size == 12 ? 14 : 12;
      mk61_service_ui_glyph snapshot = {};
      assert(source.glyph('W', snapshot));
      assert(snapshot.family == f && snapshot.size == s);
    }
  }

  uint8_t external_bytes[41];
  make_external_ui_font(external_bytes);
  fmk::Face external;
  assert(external.open(external_bytes, sizeof(external_bytes)));
  external_face = &external;
  family = 3;
  size = 12;
  const markdown_ui_font::Source external_source;
  assert(external_source.enabled() && external_source.height() == 12 &&
         external_source.ascent() == 12 && external_source.line_gap() == 1);
  mk61_service_ui_glyph external_glyph = {};
  assert(external_source.glyph('A', external_glyph));
  assert(external_glyph.family == 3 && external_glyph.size == 12 &&
         external_glyph.width == 3 && external_glyph.height == 12 &&
         external_glyph.advance == 4 && !external_glyph.fallback);
  assert(external_source.glyph(0x2603, external_glyph) &&
         external_glyph.fallback);
  external_face = nullptr;
  family = 0;
  const markdown_ui_font::Source disabled;
  assert(!disabled.enabled());
  mk61_service_ui_glyph glyph = {};
  assert(!disabled.glyph('A', glyph));

  family = 1;
  size = 12;
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
  capability = false;
  const markdown_ui_font::Source old_host;
  const unsigned calls = glyph_calls;
  assert(!old_host.enabled() && !old_host.glyph('A', glyph) && calls == glyph_calls);
  capability = true;
  portable_system::api = nullptr;
  assert(!markdown_ui_font::Source().enabled());
  portable_system::api = &portable_system::dummy;
  const markdown_ui_font::Source corrupted_host;
  corrupt = true;
  assert(!corrupted_host.glyph('A', glyph));
  corrupt = false;
#else
  (void) capability;
  (void) corrupt;
  (void) glyph_calls;
#endif

  struct Guarded {
    uint8_t before[16];
    mk61_service_ui_glyph value;
    uint8_t after[16];
  } guarded;
  memset(&guarded, 0xA5, sizeof(guarded));
  for(unsigned invalid_size : {0U, 1U, 39U, 41U, 0xFFFFFFFFU}) {
    assert(!ui_font_service::call(1, 12, MK61_UI_FONT_GLYPH, 'A', invalid_size, &guarded.value));
    for(unsigned char byte : guarded.before) assert(byte == 0xA5);
    for(unsigned char byte : guarded.after) assert(byte == 0xA5);
    assert(guarded.value.family == 0xA5 && guarded.value.pixels[31] == 0xA5);
  }
  assert(!ui_font_service::call(1, 12, MK61_UI_FONT_GLYPH, 'A', sizeof(glyph), nullptr));
  assert(!ui_font_service::call(1, 12, 99, 'A', sizeof(glyph), &guarded.value));
  assert(!ui_font_service::call(1, 12, MK61_UI_FONT_GLYPH, 'A', sizeof(glyph), &guarded.value));
  guarded.value.family = 1;
  guarded.value.size = 12;
  assert(ui_font_service::call(1, 12, MK61_UI_FONT_GLYPH, 0xFFFFFFFFU, sizeof(glyph), &guarded.value));
  assert(guarded.value.fallback);
  for(unsigned char byte : guarded.before) assert(byte == 0xA5);
  for(unsigned char byte : guarded.after) assert(byte == 0xA5);
  std::puts("Markdown UI font bridge: all rasters, styles, settings snapshot, ABI bounds passed");
}
