#include <cstdio>
#include "cross_hal.h"
#include "terminal_key_sequence.hpp"
#include "terminal_key_sequence_legacy.hpp"

int main() {
  static_assert(sizeof(legacy_key_sequences) / sizeof(u32) == terminal_keys::COUNT);
  for(unsigned opcode = 0; opcode < 256; ++opcode) {
    const u32 expected = opcode < terminal_keys::COUNT ? legacy_key_sequences[opcode] : seqNOP;
    const u32 actual = terminal_keys::sequence((u8) opcode);
    if(actual != expected) {
      std::fprintf(stderr, "opcode=%02x expected=%08lx actual=%08lx\n", opcode,
                   (unsigned long) expected, (unsigned long) actual);
      return 1;
    }
  }
  std::puts("terminal key sequences: all 240 opcodes + invalid range PASS");
}
