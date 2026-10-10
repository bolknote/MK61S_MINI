#ifndef MK61_M8_CONVERSION_CANDIDATES_HPP
#define MK61_M8_CONVERSION_CANDIDATES_HPP
#include "mk8_codec.hpp"
#include "m8_conversion_reference.hpp"
#if defined(__ARM_FEATURE_SIMD32)
#include <arm_acle.h>
#endif

// Experimental bounded normal-memory kernels. A failed block check falls
// back to the same strict scalar conversion, preserving its partial prefix,
// capacity handling and rejection of malformed/unsupported Unicode.
namespace m8_conversion_candidates {
typedef u32 Word __attribute__((aligned(1),may_alias));
static_assert(alignof(Word)==1,"byte-aligned word access required");
inline u32 load(const void* p) {return *(const Word*)p;}
inline void store(void* p,u32 v) {*(Word*)p=v;}
inline bool ascii4(u32 w) {
  return !(w&0x80808080U) && !((w+0x01010101U)&0x80808080U) &&
         !((w-0x20202020U)&0x80808080U);
}
inline bool russian4(u32 w) {return (w&0xC0C0C0C0U)==0xC0C0C0C0U;}
inline u32 even_bytes(u32 w) {return w&0x00FF00FFU;}
inline u32 rotate8(u32 w) {return (w>>8)|(w<<24);}
template<bool DSP> inline u32 unpack_even(u32 w) {
#if defined(__ARM_FEATURE_SIMD32)
  if constexpr(DSP)return __uxtb16(w);
#endif
  return even_bytes(w);
}
template<bool DSP> inline u32 widen_even(u32 w,u32 add) {
#if defined(__ARM_FEATURE_SIMD32)
  if constexpr(DSP)return __uxtab16(add,w);
#endif
  return even_bytes(w)+add;
}
inline void interleave(void* output,u32 even,u32 odd) {
  store(output,(even&0xFFFFU)|(odd<<16));
  store((u8*)output+4,(even>>16)|(odd&0xFFFF0000U));
}
inline u32 pack_units(u32 a,u32 b) {
  return (a&0xFFU)|((a>>8)&0xFF00U)|((b<<16)&0xFF0000U)|((b<<8)&0xFF000000U);
}
inline bool ascii_units(u32 p) {
  return !(p&0xFF80FF80U) && !((p+0x00010001U)&0xFF80FF80U) &&
         !((p-0x00200020U)&0xFF80FF80U);
}
inline bool russian_units(u32 p) {return !((p-0x04100410U)&0xFFC0FFC0U);}

template<bool DSP> inline bool to_utf16(const u8* input,usize length,u16* output,
                                      usize capacity,usize& written) {
  written=0;
  if((!input&&length)||(!output&&capacity)||length>capacity)return false;
  while(length-written>=4) {
    const u32 w=load(input+written);u32 add;
    if(ascii4(w))add=0;
    else if(russian4(w))add=0x03500350U;
    else break;
    interleave(output+written,widen_even<DSP>(w,add),widen_even<DSP>(rotate8(w),add));
    written+=4;
  }
  // Continue through exceptions; resume block checks after each scalar byte.
  while(written<length) {
    if(!mk8::valid_byte(input[written]))return false;
    output[written]=mk8::codepoint(input[written]);++written;
    while(length-written>=4) {
      const u32 w=load(input+written);u32 add;
      if(ascii4(w))add=0;
      else if(russian4(w))add=0x03500350U;
      else break;
      interleave(output+written,widen_even<DSP>(w,add),widen_even<DSP>(rotate8(w),add));
      written+=4;
    }
  }
  return true;
}

template<bool DSP> inline bool from_utf16(const u16* input,usize length,u8* output,
                                        usize capacity,usize& written) {
  written=0;
  if((!input&&length)||(!output&&capacity)||length>capacity)return false;
  while(written<length) {
    if(length-written>=4) {
      u32 a=load(input+written),b=load(input+written+2);
      if(ascii_units(a)&&ascii_units(b)) {store(output+written,pack_units(a,b));written+=4;continue;}
      if(russian_units(a)&&russian_units(b)) {
        a=a-0x04100410U+0x00C000C0U;b=b-0x04100410U+0x00C000C0U;
        store(output+written,pack_units(a,b));written+=4;continue;
      }
    }
    u8 byte=0;
    if(!mk8::from_codepoint(input[written],byte)||!mk8::valid_byte(byte))return false;
    output[written++]=byte;
  }
  return true;
}

template<bool DSP> inline bool to_utf8(const u8* input,usize length,u8* output,
                                     usize capacity,usize& written) {
  written=0;
  if((!input&&length)||(!output&&capacity))return false;
  usize at=0;
  while(at<length) {
    if(length-at>=4) {
      const u32 w=load(input+at);
      if(ascii4(w)&&capacity-written>=4) {store(output+written,w);written+=4;at+=4;continue;}
      if(russian4(w)&&capacity-written>=8) {
        u32 leads,trails;
#if defined(__ARM_FEATURE_SIMD32)
        if constexpr(DSP) {
          const u32 sum=__uadd8(w,0x10101010U);
          leads=__sel(0xD1D1D1D1U,0xD0D0D0D0U);
          trails=(sum&0x3F3F3F3FU)|0x80808080U;
        } else
#endif
        {
          const u32 sum=(w&0x3F3F3F3FU)+0x10101010U;
          leads=0xD0D0D0D0U+((sum>>6)&0x01010101U);
          trails=(sum&0x3F3F3F3FU)|0x80808080U;
        }
        const u32 even=unpack_even<DSP>(leads)|(unpack_even<DSP>(trails)<<8);
        const u32 odd=unpack_even<DSP>(rotate8(leads))|(unpack_even<DSP>(rotate8(trails))<<8);
        interleave(output+written,even,odd);written+=8;at+=4;continue;
      }
    }
    if(!mk8::valid_byte(input[at]))return false;
    const auto e=mk8::utf8(input[at]);
    if(e.size>capacity-written)return false;
    for(u8 i=0;i<e.size;++i)output[written++]=e.data[i];
    ++at;
  }
  return true;
}

template<bool DSP> inline bool decode_russian_pairs(u32 w,u32& units) {
  if((w&0x00FE00FEU)!=0x00D000D0U || (w&0xC000C000U)!=0x80008000U)return false;
  const u32 leads=unpack_even<DSP>(w),trails=unpack_even<DSP>(w>>8);
  const u32 d=((leads&0x00010001U)<<6)|(trails&0x003F003FU);
  const u32 diff=d-0x00100010U;
  if(diff&0xFFC0FFC0U)return false;
  units=diff+0x00C000C0U;return true;
}
template<bool DSP> inline bool from_utf8(const u8* input,usize length,u8* output,
                                       usize capacity,usize& written) {
  written=0;
  if((!input&&length)||(!output&&capacity))return false;
  usize at=0;
  while(at<length) {
    if(length-at>=4&&capacity-written>=4) {
      const u32 w=load(input+at);
      if(ascii4(w)) {store(output+written,w);written+=4;at+=4;continue;}
      if(length-at>=8) {
        u32 a,b;
        if(decode_russian_pairs<DSP>(w,a)&&decode_russian_pairs<DSP>(load(input+at+4),b)) {
          store(output+written,pack_units(a,b));written+=4;at+=8;continue;
        }
      }
    }
    const auto d=utf8_codec::decode(input+at,length-at);u8 byte=0;
    if(!d.valid||!mk8::from_codepoint(d.codepoint,byte)||!mk8::valid_byte(byte)||written>=capacity)return false;
    output[written++]=byte;at+=d.size;
  }
  return true;
}
}
#endif
