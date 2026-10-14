// Records the same addressed launch as `run 8` at real ROM command boundaries.
#include "calculator_control.hpp"
#include "cross_hal.h"
#include "mk61emu_core.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

const TMK61_cross_key KeyPairs[40] = {
  Cx, POW, NEG, DOT, _0_, Bx, XY, _3_, _2_, _1_,
  MUL, ADD, _6_, _5_, _4_, DIV, SUB, _9_, _8_, _7_,
  JSR, JMP, xP, Px, K, RUN, RET, SF, SB, F,
  NON, NON, NON, NON, NON, NON, NON, NON, NON, NON
};

static double memory_value(int r) {
  char value[15] = {};
  MK61Emu_ReadRegister(r, value, "0123456789-     ");
  std::string decimal = value[0] == '-' ? "-" : "";
  for(int i=1;i<=9;i++) if(value[i]!=' ') decimal+=value[i];
  decimal+='e'; decimal+=value[11]=='-' ? '-' : '+';
  decimal+=value[12]; decimal+=value[13];
  return std::strtod(decimal.c_str(),nullptr);
}

static void snapshot(int pc, int opcode) {
  std::cout << "{\"pc\":" << pc << ",\"op\":" << opcode << ",\"mem\":\"";
  for(unsigned a=0;a<105;a++) {
    u8 byte=0; assert(core_61::read_absolute_program(a,byte));
    std::cout << std::hex << std::setfill('0') << std::setw(2) << unsigned(byte);
  }
  std::cout << "\",\"ms\":\"";
  const unsigned high_digits[]={13,1,3,5,7,9,11};
  for(unsigned page=0;page<9;page++) for(unsigned high:high_digits) {
    const unsigned base=page*42;
    const unsigned byte=(ringM[base+high*3+1]&15)*16+
                              (ringM[base+(high-1)*3+1]&15);
    std::cout << std::hex << std::setfill('0') << std::setw(2) << byte;
  }
  std::cout << std::dec << "\",\"regs\":[";
  for(int r=0;r<16;r++) {
    if(r) std::cout << ',';
    std::cout << std::setprecision(12) << memory_value(r);
  }
  std::cout << "],\"reg_display\":[";
  for(int r=0;r<16;r++) {
    char value[15] = {};
    MK61Emu_ReadRegister(r,value,"0123456789-LCGE ");
    if(r) std::cout << ',';
    std::cout << '"' << value << '"';
  }
  std::cout << "]}" << std::endl;
}

static bool boundary(const core_61::Mk61ProgramBoundaryContext& c,void*) {
  snapshot(c.address,c.opcode);
  return false;
}

int main(int argc,char** argv) {
  assert(argc==2);
  core_61::set_expanded_program_mode(true);
  core_61::enable();
  core_61::clear_extended_program_banks();
  std::ifstream input(argv[1],std::ios::binary);
  std::vector<unsigned char> image((std::istreambuf_iterator<char>(input)),{});
  assert(image.size()==105);
  for(unsigned a=0;a<image.size();a++)
    assert(core_61::write_absolute_program(a,image[a]));
  assert(core_61::set_mk61_program_boundary_hook(boundary));
  hidden_start_loaded_program(8);
  MK61Emu_SetKeyPress(0,0);
  unsigned ticks=0;
  while(core_61::is_RUN() && ticks++<2000000) core_61::step();
  assert(!core_61::is_RUN() && !core_61::has_error() &&
         !core_61::extended_program_error() && ticks<2000000);
  snapshot(-1,-1);
}
