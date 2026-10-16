#ifndef MK61_FOCAL_GRAPHICS_HOST_HPP
#define MK61_FOCAL_GRAPHICS_HOST_HPP
#include "basic_graphics.hpp"
namespace focal_host_graphics {
inline uint16_t width = 0, height = 0;
inline uint8_t frame[1536] = {};
inline unsigned presents = 0;
inline const uint8_t *glyph(uint16_t c) {
  static const uint8_t ink[8] = {31,17,17,17,17,17,31,0}, blank[8] = {};
  return c == ' ' ? blank : ink;
}
inline bool capture(void *, uint8_t *pixels, size_t size, uint8_t first, uint8_t count) {
  if (!width || size != size_t(width) * height / 8) return false;
  for (unsigned row = first; row < unsigned(first) + count && row * 8 < height; ++row) {
    memset(pixels + row * width, 0, width);
    const char *text = main_lcd().line(uint8_t(row));
    for (unsigned col = 0; text[col] && col * 6 < width; ++col)
      for (unsigned x = 0; x < 5 && col * 6 + x < width; ++x)
        for (unsigned y = 0; y < 8; ++y)
          if (glyph(uint8_t(text[col]))[y] & (1U << (4-x)))
            pixels[row * width + col * 6 + x] |= uint8_t(1U << y);
  }
  return true;
}
}
namespace basic_graphics {
Result dispatch(Request &request) {
  using namespace focal_host_graphics;
  static Session session({nullptr,
    [](void *, uint16_t &w, uint16_t &h) { w = width; h = height; },
    [](void *) { return true; }, [](void *) {},
    [](void *, const uint8_t *pixels, size_t size) {
      memcpy(frame, pixels, size); ++presents; return true;
    }, focal_host_graphics::capture, glyph,
    [](void *, uint8_t *pixels, size_t size, const char *text, uint16_t length,
       uint8_t first, uint8_t maximum, bool empty) {
      const char *end = text + length;
      unsigned row = first;
      while (row < main_lcd().rows() && row < unsigned(first) + maximum &&
             (text < end || (row == first && empty))) {
        main_lcd().setCursor(0, uint8_t(row)); unsigned col = 0;
        while (text < end && col < main_lcd().cols()) { main_lcd().write(uint8_t(*text++)); ++col; }
        while (col++ < main_lcd().cols()) main_lcd().write(' ');
        ++row;
      }
      return focal_host_graphics::capture(nullptr, pixels, size, first, uint8_t(row-first)) ? int(row-first) : -1;
    }, [](void *, size_t size) -> void * { return malloc(size); },
       [](void *, void *pointer) { free(pointer); }});
  return session.apply(request);
}
}
#endif
