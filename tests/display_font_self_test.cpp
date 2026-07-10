#include "fmk_font.hpp"
#include "text_screen.hpp"

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

} // namespace

static void validate_external_font(const char* path) {
  std::ifstream input(path, std::ios::binary);
  assert(input);
  const std::vector<u8> bytes((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
  fmk::Face face;
  assert(face.open(bytes.data(), bytes.size()));
  for(u16 index = 0; index < face.metrics().glyph_count; index++) {
    fmk::Glyph glyph;
    u8 bitmap[fmk::MAX_BITMAP_SIZE];
    assert(face.glyphAt(index, glyph));
    assert(face.decode(glyph, bitmap, sizeof(bitmap)));
  }
}

int main(int argc, char** argv) {
  test_mono_raw_and_rle();
  test_proportional_metadata_is_read();
  test_crc_and_padding_are_validated();
  test_lcd_scaling();
  test_text_grid();
  if(argc > 1) validate_external_font(argv[1]);
  printf("display_font_self_test: ok\n");
  return 0;
}
