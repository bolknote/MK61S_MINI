#ifndef MK61_MK8_CODEC_HPP
#define MK61_MK8_CODEC_HPP

#include "rust_types.h"
#include "utf8_codec.hpp"

// M8 is the only text encoding used inside the device: C6, resident UI,
// language sources and the APP ABI all store the same single-byte text.
// Printable bytes preserve Windows-1251 exactly; calculator symbols absent
// from that charset occupy otherwise unused C0 control positions. Unicode
// exists only at external boundaries such as FAT LFN and desktop UI.
namespace mk8 {

// Keep private symbols dense so the exceptional Unicode codepoints need only
// one tiny table. Starting at 0E preserves NUL, TAB, LF and CR. The bulk
// Russian mapping is arithmetic and occupies no table at all.
static constexpr u8 BYTE_LEFT_ARROW    = 0x0E;
static constexpr u8 BYTE_RIGHT_ARROW   = 0x0F;
static constexpr u8 BYTE_UP_ARROW      = 0x10;
static constexpr u8 BYTE_DOWN_ARROW    = 0x11;
static constexpr u8 BYTE_PI            = 0x12;
static constexpr u8 BYTE_SQRT          = 0x13;
static constexpr u8 BYTE_CYCLE_ARROW   = 0x14;
static constexpr u8 BYTE_NOT_EQUAL     = 0x15;
static constexpr u8 BYTE_LESS_EQUAL    = 0x16;
static constexpr u8 BYTE_GREATER_EQUAL = 0x17;
static constexpr u8 BYTE_MULTIPLY      = 0x18;
static constexpr u8 BYTE_DIVIDE        = 0x19;
static constexpr u8 BYTE_POWER_2       = 0x1A;
static constexpr u8 BYTE_POWER_Y       = 0x1B;
static constexpr u8 BYTE_POWER_X       = 0x1C;
static constexpr u8 BYTE_XOR           = 0x1D;
static constexpr u8 BYTE_POWER_MINUS   = 0x1E;
static constexpr u8 BYTE_RETURN_ARROW  = 0x1F;

static constexpr u16 PRIVATE_CODEPOINTS[] = {
  0x2190, 0x2192, 0x2191, 0x2193, 0x03C0, 0x221A,
  0x21BB, 0x2260, 0x2264, 0x2265, 0x00D7, 0x00F7,
  0x00B2, 0x02B8, 0x02E3, 0x22BB, 0x207B, 0x21B5
};

// Windows-1251 80..BF. 98 is intentionally undefined by the code page.
// Keeping this as one 128-byte table is smaller than the collection of
// exceptional branches and also makes import/export strictly reversible.
static constexpr u16 CP1251_80_BF[] = {
  0x0402, 0x0403, 0x201A, 0x0453, 0x201E, 0x2026, 0x2020, 0x2021,
  0x20AC, 0x2030, 0x0409, 0x2039, 0x040A, 0x040C, 0x040B, 0x040F,
  0x0452, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014,
  0x0000, 0x2122, 0x0459, 0x203A, 0x045A, 0x045C, 0x045B, 0x045F,
  0x00A0, 0x040E, 0x045E, 0x0408, 0x00A4, 0x0490, 0x00A6, 0x00A7,
  0x0401, 0x00A9, 0x0404, 0x00AB, 0x00AC, 0x00AD, 0x00AE, 0x0407,
  0x00B0, 0x00B1, 0x0406, 0x0456, 0x0491, 0x00B5, 0x00B6, 0x00B7,
  0x0451, 0x2116, 0x0454, 0x00BB, 0x0458, 0x0405, 0x0455, 0x0457,
};

struct Utf8Bytes {
  u8 data[3];
  u8 size;
};

constexpr u16 codepoint(u8 byte) {
  if(byte >= 0xC0) return (u16) (0x0410U + byte - 0xC0U);
  if(byte == 0x98) return '?';
  if(byte >= 0x80) return CP1251_80_BF[byte - 0x80];
  const u8 control = (u8) (byte - BYTE_LEFT_ARROW);
  if(control < sizeof(PRIVATE_CODEPOINTS) / sizeof(PRIVATE_CODEPOINTS[0])) {
    return PRIVATE_CODEPOINTS[control];
  }
  if(byte == '\t' || byte == '\n' || byte == '\r' || byte >= 0x20) {
    return byte == 0x7F ? (u16) '?' : byte;
  }
  return '?';
}

constexpr bool valid_byte(u8 byte) {
  if(byte == 0 || byte == 0x7F || byte == 0x98) return false;
  if(byte == '\t' || byte == '\n' || byte == '\r') return true;
  if(byte >= BYTE_LEFT_ARROW && byte <= BYTE_RETURN_ARROW) return true;
  return byte >= 0x20;
}

constexpr bool from_codepoint(u32 value, u8& byte) {
  if(value >= 0x20 && value <= 0x7E) {
    byte = (u8) value;
    return true;
  }
  if(value == '\t' || value == '\n' || value == '\r') {
    byte = (u8) value;
    return true;
  }
  for(u8 index = 0;
      index < sizeof(PRIVATE_CODEPOINTS) / sizeof(PRIVATE_CODEPOINTS[0]);
      ++index) {
    if(PRIVATE_CODEPOINTS[index] == value) {
      byte = (u8) (BYTE_LEFT_ARROW + index);
      return true;
    }
  }
  if(value >= 0x0410 && value <= 0x044F) {
    byte = (u8) (0xC0U + value - 0x0410U);
    return true;
  }
  for(u8 index = 0; index < sizeof(CP1251_80_BF) / sizeof(CP1251_80_BF[0]);
      ++index) {
    if(CP1251_80_BF[index] == value && value != 0) {
      byte = (u8) (0x80U + index);
      return true;
    }
  }
  return false;
}

inline Utf8Bytes utf8(u8 byte) {
  const u16 value = codepoint(byte);
  if(value <= 0x7F) return {{(u8) value, 0, 0}, 1};
  if(value <= 0x7FF) {
    return {{(u8) (0xC0U | (value >> 6)),
             (u8) (0x80U | (value & 0x3FU)), 0}, 2};
  }
  return {{(u8) (0xE0U | (value >> 12)),
           (u8) (0x80U | ((value >> 6) & 0x3FU)),
           (u8) (0x80U | (value & 0x3FU))}, 3};
}

inline bool text_valid(const u8* text, usize length) {
  if(text == nullptr && length != 0) return false;
  for(usize index = 0; index < length; ++index) {
    if(!valid_byte(text[index])) return false;
  }
  return true;
}

// Convert one bounded UTF-8 span to raw M8. output_length never includes a
// terminator. Unsupported Unicode and malformed UTF-8 reject the whole span.
inline bool from_utf8(const u8* input, usize input_length, u8* output,
                      usize capacity, usize& output_length) {
  output_length = 0;
  if((input == nullptr && input_length != 0) ||
     (output == nullptr && capacity != 0)) return false;
  for(usize offset = 0; offset < input_length;) {
    const utf8_codec::Decoded decoded =
        utf8_codec::decode(input + offset, input_length - offset);
    u8 byte = 0;
    if(!decoded.valid || !from_codepoint(decoded.codepoint, byte) ||
       !valid_byte(byte) || output_length >= capacity) return false;
    output[output_length++] = byte;
    offset += decoded.size;
  }
  return true;
}

inline bool to_utf8(const u8* input, usize input_length, u8* output,
                    usize capacity, usize& output_length) {
  output_length = 0;
  if((input == nullptr && input_length != 0) ||
     (output == nullptr && capacity != 0)) return false;
  for(usize index = 0; index < input_length; ++index) {
    if(!valid_byte(input[index])) return false;
    const Utf8Bytes encoded = utf8(input[index]);
    if(output_length + encoded.size > capacity) return false;
    for(u8 part = 0; part < encoded.size; ++part) {
      output[output_length++] = encoded.data[part];
    }
  }
  return true;
}

// FAT LFN stores UTF-16 code units. Every M8 character maps to one BMP
// codepoint, so the conversion is exactly one unit per byte and never emits a
// surrogate pair.
inline bool to_utf16(const u8* input, usize input_length, u16* output,
                     usize capacity, usize& output_length) {
  output_length = 0;
  if((input == nullptr && input_length != 0) ||
     (output == nullptr && capacity != 0)) return false;
  if(input_length > capacity) return false;
  for(usize index = 0; index < input_length; ++index) {
    if(!valid_byte(input[index])) return false;
    output[output_length++] = codepoint(input[index]);
  }
  return true;
}

inline bool from_utf16(const u16* input, usize input_length, u8* output,
                       usize capacity, usize& output_length) {
  output_length = 0;
  if((input == nullptr && input_length != 0) ||
     (output == nullptr && capacity != 0)) return false;
  if(input_length > capacity) return false;
  for(usize index = 0; index < input_length; ++index) {
    const u16 codepoint = input[index];
    u8 byte = 0;
    if((codepoint >= 0xD800U && codepoint <= 0xDFFFU) ||
       !from_codepoint(codepoint, byte) || !valid_byte(byte)) return false;
    output[output_length++] = byte;
  }
  return true;
}

inline u8 fold_case(u8 byte) {
  if(byte >= 'A' && byte <= 'Z') return (u8) (byte + ('a' - 'A'));
  if(byte >= 0xC0 && byte <= 0xDF) return (u8) (byte + 0x20);
  switch(byte) {
    case 0x80: return 0x90; case 0x81: return 0x83;
    case 0x8A: return 0x9A; case 0x8C: return 0x9C;
    case 0x8D: return 0x9D; case 0x8E: return 0x9E;
    case 0x8F: return 0x9F; case 0xA1: return 0xA2;
    case 0xA3: return 0xBC; case 0xA5: return 0xB4;
    case 0xA8: return 0xB8; case 0xAA: return 0xBA;
    case 0xAF: return 0xBF; case 0xB2: return 0xB3;
    case 0xBD: return 0xBE; default: return byte;
  }
}

inline u16 next(const char*& cursor) {
  if(cursor == nullptr || *cursor == 0) return 0;
  return codepoint((u8) *cursor++);
}

} // namespace mk8

#endif
