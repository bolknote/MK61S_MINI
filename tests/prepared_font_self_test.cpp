#include "fmk_font.hpp"
#include "prepared_font.hpp"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>

namespace {

std::vector<u8> readFile(const char* path) {
  std::ifstream input(path, std::ios::binary);
  assert(input.good());
  return std::vector<u8>(std::istreambuf_iterator<char>(input),
                         std::istreambuf_iterator<char>());
}

void writeLe16(u8* data, u16 value) {
  data[0] = (u8) value;
  data[1] = (u8) (value >> 8);
}

usize verify(const char* path, bool must_fit_f401) {
  const auto source_bytes = readFile(path);
  fmk::Face source;
  assert(source.open(source_bytes.data(), source_bytes.size()));

  std::vector<u8> image(prepared_font::MAX_IMAGE_SIZE);
  usize image_size = 0;
  assert(fmk::prepare(source, image.data(), image.size(), image_size));
  assert(image_size >= prepared_font::HEADER_SIZE &&
         image_size <= prepared_font::MAX_IMAGE_SIZE);
  if(must_fit_f401) assert(image_size <= 1536);
  image.resize(image_size);

  prepared_font::Face prepared;
  assert(prepared.open(image.data(), image.size()));
  const auto& a = source.metrics();
  const auto& b = prepared.metrics();
  assert(a.monospaced == b.monospaced && a.max_width == b.max_width &&
         a.height == b.height && a.default_advance == b.default_advance &&
         a.line_gap == b.line_gap && a.glyph_count == b.glyph_count);

  for(u16 index = 0; index < a.glyph_count; ++index) {
    fmk::Glyph source_glyph = {};
    prepared_font::Glyph prepared_glyph = {};
    assert(source.glyphAt(index, source_glyph));
    assert(prepared.glyphAt(index, prepared_glyph));
    assert(source_glyph.byte == prepared_glyph.byte &&
           source_glyph.index == prepared_glyph.index &&
           source_glyph.width == prepared_glyph.width &&
           source_glyph.height == prepared_glyph.height &&
           source_glyph.advance == prepared_glyph.advance);
    u8 source_bitmap[fmk::MAX_BITMAP_SIZE] = {};
    u8 prepared_bitmap[prepared_font::MAX_BITMAP_SIZE] = {};
    assert(source.decode(source_glyph, source_bitmap, sizeof(source_bitmap)));
    assert(prepared.decode(prepared_glyph, prepared_bitmap,
                           sizeof(prepared_bitmap)));
    const usize bytes = (usize) ((source_glyph.width + 7U) / 8U) *
                        source_glyph.height;
    assert(std::memcmp(source_bitmap, prepared_bitmap, bytes) == 0);
    prepared_font::Glyph lookup = {};
    assert(prepared.glyph(source_glyph.byte, lookup));
    assert(lookup.index == index);
  }

  prepared_font::Face invalid;
  assert(!invalid.open(image.data(), image.size() - 1U));
  auto corrupt = image;
  corrupt[0] ^= 1U;
  assert(!invalid.open(corrupt.data(), corrupt.size()));
  corrupt = image;
  corrupt.back() ^= 1U;
  assert(!invalid.open(corrupt.data(), corrupt.size()));
  corrupt = image;
  corrupt[8] = 16; // FMK/PFK line gaps are represented by four bits.
  writeLe16(corrupt.data() + prepared_font::CRC_OFFSET,
            prepared_font::checksum(corrupt.data(), corrupt.size()));
  assert(!invalid.open(corrupt.data(), corrupt.size()));
  if(!b.monospaced) {
    corrupt = image;
    const u16 records = (u16) corrupt[12] | ((u16) corrupt[13] << 8);
    corrupt[records] = 1; // first raster must start at relative offset zero
    writeLe16(corrupt.data() + prepared_font::CRC_OFFSET,
              prepared_font::checksum(corrupt.data(), corrupt.size()));
    assert(!invalid.open(corrupt.data(), corrupt.size()));
  }

  std::vector<u8> too_small(image_size - 1U);
  usize rejected_size = 123;
  assert(!fmk::prepare(source, too_small.data(), too_small.size(),
                       rejected_size));
  assert(rejected_size == 0);
  return image_size;
}

} // namespace

int main(int argc, char** argv) {
  assert(argc == 4);
  const usize high_noon = verify(argv[1], true);
  const usize dejavu12 = verify(argv[2], false);
  const usize dejavu14 = verify(argv[3], false);
  std::printf("prepared_font_self_test: ok (HighNoon=%u, DejaVu12=%u, DejaVu14=%u)\n",
              (unsigned) high_noon, (unsigned) dejavu12,
              (unsigned) dejavu14);
}
