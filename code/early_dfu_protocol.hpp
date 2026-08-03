#ifndef MK61_EARLY_DFU_PROTOCOL_HPP
#define MK61_EARLY_DFU_PROTOCOL_HPP

#include "rust_types.h"

namespace early_dfu_protocol {

static constexpr u32 MAGIC = 0x31465544UL; // "DUF1" LE.

struct Request {
  u32 magic;
  u32 inverse_magic;
};

constexpr bool valid(u32 magic, u32 inverse_magic) {
  return magic == MAGIC && inverse_magic == ~MAGIC;
}

} // namespace early_dfu_protocol

#endif
