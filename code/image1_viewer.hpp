#ifndef MK61_IMAGE1_VIEWER_HPP
#define MK61_IMAGE1_VIEWER_HPP

#include "display.hpp"
#include "program_store.hpp"
#include "wbmp.hpp"

namespace image1_viewer {

enum class Result : u8 {
  OK = 0,
  BUSY,
  READ_ERROR,
  INVALID_IMAGE,
  DECODE_ERROR,
  DISPLAY_ERROR,
};

// Низкоуровневый вход для уже загруженного WBMP Type 0.
Result view(MK61Display& display, const u8* data, u16 size,
            wbmp::Status* image_status = NULL);

// Единый вход для Проводника, терминала и языков: файл один раз проверяется и
// считывается из C5 в общий scratch, после чего декодирование не обращается к
// SPI NOR в горячем цикле.
Result view_entry(MK61Display& display, const program_store::Entry& entry,
                  wbmp::Status* image_status = NULL);

const char* result_text(Result result);

} // namespace image1_viewer

#endif
