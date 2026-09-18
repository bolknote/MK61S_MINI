#include "prepared_font.hpp"

#include <string.h>

namespace prepared_font {
namespace {

static u16 readLe16(const u8* data) {
  return (u16) data[0] | ((u16) data[1] << 8);
}

static usize bitmapBytes(u8 width, u8 height) {
  return (usize) ((width + 7U) / 8U) * height;
}

} // namespace

Face::Face(void) { reset(); }

void Face::reset(void) {
  bytes_ = nullptr;
  byte_count_ = 0;
  range_count_ = 0;
  records_offset_ = 0;
  bitmap_offset_ = 0;
  metrics_ = {false, 0, 0, 0, 0, 0};
}

u16 checksum(const u8* data, usize size) {
  if(data == nullptr) return 0;
  u16 crc = 0xFFFF;
  for(usize i = 0; i < size; ++i) {
    const u8 byte = (i == CRC_OFFSET || i == CRC_OFFSET + 1U) ? 0 : data[i];
    crc ^= (u16) byte << 8;
    for(u8 bit = 0; bit < 8; ++bit) {
      crc = (crc & 0x8000U)
          ? (u16) ((crc << 1) ^ 0x1021U) : (u16) (crc << 1);
    }
  }
  return crc;
}

bool Face::open(const u8* data, usize size) {
  reset();
  if(data == nullptr || size < HEADER_SIZE || size > MAX_IMAGE_SIZE ||
     data[0] != 'P' || data[1] != 'F' || data[2] != 'K' || data[3] != '1' ||
     (data[4] & (u8) ~FLAG_MONOSPACED) != 0) return false;

  const Metrics candidate = {
      (data[4] & FLAG_MONOSPACED) != 0,
      data[5], data[6], data[7], data[8], readLe16(data + 10)};
  const u8 ranges = data[9];
  const u16 records = readLe16(data + 12);
  const u16 bitmap = readLe16(data + 14);
  const u16 declared_size = readLe16(data + 16);
  const u16 declared_crc = readLe16(data + CRC_OFFSET);

  if(candidate.max_width == 0 || candidate.max_width > MAX_GLYPH_WIDTH ||
     candidate.height == 0 || candidate.height > MAX_GLYPH_HEIGHT ||
     candidate.default_advance == 0 ||
     candidate.default_advance > MAX_GLYPH_WIDTH ||
     candidate.line_gap > 15 ||
     candidate.glyph_count == 0 || ranges == 0 ||
     declared_size != size || declared_crc != checksum(data, size)) return false;

  const usize expected_records = HEADER_SIZE + (usize) ranges * RANGE_SIZE;
  const usize expected_bitmap = expected_records +
      (candidate.monospaced ? 0U
                            : (usize) candidate.glyph_count * GLYPH_RECORD_SIZE);
  if(records != expected_records || bitmap != expected_bitmap ||
     bitmap > size) return false;

  u32 glyphs_in_ranges = 0;
  u32 previous_end = 0;
  for(u8 i = 0; i < ranges; ++i) {
    const u8* range = data + HEADER_SIZE + (usize) i * RANGE_SIZE;
    const u16 start = readLe16(range);
    const u16 count = (u16) range[2] + 1U;
    if((i != 0 && start < previous_end) ||
       (u32) start + count > 0x10000UL) return false;
    previous_end = (u32) start + count;
    glyphs_in_ranges += count;
    if(glyphs_in_ranges > candidate.glyph_count) return false;
  }
  if(glyphs_in_ranges != candidate.glyph_count) return false;

  usize used = 0;
  if(candidate.monospaced) {
    const usize per_glyph = bitmapBytes(candidate.max_width, candidate.height);
    used = per_glyph * candidate.glyph_count;
  } else {
    for(u16 index = 0; index < candidate.glyph_count; ++index) {
      const u8* record = data + records +
          (usize) index * GLYPH_RECORD_SIZE;
      const u16 offset = readLe16(record);
      const u8 width = (u8) ((record[2] >> 4) + 1U);
      const u8 advance = (u8) ((record[2] & 0x0FU) + 1U);
      if(offset != used || width > candidate.max_width ||
         advance > MAX_GLYPH_WIDTH) return false;
      used += bitmapBytes(width, candidate.height);
      if((usize) bitmap + used > size) return false;
    }
  }
  if((usize) bitmap + used != size) return false;

  bytes_ = data;
  byte_count_ = size;
  range_count_ = ranges;
  records_offset_ = records;
  bitmap_offset_ = bitmap;
  metrics_ = candidate;
  return true;
}

bool Face::glyphIndex(u16 codepoint, u16& index) const {
  if(!valid()) return false;
  u16 first = 0;
  for(u8 i = 0; i < range_count_; ++i) {
    const u8* range = bytes_ + HEADER_SIZE + (usize) i * RANGE_SIZE;
    const u16 start = readLe16(range);
    const u16 count = (u16) range[2] + 1U;
    if(codepoint >= start && (u32) codepoint < (u32) start + count) {
      index = (u16) (first + codepoint - start);
      return true;
    }
    first = (u16) (first + count);
  }
  return false;
}

bool Face::codepointAt(u16 index, u16& codepoint) const {
  if(!valid() || index >= metrics_.glyph_count) return false;
  u16 first = 0;
  for(u8 i = 0; i < range_count_; ++i) {
    const u8* range = bytes_ + HEADER_SIZE + (usize) i * RANGE_SIZE;
    const u16 start = readLe16(range);
    const u16 count = (u16) range[2] + 1U;
    if(index < first + count) {
      codepoint = (u16) (start + index - first);
      return true;
    }
    first = (u16) (first + count);
  }
  return false;
}

bool Face::recordAt(u16 index, Glyph& out) const {
  if(!valid() || index >= metrics_.glyph_count) return false;
  u8 width = metrics_.max_width;
  u8 advance = metrics_.default_advance;
  usize offset = 0;
  if(metrics_.monospaced) {
    offset = (usize) index * bitmapBytes(width, metrics_.height);
  } else {
    const u8* record = bytes_ + records_offset_ +
        (usize) index * GLYPH_RECORD_SIZE;
    offset = readLe16(record);
    width = (u8) ((record[2] >> 4) + 1U);
    advance = (u8) ((record[2] & 0x0FU) + 1U);
  }
  const usize absolute = (usize) bitmap_offset_ + offset;
  if(absolute > 0xFFFFU ||
     absolute + bitmapBytes(width, metrics_.height) > byte_count_) return false;
  out = {};
  out.index = index;
  out.bitmap_offset = (u16) absolute;
  out.width = width;
  out.height = metrics_.height;
  out.advance = advance;
  return true;
}

bool Face::glyph(u16 codepoint, Glyph& out) const {
  u16 index = 0;
  if(!glyphIndex(codepoint, index) || !recordAt(index, out)) return false;
  // glyphIndex already resolved this range; do not scan it a second time.
  out.codepoint = codepoint;
  return true;
}

bool Face::glyphAt(u16 index, Glyph& out) const {
  return recordAt(index, out) && codepointAt(index, out.codepoint);
}

bool Face::decode(const Glyph& glyph, u8* bitmap, usize capacity) const {
  Glyph canonical = {};
  if(bitmap == nullptr || !recordAt(glyph.index, canonical) ||
     canonical.bitmap_offset != glyph.bitmap_offset ||
     canonical.width != glyph.width || canonical.height != glyph.height ||
     canonical.advance != glyph.advance) return false;
  const usize required = bitmapBytes(glyph.width, glyph.height);
  if(required > capacity) return false;
  memcpy(bitmap, bytes_ + glyph.bitmap_offset, required);
  return true;
}

} // namespace prepared_font
