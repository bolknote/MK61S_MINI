#include "fmk_font.hpp"
#include "prepared_font.hpp"

#include <string.h>

namespace fmk {
namespace {

static void writeLe16(u8* data, u16 value) {
  data[0] = (u8) value;
  data[1] = (u8) (value >> 8);
}

} // namespace

bool prepare(const Face& face, u8* output, usize capacity,
             usize& output_size) {
  output_size = 0;
  if(!face.valid() || output == NULL ||
     capacity < prepared_font::HEADER_SIZE ||
     capacity > prepared_font::MAX_IMAGE_SIZE) return false;
  const Metrics& metrics = face.metrics();
  const u8 ranges = face.rangeCount();
  const usize records_offset = prepared_font::HEADER_SIZE +
      (usize) ranges * prepared_font::RANGE_SIZE;
  const usize bitmap_offset = records_offset +
      (metrics.monospaced ? 0U :
       (usize) metrics.glyph_count * prepared_font::GLYPH_RECORD_SIZE);
  if(bitmap_offset > capacity || bitmap_offset > 0xFFFFU) return false;

  usize bitmap_size = 0;
  for(u16 index = 0; index < metrics.glyph_count; ++index) {
    Glyph glyph = {};
    if(!face.glyphAt(index, glyph) || glyph.width == 0 ||
       glyph.width > prepared_font::MAX_GLYPH_WIDTH ||
       glyph.height != metrics.height || glyph.advance == 0 ||
       glyph.advance > prepared_font::MAX_GLYPH_WIDTH ||
       (metrics.monospaced &&
        (glyph.width != metrics.max_width ||
         glyph.advance != metrics.default_advance))) return false;
    bitmap_size += (usize) ((glyph.width + 7U) / 8U) * glyph.height;
    if(bitmap_offset + bitmap_size > capacity || bitmap_size > 0xFFFFU)
      return false;
  }

  const usize total = bitmap_offset + bitmap_size;
  if(total > 0xFFFFU) return false;
  memset(output, 0, total);
  output[0] = 'P'; output[1] = 'F'; output[2] = 'K'; output[3] = '1';
  output[4] = metrics.monospaced ? prepared_font::FLAG_MONOSPACED : 0;
  output[5] = metrics.max_width;
  output[6] = metrics.height;
  output[7] = metrics.default_advance;
  output[8] = metrics.line_gap;
  output[9] = ranges;
  writeLe16(output + 10, metrics.glyph_count);
  writeLe16(output + 12, (u16) records_offset);
  writeLe16(output + 14, (u16) bitmap_offset);
  writeLe16(output + 16, (u16) total);

  for(u8 index = 0; index < ranges; ++index) {
    u16 start = 0;
    u16 count = 0;
    if(!face.rangeAt(index, start, count) || count == 0 || count > 256U)
      return false;
    u8* range = output + prepared_font::HEADER_SIZE +
        (usize) index * prepared_font::RANGE_SIZE;
    writeLe16(range, start);
    range[2] = (u8) (count - 1U);
  }

  usize bitmap_cursor = 0;
  for(u16 index = 0; index < metrics.glyph_count; ++index) {
    Glyph glyph = {};
    if(!face.glyphAt(index, glyph)) return false;
    const usize bytes = (usize) ((glyph.width + 7U) / 8U) * glyph.height;
    if(!metrics.monospaced) {
      u8* record = output + records_offset +
          (usize) index * prepared_font::GLYPH_RECORD_SIZE;
      writeLe16(record, (u16) bitmap_cursor);
      record[2] = (u8) (((glyph.width - 1U) << 4) |
                        (glyph.advance - 1U));
    }
    if(!face.decode(glyph, output + bitmap_offset + bitmap_cursor, bytes))
      return false;
    bitmap_cursor += bytes;
  }
  writeLe16(output + prepared_font::CRC_OFFSET,
            prepared_font::checksum(output, total));
  output_size = total;
  return true;
}

} // namespace fmk
