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
#if (MK61_ENABLE_TINYBASIC || MK61_ENABLE_FOCAL) && MK61_HAS_FULLSCREEN_BITMAP
#include "display.hpp"
#include "builtin_font.hpp"
#include "cross_hal.h"
#include "mk_math.hpp"
#include "native_libc.h"
#include "shared_memory.hpp"
#include <new>
#include <string.h>
namespace basic_graphics {
namespace {
__attribute__((noinline)) void screen_geometry(void *, uint16_t &width, uint16_t &height) {
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
constexpr size_t canvas_capacity = MK61_HAS_COMPILED_GRAPHICS ? 1536 : 160;
Session *value = nullptr;
#if MK61_SCOPED_RESIDENT_BUFFERS
shared_memory::LifetimeBuffer session_storage;
#endif
Session *session() {
  if (value)
    return value;
  // Keep one lazy, stable session until END across APP/INPUT replacement. On native
  // F411 its independent high-gap buffer can also start after USB Screen has
  // pinned the lower arena; growing the retained heap then is forbidden.
#if defined(__arm__) || defined(__thumb__)
  __asm__ volatile(".global mk61_lazy_basic_graphics_bytes\n"
                   ".set mk61_lazy_basic_graphics_bytes, %c0" ::
                   "i" (sizeof(Session) + canvas_capacity +
                        (MK61_USE_NATIVE_LIBC ? 16 : 32)));
#endif
#if MK61_SCOPED_RESIDENT_BUFFERS
  if (!session_storage.acquire(shared_memory::Owner::BASIC_GRAPHICS,
                               sizeof(Session) + canvas_capacity))
    return nullptr;
  auto *storage = session_storage.data();
  memset(storage, 0, sizeof(Session) + canvas_capacity);
#else
  auto *storage = static_cast<uint8_t *>(
      shared_memory::allocate_retained_buffer(sizeof(Session) + canvas_capacity));
#endif
  if (!storage)
    return nullptr;
  auto *canvas = storage + sizeof(Session);
  value = new (storage) Session(
      {canvas, screen_geometry, screen_begin, screen_end, screen_present, screen_capture,
       screen_glyph, screen_flow,
       [](void *canvas, size_t size) -> void * { return size <= canvas_capacity ? canvas : nullptr; },
       [](void *, void *) {}});
  return value;
}
} // namespace
Result dispatch(Request &request) {
  if (!value) {
    // Housekeeping and capability queries must remain usable under OOM.
    if (request.count > 6)
      return Result::ARGUMENT;
    for (unsigned i = 0; i < request.count; ++i)
      if (!mk_math::is_finite(request.args[i]))
        return Result::ARGUMENT;
    switch (request.operation) {
    case Operation::WIDTH:
    case Operation::HEIGHT: {
      uint16_t width = 0, height = 0;
      screen_geometry(nullptr, width, height);
      request.value = request.operation == Operation::WIDTH ? width : height;
      return Result::OK;
    }
    case Operation::POINT: {
      if (request.count < 2 || request.count > 3 ||
          (request.count == 3 && (request.args[2] < 0 || request.args[2] > 2 ||
                                  request.args[2] != mk_math::floor(request.args[2]))))
        return Result::ARGUMENT;
      uint16_t width = 0, height = 0;
      screen_geometry(nullptr, width, height);
      if (!width || !height)
        return Result::UNAVAILABLE;
      request.value = 0;
      return Result::OK;
    }
    case Operation::ACTIVE:
    case Operation::TEXT_FLOW:
      request.value = 0;
      return Result::OK;
    case Operation::RESET:
    case Operation::END:
    case Operation::CHECK:
    case Operation::CLEAR:
    case Operation::SHOW:
    case Operation::TEXT_ROWS:
    case Operation::SUSPEND:
    case Operation::RESUME:
      return Result::OK;
    case Operation::RESTORE_PRINT:
      return Result::ARGUMENT;
    default:
      break;
    }
  }
  auto *current = session();
  if (!current)
    return Result::FULL;
  const auto result = current->apply(request);
#if MK61_SCOPED_RESIDENT_BUFFERS
  if (result == Result::OK && request.operation == Operation::END) {
    // Release only after the run has finished, never on INPUT/SUSPEND or an
    // invalid END. Otherwise the old VM-sized upper gap can obstruct a larger
    // compiler/APP on the next run while USB still owns the lower boundary.
    current->~Session();
    value = nullptr;
    session_storage.reset();
  }
#endif
  return result;
}
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
