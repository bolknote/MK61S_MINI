// Loads RACE through the real binary/M61 loader and drives the real ROM.
// Host facilities only set the angle switch and observe published frames.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include "mk61emu_core.h"
#include "m61_text.hpp"

unsigned elite_load_game(const char* directory);
static unsigned steps = 0;
static unsigned changes = 0;
static unsigned bank_steps[32] = {};
static const char symbols[] = "0123456789-     ";

void elite_tracked_step() {
  const unsigned bank = core_61::active_program_bank();
  if(bank < 32) ++bank_steps[bank];
  u8 before[12] = {};
  const u8* frame = core_61::segment_display_frame();
  if(frame) std::memcpy(before, frame, 12);
  core_61::step();
  frame = core_61::segment_display_frame();
  if(frame && std::memcmp(before, frame, 12) != 0) ++changes;
  ++steps;
}

static void press_start() {
  core_61::clear_displayed();
  MK61Emu_SetKeyPress(2, 9);  // C/P, same physical command as the calculator.
  for(unsigned i = 0; i < 4; ++i) {
    elite_tracked_step();
    if(core_61::is_RUN()) break;
  }
  MK61Emu_SetKeyPress(0, 0);
  for(unsigned i = 0; i < 512 && !core_61::is_RUN(); ++i) elite_tracked_step();
}

static double number(const char* value) {
  std::string s = value[0] == '-' ? "-" : "";
  for(int i = 1; i <= 9; ++i) if(value[i] != ' ') s += value[i];
  s += 'e'; s += value[11] == '-' ? '-' : '+'; s += value[12]; s += value[13];
  return std::strtod(s.c_str(), nullptr);
}

static double memory(int reg) {
  char value[15] = {};
  MK61Emu_ReadRegister(reg, value, symbols);
  return number(value);
}

static void fixture(int reg, int value) {
  // Same public numeric ring layout used by mk_math_self_test fixtures.
  // Only test setup uses this; no instruction is replaced or accelerated.
  const usize base = reg * MK61_MEMORY_PAGE_TETRADES;
  const bool negative = value < 0;
  unsigned magnitude = negative ? -value : value;
  std::string digits = std::to_string(magnitude);
  const unsigned exponent = magnitude ? digits.size() - 1 : 0;
  digits.resize(8, '0');
  for(unsigned i = 0; i < 14; ++i) ringM[base + i * 3] = 0;
  for(unsigned i = 0; i < 8; ++i) ringM[base + 21 - i * 3] = digits[i] - '0';
  ringM[base + 24] = negative ? 9 : 0;
  ringM[base + 27] = exponent % 10;
  ringM[base + 30] = exponent / 10;
}

static void dump() {
  std::cout << "{\"steps\":" << steps
            << ",\"changes\":" << changes
            << ",\"running\":" << (core_61::is_RUN() ? "true" : "false")
            // ROM indicator tetrades are transient during RUN. Check its
            // error glyph at stops, and the extended error flag every frame.
            << ",\"error\":" << (core_61::extended_program_error() || (!core_61::is_RUN() && core_61::has_error()) ? "true" : "false")
            << ",\"auto\":" << (core_61::extended_display_auto() ? "true" : "false")
            << ",\"segmented\":" << (core_61::extended_display_segmented() ? "true" : "false")
            << ",\"pc\":" << unsigned(core_61::active_program_bank()) * 112 + core_61::get_IP()
            << ",\"angle\":" << unsigned(MK61Emu_GetAngleUnit()) << ",\"regs\":[";
  for(int reg = 0; reg < 16; ++reg) {
    if(reg) std::cout << ',';
    std::cout << std::setprecision(12) << memory(reg);
  }
  std::cout << "],\"frame\":[";
  const u8* frame = core_61::segment_display_frame();
  for(int cell = 0; cell < 12; ++cell) {
    if(cell) std::cout << ',';
    std::cout << (frame ? unsigned(frame[cell]) : 0);
  }
  std::cout << "],\"bank_steps\":[";
  for(unsigned bank = 0; bank < 32; ++bank) {
    if(bank) std::cout << ',';
    std::cout << bank_steps[bank];
  }
  std::cout << "]}" << std::endl;
}

int main(int argc, char** argv) {
  if(argc != 2) return 2;
  elite_load_game(argv[1]);
  dump();
  std::string line;
  while(std::getline(std::cin, line)) {
    std::istringstream input(line);
    std::string op; input >> op;
    steps = changes = 0;
    std::memset(bank_steps, 0, sizeof(bank_steps));
    if(op == "angle") {
      std::string mode; input >> mode;
      if(mode == "P") MK61Emu_SetAngleUnit(RADIAN);
      else if(mode == "G") MK61Emu_SetAngleUnit(DEGREE);
      else if(mode == "GRD") MK61Emu_SetAngleUnit(GRADE);
      else return 3;
      continue;
    }
    if(op == "set") {
      int reg, value; input >> reg >> value;
      fixture(reg, value);
      continue;
    }
    if(op == "help") {
      if(!m61_text::handle_key_event(0x13,true)) return 4;
      (void)m61_text::handle_key_event(0x13,false);
      for(unsigned i=0;i<4096 && core_61::is_RUN() && !m61_text::calculator_suspended();++i) elite_tracked_step();
      m61_text::service();
      m61_text::Error error = {};
      if(m61_text::last_error(error) || m61_text::calculator_suspended()) return 5;
    }
    const auto revision = core_61::extended_display_revision();
    if(op == "start") press_start();
    if(op == "start" || op == "next") {
      while(core_61::is_RUN() && core_61::extended_display_revision() == revision && steps < 200000) elite_tracked_step();
    } else if(op == "stop") {
      while(core_61::is_RUN() && steps < 200000) elite_tracked_step();
    }
    if(steps >= 200000) return 6;
    dump();
  }
}
