// Project-owned ARMv6-M IEEE binary32/binary64 arithmetic.
// Integer algorithms: nearest-even, gradual underflow, signed zero and NaNs.
// No floating expressions, allocation, errno/fenv, division instructions,
// 64-bit multiply instructions, or dependency on compiler runtime archives.
#include "native_eabi_m0.hpp"
#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI
#include <float.h>
static_assert(sizeof(double)==8 && DBL_MANT_DIG==53 && sizeof(float)==4 && FLT_MANT_DIG==24,
              "M0 EABI requires IEEE binary64/binary32");
namespace m0_eabi {
using U = uint64_t;
template<class To, class From> inline To copy(From x) {
  static_assert(sizeof(To)==sizeof(From), "bit copy size");
  To y; __builtin_memcpy(&y,&x,sizeof(y)); return y;
}
unsigned clz32(uint32_t x) {
  if(!x) return 32;
  unsigned n=0;
  if(!(x&0xFFFF0000U)) {n+=16;x<<=16;}
  if(!(x&0xFF000000U)) {n+=8;x<<=8;}
  if(!(x&0xF0000000U)) {n+=4;x<<=4;}
  if(!(x&0xC0000000U)) {n+=2;x<<=2;}
  return n+unsigned(!(x&0x80000000U));
}
unsigned clz64(U x) {return uint32_t(x>>32)?clz32(uint32_t(x>>32)):32+clz32(uint32_t(x));}
// Four 16x16 products, each fitting in a 32-bit MULS result. In particular,
// do not express this as uint64_t(a)*b: that would call our own __aeabi_lmul.
__attribute__((always_inline)) inline U wide32(uint32_t a,uint32_t b) {
  const uint32_t al=a&0xFFFFU,ah=a>>16,bl=b&0xFFFFU,bh=b>>16;
  const uint32_t p=al*bl,t=ah*bl+(p>>16),v=al*bh+(t&0xFFFFU);
  return (U(ah*bh+(t>>16)+(v>>16))<<32)|(uint32_t(v<<16)|(p&0xFFFFU));
}
struct Product {U high,low;};
__attribute__((always_inline)) inline Product multiply(U a,U b) {
  const uint32_t al=uint32_t(a),ah=uint32_t(a>>32),bl=uint32_t(b),bh=uint32_t(b>>32);
  const U p=wide32(al,bl),t=wide32(ah,bl)+(p>>32),v=wide32(al,bh)+uint32_t(t);
  return {wide32(ah,bh)+(t>>32)+(v>>32),(v<<32)|uint32_t(p)};
}
U jam(U x,unsigned n) {
  if(!n) return x;
  if(n>=64) return x!=0;
  return (x>>n)|U((x<<(64-n))!=0);
}
U jam_product(Product p,unsigned n) {
  // Used for binary64 (49/50) and binary32 (20/21) product reductions.
  return (p.high<<(64-n))|(p.low>>n)|U((p.low<<(64-n))!=0);
}
// Exact rational seeds, evaluated at compile time. These are independently
// generated constants, not a table or code taken from another math library.
struct ReciprocalSeeds {
  uint16_t values[128]{};
  constexpr ReciprocalSeeds() {
    for(unsigned i=0;i<128;++i) values[i]=uint16_t((1U<<22)/(128+i));
  }
};
constexpr ReciprocalSeeds reciprocal_seeds;
inline U low_product(U a,U b) {
  return wide32(uint32_t(a),uint32_t(b))+
    (U(uint32_t(a)*uint32_t(b>>32)+uint32_t(a>>32)*uint32_t(b))<<32);
}
// Quotient estimate for 1 <= a/b < 2, followed by an exact remainder.
// Refining 16 -> 32 -> 63 reciprocal bits avoids a 56-step restoring loop.
// Once the estimate is within a few units, its signed residual fits in 64
// bits: only the low product is needed to correct the full 106-bit quotient.
U divide_significands(U a,U b,U& remainder) {
  if(b==(U(1)<<52)) {remainder=0;return a;}
  const uint32_t d16=uint32_t(b>>37);
  uint32_t r16=reciprocal_seeds.values[(d16>>8)-128];
  uint32_t product=d16*r16;
  bool negative=product>(1U<<30);
  uint32_t error=negative?product-(1U<<30):(1U<<30)-product;
  uint32_t correction=(r16*(error>>7))>>23;
  r16=negative?r16-correction:r16+correction;
  product=d16*r16;negative=product>(1U<<30);
  error=negative?product-(1U<<30):(1U<<30)-product;
  correction=((r16>>2)*(error>>2))>>26;
  r16=negative?r16-correction:r16+correction;

  uint32_t r32=r16<<16;
  const U p32=wide32(uint32_t(b>>21),r32),one=U(1)<<62;
  negative=p32>one;
  const U e32=negative?p32-one:one-p32;
  correction=uint32_t(wide32(r32>>15,uint32_t(e32>>17))>>30);
  r32=negative?r32-correction:r32+correction;

  const U signed_error=U(0)-low_product(b,r32);
  negative=(signed_error>>63)!=0;
  const U e64=negative?U(0)-signed_error:signed_error;
  const U c54=wide32(r32,uint32_t(e64>>24))>>37;
  U reciprocal=U(r32)<<22;
  reciprocal=(negative?reciprocal-c54:reciprocal+c54)<<10;

  const uint32_t al=uint32_t(a),ah=uint32_t(a>>32),rl=uint32_t(reciprocal),rh=uint32_t(reciprocal>>32);
  const U cross1=wide32(al,rh),cross=cross1+wide32(ah,rl);
  const U high=wide32(ah,rh)+(cross>>32)+(cross<cross1?(U(1)<<32):0);
  U q=(high<<1)|(uint32_t(cross)>>31);
  remainder=(a<<52)-low_product(q,b);
  while(remainder>>63) {--q;remainder+=b;}
  while(remainder>=b) {++q;remainder-=b;}
  return q;
}

template<unsigned F,unsigned E> struct Binary {
  static constexpr U Hidden=U(1)<<F,Sign=U(1)<<(F+E),Magnitude=Sign-1;
  static constexpr U Fraction=Hidden-1,Infinity=((U(1)<<E)-1)<<F,Quiet=Hidden>>1;
  static constexpr int Bias=(1<<(E-1))-1,Min=1-Bias,Max=Bias;
  static bool is_nan(U x) {return (x&Magnitude)>Infinity;}
  static U nan(U a,U b) {return (is_nan(a)?a:b)|Quiet;}
  static U normalize(U a,int& e) {
    const unsigned raw=unsigned((a>>F)&((1U<<E)-1));
    U s=a&Fraction;
    if(raw) {e=int(raw)-Bias;return s|Hidden;}
    const unsigned shift=clz64(s)-(63-F);
    e=Min-int(shift);return s<<shift;
  }
  // s has F fraction bits plus guard/round/sticky, and its leading bit at F+3.
  static U pack(U sign,int e,U s) {
    if(e<Min) {s=jam(s,unsigned(Min-e));e=Min;}
    U q=s>>3;const unsigned tail=unsigned(s&7);
    q+=tail>4 || (tail==4 && (q&1));
    if(q>=Hidden+Hidden) {q>>=1;++e;}
    if(e>Max) return sign|Infinity;
    if(q<Hidden) return sign|q;
    return sign|(U(e+Bias)<<F)|(q&Fraction);
  }
  static U add(U a,U b) {
    U ma=a&Magnitude,mb=b&Magnitude;
    if(ma>Infinity || mb>Infinity) return nan(a,b);
    if(ma==Infinity || mb==Infinity) {
      if(ma==Infinity && mb==Infinity && ((a^b)&Sign)) return Infinity|Quiet;
      return ma==Infinity?a:b;
    }
    if(!ma && !mb) return (a&b)&Sign;
    if(!ma) return b;
    if(!mb) return a;
    if(ma<mb) {const U t=a;a=b;b=t;}
    int ea,eb;U sa=normalize(a,ea)<<3,sb=normalize(b,eb)<<3;
    sb=jam(sb,unsigned(ea-eb));
    if(!((a^b)&Sign)) {
      sa+=sb;
      if(sa&(Hidden<<4)) {sa=jam(sa,1);++ea;}
    } else {
      sa-=sb;
      if(!sa) return 0;
      const unsigned shift=clz64(sa)-(63-F-3);sa<<=shift;ea-=int(shift);
    }
    return pack(a&Sign,ea,sa);
  }
  static U mul(U a,U b) {
    const U ma=a&Magnitude,mb=b&Magnitude,sign=(a^b)&Sign;
    if(ma>Infinity || mb>Infinity) return nan(a,b);
    if(ma==Infinity || mb==Infinity) return !ma || !mb?Infinity|Quiet:sign|Infinity;
    if(!ma || !mb) return sign;
    int ea,eb;const U sa=normalize(a,ea),sb=normalize(b,eb);
    const Product p=multiply(sa,sb);
    const bool high=F==52 ? (p.high&(U(1)<<41))!=0:(p.low&(U(1)<<47))!=0;
    return pack(sign,ea+eb+int(high),jam_product(p,F-3+unsigned(high)));
  }
  static U div(U a,U b) {
    const U ma=a&Magnitude,mb=b&Magnitude,sign=(a^b)&Sign;
    if(ma>Infinity || mb>Infinity) return nan(a,b);
    if((ma==Infinity && mb==Infinity) || (!ma && !mb)) return Infinity|Quiet;
    if(ma==Infinity || !mb) return sign|Infinity;
    if(!ma || mb==Infinity) return sign;
    int ea,eb;U remainder=normalize(a,ea);const U denominator=normalize(b,eb);
    int e=ea-eb;
    if(remainder<denominator) {remainder<<=1;--e;}
    if constexpr(F==52) {
      U residual;const U q=divide_significands(remainder,denominator,residual);
      const U twice=residual+residual;
      return pack(sign,e,(q<<3)|(twice>denominator?5:twice==denominator?4:residual?1:0));
    }
    // Exact restoring quotient, retaining three rounding bits and a sticky
    // remainder. All intermediate remainders fit in F+2 bits.
    U q=0;
    for(unsigned i=0;i<F+4;++i) {
      q<<=1;
      if(remainder>=denominator) {remainder-=denominator;q|=1;}
      if(i!=F+3) remainder<<=1;
    }
    return pack(sign,e,q|U(remainder!=0));
  }
  static int compare(U a,U b) {
    if(is_nan(a) || is_nan(b)) return 2;
    if(a==b || !((a|b)&Magnitude)) return 0;
    if((a^b)&Sign) return a&Sign?-1:1;
    return (a&Sign?a>b:a<b)?-1:1;
  }
  static U from_integer(U x,U sign=0) {
    if(!x) return 0;
    const unsigned top=63-clz64(x);
    return pack(sign,int(top),top>F+3?jam(x,top-F-3):x<<(F+3-top));
  }
  static U magnitude_integer(U a) {
    const U m=a&Magnitude;const int e=int(m>>F)-Bias;
    if(m>Infinity || e<0) return 0;
    if(e>=64) return UINT64_MAX;
    const U s=(a&Fraction)|Hidden;
    return e>=int(F)?s<<unsigned(e-F):s>>unsigned(F-e);
  }
  static int32_t signed32(U a) {
    const U m=magnitude_integer(a),limit=a&Sign?U(0x80000000):U(0x7FFFFFFF);
    const uint32_t q=uint32_t(m>limit?limit:m);
    return copy<int32_t>(a&Sign?uint32_t(0)-q:q);
  }
  static uint32_t unsigned32(U a) {
    if(a&Sign) return 0;
    const U m=magnitude_integer(a);return m>UINT32_MAX?UINT32_MAX:uint32_t(m);
  }
};
using D=Binary<52,11>;
using S=Binary<23,8>;
inline U bits(double x) {return copy<U>(x);}
inline U bits(float x) {return copy<uint32_t>(x);}
inline double real(U x) {return copy<double>(x);}
inline float single(U x) {return copy<float>(uint32_t(x));}
U integer_magnitude(int64_t x) {const U u=copy<U>(x);return x<0?U(0)-u:u;}
U extend(U a) {
  const U sign=(a&S::Sign)<<32,m=a&S::Magnitude;
  if(m>=S::Infinity) return sign|D::Infinity|((a&S::Fraction)<<29)|(m>S::Infinity?D::Quiet:0);
  if(!m) return sign;
  int e;const U sig=S::normalize(a,e);return D::pack(sign,e,sig<<32);
}
U narrow(U a) {
  const U sign=(a&D::Sign)>>32,m=a&D::Magnitude;
  if(m>=D::Infinity) return sign|S::Infinity|((a&D::Fraction)>>29)|(m>D::Infinity?S::Quiet:0);
  if(!m) return sign;
  int e;const U sig=D::normalize(a,e);return S::pack(sign,e,jam(sig,26));
}
#if !defined(__arm__) && !defined(__thumb__)
U sqrt_single(U a) {
  const U magnitude=a&S::Magnitude;
  if(!magnitude) return a;
  if(S::is_nan(a)) return a|S::Quiet;
  if(a&S::Sign) return S::Infinity|S::Quiet;
  if(magnitude==S::Infinity) return a;
  int e;U sig=S::normalize(a,e);const unsigned odd=unsigned(e)&1;
  const U radicand=sig<<(23+odd);
  // Restoring integer square root, two radicand bits per iteration.
  U root=0,remainder=0;
  for(unsigned i=24;i--;) {
    remainder=(remainder<<2)|((radicand>>(i*2))&3);
    const U trial=(root<<2)|1;root<<=1;
    if(remainder>=trial) {remainder-=trial;root|=1;}
  }
  root+=remainder>root; // An integer radicand cannot be exactly (root+1/2)^2.
  int out=(e-int(odd))/2;
  if(root>=S::Hidden+S::Hidden) {root>>=1;++out;}
  return (U(out+S::Bias)<<23)|(root&S::Fraction);
}
#endif
} // namespace m0_eabi
using namespace m0_eabi;
extern "C" {
#if defined(__arm__) || defined(__thumb__)
MK61_SOFT_PCS double mk61_m0_dadd_slow(double a,double b) {return real(D::add(bits(a),bits(b)));}
#else
MK61_SOFT_PCS double __aeabi_dadd(double a,double b) {return real(D::add(bits(a),bits(b)));}
MK61_SOFT_PCS double __aeabi_dsub(double a,double b) {return real(D::add(bits(a),bits(b)^D::Sign));}
#endif
MK61_SOFT_PCS double __aeabi_drsub(double a,double b) {return __aeabi_dsub(b,a);}
#if defined(__arm__) || defined(__thumb__)
MK61_SOFT_PCS double mk61_m0_dmul_slow(double a,double b) {return real(D::mul(bits(a),bits(b)));}
#else
MK61_SOFT_PCS double __aeabi_dmul(double a,double b) {return real(D::mul(bits(a),bits(b)));}
#endif
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
MK61_SOFT_PCS double mk61_m0_ddiv_slow(double a,double b) {return real(D::div(bits(a),bits(b)));}
#else
MK61_SOFT_PCS double __aeabi_ddiv(double a,double b) {return real(D::div(bits(a),bits(b)));}
#endif
MK61_SOFT_PCS float __aeabi_fadd(float a,float b) {return single(S::add(bits(a),bits(b)));}
MK61_SOFT_PCS float __aeabi_fsub(float a,float b) {return single(S::add(bits(a),bits(b)^S::Sign));}
MK61_SOFT_PCS float __aeabi_frsub(float a,float b) {return __aeabi_fsub(b,a);}
MK61_SOFT_PCS float __aeabi_fmul(float a,float b) {return single(S::mul(bits(a),bits(b)));}
MK61_SOFT_PCS float __aeabi_fdiv(float a,float b) {return single(S::div(bits(a),bits(b)));}
#define COMPARES(letter,type,format) \
MK61_SOFT_PCS int __aeabi_##letter##cmpeq(type a,type b) {return format::compare(bits(a),bits(b))==0;} \
MK61_SOFT_PCS int __aeabi_##letter##cmplt(type a,type b) {return format::compare(bits(a),bits(b))==-1;} \
MK61_SOFT_PCS int __aeabi_##letter##cmple(type a,type b) {return format::compare(bits(a),bits(b))<=0;} \
MK61_SOFT_PCS int __aeabi_##letter##cmpge(type a,type b) {const int c=format::compare(bits(a),bits(b));return c==0 || c==1;} \
MK61_SOFT_PCS int __aeabi_##letter##cmpgt(type a,type b) {return format::compare(bits(a),bits(b))==1;} \
MK61_SOFT_PCS int __aeabi_##letter##cmpun(type a,type b) {return format::compare(bits(a),bits(b))==2;}
COMPARES(d,double,D)
COMPARES(f,float,S)
#undef COMPARES
MK61_SOFT_PCS double __aeabi_i2d(int32_t x) {return real(D::from_integer(x<0?U(0)-U(int64_t(x)):U(x),x<0?D::Sign:0));}
MK61_SOFT_PCS double __aeabi_ui2d(uint32_t x) {return real(D::from_integer(x));}
MK61_SOFT_PCS double __aeabi_l2d(int64_t x) {return real(D::from_integer(integer_magnitude(x),x<0?D::Sign:0));}
MK61_SOFT_PCS double __aeabi_ul2d(U x) {return real(D::from_integer(x));}
MK61_SOFT_PCS float __aeabi_i2f(int32_t x) {return single(S::from_integer(x<0?U(0)-U(int64_t(x)):U(x),x<0?S::Sign:0));}
MK61_SOFT_PCS float __aeabi_ui2f(uint32_t x) {return single(S::from_integer(x));}
MK61_SOFT_PCS int32_t __aeabi_d2iz(double x) {return D::signed32(bits(x));}
MK61_SOFT_PCS uint32_t __aeabi_d2uiz(double x) {return D::unsigned32(bits(x));}
MK61_SOFT_PCS int32_t __aeabi_f2iz(float x) {return S::signed32(bits(x));}
MK61_SOFT_PCS uint32_t __aeabi_f2uiz(float x) {return S::unsigned32(bits(x));}
MK61_SOFT_PCS int64_t __aeabi_d2lz(double x) {const U a=bits(x),m=D::magnitude_integer(a);return copy<int64_t>(a&D::Sign?U(0)-m:m);}
MK61_SOFT_PCS U __aeabi_d2ulz(double x) {const U a=bits(x);return a&D::Sign?0:D::magnitude_integer(a);}
MK61_SOFT_PCS float __aeabi_d2f(double x) {return single(narrow(bits(x)));}
MK61_SOFT_PCS double __aeabi_f2d(float x) {return real(extend(bits(x)));}
#if !defined(__arm__) && !defined(__thumb__)
MK61_SOFT_PCS float mk61_m0_sqrtf(float x) {return single(sqrt_single(bits(x)));}
#endif
MK61_SOFT_PCS U __aeabi_lmul(U a,U b) {
  return low_product(a,b);
}
int __clzsi2(uint32_t x) {return int(clz32(x));}
int __clzdi2(U x) {return int(clz64(x));}
void mk61_m0_divmod64(U n,U d,mk61_eabi_divmod* result) {
  if(!d) {*result={n?UINT64_MAX:0,0};return;}
  U q=0;
  if(n>=d) {
    unsigned shift=clz64(d)-clz64(n);U divisor=d<<shift;
    do {
      if(n>=divisor) {n-=divisor;q|=U(1)<<shift;}
      divisor>>=1;
    } while(shift--);
  }
  *result={q,n};
}
// The generic ARMv6-M fallback is useful outside RP2040 as well. PicoCalc
// keeps the Pico SDK's interrupt-safe SIO wrappers for integer division.
U mk61_m0_udiv32(uint32_t n,uint32_t d) {
  if(!d) return n?UINT32_MAX:0;
  uint32_t q=0;
  if(n>=d) {
    unsigned shift=clz32(d)-clz32(n);uint32_t divisor=d<<shift;
    do {if(n>=divisor) {n-=divisor;q|=1U<<shift;}divisor>>=1;} while(shift--);
  }
  return (U(n)<<32)|q;
}
U mk61_m0_sdiv32(int32_t n,int32_t d) {
  if(!d) return n<0?0x80000000U:n?0x7FFFFFFFU:0;
  const uint32_t un=uint32_t(n),ud=uint32_t(d);
  const U qr=mk61_m0_udiv32(n<0?0U-un:un,d<0?0U-ud:ud);
  uint32_t q=uint32_t(qr),r=uint32_t(qr>>32);
  if((n<0)!=(d<0)) q=0U-q;
  if(n<0) r=0U-r;
  return (U(r)<<32)|q;
}
void mk61_m0_sdivmod64(U n,U d,mk61_eabi_divmod* result) {
  const bool negative_n=(n>>63)!=0,negative_d=(d>>63)!=0;
  if(!d) {*result={negative_n?U(1)<<63:n?(U(1)<<63)-1:0,0};return;}
  mk61_m0_divmod64(negative_n?U(0)-n:n,negative_d?U(0)-d:d,result);
  if(negative_n!=negative_d) result->quotient=U(0)-result->quotient;
  if(negative_n) result->remainder=U(0)-result->remainder;
}
}
#endif
