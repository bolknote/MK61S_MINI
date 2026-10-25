#ifndef MK61_MK8_SPAN_HPP
#define MK61_MK8_SPAN_HPP

#include "mk8_codec.hpp"
#include <string.h>

// Bounded little-endian word kernels. A failed probe suppresses probes for
// eight scalar characters, so alternating alphabets do not pay per-byte
// classification. No load/store crosses either supplied span.
namespace mk8_span {
inline u32 load(const void* p) { u32 w; memcpy(&w, p, 4); return w; }
inline void store(void* p, u32 w) { memcpy(p, &w, 4); }
inline bool ascii(u32 w) {
  return !(w & 0x80808080U) && !((w + 0x01010101U) & 0x80808080U) &&
         !((w - 0x20202020U) & 0x80808080U);
}
inline bool russian(u32 w) { return (w & 0xC0C0C0C0U) == 0xC0C0C0C0U; }
inline u32 pack(u32 a, u32 b) {
  return (a & 0xFFU) | ((a >> 8) & 0xFF00U) |
         ((b << 16) & 0xFF0000U) | ((b << 8) & 0xFF000000U);
}
inline void interleave(void* out, u32 even, u32 odd) {
  store(out, (even & 0xFFFFU) | (odd << 16));
  store((u8*)out + 4, (even >> 16) | (odd & 0xFFFF0000U));
}
inline bool pairs(u32 w, u32& units) {
  if((w & 0x00FE00FEU) != 0x00D000D0U ||
     (w & 0xC000C000U) != 0x80008000U) return false;
  const u32 d = ((w & 0x00010001U) << 6) | ((w >> 8) & 0x003F003FU);
  const u32 diff = d - 0x00100010U;
  if(diff & 0xFFC0FFC0U) return false;
  units = diff + 0x00C000C0U;
  return true;
}

// Consume complete characters fitting output. An unfinished input character
// is left for the next span when !final; invalid/unsupported input is rejected.
inline bool from_utf8(const u8* input, usize length, u8* output, usize capacity,
                      bool final, usize& consumed, usize& written) {
  consumed = written = 0;
  if((!input && length) || (!output && capacity)) return false;
  u8 cooldown = 0;
  while(consumed < length && written < capacity) {
    if(!cooldown && length - consumed >= 4 && capacity - written >= 4) {
      const u32 w = load(input + consumed);
      if(ascii(w)) { store(output + written, w); consumed += 4; written += 4; continue; }
      u32 a, b;
      if(length - consumed >= 8 && pairs(w, a) && pairs(load(input + consumed + 4), b)) {
        store(output + written, pack(a, b)); consumed += 8; written += 4; continue;
      }
      cooldown = 8;
    }
    const u8 lead = input[consumed];
    // All M8 codepoints are BMP: no four-byte UTF8 sequence can be accepted.
    if(lead >= 0xF0) return false;
    const u8 expected = lead < 0x80 ? 1 : lead >= 0xC2 && lead <= 0xDF ? 2 :
        lead >= 0xE0 ? 3 : 1;
    if(!final && expected > length - consumed) break;
    const auto decoded = utf8_codec::decode(input + consumed, length - consumed);
    u8 byte;
    if(!decoded.valid || !mk8::from_codepoint(decoded.codepoint, byte) || !mk8::valid_byte(byte)) return false;
    output[written++] = byte; consumed += decoded.size;
    if(cooldown) --cooldown;
  }
  return true;
}

inline bool to_utf8(const u8* input, usize length, u8* output, usize capacity,
                    usize& consumed, usize& written) {
  consumed = written = 0;
  if((!input && length) || (!output && capacity)) return false;
  u8 cooldown = 0;
  while(consumed < length) {
    if(!cooldown && length - consumed >= 4 && capacity - written >= 4) {
      const u32 w = load(input + consumed);
      if(ascii(w)) { store(output + written, w); consumed += 4; written += 4; continue; }
      if(russian(w) && capacity - written >= 8) {
        const u32 sum = (w & 0x3F3F3F3FU) + 0x10101010U;
        const u32 lead = 0xD0D0D0D0U + ((sum >> 6) & 0x01010101U);
        const u32 tail = (sum & 0x3F3F3F3FU) | 0x80808080U;
        interleave(output + written, (lead & 0x00FF00FFU) | ((tail & 0x00FF00FFU) << 8),
                   ((lead >> 8) & 0x00FF00FFU) | (((tail >> 8) & 0x00FF00FFU) << 8));
        consumed += 4; written += 8; continue;
      }
      cooldown = 8;
    }
    if(!mk8::valid_byte(input[consumed])) return false;
    const auto bytes = mk8::utf8(input[consumed]);
    if(bytes.size > capacity - written) break;
    memcpy(output + written, bytes.data, bytes.size);
    written += bytes.size; ++consumed;
    if(cooldown) --cooldown;
  }
  return true;
}
inline bool ascii_units(u32 w) {
  return !(w & 0xFF80FF80U) && !((w + 0x00010001U) & 0xFF80FF80U) &&
         !((w - 0x00200020U) & 0xFF80FF80U);
}
inline bool russian_units(u32 w) { return !((w - 0x04100410U) & 0xFFC0FFC0U); }
// Names are short: after the first heterogeneous block, finish the suffix
// scalarly rather than retrying classification at every remaining position.
__attribute__((always_inline)) inline bool to_utf16(const u8* input, usize length, u16* output, usize capacity, usize& written) {
  written = 0;
  if((!input && length) || (!output && capacity) || length > capacity) return false;
  while(length - written >= 4) {
    const u32 w = load(input + written);
    u32 add;
    if(ascii(w)) add = 0;
    else if(russian(w)) add = 0x03500350U;
    else break;
    interleave(output + written, (w & 0x00FF00FFU) + add,
               ((w >> 8) & 0x00FF00FFU) + add);
    written += 4;
  }
  for(; written < length; ++written) {
    if(!mk8::valid_byte(input[written])) return false;
    output[written] = mk8::codepoint(input[written]);
  }
  return true;
}
__attribute__((always_inline)) inline bool from_utf16(const u16* input, usize length, u8* output, usize capacity, usize& written) {
  written = 0;
  if((!input && length) || (!output && capacity) || length > capacity) return false;
  while(length - written >= 4) {
    u32 a = load(input + written), b = load(input + written + 2);
    if(ascii_units(a) && ascii_units(b)) {}
    else if(russian_units(a) && russian_units(b)) {
      a = a - 0x04100410U + 0x00C000C0U;
      b = b - 0x04100410U + 0x00C000C0U;
    } else break;
    store(output + written, pack(a, b)); written += 4;
  }
  for(; written < length; ++written) {
    u8 byte;
    if(!mk8::from_codepoint(input[written], byte) || !mk8::valid_byte(byte)) return false;
    output[written] = byte;
  }
  return true;
}
} // namespace mk8_span
#endif
