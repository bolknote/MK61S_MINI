#include <cassert>
#include <cstdio>
#include <cstring>

#include "program_memory_policy.hpp"

static usize opcode_length(u8 opcode) {
  return opcode == 0x51U || opcode == 0x53U ||
      (opcode >= 0x57U && opcode <= 0x5EU) ? 2U : 1U;
}

static bool needs_expanded(const u8* code_page, usize code_len) {
  return program_memory_policy::listing_needs_expanded_memory(
      code_page, code_len, &opcode_length);
}

static void test_extended_only_commands(void) {
  u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};

  code_page[0] = MK61_EXCHANGE_DATA_WITH_MS;
  assert(needs_expanded(code_page, 1));

  std::memset(code_page, 0, sizeof(code_page));
  code_page[17] = MK61_EXCHANGE_PROGRAM_WITH_MS;
  assert(needs_expanded(code_page, 18));

  std::memset(code_page, 0, sizeof(code_page));
  code_page[0] = program_memory_policy::STORE_REGISTER_F;
  assert(needs_expanded(code_page, 1));

  code_page[0] = program_memory_policy::LOAD_REGISTER_F;
  assert(needs_expanded(code_page, 1));
}

static void test_exchange_bytes_used_as_operands(void) {
  static const u8 two_byte_opcodes[] = {
      0x51U, 0x53U, 0x57U, 0x58U, 0x59U,
      0x5AU, 0x5BU, 0x5CU, 0x5DU, 0x5EU
  };
  u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};

  for(u8 opcode : two_byte_opcodes) {
    code_page[0] = opcode;
    code_page[1] = MK61_EXCHANGE_DATA_WITH_MS;
    assert(!needs_expanded(code_page, 2));

    code_page[1] = MK61_EXCHANGE_PROGRAM_WITH_MS;
    assert(!needs_expanded(code_page, 2));
  }

  code_page[0] = 0x51U;
  code_page[1] = MK61_EXCHANGE_DATA_WITH_MS;
  code_page[2] = MK61_EXCHANGE_PROGRAM_WITH_MS;
  assert(needs_expanded(code_page, 3));
}

static void test_program_size_detection_and_bounds(void) {
  u8 code_page[core_61::CODE_PAGE_BUFFER_SIZE] = {};
  assert(!needs_expanded(code_page, core_61::MAX_PROGRAM_STEP));
  assert(!needs_expanded(nullptr, 0));

  code_page[core_61::CLASSIC_PROGRAM_STEP] = 0x01U;
  assert(needs_expanded(code_page,
      core_61::CLASSIC_PROGRAM_STEP + 1U));

  std::memset(code_page, 0, sizeof(code_page));
  code_page[core_61::MAX_PROGRAM_STEP] = MK61_EXCHANGE_DATA_WITH_MS;
  assert(!needs_expanded(code_page,
      core_61::CODE_PAGE_BUFFER_SIZE));
}

int main(void) {
  test_extended_only_commands();
  test_exchange_bytes_used_as_operands();
  test_program_size_detection_and_bounds();
  std::puts("program_memory_policy_self_test: ok");
  return 0;
}
