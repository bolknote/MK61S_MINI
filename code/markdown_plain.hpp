#ifndef MK61_MARKDOWN_PLAIN_HPP
#define MK61_MARKDOWN_PLAIN_HPP

#include "rust_types.h"

namespace markdown_plain {

static constexpr u16 MAX_SOURCE_SIZE = 1536;
static constexpr u16 MAX_OUTPUT_SIZE = 2048;

enum class Status : u8 {
  OK = 0,
  INVALID_ARGUMENT,
  SOURCE_TOO_LARGE,
  OUTPUT_TOO_SMALL
};

// Converts Markdown directly to the semantic text shown on a character LCD.
// This path deliberately has no compiled document, style model or graphics.
Status convert(const u8* source, u16 source_size,
               char* output, u16 output_capacity, u16& output_size);

} // namespace markdown_plain

#endif
