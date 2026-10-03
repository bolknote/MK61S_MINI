#include "dfu_splash.hpp"
#include "zx0.hpp"
#include "fixtures/dfu_splash_bitmap.hpp"
#include <vector>

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

int main(int argc, char** argv) {
  if(argc == 2 && strcmp(argv[1], "--pack") == 0) {
    std::vector<u8> workspace(4 * (sizeof(SOURCE_BITMAP) + 1));
    std::vector<u8> packed;
    zx0::Output output = {&packed, [](void* p, u8 value) {
      static_cast<std::vector<u8>*>(p)->push_back(value);
      return true;
    }};
    zx0::EncodeResult result = {};
    assert(zx0::encode(SOURCE_BITMAP, sizeof(SOURCE_BITMAP),
                      workspace.data(), workspace.size(), output, result));
    for(usize i = 0; i < packed.size(); i++)
      printf("%s0x%02X,%s", i % 16 == 0 ? "    " : "", packed[i],
             i % 16 == 15 || i + 1 == packed.size() ? "\n" : " ");
    return 0;
  }
  static_assert(dfu_splash::WIDTH == 192, "DFU splash width changed");
  static_assert(dfu_splash::HEIGHT == 64, "DFU splash height changed");
  static_assert(dfu_splash::BYTE_COUNT == 1536, "DFU splash size changed");

  u8 bitmap[dfu_splash::BYTE_COUNT] = {};
  assert(!dfu_splash::decode(nullptr, sizeof(bitmap)));
  assert(!dfu_splash::decode(bitmap, sizeof(bitmap) - 1U));
  assert(dfu_splash::decode(bitmap, sizeof(bitmap)));
  assert(fnv1a32(bitmap, sizeof(bitmap)) == 0x4A385D9Eu);
  assert(memcmp(bitmap, SOURCE_BITMAP, sizeof(bitmap)) == 0);
  u8 guarded[dfu_splash::BYTE_COUNT + 2];
  memset(guarded, 0xA5, sizeof(guarded));
  assert(dfu_splash::decode(guarded + 1, sizeof(guarded) - 1));
  assert(guarded[0] == 0xA5 && guarded[sizeof(guarded) - 1] == 0xA5);
  assert(memcmp(guarded + 1, SOURCE_BITMAP, sizeof(bitmap)) == 0);
  assert(dfu_splash::packed_byte_count() == 457U);
  assert(dfu_splash::packed_byte_count() < dfu_splash::BYTE_COUNT / 2U);
  printf("dfu_splash_self_test: ok\n");
  return 0;
}
