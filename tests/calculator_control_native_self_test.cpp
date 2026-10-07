#include "calculator_control.hpp"
#include "cross_hal.h"
#include "mk61emu_core.h"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>

// Physical calculator key matrix for the classic layout used by this test.
const TMK61_cross_key KeyPairs[40] = {
  Cx, POW, NEG, DOT, _0_, Bx, XY, _3_, _2_, _1_,
  MUL, ADD, _6_, _5_, _4_, DIV, SUB, _9_, _8_, _7_,
  JSR, JMP, xP, Px, K, RUN, RET, SF, SB, F,
  NON, NON, NON, NON, NON, NON, NON, NON, NON, NON
};

static double xvalue() {
  char value[15] = {};
  read_stack_register(stack::X, value, "0123456789-LCGE ");
  return std::strtod(value + 1, nullptr);
}

static void finish_run() {
  MK61Emu_SetKeyPress(0, 0);
  for(unsigned i=0;core_61::is_RUN() && i<20000;i++) core_61::step();
  assert(!core_61::is_RUN() && !core_61::has_error() && !core_61::extended_program_error());
}

static void prepare(bool expanded) {
  core_61::set_expanded_program_mode(expanded);
  core_61::enable();
  core_61::clear_extended_program_banks();
}

static void test_target(bool expanded, u8 address, u8 digit) {
  prepare(expanded);
  assert(core_61::write_absolute_program(0, 0x09));
  assert(core_61::write_absolute_program(1, 0x50));
  assert(core_61::write_absolute_program(address, digit));
  assert(core_61::write_absolute_program(address + 1, 0x50));
  std::array<u8,112> before = {};
  for(usize i=0;i<core_61::program_steps();i++) assert(core_61::read_absolute_program(i,before[i]));
  hidden_start_loaded_program(address);
  finish_run();
  assert(xvalue()==digit);
  for(usize i=0;i<core_61::program_steps();i++) {
    u8 value=0;
    assert(core_61::read_absolute_program(i,value) && value==before[i]);
  }
}

static void test_default_and_last_address(bool expanded) {
  prepare(expanded);
  assert(core_61::write_absolute_program(0,0x07));
  assert(core_61::write_absolute_program(1,0x50));
  hidden_start_loaded_program();
  finish_run();
  assert(xvalue()==7);
  const u8 last=(u8)(core_61::program_steps()-1);
  assert(core_61::write_absolute_program(last,0x50));
  hidden_start_loaded_program(last);
  finish_run();
  assert(xvalue()==7);
}

static void test_current_bank() {
  prepare(true);
  const u8 jump[]={0x1f,0x51,0x01,0x12}; // BP bank 1, offset 0.
  for(u8 i=0;i<sizeof(jump);i++) assert(core_61::write_absolute_program(i,jump[i]));
  assert(core_61::write_absolute_program(112,0x01));
  assert(core_61::write_absolute_program(113,0x50));
  assert(core_61::write_absolute_program(120,0x06));
  assert(core_61::write_absolute_program(121,0x50));
  hidden_start_loaded_program();
  finish_run();
  assert(core_61::active_program_bank()==1 && xvalue()==1);
  hidden_start_loaded_program(8);
  finish_run();
  assert(core_61::active_program_bank()==1 && xvalue()==6);
}

int main() {
  for(bool expanded : {false,true}) {
    test_target(expanded,8,4);
    // Address operands 55/56 must not execute the Ms exchange opcodes.
    test_target(expanded,55,5);
    test_target(expanded,56,6);
    test_target(expanded,100,8);
    test_default_and_last_address(expanded);
  }
  test_current_bank();
  std::puts("calculator_control_native_self_test: addressed/default start, bounds and code preservation ok");
}
