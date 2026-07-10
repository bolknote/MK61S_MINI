#include "fmk_font.hpp"

#include <string.h>

namespace fmk {

namespace {

static constexpr u8 CRC_OFFSET = 14;

static u16 readLe16(const u8* data) {
  return (u16) data[0] | ((u16) data[1] << 8);
}

class BitReader {
  public:
    BitReader(const u8* data, usize size, u32 position = 0)
      : data(data), bit_count((u32) size * 8), position(position) {}

    bool read(u8 count, u16& value) {
      if(count > 16 || position + count > bit_count) return false;
      value = 0;
      for(u8 i = 0; i < count; i++) {
        const u32 bit = position++;
        value = (u16) ((value << 1) | ((data[bit / 8] >> (7 - (bit & 7))) & 1));
      }
      return true;
    }

    bool skip(u32 count) {
      if(position + count > bit_count) return false;
      position += count;
      return true;
    }

    u32 tell(void) const { return position; }

  private:
    const u8* data;
    u32 bit_count;
    u32 position;
};

static bool readGlyphMetrics(BitReader& reader, const Metrics& metrics, u8& width, u8& advance) {
  if(metrics.monospaced) {
    width = metrics.max_width;
    advance = metrics.default_advance;
    return true;
  }

  u16 value = 0;
  if(!reader.read(4, value)) return false;
  width = (u8) (value + 1);
  if(!reader.read(4, value)) return false;
  advance = (u8) (value + 1);
  return width <= metrics.max_width;
}

static bool skipBitmap(BitReader& reader, u16 pixels) {
  u16 mode = 0;
  if(!reader.read(1, mode)) return false;
  if(mode == 0) return reader.skip(pixels);

  u16 produced = 0;
  while(produced < pixels) {
    u16 kind = 0;
    u16 value = 0;
    if(!reader.read(1, kind)) return false;
    if(kind == 0) {
      if(!reader.read(4, value)) return false;
      const u16 count = (u16) (value + 1);
      if(count > pixels - produced || !reader.skip(count)) return false;
      produced = (u16) (produced + count);
    } else {
      if(!reader.read(5, value)) return false;
      const u16 count = (u16) (value + 2);
      if(count > pixels - produced || !reader.skip(1)) return false;
      produced = (u16) (produced + count);
    }
  }
  return true;
}

static bool decodeBitmap(BitReader& reader, u16 pixels, u8 width, u8* bitmap, usize capacity) {
  const usize stride = (width + 7) / 8;
  const usize required = stride * ((pixels + width - 1) / width);
  if(bitmap == NULL || required > capacity) return false;
  memset(bitmap, 0, required);

  u16 mode = 0;
  if(!reader.read(1, mode)) return false;

  u16 produced = 0;
  while(produced < pixels) {
    if(mode == 0) {
      u16 pixel = 0;
      if(!reader.read(1, pixel)) return false;
      if(pixel != 0) {
        const u16 y = produced / width;
        const u16 x = produced % width;
        bitmap[y * stride + x / 8] |= (u8) (0x80 >> (x & 7));
      }
      produced++;
      continue;
    }

    u16 kind = 0;
    u16 value = 0;
    if(!reader.read(1, kind)) return false;
    u16 count = 0;
    if(kind == 0) {
      if(!reader.read(4, value)) return false;
      count = (u16) (value + 1);
      if(count > pixels - produced) return false;
      for(u16 i = 0; i < count; i++) {
        u16 pixel = 0;
        if(!reader.read(1, pixel)) return false;
        if(pixel != 0) {
          const u16 offset = (u16) (produced + i);
          const u16 y = offset / width;
          const u16 x = offset % width;
          bitmap[y * stride + x / 8] |= (u8) (0x80 >> (x & 7));
        }
      }
    } else {
      if(!reader.read(5, value)) return false;
      count = (u16) (value + 2);
      if(count > pixels - produced || !reader.read(1, value)) return false;
      if(value != 0) {
        for(u16 i = 0; i < count; i++) {
          const u16 offset = (u16) (produced + i);
          const u16 y = offset / width;
          const u16 x = offset % width;
          bitmap[y * stride + x / 8] |= (u8) (0x80 >> (x & 7));
        }
      }
    }
    produced = (u16) (produced + count);
  }
  return true;
}

} // namespace

Face::Face(void) {
  reset();
}

void Face::reset(void) {
  bytes = NULL;
  byte_count = 0;
  range_count = 0;
  stream_bit_offset = 0;
  face_metrics = {false, 0, 0, 0, 0, 0};
}

u16 checksum(const u8* data, usize size) {
  if(data == NULL) return 0;
  u16 crc = 0xFFFF;
  for(usize i = 0; i < size; i++) {
    const u8 byte = (i == CRC_OFFSET || i == CRC_OFFSET + 1) ? 0 : data[i];
    crc ^= (u16) byte << 8;
    for(u8 bit = 0; bit < 8; bit++) {
      crc = (crc & 0x8000) ? (u16) ((crc << 1) ^ 0x1021) : (u16) (crc << 1);
    }
  }
  return crc;
}

bool Face::open(const u8* data, usize size) {
  reset();
  if(data == NULL || size < HEADER_SIZE || size > MAX_FILE_SIZE) return false;
  if(data[0] != 'F' || data[1] != 'M' || data[2] != 'K' || data[3] != '1') return false;
  if((data[4] & (u8) ~FLAG_MONOSPACED) != 0) return false;

  Metrics metrics = {
    (data[4] & FLAG_MONOSPACED) != 0,
    data[5],
    data[6],
    (u8) ((data[7] >> 4) + 1),
    (u8) (data[7] & 0x0F),
    readLe16(data + 8)
  };
  const u8 ranges = data[10];
  const u16 declared_size = readLe16(data + 12);
  const u16 declared_crc = readLe16(data + CRC_OFFSET);

  if(metrics.max_width == 0 || metrics.max_width > MAX_GLYPH_WIDTH) return false;
  if(metrics.height == 0 || metrics.height > MAX_GLYPH_HEIGHT) return false;
  if(metrics.default_advance > MAX_GLYPH_WIDTH) return false;
  if(metrics.glyph_count == 0 || ranges == 0) return false;
  if(data[11] != 0) return false;
  if(declared_size != size || declared_crc != checksum(data, size)) return false;
  if(HEADER_SIZE + (usize) ranges * RANGE_SIZE > size) return false;

  u32 glyphs_in_ranges = 0;
  u32 previous_end = 0;
  for(u8 i = 0; i < ranges; i++) {
    const u8* range = data + HEADER_SIZE + (usize) i * RANGE_SIZE;
    const u16 start = readLe16(range);
    const u16 count = (u16) range[2] + 1;
    if(i != 0 && start < previous_end) return false;
    previous_end = (u32) start + count;
    if(previous_end > 0x10000UL) return false;
    glyphs_in_ranges += count;
    if(glyphs_in_ranges > metrics.glyph_count) return false;
  }
  if(glyphs_in_ranges != metrics.glyph_count) return false;

  const u32 first_record = (u32) (HEADER_SIZE + (usize) ranges * RANGE_SIZE) * 8;
  BitReader reader(data, size, first_record);
  for(u16 i = 0; i < metrics.glyph_count; i++) {
    u8 width = 0;
    u8 advance = 0;
    if(!readGlyphMetrics(reader, metrics, width, advance)) return false;
    (void) advance;
    if(!skipBitmap(reader, (u16) width * metrics.height)) return false;
  }

  const u32 used_bits = reader.tell();
  const u32 total_bits = (u32) size * 8;
  if(total_bits - used_bits >= 8) return false;
  while(reader.tell() < total_bits) {
    u16 padding = 0;
    if(!reader.read(1, padding) || padding != 0) return false;
  }

  bytes = data;
  byte_count = size;
  range_count = ranges;
  stream_bit_offset = first_record;
  face_metrics = metrics;
  return true;
}

bool Face::glyphIndex(u16 codepoint, u16& index) const {
  if(!valid()) return false;
  u16 first_index = 0;
  for(u8 i = 0; i < range_count; i++) {
    const u8* range = bytes + HEADER_SIZE + (usize) i * RANGE_SIZE;
    const u16 start = readLe16(range);
    const u16 count = (u16) range[2] + 1;
    if(codepoint >= start && (u32) codepoint < (u32) start + count) {
      index = (u16) (first_index + codepoint - start);
      return true;
    }
    first_index = (u16) (first_index + count);
  }
  return false;
}

bool Face::codepointAt(u16 index, u16& codepoint) const {
  if(!valid() || index >= face_metrics.glyph_count) return false;
  u16 first_index = 0;
  for(u8 i = 0; i < range_count; i++) {
    const u8* range = bytes + HEADER_SIZE + (usize) i * RANGE_SIZE;
    const u16 start = readLe16(range);
    const u16 count = (u16) range[2] + 1;
    if(index < first_index + count) {
      codepoint = (u16) (start + index - first_index);
      return true;
    }
    first_index = (u16) (first_index + count);
  }
  return false;
}

bool Face::recordAt(u16 index, Glyph& out) const {
  if(!valid() || index >= face_metrics.glyph_count) return false;
  BitReader reader(bytes, byte_count, stream_bit_offset);
  for(u16 i = 0; i <= index; i++) {
    const u32 record = reader.tell();
    u8 width = 0;
    u8 advance = 0;
    if(!readGlyphMetrics(reader, face_metrics, width, advance)) return false;
    if(i == index) {
      out.index = index;
      out.record_bit_offset = record;
      out.width = width;
      out.height = face_metrics.height;
      out.advance = advance;
      return codepointAt(index, out.codepoint);
    }
    if(!skipBitmap(reader, (u16) width * face_metrics.height)) return false;
  }
  return false;
}

bool Face::glyph(u16 codepoint, Glyph& out) const {
  u16 index = 0;
  return glyphIndex(codepoint, index) && recordAt(index, out);
}

bool Face::glyphAt(u16 index, Glyph& out) const {
  return recordAt(index, out);
}

bool Face::decode(const Glyph& glyph, u8* bitmap, usize capacity) const {
  if(!valid() || glyph.index >= face_metrics.glyph_count) return false;
  BitReader reader(bytes, byte_count, glyph.record_bit_offset);
  u8 width = 0;
  u8 advance = 0;
  if(!readGlyphMetrics(reader, face_metrics, width, advance)) return false;
  if(width != glyph.width || advance != glyph.advance) return false;
  return decodeBitmap(reader, (u16) width * face_metrics.height, width, bitmap, capacity);
}

bool bitmapPixel(const u8* bitmap, u8 width, u8 x, u8 y) {
  if(bitmap == NULL || x >= width) return false;
  const usize stride = (width + 7) / 8;
  return (bitmap[(usize) y * stride + x / 8] & (0x80 >> (x & 7))) != 0;
}

bool scaleToLcd5x8(const Face& face, const Glyph& glyph, u8 rows[8]) {
  if(rows == NULL || glyph.width == 0 || glyph.height == 0) return false;
  u8 bitmap[MAX_BITMAP_SIZE];
  if(!face.decode(glyph, bitmap, sizeof(bitmap))) return false;
  memset(rows, 0, 8);
  for(u8 y = 0; y < 8; y++) {
    const u8 source_y = (u8) (((u16) y * glyph.height) / 8);
    for(u8 x = 0; x < 5; x++) {
      const u8 source_x = (u8) (((u16) x * glyph.width) / 5);
      if(bitmapPixel(bitmap, glyph.width, source_x, source_y)) rows[y] |= (u8) (1 << (4 - x));
    }
  }
  return true;
}

u8 selectPreviewGlyphs(const Face& face, Glyph out[8]) {
  if(!face.valid() || out == NULL) return 0;
  static const u16 preferred[8] = {'0', '1', '2', '3', 'A', 'B', 'C', 'D'};
  u8 count = 0;
  for(u8 i = 0; i < 8; i++) {
    Glyph glyph;
    if(face.glyph(preferred[i], glyph)) out[count++] = glyph;
  }

  for(u16 index = 0; count < 8 && index < face.metrics().glyph_count; index++) {
    Glyph glyph;
    if(!face.glyphAt(index, glyph)) continue;
    bool duplicate = false;
    for(u8 i = 0; i < count; i++) {
      if(out[i].index == glyph.index) duplicate = true;
    }
    if(!duplicate) out[count++] = glyph;
  }

  const u8 unique = count;
  while(count < 8 && unique != 0) {
    out[count] = out[count % unique];
    count++;
  }
  return count;
}

} // namespace fmk
