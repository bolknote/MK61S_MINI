#ifndef MK61_WS0010_GRAPHICS_HPP
#define MK61_WS0010_GRAPHICS_HPP

#include "rust_types.h"
#include "ws0010_controller.hpp"

namespace ws0010_graphics {

static constexpr u8 WIDTH = ws0010::GRAPHICS_WIDTH;
static constexpr u8 HEIGHT = ws0010::GRAPHICS_HEIGHT;
static constexpr u8 PAGES = ws0010::GRAPHICS_PAGES;
static constexpr usize FRAME_BYTES = ws0010::GRAPHICS_FRAME_BYTES;

struct DirtySpan {
  u8 first;
  u8 last;
  bool valid;
};

constexpr usize byteIndex(u8 x, u8 y) {
  return (usize) (y >> 3) * WIDTH + x;
}

constexpr u8 bitMask(u8 y) {
  return (u8) (1u << (y & 7u));
}

inline void clear(u8* frame, usize size, bool on = false) {
  if(frame == nullptr || size < FRAME_BYTES) return;
  const u8 value = on ? 0xFFu : 0x00u;
  for(usize i = 0; i < FRAME_BYTES; i++) frame[i] = value;
}

inline bool setPixel(u8* frame, usize size, i16 x, i16 y, bool on = true) {
  if(frame == nullptr || size < FRAME_BYTES || x < 0 || y < 0 ||
     x >= WIDTH || y >= HEIGHT) return false;
  u8& value = frame[byteIndex((u8) x, (u8) y)];
  const u8 mask = bitMask((u8) y);
  if(on) value |= mask;
  else value &= (u8) ~mask;
  return true;
}

inline bool pixel(const u8* frame, usize size, i16 x, i16 y) {
  if(frame == nullptr || size < FRAME_BYTES || x < 0 || y < 0 ||
     x >= WIDTH || y >= HEIGHT) return false;
  return (frame[byteIndex((u8) x, (u8) y)] & bitMask((u8) y)) != 0;
}

inline DirtySpan changedSpan(const u8* before, const u8* after, u8 page) {
  if(before == nullptr || after == nullptr || page >= PAGES) {
    return {0, 0, false};
  }
  const usize base = (usize) page * WIDTH;
  u8 first = 0;
  while(first < WIDTH && before[base + first] == after[base + first]) first++;
  if(first == WIDTH) return {0, 0, false};
  u8 last = WIDTH - 1;
  while(last > first && before[base + last] == after[base + last]) last--;
  return {first, last, true};
}

inline void makeQualificationPattern(u8* frame, usize size, u8 pattern) {
  clear(frame, size, false);
  if(frame == nullptr || size < FRAME_BYTES) return;
  for(u8 y = 0; y < HEIGHT; y++) {
    for(u8 x = 0; x < WIDTH; x++) {
      bool on = false;
      switch(pattern & 7u) {
        // Sparse probes expose clipping, the four corners, the page boundary
        // and the two centre columns without hiding wiring errors in a fill.
        case 0:
          on = (x == 0 && (y == 0 || y == HEIGHT - 1)) ||
               (x == WIDTH - 1 && (y == 0 || y == HEIGHT - 1)) ||
               (x == 49 && y == 7) || (x == 50 && y == 8);
          break;
        case 1:
          on = x == 0 || x == WIDTH - 1 || y == 0 || y == HEIGHT - 1;
          break;
        case 2:
          on = (((x >> 2) ^ (y >> 2)) & 1u) != 0;
          break;
        case 3:
          on = x == y || x + y == WIDTH - 1 || x == 49 || x == 50;
          break;
        case 4:
          on = (x % 10u) == 0 || x == WIDTH - 1;
          break;
        case 5:
          on = y == 0 || y == 7 || y == 8 || y == HEIGHT - 1;
          break;
        case 6:
          on = true;
          break;
        default:
          on = false;
          break;
      }
      (void) setPixel(frame, size, x, y, on);
    }
  }
}

template<typename EmitCommand, typename EmitData>
bool streamPage(u8 page, u8 first, const u8* data, usize count,
                EmitCommand command, EmitData write_data) {
  if(page >= PAGES || first >= WIDTH || data == nullptr || count == 0 ||
     count > (usize) (WIDTH - first)) return false;
  command(ws0010::graphicsXAddress(first));
  command(ws0010::graphicsPageAddress(page));
  for(usize i = 0; i < count; i++) write_data(data[i]);
  return true;
}

static_assert(byteIndex(99, 15) == FRAME_BYTES - 1,
              "WS0010 vertical-page framebuffer layout regression");
static_assert(bitMask(0) == 0x01 && bitMask(7) == 0x80 && bitMask(8) == 0x01,
              "WS0010 vertical pixel packing regression");

} // namespace ws0010_graphics

#endif
