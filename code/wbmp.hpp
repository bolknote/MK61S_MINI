#ifndef MK61_WBMP_HPP
#define MK61_WBMP_HPP

#include "rust_types.h"

namespace wbmp {

// WBMP Type 0 хранит строки сверху вниз, старшим битом слева,
// 1 означает белый пиксель, 0 — чёрный.
struct Info {
  u32 width;
  u32 height;
  u32 pixel_offset;
  u32 row_bytes;
  u32 pixel_bytes;
};

enum class Layout : u8 {
  // Строки подряд, старший бит выходного байта расположен слева.
  ROW_MAJOR_MSB,
  // Страницы по восемь строк, младший бит расположен сверху (UC1609).
  PAGE_MAJOR_LSB,
};

enum class Status : u8 {
  OK = 0,
  INVALID_ARGUMENT,
  TRUNCATED,
  UNSUPPORTED_TYPE,
  INVALID_HEADER,
  INVALID_DIMENSIONS,
  SIZE_OVERFLOW,
  INVALID_DATA_SIZE,
  INVALID_PADDING,
  OUTPUT_TOO_SMALL,
};

Status inspect(const u8* data, usize size, Info& info);

// Декодирует окно фиксированного размера. Область за границами исходного
// изображения остаётся белой; выходной бит 1 означает тёмный пиксель.
Status decode_viewport(const u8* data, usize size, const Info& info,
                       u32 view_x, u32 view_y,
                       u16 view_width, u16 view_height,
                       Layout layout, u8* output, usize output_size);

usize viewport_bytes(u16 width, u16 height, Layout layout);
const char* status_text(Status status);

} // пространство имён wbmp

#endif
