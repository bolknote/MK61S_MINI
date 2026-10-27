#include "zx0.hpp"

#include <cassert>
#include <cstdio>
#include <vector>

static const std::vector<u8>* observing = nullptr;
static std::vector<u8> immutable;
static unsigned polls = 0;

static void progress() {
  ++polls;
  assert(observing && *observing == immutable);
}

struct Sink {
  std::vector<u8> bytes;
  static bool next(void* context, u8 byte) {
    static_cast<Sink*>(context)->bytes.push_back(byte);
    return true;
  }
};

struct Read {
  const std::vector<u8>* bytes;
  usize at = 0;
  static bool next(void* context, u8& byte) {
    auto& reader = *static_cast<Read*>(context);
    if(reader.at == reader.bytes->size()) return false;
    byte = (*reader.bytes)[reader.at++];
    return true;
  }
};

int main() {
  unsigned cases = 0;
  unsigned observed = 0;
  u32 random = 0x8123abcd;
  for(usize size: {31, 128, 383, 8192}) {
    for(unsigned pattern = 0; pattern < 4; ++pattern) {
      std::vector<u8> input(size);
      for(usize i = 0; i < size; ++i) {
        random ^= random << 13;
        random ^= random >> 17;
        random ^= random << 5;
        input[i] = pattern == 0 ? 0 : pattern == 1 ? (u8) (i % 37) :
            pattern == 2 ? (u8) (i % 8 == 0 ? i / 8 : 0) : (u8) random;
      }
      // Exercise greedy and bounded-optimal plans, including a failed plan.
      for(usize capacity: {(usize) 256, (usize) 1600,
                           size <= 383 ? 4 * (size + 1) + 16 : (usize) 1600}) {
        std::vector<u8> first_workspace(capacity), second_workspace(capacity);
        zx0::Prepared first{}, second{};
        observing = &input;
        immutable = input;
        polls = 0;
        const bool original = zx0::prepare(input.data(), size,
            first_workspace.data(), first_workspace.size(), first);
        const bool cooperative = zx0::prepare_cooperative(input.data(), size,
            second_workspace.data(), second_workspace.size(), second, progress);
        assert(original == cooperative && input == immutable);
        observed += polls > 0;
        if(size == 8192) assert(polls > 0);
        if(original) {
          assert(first.output_size == second.output_size);
          assert(first.token_count == second.token_count && first.mode == second.mode);
          Sink old_stream, cooperative_stream;
          assert(zx0::emit(first, {&old_stream, Sink::next}));
          assert(zx0::emit(second, {&cooperative_stream, Sink::next}));
          assert(old_stream.bytes == cooperative_stream.bytes);
          Read read{&cooperative_stream.bytes};
          std::vector<u8> output(size);
          u32 written = 0;
          assert(zx0::decode({&read, Read::next}, cooperative_stream.bytes.size(),
                            output.data(), output.size(), written));
          assert(written == size && output == input);
        }
        ++cases;
      }
    }
  }
  u8 bytes[16] = {};
  zx0::Prepared prepared{};
  polls = 0;
  assert(!zx0::prepare_cooperative(nullptr, 16, bytes, 16, prepared, progress));
  assert(!zx0::prepare_cooperative(bytes, 0, bytes, 16, prepared, progress));
  assert(!zx0::prepare_cooperative(bytes, 16, bytes, 16, prepared, progress));
  assert(polls == 0 && observed > 0);
  std::printf("ZX0 cooperative planner PASS: %u byte-exact/null/failure/roundtrip "
              "cases, %u observed plans; input immutable\n", cases, observed);
}
