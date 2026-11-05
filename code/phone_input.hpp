#ifndef MK61_PHONE_INPUT_HPP
#define MK61_PHONE_INPUT_HPP

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
  static constexpr auto russian=M8_ARRAY("АБВГ\0ДЕЁЖЗ\0ИЙКЛ\0МНОП\0РСТУ\0ФХЦЧ\0ШЩЪЫ\0ЬЭЮЯ");
  static const char latin[]="ABC\0DEF\0GHI\0JKL\0MNO\0PQRS\0TUV\0WXYZ";
  static constexpr uint8_t ru[]={0,5,11,16,21,26,31,36}, en[]={0,4,8,12,16,20,25,29};
  return state.layout==RUSSIAN?russian.data()+ru[digit-2]:latin+en[digit-2];
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
