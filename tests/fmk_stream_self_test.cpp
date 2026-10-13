#include "fmk_font.hpp"
#include "prepared_font.hpp"

#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>

namespace {
void word(std::vector<u8>& bytes, usize offset, u16 value) {
  bytes[offset] = (u8) value; bytes[offset + 1U] = (u8) (value >> 8U);
}
void seal(std::vector<u8>& bytes) {
  word(bytes, 12, (u16) bytes.size());
  word(bytes, 14, fmk::checksum(bytes.data(), bytes.size()));
}
void bits(std::vector<u8>& bytes, usize& position, u16 value, u8 count) {
  for(u8 bit = count; bit; --bit) {
    if(position / 8U == bytes.size()) bytes.push_back(0);
    if((value >> (bit - 1U)) & 1U)
      bytes[position / 8U] |= (u8) (0x80U >> (position & 7U));
    ++position;
  }
}
std::vector<u8> font(bool largest = false, bool proportional = false) {
  std::vector<u8> bytes(18U);
  std::memcpy(bytes.data(), "FMK2", 4);
  bytes[4] = proportional ? 0 : 1;
  bytes[5] = largest ? 16 : 8;
  bytes[6] = largest ? 32 : 8;
  bytes[7] = largest ? 0xF0 : 0x70;
  bytes[8] = largest ? 64 : 4;
  bytes[10] = 1;
  bytes[16] = largest ? ' ' : '?';
  bytes[17] = (u8) (bytes[8] - 1U);
  usize position = 18U * 8U;
  for(u16 glyph = 0; glyph < bytes[8]; ++glyph) {
    const u8 width = proportional ? (u8) (glyph + 1U) : bytes[5];
    if(proportional) {
      bits(bytes, position, (u16) (width - 1U), 4);
      bits(bytes, position, width, 4);
    }
    const u16 pixels = (u16) width * bytes[6];
    const bool compressed = largest || (glyph & 1U);
    bits(bytes, position, compressed, 1);
    if(!compressed) {
      for(u16 pixel = 0; pixel < pixels; ++pixel)
        bits(bytes, position, (u16) ((pixel + glyph) & 1U), 1);
    } else if(largest) {
      // 48 records with 102 literal runs + 16 with 101 runs make exactly
      // 8192 source bytes, while the prepared image is only 4118 bytes.
      const u16 runs = glyph < 48 ? 102 : 101;
      const u16 extra = (u16) (pixels - runs * 5U);
      for(u16 run = 0; run < runs; ++run) {
        const u16 length = (u16) (5U + (run < extra));
        bits(bytes, position, 0, 1);
        bits(bytes, position, (u16) (length - 1U), 4);
        for(u16 pixel = 0; pixel < length; ++pixel)
          bits(bytes, position, (u16) ((pixel + glyph + run) & 1U), 1);
      }
    } else {
      for(u16 produced = 0; produced < pixels;) {
        const u16 length = (u16) ((pixels - produced) > 16U ? 16U : pixels - produced);
        bits(bytes, position, 1, 1);
        bits(bytes, position, (u16) (length - 2U), 5);
        bits(bytes, position, (u16) (glyph & 1U), 1);
        produced = (u16) (produced + length);
      }
    }
  }
  seal(bytes);
  return bytes;
}

std::vector<u8> maximumPrepared(bool overflow = false) {
  // 127 full 16x32 rasters plus 22 range records fill the entire PFK limit.
  // Split the printable ASCII range, then include printable M8 A0..BF.
  std::vector<u8> bytes(16U + 22U * 2U);
  std::memcpy(bytes.data(), "FMK2", 4);
  bytes[4] = 1; bytes[5] = 16; bytes[6] = 32; bytes[7] = 0xF0;
  bytes[8] = overflow ? 128 : 127; bytes[10] = 22;
  for(u8 range = 0; range < 20; ++range) bytes[16U + range * 2U] = (u8) (' ' + range);
  bytes[56] = ' ' + 20; bytes[57] = 74;
  bytes[58] = 0xA0; bytes[59] = overflow ? 32 : 31;
  usize position = (usize) bytes.size() * 8U;
  for(u16 glyph = 0; glyph < bytes[8]; ++glyph) {
    bits(bytes, position, 1, 1);
    for(u8 run = 0; run < 16; ++run) {
      bits(bytes, position, 1, 1);
      bits(bytes, position, 30, 5); // repeat 32 pixels
      bits(bytes, position, (u16) (glyph & 1U), 1);
    }
  }
  seal(bytes);
  return bytes;
}

struct Input {
  const std::vector<u8>& bytes;
  usize next = 0, fail_at = (usize) -1;
  bool partial = false;
  static bool read(void* raw, usize offset, u8* output, usize length) {
    auto& input = *static_cast<Input*>(raw);
    assert(offset == input.next && length <= 128U && length != 0 &&
           offset + length <= input.bytes.size());
    if(offset >= input.fail_at) {
      if(input.partial) std::memcpy(output, input.bytes.data() + offset, length / 2U);
      return false;
    }
    std::memcpy(output, input.bytes.data() + offset, length);
    input.next += length;
    return true;
  }
};

bool streamed(const std::vector<u8>& bytes, usize capacity,
              usize fail_at = (usize) -1, bool partial = false) {
  std::array<u8, prepared_font::MAX_IMAGE_SIZE + 32U> result;
  result.fill(0xA5U);
  Input input{bytes, 0, fail_at, partial};
  const fmk::ReadSource reader{&input, (usize) bytes.size(), Input::read};
  usize size = 123;
  const bool ok = fmk::prepare(reader, result.data() + 16U, capacity, size);
  assert(ok ? size <= capacity : size == 0);
  for(usize i = 0; i < 16U; ++i) assert(result[i] == 0xA5U);
  for(usize i = 16U + capacity; i < result.size(); ++i) assert(result[i] == 0xA5U);
  if(ok) {
    assert(input.next == bytes.size());
    fmk::Face source;
    assert(source.open(bytes.data(), bytes.size()));
    std::array<u8, prepared_font::MAX_IMAGE_SIZE> reference{};
    usize expected = 0;
    assert(fmk::prepare(source, reference.data(), capacity, expected));
    assert(size == expected && std::memcmp(reference.data(), result.data() + 16U, size) == 0);
    prepared_font::Face prepared;
    assert(prepared.open(result.data() + 16U, size));
    // Face retains the independent FMK bit/raster decoder used by preview.
    // Compare every decoded source glyph rather than only the new compiler's
    // in-memory and file-reader adapters.
    for(u16 index = 0; index < source.metrics().glyph_count; ++index) {
      fmk::Glyph original{};
      prepared_font::Glyph expanded{};
      assert(source.glyphAt(index, original) && prepared.glyphAt(index, expanded));
      assert(original.byte == expanded.byte && original.width == expanded.width &&
             original.height == expanded.height && original.advance == expanded.advance);
      u8 expected_pixels[fmk::MAX_BITMAP_SIZE]{}, pixels[fmk::MAX_BITMAP_SIZE]{};
      assert(source.decode(original, expected_pixels, sizeof(expected_pixels)));
      assert(prepared.decode(expanded, pixels, sizeof(pixels)));
      assert(std::memcmp(expected_pixels, pixels,
                         ((original.width + 7U) / 8U) * original.height) == 0);
    }
  }
  return ok;
}
void differential(const std::vector<u8>& bytes) {
  fmk::Face source;
  std::array<u8, prepared_font::MAX_IMAGE_SIZE> reference{};
  usize size = 0;
  const bool expected = source.open(bytes.data(), bytes.size()) &&
      fmk::prepare(source, reference.data(), reference.size(), size);
  assert(streamed(bytes, reference.size()) == expected);
}
}

int main() {
  for(bool proportional : {false, true}) {
    const auto bytes = font(false, proportional);
    differential(bytes);
    for(usize size = 0; size < bytes.size(); ++size)
      differential(std::vector<u8>(bytes.begin(), bytes.begin() + size));
    for(usize index = 0; index < bytes.size(); ++index) {
      for(u8 bit = 0; bit < 8; ++bit) {
        auto corrupt = bytes;
        corrupt[index] ^= (u8) (1U << bit);
        differential(corrupt); // bad source CRC
        seal(corrupt);
        differential(corrupt); // valid CRC, malformed header/records/padding
      }
    }
    auto appended = bytes;
    appended.push_back(0);
    seal(appended);
    assert(!streamed(appended, prepared_font::MAX_IMAGE_SIZE));
    assert(!streamed(bytes, 0));
    assert(!streamed(bytes, prepared_font::HEADER_SIZE));
  }
  const auto maximum = font(true);
  assert(maximum.size() == fmk::MAX_FILE_SIZE);
  assert(streamed(maximum, prepared_font::MAX_IMAGE_SIZE));
  assert(streamed(maximum, 4118U));
  assert(!streamed(maximum, 4117U));
  for(usize offset = 0; offset < maximum.size(); offset += 128U) {
    assert(!streamed(maximum, prepared_font::MAX_IMAGE_SIZE, offset));
    assert(!streamed(maximum, prepared_font::MAX_IMAGE_SIZE, offset, true));
  }
  auto oversized = maximum;
  oversized.push_back(0); seal(oversized);
  assert(!streamed(oversized, prepared_font::MAX_IMAGE_SIZE));
  const auto full_prepared = maximumPrepared();
  assert(streamed(full_prepared, prepared_font::MAX_IMAGE_SIZE));
  assert(!streamed(full_prepared, prepared_font::MAX_IMAGE_SIZE - 1U));
  assert(!streamed(maximumPrepared(true), prepared_font::MAX_IMAGE_SIZE));
  auto overlapping = full_prepared;
  overlapping[17] = 1; seal(overlapping);
  differential(overlapping);
  assert(!streamed(overlapping, prepared_font::MAX_IMAGE_SIZE));
  std::puts("fmk_stream_self_test: byte-identical, malformed input, max-size and short reads passed");
}
