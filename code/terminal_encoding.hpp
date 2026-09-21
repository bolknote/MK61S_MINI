#ifndef MK61_TERMINAL_ENCODING_HPP
#define MK61_TERMINAL_ENCODING_HPP

#include "mk8_codec.hpp"
#include "rust_types.h"

// The terminal wire format is fixed CP1251. Ordinary M8 bytes deliberately
// have the same values as CP1251 and can be written directly. M8's private C0
// glyphs cannot be sent as terminal control characters, so only those glyphs
// expand to stable ASCII spellings. Desktop clients decode/encode CP1251 at
// their own boundary; the firmware has no encoding mode or negotiation.
namespace terminal_encoding {

using ByteWriter = bool (*)(u8 byte, void* context);

inline bool write_ascii(const char* text, ByteWriter writer, void* context) {
  if(text == nullptr || writer == nullptr) return false;
  while(*text != 0) {
    if(!writer((u8) *text++, context)) return false;
  }
  return true;
}

inline const char* private_fallback(u8 byte) {
  switch(byte) {
    case mk8::BYTE_LEFT_ARROW:    return "<-";
    case mk8::BYTE_RIGHT_ARROW:   return "->";
    case mk8::BYTE_UP_ARROW:      return "^";
    case mk8::BYTE_DOWN_ARROW:    return "v";
    case mk8::BYTE_PI:            return "pi";
    case mk8::BYTE_SQRT:          return "sqrt";
    case mk8::BYTE_CYCLE_ARROW:   return "~>";
    case mk8::BYTE_NOT_EQUAL:     return "!=";
    case mk8::BYTE_LESS_EQUAL:    return "<=";
    case mk8::BYTE_GREATER_EQUAL: return ">=";
    case mk8::BYTE_MULTIPLY:      return "*";
    case mk8::BYTE_DIVIDE:        return "/";
    case mk8::BYTE_POWER_2:       return "^2";
    case mk8::BYTE_POWER_Y:       return "^y";
    case mk8::BYTE_POWER_X:       return "^x";
    case mk8::BYTE_XOR:           return "xor";
    case mk8::BYTE_POWER_MINUS:   return "^-";
    case mk8::BYTE_RETURN_ARROW:  return "<ret>";
    default:                      return nullptr;
  }
}

inline bool write_m8(const u8* text, usize length,
                     ByteWriter writer, void* context) {
  if((text == nullptr && length != 0) || writer == nullptr) return false;
  for(usize index = 0; index < length; ++index) {
    const u8 byte = text[index];
    if(byte >= mk8::BYTE_LEFT_ARROW && byte <= mk8::BYTE_RETURN_ARROW) {
      if(!write_ascii(private_fallback(byte), writer, context)) return false;
    } else if(mk8::valid_byte(byte)) {
      if(!writer(byte, context)) return false;
    } else if(!writer('?', context)) {
      return false;
    }
  }
  return true;
}

inline bool write_m8(const char* text, ByteWriter writer, void* context) {
  if(text == nullptr) return false;
  usize length = 0;
  while(text[length] != 0) ++length;
  return write_m8((const u8*) text, length, writer, context);
}

inline u8 input_byte(u8 cp1251) {
  return mk8::valid_byte(cp1251) ? cp1251 : (u8) '?';
}

} // namespace terminal_encoding

#endif
