#ifndef MK61_AI_EXACT_FP32_HPP
#define MK61_AI_EXACT_FP32_HPP
#include <cstdint>
#include <cstring>
// Preserve binary32 round-to-nearest-even for ordinary finite values using
// only 32-bit mantissa arithmetic. Unusual exponents, subnormals and nonfinite
// operands retain the existing EABI path. Multiplication and addition remain
// separate operations; there is no fusion or reordering of group reductions.
namespace mk61ai::exact_fp32 {
inline __attribute__((always_inline)) float product(float a,float b) {
  std::uint32_t x,y;std::memcpy(&x,&a,4);std::memcpy(&y,&b,4);
  const unsigned ea=(x>>23)&255,eb=(y>>23)&255;
  if(!ea || ea==255 || !eb || eb==255) return a*b;
  const std::uint32_t u=(x&0x7fffff)|0x800000,v=(y&0x7fffff)|0x800000;
  // Exact24x24 product from four32-bit MULS; no generic128-bit arithmetic.
  const std::uint32_t ul=u&65535,uh=u>>16,vl=v&65535,vh=v>>16;
  const std::uint32_t lo=ul*vl,t=uh*vl+(lo>>16),w=ul*vh+(t&65535);
  const std::uint32_t hi=uh*vh+(t>>16)+(w>>16),low=(w<<16)|(lo&65535);
  const unsigned shift=hi&0x8000?24:23;
  int exponent=int(ea)+int(eb)-127+int(shift==24);
  if(exponent<=0 || exponent>=255) return a*b;
  std::uint32_t mantissa=(hi<<(32-shift))|(low>>shift);
  const std::uint32_t remainder=low&((1U<<shift)-1),half=1U<<(shift-1);
  mantissa+=remainder>half || (remainder==half && (mantissa&1));
  if(mantissa==0x1000000) {mantissa>>=1;if(++exponent==255)return a*b;}
  const std::uint32_t encoded=((x^y)&0x80000000)|(unsigned(exponent)<<23)|(mantissa&0x7fffff);
  float result;std::memcpy(&result,&encoded,4);return result;
}
}
namespace mk61ai::exact_fp32 {
// Keep the product rounded before adding it. This normalizes the common
// one-bit cancellation inline; deeper cancellation still uses CLZ.
inline __attribute__((always_inline)) float attention_sum(float a,float b) {
  std::uint32_t x,y;std::memcpy(&x,&a,4);std::memcpy(&y,&b,4);
  unsigned ex=(x>>23)&255,ey=(y>>23)&255;
  if(ex-1U>=254 || ey-1U>=254) return a+b;
  if((x<<1)<(y<<1)) {
    const auto bits=x;x=y;y=bits;
    const auto exponent=ex;ex=ey;ey=exponent;
  }
  const unsigned gap=ex-ey;
  // Even at a power of two, the smaller operand is strictly below the
  // halfway point to the closer neighbour when the exponent gap is >=26.
  if(gap>=26) {
    float result;std::memcpy(&result,&x,4);return result;
  }
  constexpr std::uint32_t hidden=1U<<26,mask=hidden-8;
  std::uint32_t u=((x<<3)&mask)|hidden,v=((y<<3)&mask)|hidden;
  if(gap) v=(v>>gap)|((v<<(32-gap))!=0);
  if((x^y)&0x80000000U) {
    u-=v;
    if(!u)return 0.0f;
    if(u<hidden) {
      const unsigned shift=u>=hidden/2?1U:unsigned(__builtin_clz(u))-5U;
      u<<=shift;ex-=shift;
    }
  } else {
    u+=v;
    if(u>=2*hidden){u=(u>>1)|(u&1);++ex;}
  }
  if(ex-1U>=254)return a+b;
  // Three low bits are guard, round and sticky. Add the rounding carry
  // to the mantissa so a rollover carries directly into the exponent.
  const std::uint32_t encoded=((ex-1U)<<23)+((u+3U+((u>>3)&1U))>>3);
  if(encoded>=0x7f800000U)return a+b;
  const std::uint32_t bits=encoded|(x&0x80000000U);
  float result;std::memcpy(&result,&bits,4);return result;
}

#if defined(PICO_ON_DEVICE)
inline __attribute__((section(".ai_fp32_extension"),noinline)) float sum(float a,float b)
#else
inline __attribute__((always_inline)) float sum(float a,float b)
#endif
{
  std::uint32_t x,y;std::memcpy(&x,&a,4);std::memcpy(&y,&b,4);
  unsigned ea=(x>>23)&255,eb=(y>>23)&255;
  if(!ea || ea==255 || !eb || eb==255)return a+b;
  if((x&0x7fffffff)<(y&0x7fffffff)) {const auto t=x;x=y;y=t;ea=(x>>23)&255;eb=(y>>23)&255;}
  std::uint32_t sa=((x&0x7fffff)|0x800000)<<3,sb=((y&0x7fffff)|0x800000)<<3;
  const unsigned delta=ea-eb;
  if(delta>=32)sb=1;
  else if(delta)sb=(sb>>delta)|((sb&((1U<<delta)-1))!=0);
  int exponent=int(ea);
  if(!((x^y)&0x80000000)) {
    sa+=sb;if(sa&0x8000000){sa=(sa>>1)|(sa&1);++exponent;}
  }else{
    sa-=sb;if(!sa)return 0.0f;
    const unsigned shift=unsigned(__builtin_clz(sa))-5;
    sa<<=shift;exponent-=int(shift);
  }
  if(exponent<=0 || exponent>=255)return a+b;
  std::uint32_t mantissa=sa>>3;const auto remainder=sa&7;
  mantissa+=remainder>4 || (remainder==4 && (mantissa&1));
  if(mantissa==0x1000000){mantissa>>=1;if(++exponent==255)return a+b;}
  const std::uint32_t encoded=(x&0x80000000)|(unsigned(exponent)<<23)|(mantissa&0x7fffff);
  float result;std::memcpy(&result,&encoded,4);return result;
}
}

#endif
