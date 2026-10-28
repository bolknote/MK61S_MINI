#ifndef MK61_LANGUAGE_COMPILER_WORKSPACE_HPP
#define MK61_LANGUAGE_COMPILER_WORKSPACE_HPP
#include <stddef.h>

// Shared frontend sources still declare the legacy interpreter helpers. In
// compiler-only builds no AST lines are allocated or populated: parsing is
// performed by the bytecode emitter. Indexing an eliminated legacy table
// fails closed, rather than silently providing a one-element dummy array.
template <typename Line>
struct EliminatedAstLines {
  Line& operator[](size_t) { __builtin_trap(); }
  const Line& operator[](size_t) const { __builtin_trap(); }
};
#endif
