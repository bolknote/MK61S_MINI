#include "terminal_command_ids.hpp"
#include "terminal_core.hpp"

#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>

static void test_input_capacity_reserves_terminator(void) {
  assert(terminal_core::input_can_append(0));
  assert(terminal_core::input_can_append(terminal_core::MAX_INPUT_TEXT - 1));
  assert(!terminal_core::input_can_append(terminal_core::MAX_INPUT_TEXT));
  assert(terminal_core::MAX_INPUT_TEXT + 1 == terminal_core::INPUT_CAPACITY);
}

static void test_bounded_unsigned_parser(void) {
  usize value = 0;
  assert(terminal_core::parse_single_unsigned("EF", 16, 0xEF, value));
  assert(value == 0xEF);
  assert(!terminal_core::parse_single_unsigned("F0", 16, 0xEF, value));
  assert(!terminal_core::parse_single_unsigned("garbage", 16, 0xEF, value));
  assert(!terminal_core::parse_single_unsigned("10 trailing", 16, 0xEF, value));
  assert(!terminal_core::parse_single_unsigned("999999999999999999", 10, 99, value));
}

static void test_confirmation_is_a_complete_token(void) {
  assert(terminal_core::exact_confirmation("y", 'y'));
  assert(terminal_core::exact_confirmation("  Y  ", 'y'));
  assert(!terminal_core::exact_confirmation("yes", 'y'));
  assert(!terminal_core::exact_confirmation("yesterday", 'y'));
  assert(!terminal_core::exact_confirmation("n", 'y'));
}

static void test_quoted_path_tokens(void) {
  const char* input = "  \"/My Files/a.m61\"  '../Other Folder'  ";
  char first[64];
  char second[64];
  assert(terminal_core::parse_token(input, first, sizeof(first)));
  assert(std::strcmp(first, "/My Files/a.m61") == 0);
  assert(terminal_core::parse_token(input, second, sizeof(second)));
  assert(std::strcmp(second, "../Other Folder") == 0);
  assert(terminal_core::at_end(input));

  input = "\"unterminated";
  assert(!terminal_core::parse_token(input, first, sizeof(first)));
  input = "\"ok\"junk";
  assert(!terminal_core::parse_token(input, first, sizeof(first)));
}

static void test_decimal_parser_is_finite_and_bounded(void) {
  double value = 0.0;
  assert(terminal_core::parse_single_decimal("-1.25e+02", value));
  assert(std::fabs(value + 125.0) < 0.000001);
  assert(terminal_core::parse_single_decimal("3.14", value));
  assert(!terminal_core::parse_single_decimal("1e100", value));
  assert(!terminal_core::parse_single_decimal("1e", value));
  assert(!terminal_core::parse_single_decimal("1234567890123456789", value));
  assert(!terminal_core::parse_single_decimal("2.0 junk", value));
}

static void test_assembler_accepts_final_mnemonic_and_is_atomic_input(void) {
  const char isa[] = "0,1,add,jnz[E]";
  terminal_core::Assembly assembly = terminal_core::parse_assembly("0007  1\tadd  jnz[E]", 0, isa, 112);
  assert(assembly.error == terminal_core::AssemblyError::NONE);
  assert(assembly.address == 7);
  assert(assembly.count == 3);
  assert(assembly.opcodes[0] == 1);
  assert(assembly.opcodes[1] == 2);
  assert(assembly.opcodes[2] == 3);

  assembly = terminal_core::parse_assembly("0007 1 broken", 0, isa, 112);
  assert(assembly.error == terminal_core::AssemblyError::UNKNOWN_MNEMONIC);
  assert(assembly.count == 1); // caller commits only when error == NONE

  assembly = terminal_core::parse_assembly("0111 1 1", 0, isa, 112);
  assert(assembly.error == terminal_core::AssemblyError::TOO_LONG);
}

static void test_script_allowlist_is_explicit(void) {
  assert(terminal_command_allowed_in_script(CMD_HIN));
  assert(terminal_command_allowed_in_script(CMD_ASM));
  assert(terminal_command_allowed_in_script(CMD_RUN));
  assert(terminal_command_allowed_in_script(CMD_IF));
  assert(!terminal_command_allowed_in_script(CMD_DFU));
  assert(!terminal_command_allowed_in_script(CMD_RESET));
  assert(!terminal_command_allowed_in_script(CMD_FS_REMOVE));
  assert(!terminal_command_allowed_in_script(CMD_FS_CLEAN));
  assert(!terminal_command_allowed_in_script(CMD_FS_PWD));
  assert(!terminal_command_allowed_in_script(CMD_FS_CD));
  assert(!terminal_command_allowed_in_script(CMD_FS_MKDIR));
  assert(!terminal_command_allowed_in_script(CMD_FS_MOVE));
  assert(!terminal_command_allowed_in_script(CMD_FS_RMDIR));
  assert(!terminal_command_allowed_in_script(CMD_FS_STAT));
  assert(!terminal_command_allowed_in_script(CMD_ERASE_STORAGE));
  assert(!terminal_command_allowed_in_script(CMD_UNKNOWN));
}

int main(void) {
  test_input_capacity_reserves_terminator();
  test_bounded_unsigned_parser();
  test_confirmation_is_a_complete_token();
  test_quoted_path_tokens();
  test_decimal_parser_is_finite_and_bounded();
  test_assembler_accepts_final_mnemonic_and_is_atomic_input();
  test_script_allowlist_is_explicit();
  std::printf("terminal_self_test: ok\n");
  return 0;
}
