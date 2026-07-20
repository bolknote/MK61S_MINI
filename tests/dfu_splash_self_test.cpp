#include "dfu_splash.hpp"

#include <assert.h>
#include <stdio.h>

namespace {

u32 fnv1a32(const u8* data, usize size) {
  u32 hash = 2166136261u;
  for(usize i = 0; i < size; i++) {
    hash ^= data[i];
    hash *= 16777619u;
  }
  return hash;
}

} // namespace

int main(void) {
  static_assert(dfu_splash::WIDTH == 192, "DFU splash width changed");
  static_assert(dfu_splash::HEIGHT == 64, "DFU splash height changed");
  static_assert(dfu_splash::BYTE_COUNT == 1536, "DFU splash size changed");

  assert(fnv1a32(dfu_splash::BITMAP, dfu_splash::BYTE_COUNT) == 0x4A385D9Eu);
  printf("dfu_splash_self_test: ok\n");
  return 0;
}
