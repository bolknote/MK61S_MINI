#include <assert.h>
#include <stdio.h>
#include <string.h>

#include <vector>

#include "../code/zx0.hpp"

namespace {

static bool append_byte(void* context, u8 value) {
  ((std::vector<u8>*) context)->push_back(value);
  return true;
}

struct FailingOutput {
  usize accepted;
  usize limit;
};

static bool fail_after_limit(void* context, u8) {
  FailingOutput& output = *(FailingOutput*) context;
  if(output.accepted >= output.limit) return false;
  output.accepted++;
  return true;
}

struct VectorInput {
  const std::vector<u8>* bytes;
  usize position;
};

static bool next_byte(void* context, u8& value) {
  VectorInput& input = *(VectorInput*) context;
  if(input.position >= input.bytes->size()) return false;
  value = (*input.bytes)[input.position++];
  return true;
}

static std::vector<u8> pack(const std::vector<u8>& source,
                            usize workspace_size,
                            zx0::EncodeResult& result) {
  std::vector<u8> workspace(workspace_size + 4U);
  std::vector<u8> packed;
  const zx0::Output output = {&packed, append_byte};
  assert(zx0::encode(source.data(), (u32) source.size(),
                     workspace.data() + 1, workspace_size,
                     output, result));
  return packed;
}

static void verify_round_trip(const std::vector<u8>& source,
                              usize workspace_size,
                              zx0::EncodeMode expected_mode) {
  zx0::EncodeResult result = {};
  const std::vector<u8> packed = pack(source, workspace_size, result);
  assert(result.mode == expected_mode);
  assert(result.output_size == packed.size());

  VectorInput memory = {&packed, 0};
  const zx0::Input input = {&memory, next_byte};
  std::vector<u8> output(source.size());
  u32 written = 0;
  if(!zx0::decode(input, (u32) packed.size(), output.data(),
                  (u32) output.size(), written)) {
    fprintf(stderr, "round-trip failed: source=%zu packed=%zu workspace=%zu "
                    "written=%u mode=%u\n",
            source.size(), packed.size(), (size_t) workspace_size, written,
            (unsigned) result.mode);
    for(u8 value : packed) fprintf(stderr, "%02X ", value);
    fputc('\n', stderr);
    assert(false);
  }
  assert(written == source.size());
  assert(output == source);
}

static void test_short_inputs(void) {
  for(usize size = 1; size <= 32; size++) {
    std::vector<u8> source(size);
    for(usize index = 0; index < size; index++) {
      source[index] = (u8) (index * 73U + size);
    }
    verify_round_trip(source, 1024, zx0::EncodeMode::BOUNDED_OPTIMAL);
  }
}

static void test_repetitions_and_offsets(void) {
  std::vector<u8> repeated(1024, 'x');
  zx0::EncodeResult result = {};
  const std::vector<u8> packed = pack(repeated, 8192, result);
  assert(result.mode == zx0::EncodeMode::BOUNDED_OPTIMAL);
  assert(packed.size() < 20);
  verify_round_trip(repeated, 8192, zx0::EncodeMode::BOUNDED_OPTIMAL);

  std::vector<u8> distant(700);
  for(usize index = 0; index < 350; index++) {
    distant[index] = (u8) (index * 29U + index / 7U);
  }
  memcpy(distant.data() + 350, distant.data() + 150, 200);
  for(usize index = 550; index < distant.size(); index++) {
    distant[index] = (u8) (index * 11U);
  }
  verify_round_trip(distant, 8192, zx0::EncodeMode::BOUNDED_OPTIMAL);
}

static void test_greedy_fallback(void) {
  std::vector<u8> source(600, 'A');
  for(usize index = 0; index < source.size(); index += 37) {
    source[index] = (u8) index;
  }
  verify_round_trip(source, 512, zx0::EncodeMode::GREEDY);
}

static void test_deterministic_output(void) {
  std::vector<u8> source(900);
  for(usize index = 0; index < source.size(); index++) {
    source[index] = (u8) ((index % 71U) ^ (index / 13U));
  }
  zx0::EncodeResult first_result = {};
  zx0::EncodeResult second_result = {};
  const std::vector<u8> first = pack(source, 8192, first_result);
  const std::vector<u8> second = pack(source, 8192, second_result);
  assert(first == second);
  assert(first_result.output_size == second_result.output_size);
  assert(first_result.mode == second_result.mode);
}

static void verify_prepared_reuse(const std::vector<u8>& source,
                                  usize workspace_size,
                                  zx0::EncodeMode expected_mode) {
  zx0::EncodeResult encoded_result = {};
  const std::vector<u8> encoded =
      pack(source, workspace_size, encoded_result);

  std::vector<u8> workspace(workspace_size + 4U);
  zx0::Prepared prepared = {};
  assert(zx0::prepare(source.data(), (u32) source.size(),
                      workspace.data() + 1, workspace_size, prepared));
  assert(prepared.output_size == encoded.size());
  assert(prepared.mode == expected_mode);
  const std::vector<u8> snapshot = workspace;

  std::vector<u8> first;
  const zx0::Output first_sink = {&first, append_byte};
  assert(zx0::emit(prepared, first_sink));
  assert(first == encoded);
  assert(workspace == snapshot);

  FailingOutput failing = {0, prepared.output_size / 2U};
  const zx0::Output failing_sink = {&failing, fail_after_limit};
  assert(!zx0::emit(prepared, failing_sink));
  assert(failing.accepted == prepared.output_size / 2U);
  assert(workspace == snapshot);

  std::vector<u8> second;
  const zx0::Output second_sink = {&second, append_byte};
  assert(zx0::emit(prepared, second_sink));
  assert(second == encoded);
  assert(workspace == snapshot);

  zx0::Prepared invalid = prepared;
  invalid.control_count = 0;
  assert(!zx0::emit(invalid, second_sink));
  invalid = prepared;
  invalid.token_count = 0;
  assert(!zx0::emit(invalid, second_sink));
}

static void test_prepared_reuse(void) {
  std::vector<u8> bounded(900);
  for(usize index = 0; index < bounded.size(); index++) {
    bounded[index] = (u8) ((index % 71U) ^ (index / 13U));
  }
  verify_prepared_reuse(bounded, 8192,
                        zx0::EncodeMode::BOUNDED_OPTIMAL);

  std::vector<u8> greedy(600, 'A');
  for(usize index = 0; index < greedy.size(); index += 37) {
    greedy[index] = (u8) index;
  }
  verify_prepared_reuse(greedy, 512, zx0::EncodeMode::GREEDY);
}

static void test_range_decode(void) {
  std::vector<u8> source(1536);
  for(usize index = 0; index < source.size(); index++) {
    source[index] = (u8) ((index * 17U + index / 31U) % 113U);
  }
  zx0::EncodeResult result = {};
  const std::vector<u8> packed = pack(source, 8192, result);

  const u32 ranges[][2] = {
    {0, 1}, {0, 512}, {63, 64}, {255, 513}, {1024, 512}, {1536, 0}
  };
  for(const auto& range : ranges) {
    VectorInput memory = {&packed, 0};
    const zx0::Input input = {&memory, next_byte};
    std::vector<u8> output(range[1]);
    u8 window[256] = {};
    assert(zx0::decode_range(input, (u32) packed.size(),
                             (u32) source.size(), range[0],
                             output.empty() ? nullptr : output.data(),
                             range[1], window, sizeof(window)));
    assert(memory.position == packed.size());
    assert(memcmp(output.data(), source.data() + range[0], range[1]) == 0);
  }

  VectorInput short_window_memory = {&packed, 0};
  const zx0::Input short_window_input = {
    &short_window_memory, next_byte
  };
  u8 output[32] = {};
  u8 short_window[8] = {};
  assert(!zx0::decode_range(short_window_input, (u32) packed.size(),
                            (u32) source.size(), 0, output, sizeof(output),
                            short_window, sizeof(short_window)));

  std::vector<u8> trailing = packed;
  trailing.push_back(0);
  VectorInput trailing_memory = {&trailing, 0};
  const zx0::Input trailing_input = {&trailing_memory, next_byte};
  u8 window[256] = {};
  assert(!zx0::decode_range(trailing_input, (u32) trailing.size(),
                            (u32) source.size(), 0, output, sizeof(output),
                            window, sizeof(window)));
}

static void test_invalid_arguments(void) {
  u8 source = 1;
  u8 workspace[32] = {};
  std::vector<u8> packed;
  const zx0::Output output = {&packed, append_byte};
  zx0::EncodeResult result = {};
  assert(!zx0::encode(nullptr, 1, workspace, sizeof(workspace),
                      output, result));
  assert(!zx0::encode(&source, 0, workspace, sizeof(workspace),
                      output, result));
  assert(!zx0::encode(&source, 1, nullptr, sizeof(workspace),
                      output, result));
  assert(!zx0::encode(workspace, 1, workspace, sizeof(workspace),
                      output, result));
  const zx0::Output invalid_output = {nullptr, nullptr};
  assert(!zx0::encode(&source, 1, workspace, sizeof(workspace),
                      invalid_output, result));

  zx0::Prepared prepared = {};
  assert(!zx0::prepare(nullptr, 1, workspace, sizeof(workspace), prepared));
  assert(!zx0::prepare(&source, 0, workspace, sizeof(workspace), prepared));
  assert(!zx0::prepare(&source, 1, nullptr, sizeof(workspace), prepared));
  assert(!zx0::prepare(workspace, 1, workspace,
                       sizeof(workspace), prepared));
  assert(!zx0::emit(prepared, output));
}

} // namespace

int main(void) {
  test_short_inputs();
  test_repetitions_and_offsets();
  test_greedy_fallback();
  test_deterministic_output();
  test_prepared_reuse();
  test_range_decode();
  test_invalid_arguments();
  puts("zx0 encode self-test: ok");
  return 0;
}
