#include "dfu_splash.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>

namespace {

u32 fnv1a32(const u8* data, usize size) {
  u32 hash = 2166136261u;
  for(usize i = 0; i < size; i++) {
    hash ^= data[i];
    hash *= 16777619u;
  }
  return hash;
}

} // безымянное пространство имён

int main(void) {
  static_assert(dfu_splash::WIDTH == 192, "DFU splash width changed");
  static_assert(dfu_splash::HEIGHT == 64, "DFU splash height changed");
  static_assert(dfu_splash::BYTE_COUNT == 1536, "DFU splash size changed");

  u8 bitmap[dfu_splash::BYTE_COUNT] = {};
  assert(!dfu_splash::decode(nullptr, sizeof(bitmap)));
  assert(!dfu_splash::decode(bitmap, sizeof(bitmap) - 1U));
  assert(dfu_splash::decode(bitmap, sizeof(bitmap)));
  assert(fnv1a32(bitmap, sizeof(bitmap)) == 0x4A385D9Eu);
  assert(dfu_splash::packed_byte_count() == 523U);
  assert(dfu_splash::packed_byte_count() < dfu_splash::BYTE_COUNT / 2U);
  printf("dfu_splash_self_test: ok\n");
  return 0;
}
