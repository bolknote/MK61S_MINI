#ifndef MK61_PROGRAM_MEMORY_POLICY_HPP
#define MK61_PROGRAM_MEMORY_POLICY_HPP

#include "mk61emu_core.h"

namespace program_memory_policy {

static constexpr u8 STORE_REGISTER_F = 0x4FU;
static constexpr u8 LOAD_REGISTER_F = 0x6FU;

constexpr bool opcode_needs_expanded_memory(u8 opcode) {
  return opcode == STORE_REGISTER_F || opcode == LOAD_REGISTER_F ||
      opcode == MK61_EXCHANGE_DATA_WITH_MS ||
      opcode == MK61_EXCHANGE_PROGRAM_WITH_MS;
}

using OpcodeLength = usize (*)(u8 opcode);

inline bool listing_needs_expanded_memory(const u8* code_page,
                                          usize code_len,
                                          OpcodeLength opcode_length) {
  if(code_page == nullptr) return false;

  const usize bounded_len =
      (code_len > core_61::MAX_PROGRAM_STEP)
          ? core_61::MAX_PROGRAM_STEP : code_len;

  for(usize i = core_61::CLASSIC_PROGRAM_STEP; i < bounded_len; i++) {
    if(code_page[i] != 0) return true;
  }

  for(usize i = 0; i < bounded_len;) {
    const u8 opcode = code_page[i];
    if(opcode_needs_expanded_memory(opcode)) return true;
    const usize opcode_len = opcode_length(opcode);
    i += (opcode_len == 0) ? 1 : opcode_len;
  }

  return false;
}

} // namespace program_memory_policy

#endif
