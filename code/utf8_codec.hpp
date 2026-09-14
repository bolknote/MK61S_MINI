#ifndef UTF8_CODEC_HPP
#define UTF8_CODEC_HPP

#include "rust_types.h"

namespace utf8_codec {

static constexpr u32 REPLACEMENT_CODEPOINT = 0xFFFDU;

struct Decoded {
  u32 codepoint;
  u8 size;
  bool valid;
};

inline bool is_continuation(u8 value) {
  return (value & 0xC0U) == 0x80U;
}

// One strict RFC 3629 decoder is shared by every firmware subsystem.  Invalid
// input always consumes one byte, so streaming callers cannot get stuck; an
// empty span is the only result with size == 0.  noinline keeps a single COMDAT
// implementation in Flash even when this header is included by many units.
#if defined(__GNUC__)
__attribute__((noinline))
#endif
inline Decoded decode(const u8* data, usize length) {
  if(data == nullptr || length == 0) {
    return {REPLACEMENT_CODEPOINT, 0, false};
  }

  const u8 first = data[0];
  if(first < 0x80U) return {first, 1, true};

  u8 size = 0;
  u32 codepoint = 0;
  u32 minimum = 0;
  if(first >= 0xC2U && first <= 0xDFU) {
    size = 2;
    codepoint = first & 0x1FU;
    minimum = 0x80U;
  } else if(first >= 0xE0U && first <= 0xEFU) {
    size = 3;
    codepoint = first & 0x0FU;
    minimum = 0x800U;
  } else if(first >= 0xF0U && first <= 0xF4U) {
    size = 4;
    codepoint = first & 0x07U;
    minimum = 0x10000U;
  } else {
    return {REPLACEMENT_CODEPOINT, 1, false};
  }

  if(size > length) return {REPLACEMENT_CODEPOINT, 1, false};
  for(u8 index = 1; index < size; ++index) {
    if(!is_continuation(data[index])) {
      return {REPLACEMENT_CODEPOINT, 1, false};
    }
    codepoint = (codepoint << 6) | (data[index] & 0x3FU);
  }

  if(codepoint < minimum || codepoint > 0x10FFFFU ||
     (codepoint >= 0xD800U && codepoint <= 0xDFFFU)) {
    return {REPLACEMENT_CODEPOINT, 1, false};
  }
  return {codepoint, size, true};
}

// Bounded look-ahead for NUL-terminated strings.  It never examines bytes past
// the terminator and gives decode() enough input for at most one codepoint.
inline Decoded decode_cstring(const char* text) {
  if(text == nullptr) return {REPLACEMENT_CODEPOINT, 0, false};
  usize available = 0;
  while(available < 4U && text[available] != 0) ++available;
  return decode((const u8*) text, available);
}

} // namespace utf8_codec

#endif
