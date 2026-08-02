#include <assert.h>
#include <stdio.h>

#include <vector>

#include "../code/crc32.hpp"

namespace {

static u32 software_crc(const u8* data, usize size) {
  return mk61_crc32::finish(
      mk61_crc32::extend(mk61_crc32::INITIAL_STATE, data, size));
}

static void verify_chunks(const std::vector<u8>& data, usize chunk_size) {
  mk61_crc32::Context context;
#if defined(MK61_CRC32_EMULATE_STM32)
  assert(context.using_hardware());
#endif
  usize offset = 0;
  while(offset < data.size()) {
    const usize count = data.size() - offset < chunk_size
        ? data.size() - offset : chunk_size;
    assert(context.update(data.data() + offset, count));
    offset += count;
  }
  assert(context.finish() == software_crc(data.data(), data.size()));
  assert(context.finish() == software_crc(data.data(), data.size()));
}

static void test_known_vector(void) {
  static const u8 digits[] = "123456789";
  assert(software_crc(digits, sizeof(digits) - 1U) == 0xCBF43926UL);
  mk61_crc32::Context context;
  assert(context.update(digits, sizeof(digits) - 1U));
  assert(context.finish() == 0xCBF43926UL);
}

static void test_sizes_and_chunking(void) {
  std::vector<u8> data(4095);
  u32 state = 0xC5A55A3CUL;
  for(usize index = 0; index < data.size(); index++) {
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    data[index] = (u8) state;
  }

  const usize chunks[] = {1, 2, 3, 4, 5, 7, 16, 63, 64, 255, 512};
  for(usize size = 0; size <= 80; size++) {
    std::vector<u8> prefix(data.begin(), data.begin() + size);
    for(usize chunk : chunks) verify_chunks(prefix, chunk);
  }
  const usize sizes[] = {
    127, 128, 129, 255, 256, 257, 511, 512, 513,
    1023, 1536, 2048, 3584, 4095
  };
  for(usize size : sizes) {
    std::vector<u8> prefix(data.begin(), data.begin() + size);
    for(usize chunk : chunks) verify_chunks(prefix, chunk);
  }
}

static void test_sequential_contexts(void) {
  const u8 first[] = {1, 2, 3};
  const u8 second[] = {4, 5, 6, 7, 8};
  {
    mk61_crc32::Context first_context;
    assert(first_context.update(first, sizeof(first)));
    assert(first_context.finish() == software_crc(first, sizeof(first)));
  }
  mk61_crc32::Context second_context;
  assert(second_context.update(second, sizeof(second)));
  assert(second_context.finish() == software_crc(second, sizeof(second)));
}

static void test_nested_contexts_are_isolated(void) {
  const u8 outer_data[] = {0x61, 0x5A, 0xC5, 1, 2, 3, 4, 5, 6};
  const u8 inner_data[] = {9, 8, 7, 6, 5, 4, 3, 2, 1};
  mk61_crc32::reset_arbitration_statistics();
  mk61_crc32::Context outer;
  assert(outer.update(outer_data, 4));
  {
    mk61_crc32::Context inner;
#if defined(MK61_CRC32_EMULATE_STM32)
    assert(outer.using_hardware());
    assert(!inner.using_hardware());
#endif
    assert(inner.update(inner_data, sizeof(inner_data)));
    assert(inner.finish() == software_crc(inner_data, sizeof(inner_data)));
  }
  assert(outer.update(outer_data + 4, sizeof(outer_data) - 4));
  assert(outer.finish() == software_crc(outer_data, sizeof(outer_data)));

  const mk61_crc32::ArbitrationSnapshot arbitration =
      mk61_crc32::arbitration_statistics();
#if defined(MK61_CRC32_EMULATE_STM32)
  assert(arbitration.supported && !arbitration.busy);
  assert(arbitration.hardware_acquisitions == 1);
  assert(arbitration.software_fallbacks == 1);
  mk61_crc32::Context after;
  assert(after.using_hardware());
#else
  assert(!arbitration.supported && !arbitration.busy);
  assert(arbitration.hardware_acquisitions == 0);
  assert(arbitration.software_fallbacks == 0);
#endif
}

static void test_abandoned_context_releases_hardware(void) {
#if defined(MK61_CRC32_EMULATE_STM32)
  {
    mk61_crc32::Context abandoned;
    assert(abandoned.using_hardware());
    const u8 value = 0xA5;
    assert(abandoned.update(&value, 1));
  }
  mk61_crc32::Context next;
  assert(next.using_hardware());
#endif
}

static void test_invalid_update(void) {
  mk61_crc32::Context context;
  assert(!context.update(nullptr, 1));
  assert(context.update(nullptr, 0));
  assert(context.finish() == 0);
  const u8 value = 1;
  assert(!context.update(&value, 1));
}

} // namespace

int main(void) {
  test_known_vector();
  test_sizes_and_chunking();
  test_sequential_contexts();
  test_nested_contexts_are_isolated();
  test_abandoned_context_releases_hardware();
  test_invalid_update();
  puts("crc32_self_test: ok");
  return 0;
}
