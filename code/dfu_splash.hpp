#ifndef MK61_DFU_SPLASH_HPP
#define MK61_DFU_SPLASH_HPP

#include "rust_types.h"

namespace dfu_splash {

static constexpr u8 WIDTH = 192;
static constexpr u8 HEIGHT = 64;
static constexpr usize BYTE_COUNT = (usize) WIDTH * HEIGHT / 8;

static_assert(HEIGHT % 8 == 0, "DFU bitmap height must contain whole LCD pages");
static_assert(BYTE_COUNT == 1536, "DFU bitmap geometry changed unexpectedly");

// The editable bitmap remains the source of truth in dfu_splash.cpp, while the
// firmware stores only its compile-time LZ representation.  The decoder writes
// exactly BYTE_COUNT bytes and never allocates memory itself.
bool decode(u8* bitmap, usize capacity);
usize packed_byte_count(void);

} // пространство имён dfu_splash

#endif
