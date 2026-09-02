#include "stack_watermark.hpp"

#include <assert.h>
#include <stdio.h>

int main(void) {
  u32 words[32] = {};
  for(usize index = 0; index < 32; index++) {
    words[index] = stack_watermark::pattern(index);
  }
  assert(stack_watermark::untouchedPrefixWords(words, 32) == 32);

  words[31] = 0;
  assert(stack_watermark::untouchedPrefixWords(words, 32) == 31);
  words[24] = 0;
  assert(stack_watermark::untouchedPrefixWords(words, 32) == 24);
  words[0] = 0;
  assert(stack_watermark::untouchedPrefixWords(words, 32) == 0);
  assert(stack_watermark::untouchedPrefixWords(nullptr, 32) == 0);
  assert(stack_watermark::untouchedPrefixWords(words, 0) == 0);

  static_assert(stack_watermark::pattern(0) !=
                stack_watermark::pattern(1),
                "adjacent watermark words must differ");
  puts("stack_watermark_self_test: ok");
  return 0;
}
