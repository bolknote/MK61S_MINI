#ifndef MK61_EARLY_DFU_PROTOCOL_HPP
#define MK61_EARLY_DFU_PROTOCOL_HPP

#include "rust_types.h"

namespace early_dfu_protocol {

static constexpr u32 MAGIC = 0x31465544UL; // "DUF1" LE.
static constexpr u32 DIAGNOSTIC_PREFIX = 0xDFD10000UL;
static constexpr u32 DIAGNOSTIC_PREFIX_MASK = 0xFFFF0000UL;
static constexpr u32 ATTEMPT_PREFIX = 0xDFD20000UL;
static constexpr u32 ATTEMPT_PREFIX_MASK = 0xFFFFFF00UL;
static constexpr u8 MAX_ATTEMPTS = 3;

enum Source : u8 {
  SOURCE_NONE = 0,
  SOURCE_SRAM = 1U << 0,
  SOURCE_BACKUP = 1U << 1,
  SOURCE_ESCAPE = 1U << 2,
  // Diagnostic-only bit: the ROM loader needed more than one attempt.
  SOURCE_RETRY = 1U << 3
};

enum Stage : u8 {
  STAGE_NONE = 0,
  STAGE_PUBLISHED = 1,
  STAGE_ACCEPTED = 2,
  STAGE_VECTOR_INVALID = 3,
  STAGE_BRANCHING = 4,
  STAGE_RETRYING = 5,
  STAGE_COMPLETED = 6,
  STAGE_RETRY_EXHAUSTED = 7,
  STAGE_ABORTED = 8
};

struct Request {
  u32 magic;
  u32 inverse_magic;
};

constexpr bool valid(u32 magic, u32 inverse_magic) {
  return magic == MAGIC && inverse_magic == ~MAGIC;
}

struct Diagnostic {
  bool valid;
  u8 generation;
  Stage stage;
  u8 sources;
};

constexpr u32 diagnostic_word(u8 generation, Stage stage, u8 sources) {
  return DIAGNOSTIC_PREFIX |
      ((u32) generation << 8) |
      ((u32) stage << 4) |
      (sources & 0x0FU);
}

constexpr Diagnostic decode_diagnostic(u32 word) {
  return {
    (word & DIAGNOSTIC_PREFIX_MASK) == DIAGNOSTIC_PREFIX &&
        ((word >> 4) & 0x0FU) <= STAGE_ABORTED,
    (u8) (word >> 8),
    (Stage) ((word >> 4) & 0x0FU),
    (u8) (word & 0x0FU)
  };
}

// The ROM bootloader on STM32F411 deliberately issues SYSRESETREQ when its
// HSE qualification fails. This torn-safe retained pair lets the application
// distinguish that reset from a normal DFU leave and retry a bounded number
// of times without creating a permanent boot loop.
struct Attempt {
  bool valid;
  u8 number;
  u8 sources;
};

constexpr u32 attempt_word(u8 number, u8 sources) {
  return ATTEMPT_PREFIX |
      ((u32) (number & 0x0FU) << 4) |
      (sources & 0x0FU);
}

constexpr Attempt decode_attempt(u32 word, u32 inverse_word) {
  const u8 number = (u8) ((word >> 4) & 0x0FU);
  const u8 sources = (u8) (word & 0x0FU);
  return {
    inverse_word == ~word &&
        (word & ATTEMPT_PREFIX_MASK) == ATTEMPT_PREFIX &&
        number >= 1 && number <= MAX_ATTEMPTS &&
        sources != SOURCE_NONE &&
        (sources & SOURCE_RETRY) == 0,
    number,
    sources
  };
}

constexpr bool retry_after_reset(const Attempt& attempt,
                                 bool software_reset) {
  return attempt.valid && software_reset &&
      attempt.number < MAX_ATTEMPTS;
}

constexpr u8 next_generation(u32 previous_word) {
  const Diagnostic previous = decode_diagnostic(previous_word);
  return !previous.valid || previous.generation == 0xFF
      ? 1 : (u8) (previous.generation + 1U);
}

} // namespace early_dfu_protocol

#endif
