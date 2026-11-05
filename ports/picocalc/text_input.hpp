#ifndef MK61_PICOCALC_TEXT_INPUT_HPP
#define MK61_PICOCALC_TEXT_INPUT_HPP
#include "mk8_codec.hpp"
#include "mk8_literal.hpp"
#include "loadable_app_services.h"
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
inline void event(u8 key,bool& russian,mk61_service_text_event& out) {
  out={};out.layout=russian?1U:0U;
  switch(key) {
  case 0x88:russian=!russian;out.kind=MK61_TEXT_LAYOUT;out.layout=russian?1U:0U;break;
  case '\r':case '\n':out.kind=MK61_TEXT_SUBMIT;break;
  case 0x1B:case 0xB1:out.kind=MK61_TEXT_CANCEL;break;
  case '\t':out.kind=MK61_TEXT_MENU;break;
  case 8:out.kind=MK61_TEXT_BACKSPACE;break;
  case 0x7F:case 0xD4:out.kind=MK61_TEXT_DELETE;break;
  case 0xB4:out.kind=MK61_TEXT_LEFT;break;
  case 0xB7:out.kind=MK61_TEXT_RIGHT;break;
  case 0xB5:out.kind=MK61_TEXT_UP;break;
  case 0xB6:out.kind=MK61_TEXT_DOWN;break;
  case 0xD2:out.kind=MK61_TEXT_HOME;break;
  case 0xD5:out.kind=MK61_TEXT_END_LINE;break;
  case 0xD6:out.kind=MK61_TEXT_PAGE_UP;break;
  case 0xD7:out.kind=MK61_TEXT_PAGE_DOWN;break;
  default:
    out.value=mapped(key,russian);
    if(out.value) out.kind=MK61_TEXT_CHAR;
    break;
  }
}
inline bool backspace_utf8(char* text,u16& length) {
  if(!length) return false;
  --length;
  while(length && (((u8)text[length]&0xC0)==0x80)) --length;
  text[length]=0;return true;
}
}
#endif
