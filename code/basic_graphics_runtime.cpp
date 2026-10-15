#include "config.h"
#include "basic_graphics.hpp"
#include "basic_native_io.hpp"
#if MK61_ENABLE_TINYBASIC
#include "display.hpp"
namespace basic_graphics {
__attribute__((noinline)) uint8_t native_text_rows() { return main_lcd().rows(); }
__attribute__((noinline)) int native_text_flow(const char *text, uint16_t length, uint8_t first,
                                               uint8_t maximum) {
  return main_lcd().printWrappedText(text, length, first, maximum, false, true);
}
} // namespace basic_graphics
#endif
#if MK61_ENABLE_TINYBASIC && MK61_HAS_FULLSCREEN_BITMAP
#include "display.hpp"
#include "builtin_font.hpp"
#include "cross_hal.h"
#include <new>
namespace basic_graphics {
namespace {
void screen_geometry(void *, uint16_t &width, uint16_t &height) {
  auto &lcd = main_lcd();
  width = lcd.supportsFullscreenBitmap() ? lcd.fullscreenBitmapWidth() : 0;
  height = width ? lcd.fullscreenBitmapHeight() : 0;
}
bool screen_begin(void *) { return main_lcd().beginFullscreenBitmap(); }
void screen_end(void *) { main_lcd().endFullscreenBitmap(); }
bool screen_present(void *, const uint8_t *pixels, size_t size) {
  return main_lcd().showFullscreenBitmap(pixels, size);
}
bool screen_capture(void *, uint8_t *pixels, size_t size, uint8_t first, uint8_t count) {
  return main_lcd().copyTextBitmap(pixels, size, first, count);
}
const uint8_t *screen_glyph(uint16_t codepoint) {
  static uint8_t rows[8];
  if (!builtin_font::copyRows5x8(codepoint, rows) && !builtin_font::copyRows5x8('?', rows))
    return nullptr;
  return rows;
}
int screen_flow(void *, uint8_t *pixels, size_t size, const char *text, uint16_t length,
                uint8_t first, uint8_t maximum, bool empty) {
  return main_lcd().flowTextBitmap(pixels, size, text, length, first, maximum, empty);
}
Session &session() {
  static uint8_t canvas[MK61_HAS_COMPILED_GRAPHICS ? 1536 : 160];
  alignas(Session) static uint8_t storage[sizeof(Session)];
  static Session *value = nullptr;
  if (value)
    return *value;
  value = new (storage) Session(
      {nullptr, screen_geometry, screen_begin, screen_end, screen_present, screen_capture,
       screen_glyph, screen_flow,
       [](void *, size_t size) -> void * { return size <= sizeof(canvas) ? canvas : nullptr; },
       [](void *, void *) {}});
  return *value;
}
} // namespace
Result dispatch(Request &request) { return session().apply(request); }
} // namespace basic_graphics
#else
namespace basic_graphics {
Result dispatch(Request &r) {
  r.value = 0;
  return r.operation == Operation::WIDTH || r.operation == Operation::HEIGHT ||
                 r.operation == Operation::RESET || r.operation == Operation::END ||
                 r.operation == Operation::CHECK || r.operation == Operation::SHOW ||
                 r.operation == Operation::ACTIVE || r.operation == Operation::TEXT_FLOW ||
                 r.operation == Operation::CLEAR || r.operation == Operation::TEXT_ROWS ||
                 r.operation == Operation::SUSPEND || r.operation == Operation::RESUME ||
                 r.operation == Operation::SAVE_PRINT || r.operation == Operation::RESTORE_PRINT
             ? Result::OK
             : Result::UNAVAILABLE;
}
} // namespace basic_graphics
#endif
