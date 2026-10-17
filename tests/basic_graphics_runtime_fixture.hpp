#ifndef MK61_BASIC_GRAPHICS_RUNTIME_FIXTURE_HPP
#define MK61_BASIC_GRAPHICS_RUNTIME_FIXTURE_HPP
#include <cstdint>
#include <cstddef>
#include <cstdlib>
#include <cstring>
#define CONFIG
#define MK61_DISPLAY_HPP
#define MK61_BASIC_NATIVE_IO_HPP
#define MK61_MK52_CROSS_HAL
#define BUILTIN_FONT_HPP
#define MK61_ENABLE_TINYBASIC 1
#define MK61_HAS_FULLSCREEN_BITMAP 1
struct RuntimeScreen {
  uint8_t shown[1536] = {};
  unsigned begins = 0, ends = 0;
  bool available = true;
  uint8_t rows() const { return MK61_HAS_COMPILED_GRAPHICS ? 8 : 2; }
  bool supportsFullscreenBitmap() const { return available; }
  uint16_t fullscreenBitmapWidth() const { return MK61_HAS_COMPILED_GRAPHICS ? 192 : 80; }
  uint16_t fullscreenBitmapHeight() const { return MK61_HAS_COMPILED_GRAPHICS ? 64 : 16; }
  bool beginFullscreenBitmap() { ++begins; return true; }
  void endFullscreenBitmap() { ++ends; }
  bool showFullscreenBitmap(const uint8_t *pixels, size_t size) {
    std::memcpy(shown, pixels, size);
    return true;
  }
  bool copyTextBitmap(uint8_t *pixels, size_t size, uint8_t, uint8_t) {
    std::memset(pixels, 0, size);
    return true;
  }
  int flowTextBitmap(uint8_t *, size_t, const char *, uint16_t, uint8_t, uint8_t, bool) {
    return 1;
  }
  int printWrappedText(const char *, uint16_t, uint8_t, uint8_t, bool, bool) { return 1; }
};
RuntimeScreen &main_lcd();
namespace builtin_font {
bool copyRows5x8(uint16_t, uint8_t rows[8]);
}
#if !defined(BASIC_GRAPHICS_REAL_SHARED_MEMORY)
#define MK61_SHARED_MEMORY_HPP
namespace shared_memory {
void *allocate_retained_buffer(unsigned int);
}
#endif
#endif
