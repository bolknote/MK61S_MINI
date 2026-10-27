#ifndef MK61_DISASM_LINE_HPP
#define MK61_DISASM_LINE_HPP

#include "rust_types.h"

namespace disasm_line {

static constexpr usize WIDTH = 5;
using Buffer = char[WIDTH + 1];

// The display retains every character cell until it is explicitly rewritten.
// Start each update with spaces so a shorter instruction erases the tail of
// the previously displayed mnemonic; keep the terminator outside the field.
inline void clear(Buffer& buffer) {
  for(usize i = 0; i < WIDTH; ++i) buffer[i] = ' ';
  buffer[WIDTH] = 0;
}

inline void assign(Buffer& buffer, const char* text) {
  clear(buffer);
  if(text == nullptr) return;
  for(usize i = 0; i < WIDTH && text[i] != 0; ++i) buffer[i] = text[i];
}

} // namespace disasm_line

#endif
