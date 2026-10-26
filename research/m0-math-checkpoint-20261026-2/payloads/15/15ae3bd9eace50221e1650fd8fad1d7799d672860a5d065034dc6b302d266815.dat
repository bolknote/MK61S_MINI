#ifndef MK61_SEGMENT_WS0010_HPP
#define MK61_SEGMENT_WS0010_HPP

#include "rust_types.h"

// The qualified WS0010 panel exposes an 80x16 window into its 100x16 GDRAM.
// Twelve six-pixel cells fit without using CGROM or the eight CGRAM slots.
namespace segment_ws0010 {

static constexpr u8 WIDTH = 80;
static constexpr u8 HEIGHT = 16;
static constexpr u8 CELLS = 12;
static constexpr u8 CELL_WIDTH = 6;
static constexpr u8 LEFT_MARGIN = (WIDTH - CELLS * CELL_WIDTH) / 2;
static constexpr usize FRAME_BYTES = (usize) WIDTH * (HEIGHT / 8);

inline void pixel(u8 frame[FRAME_BYTES], u8 x, u8 y) {
  frame[(usize) (y / 8) * WIDTH + x] |= (u8) (1u << (y % 8));
}

inline void render(const u8 masks[CELLS], u8 frame[FRAME_BYTES]) {
  for(usize i = 0; i < FRAME_BYTES; ++i) frame[i] = 0;
  if(masks == nullptr) return;

  for(u8 cell = 0; cell < CELLS; ++cell) {
    const u8 mask = masks[cell];
    const u8 x = (u8) (LEFT_MARGIN + cell * CELL_WIDTH);
    if(mask & 0x01u) for(u8 dx = 1; dx <= 3; ++dx) pixel(frame, x + dx, 0);  // A
    if(mask & 0x02u) for(u8 y = 1; y <= 6; ++y) pixel(frame, x + 4, y);     // B
    if(mask & 0x04u) for(u8 y = 8; y <= 13; ++y) pixel(frame, x + 4, y);    // C
    if(mask & 0x08u) for(u8 dx = 1; dx <= 3; ++dx) pixel(frame, x + dx, 14); // D
    if(mask & 0x10u) for(u8 y = 8; y <= 13; ++y) pixel(frame, x, y);        // E
    if(mask & 0x20u) for(u8 y = 1; y <= 6; ++y) pixel(frame, x, y);         // F
    if(mask & 0x40u) for(u8 dx = 1; dx <= 3; ++dx) pixel(frame, x + dx, 7); // G
    if(mask & 0x80u) pixel(frame, x + 5, 15);                               // dot
  }
}

} // namespace segment_ws0010

#endif
