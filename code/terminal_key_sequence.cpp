#include "terminal_key_sequence.hpp"
#include "cross_hal.h"

namespace terminal_keys {
namespace {
constexpr u32 seqNOP = seq(sw::K, sw::_0);
// Only irregular opcodes need a table; one/two-key sequences fit 16 bits.
const u16 direct[80] = {
  (u16) seq(sw::_0), (u16) seq(sw::_1), (u16) seq(sw::_2), (u16) seq(sw::_3), (u16) seq(sw::_4), (u16) seq(sw::_5), (u16) seq(sw::_6), (u16) seq(sw::_7),
  (u16) seq(sw::_8), (u16) seq(sw::_9), (u16) seq(sw::DOT), (u16) seq(sw::NEG), (u16) seq(sw::POW), (u16) seq(sw::CX), (u16) seq(sw::Bx), (u16) seq(sw::F,sw::Bx),
  (u16) seq(sw::ADD), (u16) seq(sw::SUB), (u16) seq(sw::MUL), (u16) seq(sw::DIV), (u16) seq(sw::XY), (u16) seq(sw::F,sw::DOT), (u16) seq(sw::F,sw::_5), (u16) seq(sw::F,sw::_1),
  (u16) seq(sw::F,sw::_2), (u16) seq(sw::F,sw::_4), (u16) seq(sw::F,sw::_5), (u16) seq(sw::F,sw::_6), (u16) seq(sw::F,sw::_7), (u16) seq(sw::F,sw::_8), (u16) seq(sw::F,sw::_9), (u16) seqNOP,
  (u16) seq(sw::F,sw::ADD), (u16) seq(sw::F,sw::SUB), (u16) seq(sw::F,sw::MUL), (u16) seq(sw::F,sw::DIV), (u16) seq(sw::F,sw::XY), (u16) seq(sw::F,sw::DOT), (u16) seq(sw::K,sw::ADD), (u16) seq(sw::K,sw::SUB),
  (u16) seq(sw::K,sw::MUL), (u16) seq(sw::K,sw::DIV), (u16) seq(sw::K,sw::XY), (u16) seqNOP, (u16) seqNOP, (u16) seqNOP, (u16) seqNOP, (u16) seqNOP,
  (u16) seq(sw::K,sw::_3), (u16) seq(sw::K,sw::_4), (u16) seq(sw::K,sw::_5), (u16) seq(sw::K,sw::_6), (u16) seq(sw::K,sw::_7), (u16) seq(sw::K,sw::_8), (u16) seq(sw::K,sw::_9), (u16) seq(sw::K,sw::DOT),
  (u16) seq(sw::K,sw::NEG), (u16) seq(sw::K,sw::POW), (u16) seq(sw::K,sw::CX), (u16) seq(sw::K,sw::Bx), (u16) seqNOP, (u16) seqNOP, (u16) seqNOP, (u16) seqNOP,
  (u16) seq(sw::RUN), (u16) seq(sw::JP), (u16) seq(sw::RET), (u16) seq(sw::JSR), (u16) seqNOP, (u16) seq(sw::K,sw::_1), (u16) seq(sw::K,sw::_2), (u16) seq(sw::F,sw::RUN),
  (u16) seq(sw::F,sw::JP), (u16) seq(sw::F,sw::RET), (u16) seq(sw::F,sw::JSR), (u16) seq(sw::F,sw::xP), (u16) seq(sw::F,sw::BK), (u16) seq(sw::F,sw::Px), (u16) seq(sw::F,sw::FW), (u16) seqNOP,
};
const u8 registers[15] = {
  (u8) sw::_0, (u8) sw::_1, (u8) sw::_2, (u8) sw::_3, (u8) sw::_4, (u8) sw::_5, (u8) sw::_6, (u8) sw::_7,
  (u8) sw::_8, (u8) sw::_9, (u8) sw::DOT, (u8) sw::NEG, (u8) sw::POW, (u8) sw::CX, (u8) sw::Bx
};
const u8 indirect[8] = {
  (u8) sw::RUN, (u8) sw::JP, (u8) sw::RET, (u8) sw::JSR, (u8) sw::xP, (u8) sw::BK, (u8) sw::Px, (u8) sw::FW
};
} // namespace

u32 sequence(u8 opcode) {
  if(opcode < 0x40) return 0xFFFF0000U | direct[opcode];
  if(opcode >= 0x50 && opcode < 0x60)
    return 0xFFFF0000U | direct[opcode - 0x10];
  const u8 reg = opcode & 15U;
  if(opcode >= COUNT || reg == 15) return seqNOP;
  if(opcode < 0x50) return seq(sw::xP, (sw) registers[reg]);
  if(opcode < 0x70) return seq(sw::Px, (sw) registers[reg]);
  return seq(sw::K, (sw) indirect[(opcode >> 4) - 7], (sw) registers[reg]);
}
} // namespace terminal_keys
