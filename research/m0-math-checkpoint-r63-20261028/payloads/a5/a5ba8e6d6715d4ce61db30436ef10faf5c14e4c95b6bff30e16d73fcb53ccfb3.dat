#ifndef MK61_TERMINAL_MNEMONICS_HPP
#define MK61_TERMINAL_MNEMONICS_HPP

#include "rust_types.h"
#include <string.h>

namespace terminal_mnemonics {

static constexpr usize MAX_LENGTH = 8;

inline char hex_digit(u8 value) {
  return value < 10 ? (char) ('0' + value) : (char) ('A' + value - 10);
}

inline char* hex(u8 opcode, char* text) {
  text[0] = hex_digit(opcode >> 4);
  text[1] = hex_digit(opcode & 15);
  text[2] = 0;
  return text;
}

inline char* csv(const char* table, usize opcode, char* text) {
  while(opcode != 0 && *table != 0) {
    if(*table++ == ',') --opcode;
  }
  usize length = 0;
  if(opcode == 0) {
    while(*table != 0 && *table != ',' && length < MAX_LENGTH)
      text[length++] = *table++;
  }
  text[length] = 0;
  return text;
}

// Register families are generated instead of storing a second 240-entry table.
// This restores the assembler vocabulary without another SRAM lease on F401.
inline char* english(u8 opcode, char* text) {
  static constexpr char basic[] =
      "0,1,2,3,4,5,6,7,8,9,dot,neg,pow10,clr,push,preX,"
      "add,sub,mul,div,swap,e10,exp,lg,ln,asin,acos,atg,sin,cos,tg,far,"
      "pi,sqrt,sqr,rec,pow,rot,toM,,,,toMS,,,,,disp,"
      "inMS,mod,sgn,inM,int,frc,max,and,or,xor,not,rnd,,,,";
  static constexpr char control[] =
      "hlt,jmp,ret,call,nop,xmsr,xmsp,jz,rpt2,jl,rpt3,rpt1,jme,rpt0,jnz,";
  if(opcode < 0x40) {
    csv(basic, opcode, text);
  } else if(opcode >= 0x50 && opcode < 0x60) {
    csv(control, opcode - 0x50, text);
  } else {
    const u8 family = opcode >> 4;
    const u8 reg = opcode & 15;
    const char* name = nullptr;
    switch(family) {
      case 4: name = "sto"; break;
      case 6: name = "ld"; break;
      case 7: name = "jz"; break;
      case 8: name = "jmp"; break;
      case 9: name = "jlz"; break;
      case 10: name = "call"; break;
      case 11: name = "sto"; break;
      case 12: name = "jme"; break;
      case 13: name = "ld"; break;
      case 14: name = "jnz"; break;
    }
    text[0] = 0;
    if(name != nullptr && (reg < 15 || family == 4 || family == 6)) {
      usize length = 0;
      while(*name != 0) text[length++] = *name++;
      if(family >= 7) text[length++] = '[';
      text[length++] = hex_digit(reg);
      if(family >= 7) text[length++] = ']';
      text[length] = 0;
    }
  }
  return text[0] == 0 ? hex(opcode, text) : text;
}

inline isize find(const char* token, usize length) {
  // Retain the documented direct-jump spelling and the old E4 table spelling.
  if(length == 3 && memcmp(token, "jlz", 3) == 0) return 0x59;
  if(length == 7 && memcmp(token, "jnz[R4]", 7) == 0) return 0xE4;
  for(usize opcode = 0; opcode < 0xF0; ++opcode) {
    char text[MAX_LENGTH + 1];
    english((u8) opcode, text);
    if(strlen(text) == length && memcmp(text, token, length) == 0)
      return (isize) opcode;
  }
  return -1;
}

} // namespace terminal_mnemonics

#endif
