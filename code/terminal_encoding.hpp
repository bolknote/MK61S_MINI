#ifndef MK61_TERMINAL_ENCODING_HPP
#define MK61_TERMINAL_ENCODING_HPP

#include "rust_types.h"
#include "utf8_codec.hpp"

namespace terminal_encoding {

// The firmware keeps all user-visible names and command lines as UTF-8.  The
// classic MK-61 mnemonic table is deliberately kept in single-byte CP1251 so
// its fixed publication columns cost one byte per printed character.
enum class Mode : u8 { CP1251, UTF8 };

enum class ParseResult : u8 { QUERY, SET, INVALID };

struct Bytes {
  u8 data[4];
  u8 size;
};

using ByteWriter = bool (*)(u8 byte, void* context);

inline const char* name(Mode mode) {
  return mode == Mode::UTF8 ? "utf-8" : "cp1251";
}

inline ParseResult parse(const char* text, Mode& mode) {
  if(text == nullptr) return ParseResult::QUERY;
  while(*text == ' ' || *text == '\t') text++;
  if(*text == 0 || *text == '\r' || *text == '\n') {
    return ParseResult::QUERY;
  }

  const char* expected = nullptr;
  Mode parsed = Mode::CP1251;
  if(text[0] == 'u' && text[1] == 't' && text[2] == 'f' &&
     text[3] == '-' && text[4] == '8') {
    expected = text + 5;
    parsed = Mode::UTF8;
  } else if(text[0] == 'u' && text[1] == 't' && text[2] == 'f' &&
            text[3] == '8') {
    expected = text + 4;
    parsed = Mode::UTF8;
  } else if(text[0] == 'c' && text[1] == 'p' && text[2] == '1' &&
            text[3] == '2' && text[4] == '5' && text[5] == '1') {
    expected = text + 6;
    parsed = Mode::CP1251;
  } else {
    return ParseResult::INVALID;
  }

  while(*expected == ' ' || *expected == '\t') expected++;
  if(*expected != 0 && *expected != '\r' && *expected != '\n') {
    return ParseResult::INVALID;
  }
  mode = parsed;
  return ParseResult::SET;
}

// Russian А..я is one contiguous range in both Unicode and Windows-1251.
// Only Ё/ё sit outside it, so the terminal needs arithmetic plus two special
// cases rather than a lookup table.  Other Unicode has no calculator mnemonic
// meaning and is represented by '?' in CP1251 mode.
constexpr u32 cp1251_codepoint(u8 byte) {
  if(byte < 0x80) return byte;
  if(byte >= 0xC0) return 0x0410U + (u32) (byte - 0xC0);
  if(byte == 0xA8) return 0x0401;
  if(byte == 0xB8) return 0x0451;
  return '?';
}

inline bool codepoint_to_cp1251(u32 codepoint, u8& byte) {
  if(codepoint < 0x80) {
    byte = (u8) codepoint;
    return true;
  }
  if(codepoint >= 0x0410 && codepoint <= 0x044F) {
    byte = (u8) (0xC0 + codepoint - 0x0410);
    return true;
  }
  if(codepoint == 0x0401) { byte = 0xA8; return true; }
  if(codepoint == 0x0451) { byte = 0xB8; return true; }
  return false;
}

inline Bytes encode_utf8(u32 codepoint) {
  Bytes result = {{'?'}, 1};
  if(codepoint <= 0x7F) {
    result.data[0] = (u8) codepoint;
  } else if(codepoint <= 0x7FF) {
    result.data[0] = (u8) (0xC0 | (codepoint >> 6));
    result.data[1] = (u8) (0x80 | (codepoint & 0x3F));
    result.size = 2;
  } else if(codepoint <= 0xFFFF &&
            !(codepoint >= 0xD800 && codepoint <= 0xDFFF)) {
    result.data[0] = (u8) (0xE0 | (codepoint >> 12));
    result.data[1] = (u8) (0x80 | ((codepoint >> 6) & 0x3F));
    result.data[2] = (u8) (0x80 | (codepoint & 0x3F));
    result.size = 3;
  } else if(codepoint <= 0x10FFFF) {
    result.data[0] = (u8) (0xF0 | (codepoint >> 18));
    result.data[1] = (u8) (0x80 | ((codepoint >> 12) & 0x3F));
    result.data[2] = (u8) (0x80 | ((codepoint >> 6) & 0x3F));
    result.data[3] = (u8) (0x80 | (codepoint & 0x3F));
    result.size = 4;
  }
  return result;
}

inline bool emit(const Bytes& bytes, ByteWriter writer, void* context) {
  if(writer == nullptr) return false;
  for(u8 index = 0; index < bytes.size; index++) {
    if(!writer(bytes.data[index], context)) return false;
  }
  return true;
}

inline bool write_cp1251(const u8* text, usize length, Mode mode,
                         ByteWriter writer, void* context) {
  if(text == nullptr || writer == nullptr) return false;
  for(usize index = 0; index < length; index++) {
    if(mode == Mode::CP1251) {
      if(!writer(text[index], context)) return false;
    } else if(!emit(encode_utf8(cp1251_codepoint(text[index])), writer,
                    context)) {
      return false;
    }
  }
  return true;
}

inline bool write_cp1251(const char* text, Mode mode,
                         ByteWriter writer, void* context) {
  if(text == nullptr) return false;
  usize length = 0;
  while(text[length] != 0) length++;
  return write_cp1251((const u8*) text, length, mode, writer, context);
}

inline bool write_utf8(const u8* text, usize length, Mode mode,
                       ByteWriter writer, void* context) {
  if(text == nullptr || writer == nullptr) return false;
  if(mode == Mode::UTF8) {
    for(usize index = 0; index < length; index++) {
      if(!writer(text[index], context)) return false;
    }
    return true;
  }

  for(usize offset = 0; offset < length;) {
    const utf8_codec::Decoded decoded =
        utf8_codec::decode(text + offset, length - offset);
    u8 byte = '?';
    if(decoded.valid) (void) codepoint_to_cp1251(decoded.codepoint, byte);
    if(!writer(byte, context)) return false;
    offset += decoded.size == 0 ? 1 : decoded.size;
  }
  return true;
}

inline bool write_utf8(const char* text, Mode mode,
                       ByteWriter writer, void* context) {
  if(text == nullptr) return false;
  usize length = 0;
  while(text[length] != 0) length++;
  return write_utf8((const u8*) text, length, mode, writer, context);
}

inline Bytes input_byte(u8 byte, Mode mode) {
  if(mode == Mode::CP1251 && byte >= 0x80) {
    return encode_utf8(cp1251_codepoint(byte));
  }
  return {{byte}, 1};
}

} // namespace terminal_encoding

#endif
