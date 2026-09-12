#ifndef MK61_CALCULATOR_FACE_HPP
#define MK61_CALCULATOR_FACE_HPP

#include "rust_types.h"
#include "text_screen.hpp"

// Fixed calculator face for the 192x64 UC1609.  It deliberately consumes the
// canonical 16-column text shadow: the emulator/core keeps its old contract,
// while presentation is no longer tied to a configurable text font.
namespace calculator_face {

static constexpr u16 WIDTH = 192;
static constexpr u8 HEIGHT = 64;
static constexpr u8 PAGE_HEIGHT = 8;
static constexpr u8 PAGE_COUNT = HEIGHT / PAGE_HEIGHT;
static constexpr usize FRAME_BYTES = (usize) WIDTH * PAGE_COUNT;

void renderPage(const text_screen::Grid& grid, u8 page, u8 out[WIDTH]);
void renderFrame(const text_screen::Grid& grid, u8 out[FRAME_BYTES]);

} // namespace calculator_face

#endif
