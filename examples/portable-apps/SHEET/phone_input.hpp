#ifndef MK61_SHEET_PHONE_INPUT_HPP
#define MK61_SHEET_PHONE_INPUT_HPP

#include "mk8_literal.hpp"
#include <stdint.h>
#include <string.h>

namespace phone_input {
enum Layout : uint8_t { RUSSIAN, LATIN, DIGITS };
constexpr uint32_t TIMEOUT_MS = 1200;
struct State {
  uint32_t deadline;
  uint8_t layout, key, index;
  bool lowercase;
};
inline void finish(State& state) { state.key=0; }
inline bool expire(State& state, uint32_t now) {
  if(state.key && (int32_t)(now-state.deadline)>=0) { finish(state); return true; }
  return false;
}
inline const char* group(const State& state, uint8_t digit) {
  if(digit==1) return ".,?!-:;()%\"";
  if(digit<2 || digit>9) return "";
  static const char* const russian[]={M8("АБВГ"),M8("ДЕЁЖЗ"),M8("ИЙКЛ"),M8("МНОП"),
      M8("РСТУ"),M8("ФХЦЧ"),M8("ШЩЪЫ"),M8("ЬЭЮЯ")};
  static const char* const latin[]={"ABC","DEF","GHI","JKL","MNO","PQRS","TUV","WXYZ"};
  return state.layout==RUSSIAN?russian[digit-2]:latin[digit-2];
}
inline char letter(const State& state, uint8_t byte) {
  if(state.lowercase) {
    if((byte>='A' && byte<='Z') || (byte>=0xC0 && byte<=0xDF)) byte=(uint8_t)(byte+0x20);
    else if(byte==0xA8) byte=0xB8; // Ё/ё in M8.
  }
  return (char)byte;
}
inline bool tap(State& state, char* source, uint16_t& length,
                uint16_t& cursor, uint16_t capacity, uint8_t digit, uint32_t now) {
  if(!source || !capacity || length>=capacity || cursor>length || digit>9) return false;
  expire(state,now);
  const bool direct=state.layout==DIGITS || digit==0;
  const char* letters=group(state,digit);
  if(!direct && state.key==digit && cursor) {
    state.index=(uint8_t)((state.index+1)%strlen(letters));
    source[cursor-1]=letter(state,(uint8_t)letters[state.index]);
  } else {
    if(length+1>=capacity) return false;
    memmove(source+cursor+1,source+cursor,length-cursor+1);
    source[cursor++]=direct?(state.layout==DIGITS?(char)('0'+digit):' '):letter(state,(uint8_t)letters[0]);
    ++length; state.index=0;
  }
  state.key=direct?0:digit; state.deadline=now+TIMEOUT_MS;
  return true;
}
}
#endif
