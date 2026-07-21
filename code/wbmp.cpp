#include "wbmp.hpp"

#include <string.h>

namespace wbmp {
namespace {

struct Cursor {
  const u8* data;
  usize size;
  usize offset;
};

static bool add_overflows_u32(u32 left, u32 right) {
  return left > 0xFFFFFFFFUL - right;
}

static bool mul_overflows_u32(u32 left, u32 right) {
  return left != 0 && right > 0xFFFFFFFFUL / left;
}

static Status read_mb_uint32(Cursor& cursor, u32& value) {
  value = 0;
  for(u8 octet_index = 0; octet_index < 5; octet_index++) {
    if(cursor.offset >= cursor.size) return Status::TRUNCATED;
    const u8 octet = cursor.data[cursor.offset++];
    const u8 scalar = (u8) (octet & 0x7FU);

    if(value > (0xFFFFFFFFUL >> 7)) return Status::SIZE_OVERFLOW;
    value = (value << 7) | scalar;
    if((octet & 0x80U) == 0) return Status::OK;
  }
  return Status::SIZE_OVERFLOW;
}

static bool info_matches(const Info& info, usize size) {
  if(info.width == 0 || info.height == 0 || info.row_bytes == 0) return false;
  if(mul_overflows_u32(info.row_bytes, info.height)) return false;
  const u32 bytes = info.row_bytes * info.height;
  if(bytes != info.pixel_bytes || add_overflows_u32(info.pixel_offset, bytes)) {
    return false;
  }
  return (u32) size == info.pixel_offset + bytes;
}

static bool source_dark(const u8* pixels, const Info& info, u32 x, u32 y) {
  const u8 value = pixels[y * info.row_bytes + x / 8U];
  return (value & (u8) (0x80U >> (x & 7U))) == 0;
}

} // namespace

usize viewport_bytes(u16 width, u16 height, Layout layout) {
  if(width == 0 || height == 0) return 0;
  if(layout == Layout::ROW_MAJOR_MSB) {
    return ((usize) width + 7U) / 8U * height;
  }
  if(layout == Layout::PAGE_MAJOR_LSB) {
    return (usize) width * (((usize) height + 7U) / 8U);
  }
  return 0;
}

Status inspect(const u8* data, usize size, Info& info) {
  memset(&info, 0, sizeof(info));
  if(data == NULL) return Status::INVALID_ARGUMENT;

  if(size == 0) return Status::TRUNCATED;
  // В Type 0 таблица 8-1 фиксирует TypeField ровно одним байтом.
  if(data[0] != 0) return Status::UNSUPPORTED_TYPE;
  Cursor cursor = {data, size, 1};
  if(cursor.offset >= cursor.size) return Status::TRUNCATED;
  const u8 fixed_header = cursor.data[cursor.offset++];
  // Для Type 0 bit 7 (наличие extension headers) и reserved bits 4..0
  // обязаны быть нулевыми; биты 6..5 стандарт оставляет произвольными.
  if((fixed_header & 0x9FU) != 0) return Status::INVALID_HEADER;

  Status status = read_mb_uint32(cursor, info.width);
  if(status != Status::OK) return status;
  status = read_mb_uint32(cursor, info.height);
  if(status != Status::OK) return status;
  if(info.width == 0 || info.height == 0) return Status::INVALID_DIMENSIONS;
  if(info.width > 0xFFFFFFF8UL) return Status::SIZE_OVERFLOW;

  info.row_bytes = (info.width + 7U) / 8U;
  if(mul_overflows_u32(info.row_bytes, info.height)) {
    return Status::SIZE_OVERFLOW;
  }
  info.pixel_bytes = info.row_bytes * info.height;
  if(cursor.offset > 0xFFFFFFFFUL) return Status::SIZE_OVERFLOW;
  info.pixel_offset = (u32) cursor.offset;
  if(add_overflows_u32(info.pixel_offset, info.pixel_bytes) ||
     info.pixel_offset + info.pixel_bytes != size) {
    return Status::INVALID_DATA_SIZE;
  }

  // В неполном последнем байте строки WBMP требует нулевые хвостовые биты.
  const u8 used_bits = (u8) (info.width & 7U);
  if(used_bits != 0) {
    const u8 padding_mask = (u8) ((1U << (8U - used_bits)) - 1U);
    const u8* const pixels = data + info.pixel_offset;
    for(u32 row = 0; row < info.height; row++) {
      if((pixels[row * info.row_bytes + info.row_bytes - 1U] &
          padding_mask) != 0) {
        return Status::INVALID_PADDING;
      }
    }
  }
  return Status::OK;
}

Status decode_viewport(const u8* data, usize size, const Info& info,
                       u32 view_x, u32 view_y,
                       u16 view_width, u16 view_height,
                       Layout layout, u8* output, usize output_size) {
  if(data == NULL || output == NULL || view_width == 0 || view_height == 0) {
    return Status::INVALID_ARGUMENT;
  }
  if(!info_matches(info, size)) return Status::INVALID_HEADER;
  const usize required = viewport_bytes(view_width, view_height, layout);
  if(required == 0) return Status::INVALID_ARGUMENT;
  if(output_size < required) return Status::OUTPUT_TOO_SMALL;
  memset(output, 0, required);

  const u8* const pixels = data + info.pixel_offset;
  if(view_x >= info.width || view_y >= info.height) return Status::OK;
  const u32 copy_width = info.width - view_x < view_width
                       ? info.width - view_x : view_width;
  const u32 copy_height = info.height - view_y < view_height
                        ? info.height - view_y : view_height;

  if(layout == Layout::ROW_MAJOR_MSB) {
    const usize output_stride = ((usize) view_width + 7U) / 8U;
    for(u32 y = 0; y < copy_height; y++) {
      u8* const row = output + y * output_stride;
      for(u32 x = 0; x < copy_width; x++) {
        if(source_dark(pixels, info, view_x + x, view_y + y)) {
          row[x / 8U] |= (u8) (0x80U >> (x & 7U));
        }
      }
    }
    return Status::OK;
  }

  if(layout != Layout::PAGE_MAJOR_LSB) return Status::INVALID_ARGUMENT;
  for(u32 y = 0; y < copy_height; y++) {
    u8* const page = output + (y / 8U) * view_width;
    const u8 page_bit = (u8) (1U << (y & 7U));
    for(u32 x = 0; x < copy_width; x++) {
      if(source_dark(pixels, info, view_x + x, view_y + y)) {
        page[x] |= page_bit;
      }
    }
  }
  return Status::OK;
}

const char* status_text(Status status) {
  switch(status) {
    case Status::OK: return "ok";
    case Status::INVALID_ARGUMENT: return "invalid argument";
    case Status::TRUNCATED: return "truncated header";
    case Status::UNSUPPORTED_TYPE: return "unsupported WBMP type";
    case Status::INVALID_HEADER: return "invalid WBMP header";
    case Status::INVALID_DIMENSIONS: return "invalid dimensions";
    case Status::SIZE_OVERFLOW: return "size overflow";
    case Status::INVALID_DATA_SIZE: return "invalid data size";
    case Status::INVALID_PADDING: return "invalid row padding";
    case Status::OUTPUT_TOO_SMALL: return "output buffer too small";
  }
  return "unknown WBMP error";
}

} // namespace wbmp
