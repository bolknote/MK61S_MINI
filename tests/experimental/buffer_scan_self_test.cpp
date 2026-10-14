#include "buffer_scan_candidates.hpp"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>

namespace candidate = buffer_scan_candidates;
namespace protocol = usb_screen_protocol;

static u32 random_state = 0x61F411U;
static u32 next_random() {
  random_state ^= random_state << 13;
  random_state ^= random_state >> 17;
  random_state ^= random_state << 5;
  return random_state;
}

static void check_utf8(const u8* data, usize size) {
  assert(candidate::count_valid_scalar(data, size) ==
         candidate::count_valid_swar(data, size));
  assert(candidate::count_strict_scalar(data, size) ==
         candidate::count_strict_ascii(data, size));
}

static void test_utf8() {
  // Vary each lane and its neighbour through every possible byte, including
  // values whose carries would break an incorrectly written SWAR reduction.
  for(unsigned pair = 0; pair < 65536; ++pair) {
    const u8 bytes[] = {(u8) pair, (u8) (pair >> 8), 0x80, 0xFF};
    check_utf8(bytes, sizeof(bytes));
  }
  for(unsigned trial = 0; trial < 1500; ++trial) {
    const usize size = next_random() % 257;
    const usize alignment = trial % 4;
    std::vector<u8> data(size + alignment);
    for(u8& byte : data) byte = (u8) next_random();
    check_utf8(size ? data.data() + alignment : nullptr, size);
  }
  const u8 mixed[] = {'a', 'b', 'c', 0xD0, 0xAF, 'd', 0xF0, 0x9F, 0x98,
                      0x80, 'e', 'f', 'g', 'h', 0xED, 0xA0, 0x80};
  for(usize length = 0; length <= sizeof(mixed); ++length)
    check_utf8(mixed, length);
}

static void compare_plan(const u8* previous, const u8* current, bool force) {
  protocol::DiffPlan reference = {}, actual = {};
  const auto status = protocol::plan_diff(previous, current, reference, force);
  assert(candidate::plan_diff(previous, current, actual, force) == status);
  assert(reference.count == actual.count && reference.keyframe == actual.keyframe);
  for(u8 i = 0; i < reference.count; ++i) {
    assert(reference.runs[i].x == actual.runs[i].x);
    assert(reference.runs[i].page == actual.runs[i].page);
    assert(reference.runs[i].width == actual.runs[i].width);
  }
}

static void test_frames() {
  for(usize alignment = 0; alignment < 4; ++alignment) {
    std::vector<u8> old_storage(protocol::FRAME_BYTES + alignment);
    std::vector<u8> new_storage(protocol::FRAME_BYTES + alignment);
    u8* previous = old_storage.data() + alignment;
    u8* current = new_storage.data() + alignment;
    for(usize position = 0; position < protocol::FRAME_BYTES; ++position) {
      current[position] = 1;
      compare_plan(previous, current, false);
      current[position] = 0;
    }
    for(unsigned trial = 0; trial < 400; ++trial) {
      for(usize i = 0; i < protocol::FRAME_BYTES; ++i) {
        previous[i] = (u8) next_random();
        current[i] = next_random() % (trial % 17 + 1) ? previous[i] :
                                                          (u8) next_random();
      }
      compare_plan(previous, current, false);
      compare_plan(previous, current, true);
    }
  }
  compare_plan(nullptr, nullptr, false);
}

static void compare_packbits(const u8* input, usize size, usize capacity) {
  std::vector<u8> expected(capacity ? capacity : 1, 0x61);
  std::vector<u8> actual(capacity ? capacity : 1, 0x61);
  usize expected_size = 0, actual_size = 0;
  const auto status = protocol::packbits_encode(input, size, expected.data(),
                                               capacity, expected_size);
  assert(candidate::packbits_encode(input, size, actual.data(), capacity,
                                    actual_size) == status);
  assert(expected_size == actual_size && expected == actual);
}

static void test_packbits() {
  for(unsigned trial = 0; trial < 1200; ++trial) {
    const usize size = trial < 260 ? trial : next_random() % 513;
    const usize alignment = trial % 4;
    std::vector<u8> storage(size + alignment + (size == 0));
    u8* data = storage.data() + alignment;
    u8 value = 0;
    for(usize i = 0; i < size; ++i) {
      if(next_random() % (trial % 23 + 1) == 0) value = (u8) next_random();
      data[i] = value;
    }
    compare_packbits(data, size, size + 8);
    compare_packbits(data, size, next_random() % (size + 1));
    compare_packbits(data, size, 0);
  }
  for(usize size = 1; size <= 256; ++size) {
    std::vector<u8> repeated(size, 0xFF);
    for(usize capacity = 0; capacity < 9; ++capacity)
      compare_packbits(repeated.data(), size, capacity);
  }
}

int main() {
  test_utf8();
  test_frames();
  test_packbits();
  std::puts("buffer scan: UTF-8 differential, frame plans, PackBits bytes/status and exact buffer boundaries PASS");
}
