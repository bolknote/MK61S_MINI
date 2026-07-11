#include "builtin_font.hpp"
#include "display_symbols.hpp"
#include "fmk_font.hpp"
#include "text_screen.hpp"
#include "uc1609_safety.hpp"

#include <assert.h>
#include <fstream>
#include <iterator>
#include <stdio.h>
#include <string.h>
#include <vector>

namespace {

class BitWriter {
  public:
    explicit BitWriter(std::vector<u8>& bytes) : bytes(bytes), bit_position((u32) bytes.size() * 8) {}

    void write(u16 value, u8 count) {
      for(i16 bit = (i16) count - 1; bit >= 0; bit--) {
        const usize byte = bit_position / 8;
        if(byte >= bytes.size()) bytes.push_back(0);
        if((value & ((u16) 1 << bit)) != 0) bytes[byte] |= (u8) (0x80 >> (bit_position & 7));
        bit_position++;
      }
    }

  private:
    std::vector<u8>& bytes;
    u32 bit_position;
};

static void put_le16(std::vector<u8>& bytes, usize offset, u16 value) {
  bytes[offset] = (u8) value;
  bytes[offset + 1] = (u8) (value >> 8);
}

static void finish_font(std::vector<u8>& bytes) {
  put_le16(bytes, 12, (u16) bytes.size());
  put_le16(bytes, 14, fmk::checksum(bytes.data(), bytes.size()));
}

static std::vector<u8> mono_fixture(void) {
  std::vector<u8> bytes(fmk::HEADER_SIZE + fmk::RANGE_SIZE, 0);
  memcpy(bytes.data(), "FMK1", 4);
  bytes[4] = fmk::FLAG_MONOSPACED;
  bytes[5] = 3;
  bytes[6] = 5;
  bytes[7] = (u8) ((4 - 1) << 4) | 1;
  put_le16(bytes, 8, 2);
  bytes[10] = 1;
  put_le16(bytes, fmk::HEADER_SIZE, 'A');
  bytes[fmk::HEADER_SIZE + 2] = 1;

  BitWriter bits(bytes);
  // A: raw 010 101 111 101 101.
  bits.write(0, 1);
  bits.write(0b010101111101101, 15);
  // B: compressed as one 15-pixel run.
  bits.write(1, 1);
  bits.write(1, 1);
  bits.write(13, 5);
  bits.write(1, 1);
  finish_font(bytes);
  return bytes;
}

static std::vector<u8> proportional_fixture(void) {
  std::vector<u8> bytes(fmk::HEADER_SIZE + fmk::RANGE_SIZE, 0);
  memcpy(bytes.data(), "FMK1", 4);
  bytes[5] = 4;
  bytes[6] = 3;
  bytes[7] = (u8) ((4 - 1) << 4);
  put_le16(bytes, 8, 1);
  bytes[10] = 1;
  put_le16(bytes, fmk::HEADER_SIZE, 'X');
  bytes[fmk::HEADER_SIZE + 2] = 0;

  BitWriter bits(bytes);
  bits.write(1, 4); // width 2
  bits.write(2, 4); // advance 3
  bits.write(0, 1);
  bits.write(0b100111, 6);
  finish_font(bytes);
  return bytes;
}

static void test_mono_raw_and_rle(void) {
  const std::vector<u8> bytes = mono_fixture();
  fmk::Face face;
  assert(face.open(bytes.data(), bytes.size()));
  assert(face.metrics().monospaced);
  assert(face.metrics().glyph_count == 2);
  assert(face.metrics().line_gap == 1);

  fmk::Glyph glyph;
  assert(face.glyph('A', glyph));
  assert(glyph.width == 3 && glyph.height == 5 && glyph.advance == 4);
  u8 bitmap[fmk::MAX_BITMAP_SIZE];
  assert(face.decode(glyph, bitmap, sizeof(bitmap)));
  assert(bitmap[0] == 0x40);
  assert(bitmap[1] == 0xA0);
  assert(bitmap[2] == 0xE0);
  assert(bitmap[3] == 0xA0);
  assert(bitmap[4] == 0xA0);

  assert(face.glyph('B', glyph));
  assert(face.decode(glyph, bitmap, sizeof(bitmap)));
  for(u8 row = 0; row < 5; row++) assert(bitmap[row] == 0xE0);
  assert(!face.glyph('C', glyph));
}

static void test_proportional_metadata_is_read(void) {
  const std::vector<u8> bytes = proportional_fixture();
  fmk::Face face;
  assert(face.open(bytes.data(), bytes.size()));
  assert(!face.metrics().monospaced);

  fmk::Glyph glyph;
  assert(face.glyph('X', glyph));
  assert(glyph.width == 2);
  assert(glyph.advance == 3);
  u8 bitmap[fmk::MAX_BITMAP_SIZE];
  assert(face.decode(glyph, bitmap, sizeof(bitmap)));
  assert(bitmap[0] == 0x80);
  assert(bitmap[1] == 0x40);
  assert(bitmap[2] == 0xC0);
}

static void test_crc_and_padding_are_validated(void) {
  std::vector<u8> bytes = mono_fixture();
  fmk::Face face;
  bytes.back() ^= 1;
  assert(!face.open(bytes.data(), bytes.size()));

  bytes = mono_fixture();
  bytes[4] |= 0x80;
  put_le16(bytes, 14, fmk::checksum(bytes.data(), bytes.size()));
  assert(!face.open(bytes.data(), bytes.size()));

  bytes = mono_fixture();
  bytes[11] = 1;
  put_le16(bytes, 14, fmk::checksum(bytes.data(), bytes.size()));
  assert(!face.open(bytes.data(), bytes.size()));
}

static void test_lcd_scaling(void) {
  const std::vector<u8> bytes = mono_fixture();
  fmk::Face face;
  assert(face.open(bytes.data(), bytes.size()));
  fmk::Glyph glyph;
  assert(face.glyph('B', glyph));
  u8 rows[8];
  assert(fmk::scaleToLcd5x8(face, glyph, rows));
  for(u8 row = 0; row < 8; row++) assert(rows[row] == 0x1F);

  fmk::Glyph preview[8];
  assert(fmk::selectPreviewGlyphs(face, preview) == 8);
  assert(preview[0].codepoint == 'A');
  assert(preview[1].codepoint == 'B');
  for(u8 i = 2; i < 8; i++) assert(preview[i].index == preview[i % 2].index);
}

static void test_uc1609_display_symbol_tokens(void) {
  assert(display_symbol::uc1609::GE != 0);
  assert(display_symbol::uc1609::CYC_ARROW >= 0x80);
  assert(display_symbol::uc1609::NOT_EQUAL >= 0x80);
  assert(display_symbol::uc1609::CYR_PE >= 0x80);
  assert(display_symbol::uc1609::unicodeCodepoint(display_symbol::uc1609::GE) == 0x2265);
  assert(display_symbol::uc1609::unicodeCodepoint(display_symbol::uc1609::NOT_EQUAL) == 0x2260);
  assert(display_symbol::uc1609::unicodeCodepoint(display_symbol::uc1609::CYR_PE) == 0x041F);
  assert(display_symbol::uc1609::builtinCodepoint(display_symbol::uc1609::NOT_EQUAL) == 0x07);

  builtin_font::Raster raster;
  assert(builtin_font::decode(builtin_font::FaceId::FONT_5X8, display_symbol::uc1609::GE, raster));
  assert(raster.width == 5 && raster.height == 8);
  assert(builtin_font::decode(builtin_font::FaceId::FONT_5X8, display_symbol::uc1609::NOT_EQUAL, raster));
  assert(raster.width == 5 && raster.height == 8);
  assert(builtin_font::decode(builtin_font::FaceId::FONT_3X5, display_symbol::uc1609::CYR_PE, raster));
  assert(raster.width == 3 && raster.height == 5);
}

static void test_text_grid(void) {
  const text_screen::FontGeometry geometry3x5 = text_screen::fitFontToDisplay(3, 5, 1);
  assert(geometry3x5.rows == 10 && geometry3x5.width == 3 && geometry3x5.height == 5 && geometry3x5.line_gap == 1);
  const text_screen::FontGeometry geometry5x8 = text_screen::fitFontToDisplay(5, 8, 2);
  assert(geometry5x8.rows == 6 && geometry5x8.line_gap == 2);
  const text_screen::FontGeometry geometry5x9 = text_screen::fitFontToDisplay(5, 9, 0);
  assert(geometry5x9.rows == 7);
  const text_screen::FontGeometry geometry8x12 = text_screen::fitFontToDisplay(8, 12, 0);
  assert(geometry8x12.rows == 5 && geometry8x12.width == 8);
  const text_screen::FontGeometry oversized = text_screen::fitFontToDisplay(16, 32, 4);
  assert(oversized.rows == 4 && oversized.width == 10 && oversized.height == 16 && oversized.line_gap == 0);
  const text_screen::FontGeometry invalid = text_screen::sanitizeFontGeometry({255, 255, 255, 255});
  assert(invalid.rows == text_screen::MAX_ROWS);
  assert(invalid.width == 10);
  assert(invalid.height == 6);
  assert(invalid.line_gap == 0);

  text_screen::Grid grid;
  grid.reset(2);
  grid.setCursor(15, 0);
  grid.writeCodepoint(0x0410);
  assert(grid.cell(15, 0) == 0x0410);
  assert(grid.cursorX() == 0 && grid.cursorY() == 1);
  assert(grid.dirtyMask(0) == 0x8000);

  grid.writeByte(3);
  assert(grid.cellIsCustom(0, 1));
  assert(grid.cell(0, 1) == 3);
  grid.clearDirty(0);
  grid.clearDirty(1);
  grid.markCustomSlot(3);
  assert(grid.dirtyMask(0) == 0);
  assert(grid.dirtyMask(1) == 1);

  grid.markAll();
  assert(grid.dirtyMask(0) == 0xFFFF && grid.dirtyMask(1) == 0xFFFF);
  grid.clearColumns(0x000F);
  assert(grid.dirtyMask(0) == 0xFFF0 && grid.dirtyMask(1) == 0xFFF0);

  grid.setCursor(2, 1);
  grid.writeCodepoint(0xFFF8);
  assert(grid.cell(2, 1) == 0xFFF8);
  assert(!grid.cellIsCustom(2, 1));
}

static void test_uc1609_buffer_geometry(void) {
  assert(uc1609_safety::valid_dimensions(192, 64, 192, 64));
  assert(uc1609_safety::valid_dimensions(12, 64, 192, 64));
  assert(!uc1609_safety::valid_dimensions(0, 64, 192, 64));
  assert(!uc1609_safety::valid_dimensions(192, 63, 192, 64));
  assert(!uc1609_safety::valid_dimensions(193, 64, 192, 64));
  assert(uc1609_safety::intersects_panel(-11, 0, 12, 64, 192, 64));
  assert(!uc1609_safety::intersects_panel(-12, 0, 12, 64, 192, 64));
  assert(!uc1609_safety::intersects_panel(192, 0, 12, 64, 192, 64));

  usize offset = 9999;
  assert(uc1609_safety::pixel_offset(12, 64, 11, 63, offset));
  assert(offset == 95);
  assert(!uc1609_safety::pixel_offset(12, 64, 12, 63, offset));
  assert(!uc1609_safety::pixel_offset(12, 64, 0, 64, offset));
}

} // namespace

static void validate_external_font(const char* path, bool require_ink) {
  std::ifstream input(path, std::ios::binary);
  assert(input);
  const std::vector<u8> bytes((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
  fmk::Face face;
  assert(face.open(bytes.data(), bytes.size()));
  bool has_ink = false;
  for(u16 index = 0; index < face.metrics().glyph_count; index++) {
    fmk::Glyph glyph;
    u8 bitmap[fmk::MAX_BITMAP_SIZE];
    assert(face.glyphAt(index, glyph));
    assert(face.decode(glyph, bitmap, sizeof(bitmap)));
    for(u8 y = 0; y < glyph.height; y++) {
      for(u8 x = 0; x < glyph.width; x++) has_ink = has_ink || fmk::bitmapPixel(bitmap, glyph.width, x, y);
    }
  }
  assert(!require_ink || has_ink);
}

int main(int argc, char** argv) {
  test_mono_raw_and_rle();
  test_proportional_metadata_is_read();
  test_crc_and_padding_are_validated();
  test_lcd_scaling();
  test_uc1609_display_symbol_tokens();
  test_text_grid();
  test_uc1609_buffer_geometry();
  if(argc > 1) validate_external_font(argv[1], argc > 2 && strcmp(argv[2], "--require-ink") == 0);
  printf("display_font_self_test: ok\n");
  return 0;
}
