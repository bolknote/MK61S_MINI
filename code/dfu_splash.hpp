#ifndef MK61_DFU_SPLASH_HPP
#define MK61_DFU_SPLASH_HPP

#include "rust_types.h"

namespace dfu_splash {

static constexpr u8 WIDTH = 192;
static constexpr u8 HEIGHT = 64;
static constexpr usize BYTE_COUNT = (usize) WIDTH * HEIGHT / 8;

static_assert(HEIGHT % 8 == 0, "DFU bitmap height must contain whole LCD pages");
static_assert(BYTE_COUNT == 1536, "DFU bitmap geometry changed unexpectedly");

extern const u8 BITMAP[BYTE_COUNT];

} // пространство имён dfu_splash

#endif
