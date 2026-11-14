#ifndef MK61_STACK_WATERMARK_HPP
#define MK61_STACK_WATERMARK_HPP

#include "rust_types.h"

namespace stack_watermark {

// Address-independent per-word values make an accidental untouched-looking
// overwrite far less likely than a repeated magic constant.  The index is
// relative to the protected stack floor, so host tests and either STM32 SRAM
// size use exactly the same rule.
constexpr u32 pattern(usize word_index) {
  return 0xA55A3CC3UL ^
         (u32) ((u32) word_index * 0x9E3779B9UL);
}

inline usize untouchedPrefixWords(const volatile u32* words, usize count) {
  if(words == nullptr) return 0;
  usize index = 0;
  while(index < count && words[index] == pattern(index)) index++;
  return index;
}

} // namespace stack_watermark

#endif
