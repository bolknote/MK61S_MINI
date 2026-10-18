#ifndef MK61_PICOCALC_TEXT_INPUT_HPP
#define MK61_PICOCALC_TEXT_INPUT_HPP
#include "mk8_codec.hpp"
#include "mk8_literal.hpp"
namespace picocalc::text_input {
// F8 changes only text entry. Calculator and APP key scan codes stay intact.
inline u8 mapped(u8 key,bool russian) {
  if(key<32 || key>=127) return 0;
  if(!russian) return key;
  constexpr char latin[]="`qwertyuiop[]asdfghjkl;'zxcvbnm,./";
  constexpr char shifted[]="~QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?";
  constexpr auto lower=M8_ARRAY("ёйцукенгшщзхъфывапролджэячсмитьбю.");
  constexpr auto upper=M8_ARRAY("ЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,");
  static_assert(sizeof(latin)==sizeof(lower) && sizeof(shifted)==sizeof(upper),"QWERTY alphabet mismatch");
  for(unsigned i=0;latin[i];++i) {
    if(key==(u8)latin[i]) return (u8)lower[i];
    if(key==(u8)shifted[i]) return (u8)upper[i];
  }
  return key;
}
inline bool append_utf8(char* text,u16& length,unsigned capacity,u8 key,bool russian) {
  const u8 byte=mapped(key,russian);if(!byte) return false;
  const auto encoded=mk8::utf8(byte);
  if(length+encoded.size>=capacity) return false;
  for(unsigned i=0;i<encoded.size;++i) text[length++]=(char)encoded.data[i];
  text[length]=0;return true;
}
inline bool backspace_utf8(char* text,u16& length) {
  if(!length) return false;
  --length;
  while(length && (((u8)text[length]&0xC0)==0x80)) --length;
  text[length]=0;return true;
}
}
#endif
