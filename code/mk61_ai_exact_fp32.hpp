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
