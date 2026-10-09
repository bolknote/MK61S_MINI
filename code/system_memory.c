// Strong ISO C symbols replace newlib's size-optimised byte loops throughout
// the STM32 resident. System APP runtime slots resolve to these same symbols.
#if (defined(ARDUINO_ARCH_STM32) && defined(__ARM_ARCH_7EM__)) || \
    defined(MK61_MEMORY_TEST_BUILD)

#if defined(__GNUC__) && !defined(__clang__)
// A byte-tail loop must not be rewritten into a recursive memcpy call.
#pragma GCC optimize ("no-tree-loop-distribute-patterns")
#endif
#include "memory_word_ops.h"

void* memcpy(void* destination, const void* source, size_t size) {
  return mk61_memory_copy(destination, source, size);
}

int memcmp(const void* left, const void* right, size_t size) {
  return mk61_memory_compare(left, right, size);
}
#endif
