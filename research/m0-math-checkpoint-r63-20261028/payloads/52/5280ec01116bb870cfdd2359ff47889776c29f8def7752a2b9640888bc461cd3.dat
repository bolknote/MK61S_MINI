#ifndef MK61_TERMINAL_KEY_SEQUENCE_HPP
#define MK61_TERMINAL_KEY_SEQUENCE_HPP
#include "rust_types.h"
namespace terminal_keys {
constexpr usize COUNT = 240;
// Packed scancodes, low byte first, 0xFF terminator. Invalid opcodes are NOP.
u32 sequence(u8 opcode);
}
#endif
