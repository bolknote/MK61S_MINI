#ifndef MK61_EXPLORER_LABEL_HPP
#define MK61_EXPLORER_LABEL_HPP

#include "bounded_string.hpp"
#include "program_store.hpp"

namespace explorer_label {

// Include the longest suffix (.state.txt), '/' and the terminator. The same
// complete label is measured, scrolled and drawn by resident and APP Explorer.
static constexpr usize SIZE = program_store::NAME_SIZE + 16;

inline void format(const program_store::Entry& entry, char (&out)[SIZE]) {
  const usize length = bounded_string::copy(out, program_store::NAME_SIZE,
                                             entry.name);
  const bool directory = entry.kind == program_store::NodeKind::DIRECTORY;
  out[length] = directory ? '/' : '.';
  bounded_string::copy(out + length + 1, SIZE - length - 1,
      directory ? "" : program_store::file_extension(entry.type));
}

} // namespace explorer_label

#endif
