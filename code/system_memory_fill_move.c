// Separate translation unit keeps the already qualified memcpy/memcmp code
// independent of GCC's decisions to share/outline the new bulk helpers.
#if (defined(ARDUINO_ARCH_STM32) && defined(__ARM_ARCH_7EM__)) || \
    defined(MK61_MEMORY_TEST_BUILD)
#if defined(__GNUC__) && !defined(__clang__)
// Byte tails must not become recursive libc calls.
#pragma GCC optimize ("no-tree-loop-distribute-patterns")
#endif
#include "memory_word_ops.h"

void* memset(void* destination, int value, size_t size) {
  return mk61_memory_fill(destination, value, size);
}

void* memmove(void* destination, const void* source, size_t size) {
  return mk61_memory_move(destination, source, size);
}
#endif
