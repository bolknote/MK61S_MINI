#ifndef MK61_TERMINAL_LISTING_HPP
#define MK61_TERMINAL_LISTING_HPP

#include "rust_types.h"

namespace terminal_listing {

static constexpr usize MAX_STEPS = 112;
static constexpr usize COLUMN_ROWS = 30;
static constexpr usize COLUMN_COUNT = 4;
static constexpr usize COLUMN_WIDTH = 28;

inline usize instruction_length(const u8* page, usize address, bool expanded) {
  const u8 opcode = page[address];
  if(expanded) {
    if(opcode == 0x2F) return 2;
    if(opcode == 0x1F) {
      const u8 next = page[address + 1];
      if(next == 0x56) return 3;
      if((next & 0xF0U) == 0x40U || next == 0x51 || next == 0x53 || (next >= 0x57 && next <= 0x5E))
        return 4;
      return 2;
    }
  }
  return opcode == 0x51 || opcode == 0x53 || (opcode >= 0x57 && opcode <= 0x5E)
      ? 2 : 1;
}

struct Layout {
  u8 lengths[MAX_STEPS] = {};
  usize end;

  // page includes three lookahead bytes for prefixes crossing a bank boundary.
  // A zero length marks an operand, independently of its byte value.
  Layout(const u8* page, usize steps, usize suggested_end, bool expanded)
      : end(suggested_end < steps ? suggested_end : steps) {
    if(steps > MAX_STEPS) steps = MAX_STEPS;
    for(usize address = 0; address < steps;) {
      const usize length = instruction_length(page, address, expanded);
      lengths[address] = (u8) length;
      if(address < end && address + length > end)
        end = address + length < steps ? address + length : steps;
      address += length;
    }
  }
};

} // namespace terminal_listing

#endif
