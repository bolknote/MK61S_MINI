#pragma once
#include <stdint.h>
using U=uint64_t;
struct D {static constexpr U Hidden=U(1)<<52,Fraction=Hidden-1,Sign=U(1)<<63,Magnitude=Sign-1,Infinity=U(0x7ff)<<52,Quiet=U(1)<<51;};
static inline U bits(double d){U v;__builtin_memcpy(&v,&d,8);return v;}
static inline double real(U v){double d;__builtin_memcpy(&d,&v,8);return d;}
struct Product {U high,low;};
static inline unsigned clz32(uint32_t x) {
  if(!x) return 32;
  unsigned n=0;
  if(!(x&0xFFFF0000U)) {n+=16;x<<=16;}
  if(!(x&0xFF000000U)) {n+=8;x<<=8;}
  if(!(x&0xF0000000U)) {n+=4;x<<=4;}
  if(!(x&0xC0000000U)) {n+=2;x<<=2;}
  return n+unsigned(!(x&0x80000000U));
}
static inline unsigned clz64(U x) {return uint32_t(x>>32)?clz32(uint32_t(x>>32)):32+clz32(uint32_t(x));}
__attribute__((always_inline)) inline U wide32(uint32_t a,uint32_t b) {
  const uint32_t al=a&0xFFFFU,ah=a>>16,bl=b&0xFFFFU,bh=b>>16;
  const uint32_t p=al*bl,t=ah*bl+(p>>16),v=al*bh+(t&0xFFFFU);
  return (U(ah*bh+(t>>16)+(v>>16))<<32)|(uint32_t(v<<16)|(p&0xFFFFU));
}
__attribute__((always_inline)) inline Product multiply(U a,U b) {
  const uint32_t al=uint32_t(a),ah=uint32_t(a>>32),bl=uint32_t(b),bh=uint32_t(b>>32);
  const U p=wide32(al,bl),t=wide32(ah,bl)+(p>>32),v=wide32(al,bh)+uint32_t(t);
  return {wide32(ah,bh)+(t>>32)+(v>>32),(v<<32)|uint32_t(p)};
}
__attribute__((always_inline)) inline U exp_high_product(U a,U b) {
  const uint32_t al=uint32_t(a),ah=uint32_t(a>>32),bl=uint32_t(b),bh=uint32_t(b>>32);
  return wide32(ah,bh)+(wide32(al,bh)>>32)+(wide32(ah,bl)>>32);
}
